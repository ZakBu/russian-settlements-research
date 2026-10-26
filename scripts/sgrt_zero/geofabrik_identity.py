"""Named Geofabrik places_a settlement polygons, not administrative areas.

Source fclass is cartographic, not a population order or proof of legal status.
No region is inferred from a nearest point or federal-district filename.
Unresolved valid settlement geometries stay in the primary inventory so a
fallback source cannot silently bypass them.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import shapely

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.match import normalize_name
from scripts.sgrt_zero.lower_profile_quality import part_inventory
from scripts.sgrt_zero.cartographic_identity import (
    ACCEPTED, assign_cartographic_identity, file_sha, geometry_from_row,
    point_polygon_offset_km,
)

SETTLEMENT_CLASSES = {'city', 'town', 'village', 'hamlet'}
RURAL_TYPES = {
    'село', 'деревня', 'посёлок', 'станица', 'аул', 'улус', 'хутор',
    'населённый пункт', 'населенный пункт', 'слобода', 'станция',
    'железнодорожный объект', 'разъезд', 'починок', 'заимка', 'местечко',
    'участок', 'аал', 'выселок', 'выселки', 'кордон', 'стойбище', 'арбан',
    'сумон', 'зимовье',
}
# Town can describe a large rural service settlement in OSM. It is not a
# literal assertion of Russia's legal urban status.
COMPATIBLE_TYPES = {
    'city': {'город'},
    'town': {'город', 'пгт'} | RURAL_TYPES,
    'village': RURAL_TYPES | {'пгт'},
    'hamlet': RURAL_TYPES,
}


def build_geofabrik_polygons(places, reference, *, allow_nominal_outside=False,
                             nominal_max_offset_km=10.):
    """Return (primary polygon inventory including holds, rejection ledger).

    Whole-reference name uniqueness is tested before removing missing points.
    The optional nominal bridge uses identity equality, never nearest ranking.
    """
    if not np.isfinite(nominal_max_offset_km) or nominal_max_offset_km < 0:
        raise ValueError('Nominal consistency limit must be finite and nonnegative')
    full, _ = part_inventory(reference)
    full = full[full.source_record_id.notna()].copy().reset_index(drop=True)
    if not full.source_record_id.is_unique:
        raise ValueError('Census identities must be unique')
    full['_name'] = full.name.map(normalize_name)
    name_index = full.groupby('_name', sort=False).indices
    coordinates = full.lat.notna() & full.lon.notna()
    coordinate_positions = np.flatnonzero(coordinates.to_numpy())
    points = shapely.points(full.loc[coordinates, 'lon'].to_numpy(), full.loc[coordinates, 'lat'].to_numpy())
    point_tree = shapely.STRtree(points)
    all_points = {int(position): point for position, point in zip(coordinate_positions, points)}
    records, rejected = [], []
    for raw in places.to_dict('records'):
        fclass = raw.get('fclass')
        feature_id = str(raw.get('osm_id'))
        if fclass not in SETTLEMENT_CLASSES:
            rejected.append({'source_feature_id': feature_id, 'reason': 'excluded_non_settlement_fclass', 'fclass': fclass})
            continue
        if not raw.get('geometry_valid', True):
            rejected.append({'source_feature_id': feature_id, 'reason': 'invalid_or_unparsed_source_geometry', 'fclass': fclass})
            continue
        try:
            geometry = geometry_from_row(raw)
        except (ValueError, TypeError, KeyError, shapely.errors.GEOSException):
            rejected.append({'source_feature_id': feature_id, 'reason': 'invalid_or_unparsed_source_geometry', 'fclass': fclass})
            continue
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {'Polygon', 'MultiPolygon'}:
            rejected.append({'source_feature_id': feature_id, 'reason': 'invalid_or_nonpolygon_source_geometry', 'fclass': fclass})
            continue
        name = normalize_name(raw.get('name'))
        wkb = raw.get('geometry_wkb')
        if not isinstance(wkb, (bytes, bytearray, memoryview)):
            wkb = shapely.to_wkb(geometry)
        wkb = bytes(wkb)
        record = {
            'source_dataset': 'geofabrik_places_a', 'source_feature_id': feature_id,
            'source_feature_index': raw.get('source_feature_index'), 'source_name': raw.get('name'),
            'source_fclass': fclass, 'source_shard': raw.get('source_shard'),
            'source_url': raw.get('source_url'), 'source_snapshot': raw.get('source_snapshot'),
            'source_http_etag': raw.get('source_http_etag'),
            'source_component_sha256_json': raw.get('source_component_sha256_json'),
            'source_record_id': None, 'name': None, 'region': None, 'settlement_type_2021': None,
            'geometry_wkb': wkb, 'geometry_json': None,
            'geometry_sha256': hashlib.sha256(wkb).hexdigest(),
            'src_geom': 'OSM_place_polygon_via_Geofabrik_places_a',
            'cartographic_currency': 'dated_osm_source_extract',
            'polygon_identity_status': 'held_named_census_identity_not_established',
            'mapping_basis': None, 'reference_point_in_polygon': None,
            'reference_point_polygon_offset_km': None,
            'nominal_outside_max_offset_km': nominal_max_offset_km if allow_nominal_outside else None,
            'name_aliases_json': json.dumps([name], ensure_ascii=False),
            'other_positive_census_places': 0,
            'other_positive_census_place_ids_json': '[]',
            'cartographic_not_legal_boundary': True,
            'source_date_is_not_observed_geometry_date': True,
        }
        reason = None
        candidate_positions = name_index.get(name, np.array([], dtype=int)) if name else np.array([], dtype=int)
        candidates = full.iloc[candidate_positions]
        candidates = candidates[candidates.settlement_type_2021.isin(COMPATIBLE_TYPES[fclass])]
        inside_positions = coordinate_positions[point_tree.query(geometry, predicate='covers')]
        inside = full.iloc[inside_positions]
        named_inside = candidates[candidates.index.isin(inside.index)]
        owner = None
        basis = 'literal_name_fclass_and_census_point_containment'
        if not name:
            reason = 'source_locality_name_unknown'
        elif len(named_inside) == 1:
            owner = named_inside.iloc[0]
        elif len(named_inside) > 1:
            reason = 'multiple_named_census_points_in_source_polygon'
        elif allow_nominal_outside and len(candidates) == 1:
            candidate = candidates.iloc[0]
            if candidate.name not in all_points:
                reason = 'nominal_reference_point_unavailable'
            else:
                offset = point_polygon_offset_km(all_points[candidate.name], geometry)
                if offset <= nominal_max_offset_km:
                    owner = candidate
                    basis = 'unique_literal_name_and_fclass_reference_point_outside'
                else:
                    reason = 'nominal_identity_reference_point_too_far_from_polygon'
                    record['reference_point_polygon_offset_km'] = offset
        elif not len(candidates):
            reason = 'no_exact_name_and_compatible_type_in_whole_reference'
        elif not allow_nominal_outside:
            reason = 'no_unique_named_census_point_contained'
        else:
            reason = 'nominal_same_name_not_unique_in_whole_reference'
        if owner is not None:
            point = all_points[owner.name]
            ordinary = inside.population_role.eq('ordinary_settlement_record') if 'population_role' in inside else pd.Series(True, index=inside.index)
            positive = inside.population_2021.gt(0) if 'population_2021' in inside else pd.Series(True, index=inside.index)
            other = inside[ordinary & positive & inside.part_status.eq('unmarked_whole_place_record')
                           & inside.source_record_id.ne(owner.source_record_id)]
            record.update(source_record_id=owner.source_record_id, name=owner['name'], region=owner.region,
                          settlement_type_2021=owner.settlement_type_2021,
                          polygon_identity_status=ACCEPTED, mapping_basis=basis,
                          reference_point_in_polygon=bool(geometry.covers(point)),
                          reference_point_polygon_offset_km=0. if geometry.covers(point) else point_polygon_offset_km(point, geometry),
                          other_positive_census_places=len(other),
                          other_positive_census_place_ids_json=json.dumps(other.source_record_id.tolist()))
        else:
            record['polygon_identity_status'] = 'held_' + reason
            rejected.append({'source_feature_id': feature_id, 'reason': reason,
                             'fclass': fclass, 'source_name': raw.get('name')})
        records.append(record)
    return pd.DataFrame(records), pd.DataFrame(rejected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['places', 'reference', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--allow-nominal-outside', action='store_true')
    parser.add_argument('--nominal-max-offset-km', type=float, default=10.)
    parser.add_argument('--sites', type=Path)
    parser.add_argument('--lat-col', default='site_lat')
    parser.add_argument('--lon-col', default='site_lon')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    inventory, rejected = build_geofabrik_polygons(pd.read_parquet(args.places), pd.read_parquet(args.reference),
        allow_nominal_outside=args.allow_nominal_outside, nominal_max_offset_km=args.nominal_max_offset_km)
    inventory.to_parquet(args.output / 'locality_polygons.parquet', index=False, compression='zstd')
    rejected.to_parquet(args.output / 'polygon_rejections.parquet', index=False, compression='zstd')
    summary = {'primary_source_dataset': 'geofabrik_places_a',
               'valid_named_or_held_settlement_polygon_inventory': len(inventory),
               'mapped_polygons': int(inventory.polygon_identity_status.eq(ACCEPTED).sum()),
               'rejection_reasons': rejected.reason.value_counts().to_dict(),
               'allow_nominal_outside': args.allow_nominal_outside,
               'nominal_max_offset_km': args.nominal_max_offset_km if args.allow_nominal_outside else None,
               'input_sha256': {str(p): file_sha(p) for p in [args.places, args.reference]},
               'builder_code_sha256': file_sha(__file__),
               'assignment_code_sha256': file_sha(Path(__file__).with_name('cartographic_identity.py')),
               'cartographic_not_legal_boundary': True, 'observed_trips': False}
    if args.sites:
        sites = pd.read_parquet(args.sites)
        if 'eligible' in sites and 'education_group' in sites:
            sites = sites[sites.eligible & sites.education_group.eq('school')].copy()
        result = assign_cartographic_identity(sites, inventory, lat_col=args.lat_col, lon_col=args.lon_col)
        result.to_parquet(args.output / 'site_cartographic_identity.parquet', index=False, compression='zstd')
        summary['site_identity_status_counts'] = result.cartographic_identity_status.value_counts().to_dict()
        summary['accepted_sites'] = int(result.cartographic_identity_accepted.sum())
        summary['accepted_census_np'] = int(result.cartographic_accepted_source_record_id.nunique())
    (args.output / 'manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
