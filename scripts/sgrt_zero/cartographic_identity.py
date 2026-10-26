"""Dated cartographic locality containment, separate from literal/legal identity.

No nearest settlement, municipal polygon, polygon repair or raw owner replacement
is used. Only current WOF locality polygons with a unique named census point and
nonconflicting regional hierarchy can support a proposed institutional owner.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.match import normalize_name, normalize_region, normalize_district
from scripts.sgrt_zero.lower_profile_quality import part_inventory

ACCEPTED = 'named_census_point_in_dated_locality_polygon'
TYPE_CLASSES = {
    'city': {'город'}, 'town': {'город', 'пгт'},
    'village': {'село', 'деревня', 'станица', 'аул', 'улус', 'посёлок'},
    'hamlet': {'село', 'деревня', 'хутор', 'посёлок', 'населённый пункт'},
}


def parse(value, default):
    if isinstance(value, (dict, list)):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def present(value):
    return value is not None and not pd.isna(value) and bool(str(value).strip())


def aliases(properties, *, region=False):
    values = [properties.get('wof:name', '')]
    for key, value in properties.items():
        if key.startswith('name:'):
            values.extend(value if isinstance(value, list) else [value])
    normalizer = normalize_region if region else normalize_name
    return {normalizer(v) for v in values if isinstance(v, str) and v.strip()}


def point_polygon_offset_km(point, geometry):
    from shapely.ops import nearest_points
    boundary_point = nearest_points(point, geometry)[1]
    lat1, lat2 = np.radians([point.y, boundary_point.y])
    delta_lat = lat2 - lat1
    delta_lon = np.radians(boundary_point.x - point.x)
    value = np.sin(delta_lat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    return float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(value, 0, 1))))


def geometry_from_row(row):
    wkb = row.get('geometry_wkb')
    if isinstance(wkb, (bytes, bytearray, memoryview)):
        return shapely.from_wkb(bytes(wkb))
    return shape(parse(row.get('geometry_json'), {}))


def physical_positive_whole_reference(reference):
    """Physical possible neighbours, independently of accounting credit/origin."""
    ref, _ = part_inventory(reference)
    ordinary = ref.get('population_role', pd.Series('ordinary_settlement_record', index=ref.index)).eq('ordinary_settlement_record')
    positive = ref.get('population_2021', pd.Series(float('nan'), index=ref.index)).gt(0)
    ref = ref[ordinary & positive & ref.part_status.eq('unmarked_whole_place_record')
              & ref.source_record_id.notna() & ref.lat.notna() & ref.lon.notna()].copy()
    if not ref.source_record_id.is_unique:
        raise ValueError('Physical census identities must be unique')
    return ref.reset_index(drop=True)


def recompute_other_positive_places(inventory, reference):
    """Refresh only physical-neighbour guards in an already mapped inventory.

    Original owner decisions/geometries/provenance are retained. Uncredited or
    non-analysis ordinary NPs remain physical neighbours; absent coordinates are
    never reconstructed. Exact raw census IDs are retained in the guard lists.
    """
    out = inventory.copy()
    physical = physical_positive_whole_reference(reference)
    if not len(out):
        return out
    tree = shapely.STRtree(shapely.points(physical.lon.to_numpy(), physical.lat.to_numpy()))
    geometries = np.empty(len(out), dtype=object)
    wkb_mask = np.array([isinstance(value, (bytes, bytearray, memoryview))
                         for value in out.get('geometry_wkb', pd.Series(None, index=out.index))])
    if wkb_mask.any():
        geometries[wkb_mask] = shapely.from_wkb(out.loc[wkb_mask, 'geometry_wkb'].to_numpy())
    if (~wkb_mask).any():
        geometries[~wkb_mask] = shapely.from_geojson(out.loc[~wkb_mask, 'geometry_json'].to_numpy())
    pairs = tree.query(geometries, predicate='covers')
    owners = out.source_record_id.to_numpy()
    ids = physical.source_record_id.to_numpy()
    keep = ids[pairs[1]] != owners[pairs[0]]
    rows = pd.DataFrame({'polygon_position': pairs[0][keep], 'source_record_id': ids[pairs[1][keep]]})
    groups = rows.groupby('polygon_position').source_record_id.agg(list).to_dict()
    lists = [groups.get(position, []) for position in range(len(out))]
    out['other_positive_census_places'] = [len(values) for values in lists]
    out['other_positive_census_place_ids_json'] = [json.dumps(values) for values in lists]
    out['physical_neighbour_guard_uses_budget_credit'] = False
    out['physical_neighbour_guard_uses_analysis_origin'] = False
    return out


def build_locality_polygons(places, parents, reference, source_manifest=None, *, include_unknown_current=False,
                            allow_nominal_outside=False, nominal_max_offset_km=10.):
    """Return mapped polygons and a rejection ledger; do not change reference."""
    if not np.isfinite(nominal_max_offset_km) or nominal_max_offset_km < 0:
        raise ValueError('Nominal coordinate consistency limit must be finite and nonnegative')
    required = ['source_record_id', 'name', 'region', 'lat', 'lon']
    full_ref, _ = part_inventory(reference)
    full_ref = full_ref[full_ref.source_record_id.notna()].copy()
    full_ref['_name'] = full_ref.name.map(normalize_name)
    full_ref['_region'] = full_ref.region.map(normalize_region)
    ref = full_ref.dropna(subset=['lat', 'lon']).copy()
    if not ref.source_record_id.is_unique:
        raise ValueError('Census identities must be unique')
    if 'analysis_origin' in ref:
        ref = ref[ref.analysis_origin.fillna(False)]
    ref = ref.reset_index(drop=True)
    ref['_name'] = ref.name.map(normalize_name)
    ref['_region'] = ref.region.map(normalize_region)
    tree = shapely.STRtree(shapely.points(ref.lon.to_numpy(), ref.lat.to_numpy()))
    physical_ref = physical_positive_whole_reference(reference)
    physical_tree = shapely.STRtree(shapely.points(physical_ref.lon.to_numpy(), physical_ref.lat.to_numpy()))
    region_aliases, county_aliases = {}, {}
    for row in parents.itertuples():
        properties = parse(row.all_properties_json, {})
        region_aliases[row.wof_id] = aliases(properties, region=True)
        county_aliases[row.wof_id] = {
            normalize_district(value) for key, values in properties.items()
            if key.startswith('name:rus') for value in (values if isinstance(values, list) else [values])
            if isinstance(value, str) and value.strip()}
    rows, rejected = [], []
    source_manifest = source_manifest or {}
    for row in places.itertuples():
        reason = None
        if row.placetype != 'locality':
            continue
        if row.geometry_type not in {'Polygon', 'MultiPolygon'}:
            continue
        if row.is_current != 1 and not (include_unknown_current and row.is_current == -1):
            rejected.append({'wof_id': row.wof_id, 'reason': 'currency_not_explicit_current'})
            continue
        properties = parse(row.all_properties_json, {})
        ceased = properties.get('edtf:cessation', properties.get('edtf:deprecated', 'uuuu'))
        if properties.get('wof:superseded_by') or (isinstance(ceased, str) and ceased not in {'', 'uuuu', '..', 'open'}):
            rejected.append({'wof_id': row.wof_id, 'reason': 'superseded_locality'})
            continue
        geometry = shape(parse(row.geometry_json, {}))
        if not geometry.is_valid or geometry.is_empty:
            rejected.append({'wof_id': row.wof_id, 'reason': 'invalid_or_empty_source_geometry'})
            continue
        names = aliases(properties)
        names.add(normalize_name(row.wof_name))
        names.discard('')
        if not names:
            rejected.append({'wof_id': row.wof_id, 'reason': 'source_locality_name_unknown'})
            continue
        hierarchy = parse(row.hierarchy_json, [])
        region_ids = {h['region_id'] for h in hierarchy if 'region_id' in h}
        contextual_regions = set().union(*(region_aliases.get(r, set()) for r in region_ids)) if region_ids else set()
        inside = ref.iloc[tree.query(geometry, predicate='covers')]
        named = inside[inside['_name'].isin(names)]
        basis = 'literal_name_region_and_census_point_containment'
        if not len(named) and allow_nominal_outside:
            # A direct literal bridge, never a closest-point choice. Repeated
            # names in the same regional context remain unresolved.
            named = full_ref[full_ref['_name'].isin(names) & full_ref['_region'].isin(contextual_regions)]
            source_type = properties.get('place') or properties.get('osm:place')
            if source_type in TYPE_CLASSES and 'settlement_type_2021' in named:
                named = named[named.settlement_type_2021.isin(TYPE_CLASSES[source_type])]
            basis = 'unique_literal_name_and_region_reference_point_outside'
        if len(named) != 1:
            rejected.append({'wof_id': row.wof_id, 'reason': 'named_contained_census_identity_not_unique',
                             'named_contained_records': len(named)})
            continue
        owner = named.iloc[0]
        if pd.isna(owner.lat) or pd.isna(owner.lon):
            rejected.append({'wof_id': row.wof_id, 'reason': 'nominal_reference_point_unavailable',
                             'candidate_source_record_id': owner.source_record_id})
            continue
        owner_point = shapely.Point(owner.lon, owner.lat)
        point_inside = geometry.covers(owner_point)
        point_offset = 0. if point_inside else point_polygon_offset_km(owner_point, geometry)
        if basis == 'unique_literal_name_and_region_reference_point_outside':
            counties = {h['county_id'] for h in hierarchy if 'county_id' in h}
            county_names = set().union(*(county_aliases.get(c, set()) for c in counties)) if counties else set()
            district = normalize_district(owner.get('district'))
            if county_names and district and district not in county_names:
                reason = 'district_hierarchy_conflict_for_nominal_outside'
            if point_offset > nominal_max_offset_km:
                reason = 'nominal_identity_reference_point_too_far_from_polygon'
        if not contextual_regions:
            reason = 'regional_hierarchy_unknown'
        elif owner['_region'] not in contextual_regions:
            reason = 'regional_hierarchy_conflict'
        source_type = properties.get('place') or properties.get('osm:place')
        census_type = owner.get('settlement_type_2021')
        if source_type in TYPE_CLASSES and census_type not in TYPE_CLASSES[source_type]:
            reason = 'literal_source_settlement_type_conflict'
        if reason:
            rejected.append({'wof_id': row.wof_id, 'reason': reason,
                             'candidate_source_record_id': owner.source_record_id,
                             'reference_point_polygon_offset_km': point_offset})
            continue
        physical_inside = physical_ref.iloc[physical_tree.query(geometry, predicate='covers')]
        other = physical_inside[physical_inside.source_record_id.ne(owner.source_record_id)]
        geometry_json = row.geometry_json
        rows.append({
            'wof_id': row.wof_id, 'wof_name': row.wof_name,
            'source_record_id': owner.source_record_id, 'name': owner['name'],
            'region': owner.region, 'settlement_type_2021': census_type,
            'polygon_identity_status': ACCEPTED,
            'mapping_basis': basis,
            'reference_point_in_polygon': bool(point_inside),
            'reference_point_polygon_offset_km': point_offset,
            'nominal_outside_max_offset_km': nominal_max_offset_km if allow_nominal_outside else None,
            'name_aliases_json': json.dumps(sorted(names), ensure_ascii=False),
            'geometry_json': geometry_json,
            'geometry_sha256': hashlib.sha256(geometry_json.encode()).hexdigest(),
            'src_geom': properties.get('src:geom'),
            'area_km2': properties.get('geom:area_square_m', 0) / 1e6,
            'other_positive_census_places': len(other),
            'other_positive_census_place_ids_json': json.dumps(other.source_record_id.tolist()),
            'source_repository_commit': source_manifest.get('github_commit'),
            'source_dataset': 'whosonfirst_locality',
            'source_feature_id': str(row.wof_id),
            'source_snapshot': 'github:' + str(source_manifest.get('github_commit')),
            'source_url': source_manifest.get('url'),
            'source_accessed_utc': source_manifest.get('accessed_utc'),
            'source_archive_sha256': source_manifest.get('sha256'),
            'source_archive_url': source_manifest.get('url'),
            'cartographic_not_legal_boundary': True,
            'wof_is_current': row.is_current,
            'cartographic_currency': 'dated_cartographic_current_flag' if row.is_current == 1 else 'dated_cartographic_unknown_currency',
            'source_date_is_not_observed_geometry_date': True,
        })
    mapped = pd.DataFrame(rows)
    if len(mapped):
        held = set()
        for _, group in mapped.groupby('source_record_id'):
            if len(group) == 1:
                continue
            contained = group[group.reference_point_in_polygon]
            # Adding a weaker nominal candidate must never erase an existing
            # unique name+region+containment match. No closest geometry is used.
            losers = group.drop(contained.index) if len(contained) == 1 else group
            for idx, row in losers.iterrows():
                reason = ('nominal_polygon_competes_with_contained_polygon' if len(contained) == 1
                          else 'multiple_current_polygons_for_same_census_identity')
                rejected.append({'wof_id': row.wof_id, 'reason': reason,
                                 'candidate_source_record_id': row.source_record_id})
                held.add(idx)
        mapped = mapped.drop(index=list(held)).reset_index(drop=True)
    return mapped, pd.DataFrame(rejected)


def typed_address_locality_claims(row):
    tags = parse(row.get('tags_json'), {})
    claims = []
    # Typed localities in actual addresses can contradict a mapped point.
    # Whole comma-separated components only: a house number, street name or
    # institution/branch name never becomes a locality witness here.
    full_addresses = [row.get(k) for k in ['source_addr_full', 'source_address_full', 'activity_address']]
    full_addresses.extend(tags.get(k) for k in ['addr:full', 'addr:full_address'])
    for address in full_addresses:
        if not present(address):
            continue
        for component in re.split(r'[,;\n]', str(address)):
            match = re.fullmatch(r'\s*(?:город\s+|г\.\s*|село\s+|с\.\s*|деревня\s+|д\.\s*|'
                                 r'пос[её]лок\s+|пос\.\s*|п\.\s*|пгт\s+|рп\s+|'
                                 r'хутор\s+|станица\s+|аул\s+)([\wА-Яа-яЁё -]+)\s*', component, flags=re.I)
            if not match or not re.search(r'[А-Яа-яЁёA-Za-z]', match[1]):
                continue
            if re.fullmatch(r'[\d/-]+[А-Яа-яA-Za-z]?', match[1].strip()):
                continue
            if re.search(r'\b(?:улица|ул|шоссе|переулок|проспект|дом|корпус)\b', match[1], flags=re.I):
                continue
            claims.append({'name': normalize_name(match[1].strip()),
                           'rural_or_town': not bool(re.match(r'^\s*(?:город\s+|г\.)', component, flags=re.I))})
    return claims


def literal_localities(row):
    tags = parse(row.get('tags_json'), {})
    values = [row.get('source_address_locality')]
    values.extend(tags.get(key) for key in ['addr:city', 'addr:village', 'addr:hamlet', 'addr:place', 'is_in:city'])
    values.extend(c['name'] for c in typed_address_locality_claims(row))
    return {normalize_name(v) for v in values if present(v)}


CARTOGRAPHIC_RESOLUTION_METADATA = [
    ('cartographic_raw_geometry_sha256', 'raw_geometry_sha256'),
    ('cartographic_geometry_identity_resolution', 'geometry_identity_resolution'),
    ('cartographic_nested_mask_census_ids_json', 'nested_mask_census_ids_json'),
    ('cartographic_coordinate_hold_census_ids_json', 'coordinate_hold_census_ids_json'),
    ('cartographic_original_other_positive_census_places', 'original_other_positive_census_places'),
]


def assign_cartographic_identity(sites, polygons, *, lat_col='site_lat', lon_col='site_lon',
                                 owner_col='source_record_id'):
    """Add provenance/proposed IDs; original columns and source owners survive.

    A polygon containing other positive census NPs cannot establish finer NP
    identity, even when a broad postal city agrees. Such cases remain held.
    """
    out = sites.copy()
    if not out.index.is_unique:
        raise ValueError('Institution row index must be unique')
    fields = ['cartographic_candidate_source_record_id', 'cartographic_accepted_source_record_id', 'verified_boundary_source_record_id',
              'cartographic_source_wof_id', 'cartographic_src_geom',
              'cartographic_source_repository_commit', 'cartographic_source_accessed_utc',
              'cartographic_source_archive_sha256', 'cartographic_geometry_sha256', 'cartographic_currency',
              'cartographic_mapping_basis', 'cartographic_reference_point_polygon_offset_km',
              'cartographic_source_dataset', 'cartographic_source_feature_id',
              'cartographic_source_snapshot', 'cartographic_source_url',
              'cartographic_source_component_sha256_json',
              *[target for target, _ in CARTOGRAPHIC_RESOLUTION_METADATA]]
    for column in fields:
        out[column] = pd.Series([None] * len(out), index=out.index, dtype=object)
    out['cartographic_identity_status'] = 'no_supported_locality_polygon'
    out['cartographic_identity_accepted'] = False
    out['cartographic_contains_other_census_places'] = False
    out['cartographic_polygon_matches'] = 0
    out['cartographic_geometry_candidate_present'] = False
    out['cartographic_not_legal_boundary'] = True
    out['cartographic_identity_is_observed_assignment'] = False
    if not len(polygons) or not len(out):
        return out
    usable = polygons.reset_index(drop=True)
    geometries = np.array([geometry_from_row(row) for _, row in usable.iterrows()], dtype=object)
    tree = shapely.STRtree(geometries)
    lat = pd.to_numeric(out[lat_col], errors='coerce')
    lon = pd.to_numeric(out[lon_col], errors='coerce')
    valid = lat.between(-90, 90) & lon.between(-180, 180)
    out.loc[~valid, 'cartographic_identity_status'] = 'invalid_source_coordinates'
    positions = np.flatnonzero(valid.to_numpy())
    points = shapely.points(lon.iloc[positions].to_numpy(), lat.iloc[positions].to_numpy())
    pairs = tree.query(points, predicate='intersects')
    by_origin = {}
    for origin_position, polygon_position in zip(*pairs):
        by_origin.setdefault(int(positions[origin_position]), []).append(int(polygon_position))
    for position, matched in by_origin.items():
        idx = out.index[position]
        row = out.iloc[position]
        candidates = usable.iloc[matched]
        out.at[idx, 'cartographic_polygon_matches'] = len(candidates)
        out.at[idx, 'cartographic_geometry_candidate_present'] = True
        if not candidates.polygon_identity_status.eq(ACCEPTED).all():
            out.at[idx, 'cartographic_identity_status'] = 'held_unresolved_primary_geometry'
            continue
        if candidates.source_record_id.nunique() != 1:
            out.at[idx, 'cartographic_identity_status'] = 'held_overlapping_different_census_localities'
            continue
        polygon = candidates.iloc[0]
        owner = polygon.source_record_id
        out.at[idx, 'cartographic_candidate_source_record_id'] = owner
        for target, source in [
            ('cartographic_source_wof_id', 'wof_id'), ('cartographic_src_geom', 'src_geom'),
            ('cartographic_source_repository_commit', 'source_repository_commit'),
            ('cartographic_source_accessed_utc', 'source_accessed_utc'),
            ('cartographic_source_archive_sha256', 'source_archive_sha256'),
            ('cartographic_geometry_sha256', 'geometry_sha256'),
            ('cartographic_currency', 'cartographic_currency'),
            ('cartographic_mapping_basis', 'mapping_basis'),
            ('cartographic_reference_point_polygon_offset_km', 'reference_point_polygon_offset_km'),
            ('cartographic_source_dataset', 'source_dataset'),
            ('cartographic_source_feature_id', 'source_feature_id'),
            ('cartographic_source_snapshot', 'source_snapshot'),
            ('cartographic_source_url', 'source_url'),
            ('cartographic_source_component_sha256_json', 'source_component_sha256_json'),
            *CARTOGRAPHIC_RESOLUTION_METADATA,
        ]:
            out.at[idx, target] = polygon.get(source)
        names = set(parse(polygon.name_aliases_json, [])) | {normalize_name(polygon['name'])}
        claims = literal_localities(row)
        tags = parse(row.get('tags_json'), {})
        region_values = [row.get('source_address_state'), tags.get('addr:state')]
        regions = {normalize_region(v) for v in region_values if present(v)}
        other_places = int(polygon.other_positive_census_places) > 0
        out.at[idx, 'cartographic_contains_other_census_places'] = other_places
        existing = row.get(owner_col)
        point = shapely.Point(float(lon.iloc[position]), float(lat.iloc[position]))
        if not geometries[matched[0]].contains(point):
            status = 'held_point_on_cartographic_boundary'
        elif present(existing) and existing != owner:
            status = 'held_existing_source_owner_conflict'
        elif claims - names:
            status = 'held_literal_locality_conflict'
        elif regions and regions != {normalize_region(polygon.region)}:
            status = 'held_literal_region_conflict'
        elif other_places:
            status = 'held_finer_census_places_inside_cartographic_polygon'
        else:
            status = 'cartographic_containment_with_literal_corroboration' if claims else 'cartographic_containment_no_literal_locality'
            out.at[idx, 'verified_boundary_source_record_id'] = owner
            out.at[idx, 'cartographic_accepted_source_record_id'] = owner
            out.at[idx, 'cartographic_identity_accepted'] = True
        out.at[idx, 'cartographic_identity_status'] = status
    return out


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['places', 'parents', 'reference', 'source_manifest', 'output']:
        parser.add_argument('--' + key.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--sites', type=Path)
    parser.add_argument('--include-unknown-current', action='store_true')
    parser.add_argument('--allow-nominal-outside', action='store_true')
    parser.add_argument('--nominal-max-offset-km', type=float, default=10.)
    parser.add_argument('--lat-col', default='site_lat')
    parser.add_argument('--lon-col', default='site_lon')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.source_manifest.read_text())
    places = pd.read_parquet(args.places, filters=[('placetype', '=', 'locality'), ('geometry_type', 'in', ['Polygon', 'MultiPolygon'])])
    # Raw country inventory contains many points. They never become buffers.
    places = places[places.placetype.eq('locality') & places.geometry_type.isin(['Polygon', 'MultiPolygon'])]
    mapped, rejected = build_locality_polygons(places, pd.read_parquet(args.parents, columns=['wof_id', 'all_properties_json']),
                                              pd.read_parquet(args.reference), manifest,
                                              include_unknown_current=args.include_unknown_current,
                                              allow_nominal_outside=args.allow_nominal_outside,
                                              nominal_max_offset_km=args.nominal_max_offset_km)
    mapped.to_parquet(args.output / 'locality_polygons.parquet', index=False, compression='zstd')
    rejected.to_parquet(args.output / 'polygon_rejections.parquet', index=False, compression='zstd')
    summary = {'mapped_locality_polygons': len(mapped), 'rejected_polygon_records': len(rejected),
               'rejection_reasons': rejected.reason.value_counts().to_dict() if len(rejected) else {},
               'cartographic_not_legal_boundary': True, 'actual_journeys_observed': False,
               'source_manifest': manifest,
               'include_unknown_current': args.include_unknown_current,
               'allow_nominal_outside': args.allow_nominal_outside,
               'nominal_outside_max_offset_km': args.nominal_max_offset_km if args.allow_nominal_outside else None,
               'assignment_code_sha256': file_sha(__file__),
               'input_sha256': {str(p): file_sha(p) for p in [args.places, args.parents, args.reference]}}
    if args.sites:
        sites = pd.read_parquet(args.sites)
        if 'eligible' in sites and 'education_group' in sites:
            sites = sites[sites.eligible & sites.education_group.eq('school')].copy()
        enriched = assign_cartographic_identity(sites, mapped, lat_col=args.lat_col, lon_col=args.lon_col)
        enriched.to_parquet(args.output / 'site_cartographic_identity.parquet', index=False, compression='zstd')
        summary['site_identity_status_counts'] = enriched.cartographic_identity_status.value_counts().to_dict()
        summary['accepted_site_records'] = int(enriched.cartographic_identity_accepted.sum())
        summary['accepted_distinct_census_localities'] = int(enriched.verified_boundary_source_record_id.nunique())
    (args.output / 'manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
