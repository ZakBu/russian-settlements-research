"""Frozen public Magnit physical-store locator, separate from the baseline.

The locator's physical address and explicit settlement name establish a
candidate identity. Coordinates can reject that identity, never choose among
homonyms. Publisher-active is not independently verified operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.match import normalize_name, normalize_region, normalize_district, norm
from scripts.sgrt_mass.routes import haversine_km
from scripts.sgrt_zero.commerce import locality_clue, locality_type_compatible, STREET_SPLIT
from scripts.sgrt_zero.explicit_locality_identity import DISTRICT, case_key

URL = 'https://magnit.ru/webgate/v1/stores-facade/search/detail'
# Literal labels from the frozen official locator UI. MC is "Моя цена";
# cosmetics have the distinct code DG and are deliberately not groceries.
FOOD_FORMATS = {'MM': 'Магнит', 'MM_MINI': 'Мини', 'GM': 'Семейный',
                'ME': 'Экстра', 'MC': 'Моя цена'}
EXCLUDED_FORMATS = {'DG': 'М.Косметик', 'MA': 'Аптека', 'DARKSTORE': 'Мигом',
                    'MO': 'Опт', 'ZARYAD': 'Заряд'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def fetch(query_path, output):
    query = json.loads(Path(query_path).read_text())
    if query['url'] != URL or query['method'] != 'POST':
        raise ValueError('Only the documented read-only public store search is supported')
    request = urllib.request.Request(URL, data=json.dumps(query['body']).encode(),
                                     headers=query['headers'], method='POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        Path(output).write_bytes(response.read())


def physical_locality(address, lat, lon, reference):
    """Unique literal/type/region/district identity; distance only rejects."""
    names = set(reference.name.map(normalize_name))
    witnesses = []
    for component in address.split(','):
        if re.search(STREET_SPLIT, norm(component)):
            break
        clue = locality_clue(component, names)
        if clue['name'] in names:
            witnesses.append(clue)
    districts = {case_key(normalize_district(x['name'])) for x in DISTRICT.finditer(address)}
    choices = None
    for witness in witnesses:
        mask = reference.name.map(normalize_name).eq(witness['name'])
        mask &= reference.settlement_type_2021.map(
            lambda t: locality_type_compatible(witness['type'], t))
        if districts:
            mask &= reference.district.map(lambda d: case_key(normalize_district(d))).isin(districts)
        found = set(reference.loc[mask, 'source_record_id'].astype(str))
        choices = found if choices is None else choices & found
    choices = choices or set()
    result = {'source_record_id': None, 'np_identity_basis': 'held_no_unique_literal_physical_address',
              'literal_candidate_count': len(choices), 'identity_is_nearest_only': False,
              'literal_coordinate_difference_km': None}
    if len(choices) != 1 or len(districts) > 1:
        return result
    identity = next(iter(choices))
    row = reference.set_index('source_record_id').loc[identity]
    if not all(np.isfinite(float(v)) for v in (lat, lon, row.lat, row.lon)):
        result['np_identity_basis'] = 'held_missing_coordinate_validation'
        return result
    distance = float(haversine_km(float(lat), float(lon), float(row.lat), float(row.lon)))
    result['literal_coordinate_difference_km'] = distance
    if distance > 5.:
        result['np_identity_basis'] = 'held_literal_coordinate_conflict'
        return result
    result.update(source_record_id=identity,
                  np_identity_basis='official_locator_physical_address_unique_literal_type_region_district')
    return result


def admitted_store(store):
    return (store.get('storeTypeV2') in FOOD_FORMATS
            and store.get('isActive') is True
            and store.get('status') == 'STATUS_ACTIVE'
            and 'DELIVERY_TYPE_OFFLINE' in store.get('deliveryTypeList', []))


def normalize(raw_path, reference_path, output, query_path=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(raw_path).read_text())
    records = payload['data']
    if len(records) != int(payload['totalCount']):
        raise ValueError('Store search is paginated/incomplete; fetch all pages first')
    keys = [(s['externalId']['owner'], s['externalId']['storeCode']) for s in records]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate official store identity')
    reference = pd.read_parquet(reference_path)
    regional_references = {region: group.copy() for region, group in reference.groupby(reference.region.map(normalize_region), sort=True)}
    if reference.source_record_id.duplicated().any():
        raise ValueError('Nonunique census identities')
    rows = []
    for store in records:
        address = store['address']
        # Keep the neighbouring-region offers for border effects. The region
        # comes from the publisher's address, never from nearest coordinates.
        source_region = address.split(',')[0].strip()
        regional_reference = regional_references.get(normalize_region(source_region), reference.iloc[:0])
        coordinates = store['coordinates']
        lat, lon = float(coordinates['latitude']), float(coordinates['longitude'])
        if not np.isfinite([lat, lon]).all() or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Invalid physical store coordinate')
        identity = physical_locality(address, lat, lon, regional_reference)
        code = str(store['externalId']['storeCode'])
        rows.append({'provider_id': 'magnit:' + code, 'family': 'grocery',
                     'source_id': 'MAGNIT_PUBLIC_PHYSICAL_STORE_LOCATOR_20261028',
                     'source_year': 2026, 'source_url': 'https://magnit.ru/shops/',
                     'activity_address': address, 'source_region_literal': source_region,
                     'is_saratov_address': normalize_region(source_region) == normalize_region('Саратовская область'),
                     'site_lat': lat, 'site_lon': lon,
                     'city_fias_id_publisher_literal': store.get('cityFiasId'),
                     'store_format': store['storeTypeV2'],
                     'store_format_label': FOOD_FORMATS.get(store['storeTypeV2'], EXCLUDED_FORMATS.get(store['storeTypeV2'], 'unknown')),
                     'publisher_is_active': store.get('isActive'), 'publisher_status': store.get('status'),
                     'offline_offer_advertised': 'DELIVERY_TYPE_OFFLINE' in store.get('deliveryTypeList', []),
                     'admitted_grocery_offer': admitted_store(store),
                     'operation_verified': False, 'capacity_verified': False,
                     'physical_address_not_legal_company_address': True,
                     'inventory_complete_for_all_retail': False,
                     **identity})
    frame = pd.DataFrame(rows).sort_values('provider_id').reset_index(drop=True)
    frame.to_parquet(output / 'physical_stores.parquet', index=False, compression='zstd')
    frame.to_csv(output / 'physical_stores.csv', index=False)
    compact = json.loads(frame.to_json(orient='records', force_ascii=False))
    save_json(output / 'physical_stores.json', compact)
    summary = {'schema': 'sgrt.saratov.official_magnit.v1', 'raw_sha256': sha(raw_path),
               'query_sha256': sha(query_path) if query_path else None,
               'source_page': 'https://magnit.ru/shops/', 'source_api': URL,
               'source_year': 2026, 'bbox_returned_records': len(records),
               'bbox_total_count': int(payload['totalCount']),
               'saratov_explicit_address_records': int(frame.is_saratov_address.sum()),
               'saratov_admitted_active_offline_grocery_records': int((frame.is_saratov_address & frame.admitted_grocery_offer).sum()),
               'admitted_active_offline_grocery_records': int(frame.admitted_grocery_offer.sum()),
               'unique_literal_np_identities': int(frame.source_record_id.nunique()),
               'stores_with_accepted_literal_np_identity': int(frame.source_record_id.notna().sum()),
               'stores_withheld_np_identity': int(frame.source_record_id.isna().sum()),
               'store_formats': frame.groupby('store_format').size().to_dict(),
               'identity_statuses': frame.groupby('np_identity_basis').size().to_dict(),
               'MC_is_Moya_Tsena_not_cosmetics_DG': True,
               'actual_operation_independently_verified': False,
               'all_retail_inventory_complete': False,
               'baseline_population_and_provider_catalog_unchanged': True}
    save_json(output / 'summary.json', summary)
    return summary


def route(curated_path, road_nodes, road_catalog, fields, output, workers=4):
    """Fresh physical snaps and exact nearest supplementary offers only."""
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    from scipy.sparse import load_npz
    from scripts.sgrt_mass.site_geometry import snap_points, ROAD_PREFIX, N_VERTICES
    from scripts.sgrt_saratov.regional_fields import (
        physical_contract, _initialize_current_provider_worker, _current_provider_origin)

    fields, output, road_nodes = Path(fields), Path(output), Path(road_nodes)
    output.mkdir(parents=True, exist_ok=True)
    if Path(curated_path).suffix == '.json':
        curated = pd.DataFrame(json.loads(Path(curated_path).read_text()))
    else:
        curated = pd.read_parquet(curated_path)
    providers = curated.loc[curated.admitted_grocery_offer.eq(True)].copy().reset_index(drop=True)
    catalogue = json.loads(Path(road_catalog).read_text())
    specs = {f['path']: f for f in catalogue['files'] if f['path'].startswith(ROAD_PREFIX)}
    parts = sorted(road_nodes.glob('part_*.parquet'))
    if len(parts) != 24 or len(specs) != 24:
        raise ValueError('All 24 published national road-coordinate parts are required')
    provenance = []
    for part in parts:
        spec = specs[ROAD_PREFIX + part.name]
        expected = catalogue['objects'][spec['blob']]['sha256']
        if part.stat().st_size != spec['bytes'] or sha(part) != expected:
            raise ValueError('Road coordinate source differs: ' + part.name)
        provenance.append({'path': ROAD_PREFIX + part.name, 'bytes': spec['bytes'], 'sha256': expected})
    roads = pd.read_parquet(road_nodes, columns=['node_index', 'osm_id', 'lat', 'lon', 'weak_component'])
    if len(roads) != N_VERTICES or not np.array_equal(roads.node_index.to_numpy(), np.arange(N_VERTICES)):
        raise ValueError('Road vertex axis differs from the published graph')
    snapped = snap_points(providers, roads, max_snap_km=2.)
    del roads
    snapped['catalog_id'] = 'magnit:sites:' + snapped.provider_id.astype(str)
    snapped['provider_name'] = 'Магнит: ' + snapped.store_format_label
    snapped['correctsource_record_id'] = snapped.source_record_id
    snapped['provider_destination_key'] = np.where(snapped.source_record_id.notna(),
        'np:' + snapped.source_record_id.fillna('').astype(str), 'site:' + snapped.catalog_id)
    snapped['service_code'] = 'daily_grocery'
    snapped['source_group'] = 'magnit_public_locator'
    snapped['input_kind'] = 'sites'
    snapped['source_year'] = '2026'
    snapped['historical_only'] = False
    snapped['historical_supply_needs_current_confirmation'] = False
    snapped['restriction_scope_unknown'] = True
    snapped['general_profile_match_required'] = False
    snapped['routable_provider'] = snapped.accepted_snap.eq(True)
    snapped['capacity_used_as_attraction_weight'] = False
    snapped.to_parquet(output / 'provider_catalog.parquet', index=False, compression='zstd')
    graph = load_npz(fields / 'reduced_graph.npz')
    axis = np.load(fields / 'road_node_axis.npy')
    mapping = np.full(N_VERTICES, -1, dtype='int32')
    mapping[axis] = np.arange(len(axis), dtype='int32')
    contract = physical_contract(output / 'provider_catalog.parquet', mapping)
    roster = pd.read_parquet(fields / 'regional_roster.parquet').set_index('source_record_id', drop=False)
    origins = sorted(roster.loc[roster.accepted_source_endpoint.eq(True)].source_record_id.astype(str))
    pairs = {(origin, 'grocery') for origin in origins}
    horizon = float(json.loads((fields / 'graph_summary.json').read_text())['horizon_minutes'])
    arguments = (graph, mapping, roster, contract, pairs, horizon)
    rows = []
    def consume(results):
        for i, records in enumerate(results, 1):
            rows.extend(records)
            if i % 128 == 0 or i == len(origins):
                print(json.dumps({'event': 'additional_magnit_physical_routes', 'completed': i,
                                  'total': len(origins)}), flush=True)
    if workers > 1 and 'fork' in multiprocessing.get_all_start_methods():
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('fork'),
                initializer=_initialize_current_provider_worker, initargs=arguments) as executor:
            consume(executor.map(_current_provider_origin, origins, chunksize=1))
    else:
        _initialize_current_provider_worker(*arguments)
        consume(map(_current_provider_origin, origins))
    candidates = pd.DataFrame(rows).sort_values(['origin_id', 'family', 'rank', 'destination_group_key'])
    candidates.to_parquet(output / 'physical_provider_candidates.parquet', index=False, compression='zstd')
    facts = {'schema': 'sgrt.saratov.official_magnit_routes.v1',
             'frozen_curated_source_sha256': sha(curated_path), 'road_coordinate_sources': provenance,
             'admitted_offline_food_stores': len(snapped),
             'accepted_physical_snaps_within2km': int(snapped.accepted_snap.sum()),
             'withheld_np_identity_still_retained': int(snapped.source_record_id.isna().sum()),
             'regional_routed_origins': len(origins), 'candidate_rows': len(candidates),
             'candidate_origins': int(candidates.origin_id.nunique()),
             'horizon_minutes': horizon, 'nearest_distinct_destination_top3_with_boundary_ties': True,
             'baseline_provider_and_population_catalog_unchanged': True,
             'observed_travel_or_operation_verified': False}
    save_json(output / 'route_summary.json', facts)
    return facts


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--raw', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query', type=Path)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--route-only', action='store_true')
    parser.add_argument('--curated', type=Path)
    parser.add_argument('--road-nodes', type=Path)
    parser.add_argument('--road-catalog', type=Path, default=REPO/'data/catalog.json')
    parser.add_argument('--fields', type=Path)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.route_only:
        if args.curated is None or args.road_nodes is None or args.fields is None:
            parser.error('--route-only requires --curated, --road-nodes and --fields')
        print(json.dumps(route(args.curated, args.road_nodes, args.road_catalog,
                               args.fields, args.output, args.workers), ensure_ascii=False))
        return
    if args.raw is None or args.reference is None:
        parser.error('Source normalization requires --raw and --reference')
    if args.fetch:
        if args.query is None:
            parser.error('--fetch requires the frozen --query descriptor')
        fetch(args.query, args.raw)
    print(json.dumps(normalize(args.raw, args.reference, args.output, args.query), ensure_ascii=False))


if __name__ == '__main__':
    main()
