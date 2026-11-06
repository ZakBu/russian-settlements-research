"""Map documented membership and direct internal roles, without invented areas.

Straight lines represent relationships, not routes or continuous boundaries.
Every full display geometry is checked against the pinned Russian outline.
Existing generalised school-zone polygons may be shown as model context only.
"""
from pathlib import Path
import json
import pandas as pd
from shapely.geometry import LineString, mapping
from scripts.sgrt_saratov.country_scope import load_russia


def run(structure, roster_path, boundary, output):
    structure, output = Path(structure), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    systems = pd.read_parquet(structure/'systems.parquet').set_index('system_id')
    members = pd.read_parquet(structure/'system_members.parquet')
    edges = pd.read_parquet(structure/'direct_function_destinations.parquet')
    roster = pd.read_parquet(roster_path).set_index('source_record_id')
    mask = load_russia(boundary)
    files = {'documented_school_relations': [], 'documented_medical_relations': [],
             'niva_internal_medical_links': []}
    held = []

    def feature(group, origin, target, properties):
        if origin == target:
            return
        if origin not in roster.index or target not in roster.index:
            held.append({**properties, 'reason': 'endpoint_not_in_regional_coordinate_axis'})
            return
        a, b = roster.loc[origin], roster.loc[target]
        coordinates = [a.lon, a.lat, b.lon, b.lat]
        if not all(pd.notna(v) for v in coordinates):
            held.append({**properties, 'reason': 'endpoint_coordinate_unknown'})
            return
        line = LineString([(a.lon, a.lat), (b.lon, b.lat)])
        if not mask.covers(line):
            held.append({**properties, 'reason': 'straight_display_relation_leaves_country'})
            return
        files[group].append({'type': 'Feature', 'geometry': mapping(line), 'properties': {
            **properties, 'origin_id': origin, 'target_id': target,
            'name': str(a['name'])+' → '+str(b['name']),
            'display_is_road_route': False, 'continuous_system_boundary_established': False}})

    documented = members[members.membership_basis.ne('model_basic_union')]
    for m in documented.itertuples(index=False):
        s = systems.loc[m.system_id]
        school = s.document_function == 'school'
        group = 'documented_school_relations' if school else 'documented_medical_relations'
        category = 0 if school or s.document_function == 'medical_physician' else 1
        properties = {'id': m.system_id+'__'+m.source_record_id,
            'class_index': category, 'system_id': m.system_id,
            'relation_basis': m.membership_basis, 'function': s.document_function,
            'evidence_year': 2025, 'population_2021': m.population_2021,
            'observed_trip_flow': False, 'source_ids_json': m.source_ids_json}
        feature(group, m.source_record_id, m.core_id, properties)
        if school and s.core_name == 'Нива':
            feature('niva_internal_medical_links', m.source_record_id, m.core_id,
                    {**properties, 'class_index': 0})
    niva = systems[(systems.core_name.eq('Нива')) & systems.document_function.eq('school')].index
    internal = edges[edges.system_id.isin(niva) & edges.family.eq('medical_basic') &
        edges.origin_population_2021.gt(0) & edges.destination_scope.eq('other_internal')]
    for e in internal.itertuples(index=False):
        feature('niva_internal_medical_links', e.origin_id, e.destination_np_id, {
            'id': e.system_id+'__medical_basic__'+e.origin_id+'__'+str(e.destination_np_id),
            'class_index': 1, 'system_id': e.system_id, 'function': e.family,
            'relation_basis': 'archived_v2_modeled_internal_primary_medical_direction',
            'model_minutes': e.cost_minutes, 'observed_trip_flow': False,
            'road_country_scope_revalidated': False})
    for name, features in files.items():
        (output/(name+'.geojson')).write_text(json.dumps(
            {'type': 'FeatureCollection', 'features': features}, ensure_ascii=False,
            separators=(',', ':'))+'\n')
    report = {'map_feature_counts': {k: len(v) for k, v in files.items()},
              'held_display_relations': held,
              'geographic_boundary': 'pinned_atlas_Russia_outline',
              'new_continuous_service_boundaries_inferred': False}
    (output/'map_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report
