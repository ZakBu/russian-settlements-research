"""Generalised node-membership cartograms; never transport service boundaries.

Geometric Voronoi cells only extend each sampled node's drawing over a map.
They do not infer travel costs, household behaviour or areas of real systems.
The numerical memberships stay unchanged. Coincident conflicting observations,
unresolved endpoints and exits remain separate neutral drawing cells.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPoint, Point, mapping
from shapely.ops import transform

from scripts.sgrt_saratov.country_scope import load_russia

PROJECTED = '+proj=laea +lat_0=51.5 +lon_0=45.5 +datum=WGS84 +units=m +no_defs'
URBAN = {'город', 'пгт', 'посёлок городского типа', 'рабочий посёлок'}
RURAL = {'село', 'посёлок', 'деревня', 'хутор', 'станция', 'железнодорожный объект',
         'железнодорожный разъезд', 'железнодорожная станция'}
BASIC = ('school', 'medical_basic', 'grocery')
DEFAULT_SCENARIOS = tuple(f'exponential__h{h}__full_radius' for h in (10, 20, 40))
ASSIGNED_STATES = {'resolved_regional_peak', 'sampled_peak_without_nonself_comparators'}
COLOUR_LABELS = {
    0: 'Ядро — городской НП по официальному типу',
    1: 'Сельское ядро: известны три базовые функции',
    2: 'Сельское ядро: известны две базовые функции',
    3: 'Сельское ядро: известна одна базовая функция',
    4: 'Сельское ядро: базовые функции пока не установлены',
}
STATUS_LABELS = {
    'external_halo_exit': 'направление сравнения выходит за пределы области',
    'external_neighbourhood_censored': 'не хватает сравнения с поселениями за границей области',
    'unknown_field': 'значение поля неизвестно',
    'comparison_incomplete': 'состав сравниваемых поселений неполон',
    'no_neighbours_at_scale': 'нет соседей для сравнения в этом масштабе',
    'plateau_ambiguous': 'равные значения поля не дают единственного назначения',
    'zero_cost_comparison_ambiguous': 'неразрешённое сравнение точек с нулевым временем',
    'coincident_or_multiple_basin_ambiguous': 'совпадающая география допускает разные назначения',
    'membership_row_unknown': 'отнесение опорной точки неизвестно',
    'comparison_cohort_excluded': 'вне общей выборки парного сравнения',
}


def _truth(value):
    return False if pd.isna(value) else bool(value is True or value == 1 or str(value).lower() == 'true')


def _polygonal(geometry):
    return shapely.union_all([g for g in shapely.get_parts(shapely.make_valid(geometry))
                             if g.geom_type in {'Polygon', 'MultiPolygon'}])


def province_mask(boundary):
    """Use the existing pinned outline; an NP is never moved to fit it."""
    country = load_russia(boundary)
    document = json.loads(Path(boundary).read_text())
    features = [f for f in document['features']
                if f['properties'].get('iso_3166_2') == 'RU-SAR']
    if len(features) != 1:
        raise ValueError('Expected one pinned Saratov administrative outline')
    region = shapely.from_geojson(json.dumps(features[0]['geometry']))
    return _polygonal(region.intersection(country)), country


def core_attributes(roster, links):
    """Colour is a documented/known attribute of a core, never its rank."""
    selected = links[links.evidence_scenario.eq('all_dated_known') & links.family.isin(BASIC)]
    if selected.duplicated(['origin_id', 'family']).any():
        raise ValueError('Repeated preferred local-function evidence')
    evidence = {(r.origin_id, r.family): _truth(r.known_local_supply)
                for r in selected.itertuples(index=False)}
    result = {}
    for r in roster.itertuples(index=False):
        present = [family for family in BASIC if evidence.get((r.source_record_id, family), False)]
        missing_rows = [family for family in BASIC if (r.source_record_id, family) not in evidence]
        if r.settlement_type_2021 in URBAN:
            colour = 0
        elif r.settlement_type_2021 in RURAL and not missing_rows:
            colour = 4 - len(present)  # 3 known -> 1, zero known -> 4, never absence.
        else:
            colour = None
        result[r.source_record_id] = {
            'class_index': colour, 'core_name': r.name,
            'core_settlement_type_2021': r.settlement_type_2021,
            'core_population_2021': None if pd.isna(r.population_2021) else float(r.population_2021),
            'known_basic_function_count': len(present),
            'known_basic_families_json': json.dumps(present),
            'basic_evidence_rows_missing_json': json.dumps(missing_rows),
            'zero_known_functions_is_absence': False,
            'colour_is_system_rank': False,
        }
    return result


def voronoi_base(roster, region):
    """One exact drawing site per coordinate; no ID wins a coincident tie."""
    if roster.source_record_id.duplicated().any():
        raise ValueError('Repeated regional source identity')
    held = []
    selected = []
    for r in roster.to_dict('records'):
        if not (pd.notna(r['lon']) and pd.notna(r['lat']) and np.isfinite(r['lon']) and np.isfinite(r['lat'])):
            held.append({'source_record_id': r['source_record_id'], 'name': r['name'],
                         'reason': 'coordinate_unknown'})
        elif not region.covers(Point(float(r['lon']), float(r['lat']))):
            held.append({'source_record_id': r['source_record_id'], 'name': r['name'],
                         'reason': 'outside_pinned_display_region'})
        else:
            selected.append(r)
    accepted = pd.DataFrame(selected)
    if len(accepted) < 4:
        raise ValueError('Too few display sites')
    sites = accepted.groupby(['lon', 'lat'], sort=True).source_record_id.apply(list).reset_index()
    project = Transformer.from_crs(4326, PROJECTED, always_xy=True).transform
    restore = Transformer.from_crs(PROJECTED, 4326, always_xy=True).transform
    mask = transform(project, region)
    points = [transform(project, Point(r.lon, r.lat)) for r in sites.itertuples(index=False)]
    cells = shapely.voronoi_polygons(MultiPoint(points), extend_to=mask.envelope,
                                    ordered=True)
    cells = [_polygonal(g.intersection(mask)) for g in cells.geoms]
    if len(cells) != len(sites) or any(g.is_empty for g in cells):
        raise ValueError('Voronoi display sites/cells differ')
    for p, cell in zip(points, cells):
        if not cell.covers(p):
            raise ValueError('Exact geometric cell lost its sampled point')
    return {'sites': sites, 'points': points, 'cells': cells, 'mask': mask,
            'region': region, 'restore': restore, 'held': held}


def site_membership(source_ids, scenario):
    """A coincident or multi-endpoint observation remains explicitly mixed."""
    selected = scenario[scenario.source_record_id.isin(source_ids)]
    if selected.source_record_id.nunique() != len(source_ids):
        return None, None, 'membership_row_unknown', selected
    allowed = selected.assignment_unique.map(_truth) & selected.status.isin(ASSIGNED_STATES)
    if not allowed.all() or selected.basin_id.isna().any() or selected.core_id.isna().any():
        statuses = sorted(set(selected.status.fillna('unknown').astype(str)))
        return None, None, '|'.join(statuses), selected
    pairs = selected[['basin_id', 'core_id']].drop_duplicates()
    if len(pairs) != 1:
        return None, None, 'coincident_or_multiple_basin_ambiguous', selected
    state = ('sampled_peak_without_nonself_comparators'
             if selected.status.eq('sampled_peak_without_nonself_comparators').any()
             else 'resolved_regional_peak')
    return str(pairs.iloc[0].basin_id), str(pairs.iloc[0].core_id), state, selected


def common_supported_cohort(primary, control, primary_scenario, control_scenario):
    """Use identical comparable NP for both drawings; never fill unknowns."""
    groups = []
    for frame, sid in [(primary, primary_scenario), (control, control_scenario)]:
        rows = frame[frame.scenario_id.eq(sid)]
        good = rows.assignment_unique.map(_truth) & rows.status.eq('resolved_regional_peak')
        groups.append(set(rows.loc[good, 'source_record_id']))
    return groups[0] & groups[1]


def generalize_coverage(geometries, point_groups, points, mask, tolerance_m=1500.):
    """Reduce shared lines, checking each sampled NP at every tolerance."""
    raw = np.asarray(geometries, dtype=object)
    attempts = []
    chosen = raw
    used = 0.
    for tolerance in [float(tolerance_m)/(2**i) for i in range(7)] + [0.]:
        candidate = raw if tolerance == 0 else shapely.coverage_simplify(raw, tolerance,
                                                                       simplify_boundary=False)
        candidate = np.asarray([_polygonal(g.intersection(mask)) for g in candidate], dtype=object)
        displaced = sum(not candidate[group].covers(point) for group, point in zip(point_groups, points))
        union = shapely.union_all(candidate)
        gap = mask.difference(union).area
        overlap = max(0., sum(g.area for g in candidate) - union.area)
        attempts.append({'tolerance_m': tolerance, 'displaced_sampled_sites': displaced,
                         'gap_m2': float(gap), 'overlap_m2': float(overlap)})
        if displaced == 0 and gap <= 1. and overlap <= 1. and all(not g.is_empty for g in candidate):
            chosen, used = candidate, tolerance
            break
    else:
        raise ValueError('Exact display coverage fails its invariants')
    return chosen, {'requested_generalization_m': float(tolerance_m),
                    'accepted_generalization_m': used, 'attempts': attempts,
                    'raw_vertices': int(shapely.count_coordinates(raw)),
                    'generalized_vertices': int(shapely.count_coordinates(chosen))}


def export_scenario(scenario, base, attributes, output, tolerance_m=1500.,
                    comparison_cohort=None):
    scenario_ids = scenario.scenario_id.unique()
    if len(scenario_ids) != 1:
        raise ValueError('One scenario required')
    sid = str(scenario_ids[0])
    groups, site_group = {}, []
    is_control = ('direct_nearest_same_peaks_control' in scenario and
                  scenario.direct_nearest_same_peaks_control.map(_truth).all())
    for i, r in enumerate(base['sites'].itertuples(index=False)):
        if comparison_cohort is not None and not set(r.source_record_id) <= comparison_cohort:
            basin, core, status = None, None, 'comparison_cohort_excluded'
            selected = scenario[scenario.source_record_id.isin(r.source_record_id)]
        else:
            basin, core, status, selected = site_membership(r.source_record_id, scenario)
        key = 'basin:'+basin if basin is not None else 'unresolved-site:'+str(i)
        support = (bool(selected.terminal_has_nonself_comparison_support.map(_truth).all())
                   if len(selected) and 'terminal_has_nonself_comparison_support' in selected
                   else None)
        if key not in groups:
            groups[key] = {'basin_id': basin, 'core_id': core, 'status': status,
                           'support': support, 'sites': [], 'source_ids': [], 'cells': []}
        elif support is False:
            groups[key]['support'] = False
        groups[key]['sites'].append(i)
        groups[key]['source_ids'].extend(r.source_record_id)
        groups[key]['cells'].append(base['cells'][i])
        site_group.append(key)
    keys = list(groups)
    index = {k: i for i, k in enumerate(keys)}
    geometries = [_polygonal(shapely.union_all(groups[k]['cells'])) for k in keys]
    shapes, diagnostic = generalize_coverage(geometries,
        [index[k] for k in site_group], base['points'], base['mask'], tolerance_m)
    features = []
    unsupported_points = []
    class_counts = {}
    for key, geometry in zip(keys, shapes):
        group = groups[key]
        props = {'id': sid+'__'+hashlib.sha256(key.encode()).hexdigest()[:20],
                 'scenario_id': sid, 'basin_id': group['basin_id'],
                 'field_kernel': str(scenario.iloc[0].get('kernel', 'unknown')),
                 'field_half_time_minutes': (float(scenario.iloc[0].half_time)
                     if 'half_time' in scenario else None),
                 'field_half_time_is_service_radius': False,
                 'core_id': group['core_id'], 'display_membership_status': group['status'],
                 'terminal_has_nonself_comparison_support': group['support'],
                 'direct_nearest_same_peaks_control': bool(is_control),
                 'comparison_cohort_drawing_mask_applied': comparison_cohort is not None,
                 'comparison_cohort_input_records': (len(comparison_cohort)
                     if comparison_cohort is not None else None),
                 'sampled_np_records': len(group['source_ids']),
                 'sampled_source_ids_json': json.dumps(sorted(group['source_ids'])),
                 'geometry_is_transport_isochrone': False,
                 'geometry_is_inferred_service_boundary': False,
                 'geometry_is_cartographic_nearest_node_extension': True,
                 'polygon_area_used_as_system_area': False}
        if group['core_id'] is not None and group['core_id'] in attributes:
            props.update(attributes[group['core_id']])
            prefix = ('Опорная точка без внешних сравнений: '
                      if group['support'] is False else 'Узловая концентрация: ')
            if is_control:
                prefix = 'Контроль ближайшего пика. '+prefix
            props['name'] = prefix+str(props['core_name'])
        else:
            meanings = [STATUS_LABELS.get(s, 'отнесение не установлено')
                        for s in group['status'].split('|')]
            props.update(class_index=None, name='Отнесение не показано: '+'; '.join(meanings))
        drawing = _polygonal(transform(base['restore'], geometry).intersection(base['region']))
        # As in the pinned country-scope exporter, overlay arithmetic can leave
        # zero-area shared-boundary residues despite explicit intersection.
        # This is a numerical geometry tolerance, not a geographic allowance.
        outside_area = float(drawing.difference(base['region']).area)
        if drawing.is_empty or outside_area > 1e-14:
            raise ValueError('Final drawing leaves the pinned region')
        for site_index in group['sites']:
            site = base['sites'].iloc[site_index]
            if not drawing.covers(Point(float(site.lon), float(site.lat))):
                raise ValueError('Final geographic drawing displaced a sampled NP')
        props['outside_display_outline_numeric_area_degrees2'] = outside_area
        class_counts[str(props['class_index'])] = class_counts.get(str(props['class_index']), 0) + 1
        features.append({'type': 'Feature', 'geometry': mapping(drawing), 'properties': props})
        if group['core_id'] is not None and group['support'] is False:
            # A separate point layer lets the publisher show unsupported sampled
            # terminals as points, rather than interpreting their drawing cell
            # as an empirically supported territorial maximum.
            matches = base['sites'][base['sites'].source_record_id.map(
                lambda ids: group['core_id'] in ids)]
            if len(matches) == 1:
                site = matches.iloc[0]
                unsupported_points.append({'type': 'Feature',
                    'geometry': mapping(Point(float(site.lon), float(site.lat))),
                    'properties': {**props, 'id': props['id']+'__sampled_point',
                        'geometry_is_cartographic_nearest_node_extension': False,
                        'geometry_is_sampled_terminal_point': True,
                        'polygon_area_used_as_system_area': False}})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/(sid+'.geojson')).write_text(json.dumps({'type': 'FeatureCollection',
        'features': features}, ensure_ascii=False, separators=(',', ':'))+'\n')
    support_directory = output/'support_points'
    support_directory.mkdir(exist_ok=True)
    (support_directory/(sid+'__unsupported_sampled_points.geojson')).write_text(json.dumps({
        'type': 'FeatureCollection', 'features': unsupported_points},
        ensure_ascii=False, separators=(',', ':'))+'\n')
    visible_ids = {i for ids in base['sites'].source_record_id for i in ids}
    return {'scenario_id': sid, 'features': len(features),
            'comparison_cohort_drawing_mask_applied': comparison_cohort is not None,
            'comparison_cohort_input_records': (len(comparison_cohort)
                if comparison_cohort is not None else None),
            'comparison_cohort_visible_sampled_records': (len(comparison_cohort & visible_ids)
                if comparison_cohort is not None else None),
            'comparison_cohort_held_geographic_records': (len(comparison_cohort - visible_ids)
                if comparison_cohort is not None else None),
            'assigned_display_basins': sum(g['basin_id'] is not None for g in groups.values()),
            'resolved_display_basins': sum(g['basin_id'] is not None and
                g['status'] == 'resolved_regional_peak' for g in groups.values()),
            'sampled_without_nonself_comparison_display_basins': sum(g['basin_id'] is not None and
                g['status'] == 'sampled_peak_without_nonself_comparators' for g in groups.values()),
            'unsupported_sampled_point_features': len(unsupported_points),
            'direct_nearest_same_peaks_control': bool(is_control),
            'neutral_individual_cells': sum(g['basin_id'] is None for g in groups.values()),
            'final_geographic_displaced_sampled_sites': 0,
            'semantic_colour_features': class_counts, **diagnostic}


def run(memberships, roster, functional_links, boundary, output,
        scenarios=DEFAULT_SCENARIOS, tolerance_m=1500., comparison_cohort=None):
    frame = pd.read_parquet(memberships)
    roster_frame = pd.read_parquet(roster)
    links = pd.read_parquet(functional_links)
    region, country = province_mask(boundary)
    base = voronoi_base(roster_frame, region)
    attributes = core_attributes(roster_frame, links)
    available = set(frame.scenario_id.unique())
    if not set(scenarios) <= available:
        raise ValueError('Requested cartographic scenarios unavailable: '+str(set(scenarios)-available))
    summaries = [export_scenario(frame[frame.scenario_id.eq(s)], base, attributes,
                                output, tolerance_m, comparison_cohort) for s in scenarios]
    report = {'schema': 'sgrt.regional_node_cartograms.v1', 'scenarios': summaries,
              'sampled_np_coordinates': sum(len(v) for v in base['sites'].source_record_id),
              'unique_display_sites': len(base['sites']), 'held_display_records': base['held'],
              'semantic_colour_labels': COLOUR_LABELS,
              'claim': 'Cartographic nearest-node extension of discrete scenario memberships; no transport or observed territorial boundaries inferred.',
              'areas_are_not_empirical_system_areas': True,
              'numeric_memberships_modified': False}
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output)/'cartographic_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--memberships', required=True, type=Path)
    p.add_argument('--roster', required=True, type=Path)
    p.add_argument('--functional-links', required=True, type=Path)
    p.add_argument('--boundary', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--scenario', action='append')
    p.add_argument('--tolerance-m', type=float, default=1500.)
    a = p.parse_args()
    print(json.dumps(run(a.memberships, a.roster, a.functional_links, a.boundary,
        a.output, a.scenario or DEFAULT_SCENARIOS, a.tolerance_m), ensure_ascii=False, indent=2))
