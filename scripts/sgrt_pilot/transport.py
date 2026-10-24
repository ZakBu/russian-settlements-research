#!/usr/bin/env python3
"""Recover a dated directed road-cost pilot; missing routes never become zero.

The historical compact matrix is reused as transport evidence, not as accepted
SGRT membership. Exact census keys are joined before selecting pilot origins.
Dependencies: numpy, pandas, pyarrow; scipy only for the route subcommand.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

LEGACY = 'research/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2'
GRAPH_SHA256 = 'a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366'
SNAPSHOT = '2021-01-01T21:42:03Z'
PILOTS = ['удмуртская', 'ленинградская', 'вологодская', 'челябинская']


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_catalogued(path, relative, catalog):
    row = next(r for r in catalog['files'] if r['path'] == relative)
    obj = catalog['objects'][row['blob']]
    if Path(path).stat().st_size != row['bytes'] or sha256(path) != obj['sha256']:
        raise ValueError('Transport source differs from published bytes: ' + relative)


def haversine_km(lat1, lon1, lat2, lon2):
    a, b, c, d = map(np.radians, (lat1, lon1, lat2, lon2))
    v = np.sin((c - a) / 2) ** 2 + np.cos(a) * np.cos(c) * np.sin((d - b) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(v, 0, 1)))


def make_crosswalk(wide, legacy_nodes):
    """Identity comes from exact root AND exact 2021 source ID, never proximity."""
    cols = ['root', 'source_record_id_2021', 'settlement_name_2021', 'region_norm_2021',
            'accepted_latitude_2021', 'accepted_longitude_2021',
            'accepted_point_present_2021', 'working_credit_present_2021']
    w = pd.read_parquet(wide, columns=cols)
    old = pd.read_parquet(legacy_nodes, columns=['id', 'root', 'source_record_id_2021',
                                               'name', 'region', 'lat', 'lon'])
    assert old.id.is_unique and w.root.is_unique
    keep = w.source_record_id_2021.notna()
    matched = old.loc[old.root.notna() & old.source_record_id_2021.notna()].merge(w.loc[keep], on=['root', 'source_record_id_2021'], how='inner',
                        validate='one_to_one', suffixes=('_legacy', ''))
    matched['settlement_id'] = matched.source_record_id_2021
    matched['identity_basis'] = 'exact_root_and_source_record_id_2021'
    matched['coordinate_difference_km'] = haversine_km(
        matched.lat, matched.lon, matched.accepted_latitude_2021, matched.accepted_longitude_2021)
    matched['external_context_anchor'] = False
    matched['transport_point_matches_2021'] = matched.coordinate_difference_km.le(0.000001)
    anchors = old.loc[old.id.isin(['ctx:RU-FED-MOW', 'ctx:RU-FED-SPB'])].copy()
    anchors['settlement_id'] = anchors.id
    anchors['identity_basis'] = 'explicit_nonadditive_federal_city_context_anchor'
    anchors['coordinate_difference_km'] = np.nan
    anchors['external_context_anchor'] = True
    anchors['transport_point_matches_2021'] = True
    matched = pd.concat([matched, anchors], ignore_index=True, sort=False)
    assert matched.id.is_unique and matched.settlement_id.is_unique
    return matched, w


def extract(args):
    started = time.monotonic()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    cat = json.loads(args.catalog.read_text())
    base = args.inputs / LEGACY
    origin_path = args.origins or base / 'route_origin_index.parquet'
    verify_catalogued(origin_path, LEGACY + '/route_origin_index.parquet', cat)
    verify_catalogued((args.destinations or base / 'route_destination_index.parquet'), LEGACY + '/route_destination_index.parquet', cat)
    origins = pd.read_parquet(origin_path)
    dest = pd.read_parquet((args.destinations or base / 'route_destination_index.parquet'))
    assert np.array_equal(origins.origin_index, np.arange(len(origins)))
    assert np.array_equal(dest.destination_index, np.arange(len(dest)))
    cross, wide = make_crosswalk(args.wide, args.legacy_nodes)
    cross.to_parquet(out / 'transport_census_crosswalk.parquet', index=False, compression='zstd')
    regions = args.regions or PILOTS
    origins = origins.merge(cross[['id', 'settlement_id', 'identity_basis', 'coordinate_difference_km',
                                   'external_context_anchor', 'transport_point_matches_2021']], on='id', how='left', validate='one_to_one')
    dest = dest.merge(cross[['id', 'settlement_id', 'identity_basis', 'coordinate_difference_km',
                             'external_context_anchor', 'transport_point_matches_2021']], on='id', how='left', validate='one_to_one')
    valid_o = origins.settlement_id.notna() & origins.transport_point_matches_2021.eq(True)
    valid_d = dest.settlement_id.notna() & dest.transport_point_matches_2021.eq(True)
    oselect = valid_o & origins.region.isin(regions)
    # Context anchors are available as destinations, never added to census totals.
    oi = origins.loc[oselect].copy()
    oi.to_parquet(out / 'pilot_road_origins.parquet', index=False, compression='zstd')
    dest.to_parquet(out / 'all_road_destinations.parquet', index=False, compression='zstd')
    if args.only_index:
        print(json.dumps({'route_origins': len(oi), 'mapped_destinations': int(valid_d.sum()),
                          'matrix_parts_required': False}, indent=2))
        return
    omask = oselect.to_numpy()
    dmask = valid_d.to_numpy()
    oids = origins.settlement_id.to_numpy()
    dids = dest.settlement_id.to_numpy()
    oldoids = origins.id.to_numpy()
    olddids = dest.id.to_numpy()
    osnap = origins.snap_km.to_numpy(dtype=float)
    dsnap = dest.snap_km.to_numpy(dtype=float)
    budgets = dest.routing_budget_minutes.to_numpy(dtype='float32')
    rows = []
    observed_source_rows = 0
    files = sorted((base / 'candidate_travel_times_parts').glob('part_*.parquet'))
    expected_files = [r for r in cat['files'] if r['path'].startswith(LEGACY + '/candidate_travel_times_parts/')]
    if len(files) != len(expected_files):
        raise ValueError('Incomplete published matrix parts: got %s expected %s' % (len(files), len(expected_files)))
    for n, path in enumerate(files):
        verify_catalogued(path, LEGACY + '/candidate_travel_times_parts/' + path.name, cat)
        table = pq.read_table(path)
        observed_source_rows += len(table)
        o = table['origin_index'].to_numpy()
        d = table['destination_index'].to_numpy()
        mask = omask[o] & dmask[d]
        if not mask.any():
            continue
        o, d = o[mask], d[mask]
        net = table['network_minutes'].to_numpy()[mask].copy()
        connector = (4 * osnap[o] + 4 * dsnap[d]).astype('float32')
        costs = net + connector
        same = oldoids[o] == olddids[d]
        net[same] = connector[same] = costs[same] = 0
        rows.append(pd.DataFrame({
            'origin_id': oids[o], 'destination_id': dids[d],
            'cost_minutes': costs, 'network_minutes': net, 'connector_minutes': connector,
            'route_status': 'routed_static_car_2021', 'destination_budget_minutes': budgets[d],
            'origin_snap_km': osnap[o], 'destination_snap_km': dsnap[d],
            'transport_source_id': 'OSM_GEOFABRIK_20210101_ACCESS_V2',
        }))
        if n % 10 == 0:
            print('decoded', n + 1, '/', len(files), flush=True)
    costs = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    assert len(costs) and not costs.duplicated(['origin_id', 'destination_id']).any()
    assert costs.cost_minutes.notna().all() and costs.cost_minutes.ge(0).all()
    assert costs.loc[costs.origin_id.eq(costs.destination_id), 'cost_minutes'].eq(0).all()
    costs.to_parquet(out / 'pilot_costs.parquet', index=False, compression='zstd')
    w = wide.loc[wide.source_record_id_2021.notna() & wide.region_norm_2021.isin(regions)].copy()
    w['settlement_id'] = w.source_record_id_2021
    join = w[['settlement_id', 'region_norm_2021', 'accepted_point_present_2021']].merge(
        origins.loc[valid_o, ['settlement_id', 'origin_index', 'snap_km', 'coordinate_difference_km']],
        on='settlement_id', how='left', validate='one_to_one')
    join['route_origin_status'] = np.where(join.origin_index.notna(), 'accepted_legacy_road_origin',
                                         'no_accepted_legacy_road_origin')
    join.to_parquet(out / 'pilot_origin_coverage.parquet', index=False, compression='zstd')
    stats = []
    for region, group in join.groupby('region_norm_2021'):
        g = costs[costs.origin_id.isin(group.settlement_id)]
        stats.append({'region': region, 'census2021_records': len(group),
                      'accepted_route_origins': int(group.origin_index.notna().sum()),
                      'origins_without_accepted_road_snap': int(group.origin_index.isna().sum()),
                      'origins_snap_over_2km': int(group.snap_km.gt(2).sum()),
                      'accepted_coordinate_vs_route_coordinate_over_100m': int(group.coordinate_difference_km.gt(.1).sum()),
                      'available_directed_pairs': len(g), 'distinct_destinations': int(g.destination_id.nunique()),
                      'external_region_destinations_in_pair_table': int(g.destination_id.nunique() -
                          len(set(g.destination_id) & set(group.settlement_id)))})
    pd.DataFrame(stats).to_csv(out / 'coverage_by_region.csv', index=False)
    names = cross.set_index('settlement_id')[['name', 'region', 'lat', 'lon']]
    pairs = [('Ижевск', 'Глазов'), ('Ижевск', 'Воткинск'), ('Ижевск', 'Сарапул'),
             ('Челябинск', 'Долгодеревенское'), ('Вологда', 'Череповец'),
             ('Тосно', 'Санкт-Петербург'), ('Гатчина', 'Санкт-Петербург')]
    checks = []
    for a, b in pairs:
        aa = names[names.name.eq(a)]
        bb = names[names.name.eq(b)]
        for sid, ar in aa.iterrows():
            for tid, br in bb.iterrows():
                selected = costs[costs.origin_id.eq(sid) & costs.destination_id.eq(tid)]
                if len(selected):
                    r = selected.iloc[0]
                    checks.append({'origin_name': a, 'destination_name': b, 'origin_id': sid,
                                   'destination_id': tid, 'cost_minutes': float(r.cost_minutes),
                                   'network_minutes': float(r.network_minutes),
                                   'connector_minutes': float(r.connector_minutes),
                                   'geodesic_km': float(haversine_km(ar.lat, ar.lon, br.lat, br.lon))})
    pd.DataFrame(checks).to_csv(out / 'recognizable_pairs.csv', index=False)
    provenance = {
        'source_snapshot_utc': SNAPSHOT, 'scenario': 'static_directed_ordinary_car',
        'source_matrix_pairs_read': observed_source_rows, 'source_matrix_parts': len(files),
        'output_pairs': len(costs), 'regions': stats,
        'source_graph_sha256': GRAPH_SHA256,
        'input_sha256': {'census_wide': sha256(args.wide), 'legacy_nodes': sha256(args.legacy_nodes),
                         'origin_index': sha256(origin_path), 'destination_index': sha256((args.destinations or base / 'route_destination_index.parquet'))},
        'missing_pair_meaning': 'Not zero. Unaccepted endpoint, outside destination budget, or disconnected; the bounded matrix alone cannot distinguish these.',
        'connector': 'Straight off-network scenario at15km/h, maximum accepted snap10km; not a mapped road.',
        'limitations': ['Not observed journeys, current traffic, bus or walking times.',
                       '2021road tags; not necessarily 2021 measured census point locations.',
                       'No ferries in main graph; no turn-restriction relations; destination access permits through routing.',
                       'Destination pool inherited from historical source eligibility, not all providers.'],
        'elapsed_seconds': time.monotonic() - started,
    }
    (out / 'transport_summary.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(provenance, ensure_ascii=False, indent=2), flush=True)


def load_graph(base):
    from scipy.sparse import load_npz
    buffer = io.BytesIO()
    h = hashlib.sha256()
    for path in sorted((base / 'graph_npz_parts').glob('part_*.bin')):
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                h.update(block)
                buffer.write(block)
    if h.hexdigest() != GRAPH_SHA256:
        raise ValueError('Joined historical graph SHA256 differs')
    buffer.seek(0)
    return load_npz(buffer)


def route(args):
    """Compute source-to-provider costs for new providers on the unchanged graph."""
    from scipy.sparse.csgraph import dijkstra
    started = time.monotonic()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    cross = pd.read_parquet(out / 'transport_census_crosswalk.parquet')
    origins = pd.read_parquet(out / 'pilot_road_origins.parquet')
    if args.origin_regions:
        origins = origins[origins.region.isin(args.origin_regions)].copy()
    full_origins = pd.read_parquet(args.origins)
    current = cross.coordinate_difference_km.le(0.000001) | cross.external_context_anchor.eq(True)
    destinations = full_origins.merge(cross.loc[current, ['id', 'settlement_id']], on='id', how='inner', validate='one_to_one')
    providers = pd.read_parquet(args.providers) if args.providers.suffix == '.parquet' else pd.read_csv(args.providers)
    column = args.provider_column
    ids = set(providers[column].dropna().astype(str))
    budget_by_id = providers.groupby(column)[args.budget_column].max().to_dict() if args.budget_column else {}
    destinations = destinations[destinations.settlement_id.isin(ids)].copy()
    assert origins.settlement_id.is_unique and destinations.settlement_id.is_unique
    unavailable = ids - set(destinations.settlement_id)
    graph = load_graph(args.graph_dir or args.inputs / LEGACY)
    reverse = graph.transpose().tocsr().astype('float64')
    del graph
    origin_nodes = origins.road_node_index.to_numpy(dtype='int64')
    origin_connectors = origins.snap_km.to_numpy(dtype=float) * 4
    writer = None
    pair_count = finite_count = written_count = 0
    status_counts = {}
    output_path = out / (args.output_name + '.parquet')
    output_temp = output_path.with_suffix('.parquet.partial')
    for n, d in enumerate(destinations.itertuples(index=False)):
        budget = float(budget_by_id.get(d.settlement_id, args.max_minutes))
        if not np.isfinite(budget) or budget <= 0:
            raise ValueError('Routing budget must be positive finite minutes')
        distance = dijkstra(reverse, directed=True, indices=int(d.road_node_index),
                            limit=budget, return_predecessors=False)
        network = distance[origin_nodes]
        connector = origin_connectors + 4 * float(d.snap_km)
        total = network + connector
        same = origins.settlement_id.eq(d.settlement_id).to_numpy()
        network[same] = connector[same] = total[same] = 0
        connected = origins.weak_component.eq(d.weak_component).to_numpy()
        finite = np.isfinite(total) & (total <= budget)
        status = np.where(finite, 'routed_static_car_2021',
                          np.where(~connected, 'disconnected_weak_components',
                                   'outside_budget_or_directed_disconnected'))
        frame = pd.DataFrame({'origin_id': origins.settlement_id.to_numpy(),
                                    'destination_id': d.settlement_id,
                                    'cost_minutes': np.where(finite, total, np.nan),
                                    'network_minutes': np.where(finite, network, np.nan),
                                    'connector_minutes': np.where(finite, connector, np.nan),
                                    'route_status': status,
                                    'destination_budget_minutes': budget,
                                    'origin_snap_km': origins.snap_km.to_numpy(),
                                    'destination_snap_km': d.snap_km,
                                    'transport_source_id': 'OSM_GEOFABRIK_20210101_ACCESS_V2'})
        selected_frame = frame[frame.cost_minutes.notna()] if args.finite_only else frame
        table = pa.Table.from_pandas(selected_frame, preserve_index=False)
        if len(table):
            if writer is None:
                writer = pq.ParquetWriter(output_temp, table.schema, compression='zstd')
            writer.write_table(table)
        written_count += len(table)
        pair_count += len(frame)
        finite_count += int(finite.sum())
        for key, count in frame.route_status.value_counts().items():
            status_counts[key] = status_counts.get(key, 0) + int(count)
        if n % 10 == 0:
            print('routed provider', n + 1, '/', len(destinations), flush=True)
    if writer is None:
        raise ValueError('No provider has an accepted source-matched road snap')
    writer.close()
    output_temp.replace(output_path)
    report = {'requested_providers': len(ids), 'routed_providers': len(destinations),
              'providers_without_accepted_road_snap': sorted(unavailable), 'pairs': pair_count,
              'finite_pairs': finite_count, 'output_pairs': written_count, 'route_status_counts': status_counts,
              'max_minutes': max((float(budget_by_id.get(x, args.max_minutes)) for x in destinations.settlement_id), default=args.max_minutes),
              'default_max_minutes': args.max_minutes, 'graph_sha256': GRAPH_SHA256,
              'snapshot_utc': SNAPSHOT, 'elapsed_seconds': time.monotonic() - started}
    (out / (args.output_name + '_summary.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)



def prepare(args):
    from scipy.spatial import cKDTree
    out = args.output
    origins = pd.read_parquet(out / 'pilot_road_origins.parquet')
    dest = pd.read_parquet(out / 'all_road_destinations.parquet')
    cross = pd.read_parquet(out / 'transport_census_crosswalk.parquet')
    current = cross.coordinate_difference_km.le(0.000001) | cross.external_context_anchor.eq(True)
    supply = pd.concat([pd.read_parquet(p)[['center_id']] for p in args.supply], ignore_index=True).drop_duplicates()
    eligible = supply.merge(cross.loc[current, ['settlement_id', 'region', 'lat', 'lon']],
                            left_on='center_id', right_on='settlement_id', how='inner', validate='one_to_one')
    def xyz(lat, lon):
        a, b = np.radians(lat), np.radians(lon)
        return np.column_stack([np.cos(a)*np.cos(b), np.cos(a)*np.sin(b), np.sin(a)])
    tree = cKDTree(xyz(origins.lat, origins.lon))
    chord = tree.query(xyz(eligible.lat, eligible.lon), k=1)[0]
    eligible['minimum_geodesic_to_pilot_km'] = 2 * 6371.0088 * np.arcsin(np.clip(chord / 2, 0, 1))
    # 130km/h is the maximum edge speed in the published profile. Every admitted
    # connector is slower. This is a computational upper bound, not a catchment.
    old_budgets = dest.dropna(subset=['settlement_id']).set_index('settlement_id').routing_budget_minutes
    eligible['routing_budget_minutes'] = eligible.center_id.map(old_budgets).fillna(args.max_minutes)
    bounds = eligible.routing_budget_minutes * 130 / 60
    bound = float(bounds.max())
    within = eligible.minimum_geodesic_to_pilot_km.le(bounds)
    if not args.all_providers:
        within &= ~eligible.center_id.isin(set(old_budgets.index))
    pending = eligible[within]
    pending.to_csv(out / ('all_providers_external.csv' if args.all_providers else 'missing_providers_external.csv'), index=False)
    print(json.dumps({'source_provider_ids': len(supply), 'current_point_provider_ids': len(eligible),
                      'new_provider_ids': len(pending), 'max_minutes': args.max_minutes,
                      'physical_distance_bound_km': bound}, indent=2))


def combine(args):
    import pyarrow.compute as pc
    out = args.output
    cross = pd.read_parquet(out / 'transport_census_crosswalk.parquet')
    valid = cross.coordinate_difference_km.le(0.000001) | cross.external_context_anchor.eq(True)
    valid_ids = pa.array(cross.loc[valid, 'settlement_id'])
    providers = pd.concat([pd.read_parquet(p)[['center_id']] for p in args.supply], ignore_index=True).drop_duplicates()
    supply_ids = pa.array(providers.center_id)
    frames = [out / 'pilot_costs.parquet', args.supplement]
    writer = None
    total = 0
    skipped = 0
    seen_destinations = []
    for path in frames:
        source_destinations = set()
        for batch in pq.ParquetFile(path).iter_batches(batch_size=250000):
            t = pa.Table.from_batches([batch])
            mask = pc.and_(pc.and_(pc.is_valid(t['cost_minutes']), pc.is_in(t['origin_id'], value_set=valid_ids)),
                           pc.and_(pc.is_in(t['destination_id'], value_set=valid_ids),
                                   pc.is_in(t['destination_id'], value_set=supply_ids)))
            selected = t.filter(mask)
            skipped += len(t) - len(selected)
            if not len(selected):
                continue
            if not pc.all(pc.greater_equal(selected['cost_minutes'], 0)).as_py():
                raise ValueError('Negative route cost')
            if set(selected['route_status'].unique().to_pylist()) != {'routed_static_car_2021'}:
                raise ValueError('Finite route has contradictory status')
            if writer is None:
                # Normalise numeric types: compact legacy float32 vs graph float64.
                schema = selected.schema
                for name in ['cost_minutes', 'network_minutes', 'connector_minutes',
                             'destination_budget_minutes', 'origin_snap_km', 'destination_snap_km']:
                    schema = schema.set(schema.get_field_index(name), pa.field(name, pa.float64()))
                writer = pq.ParquetWriter(out / 'combined_costs.parquet', schema, compression='zstd')
            writer.write_table(selected.cast(schema))
            total += len(selected)
            source_destinations.update(selected['destination_id'].unique().to_pylist())
        if any(source_destinations & old for old in seen_destinations):
            raise ValueError('Supplement duplicates existing destination pool; do not concatenate blindly')
        seen_destinations.append(source_destinations)
    if writer is None:
        raise ValueError('No usable costs')
    writer.close()
    summary = {'finite_pairs': total, 'rows_not_used': skipped,
               'destination_ids': sum(map(len, seen_destinations)),
               'source_graph_sha256': GRAPH_SHA256,
               'point_policy': 'Exact root+2021source ID and same accepted2021coordinates; explicit nonadditive context anchors excepted.',
               'pair_scope': 'All routed pilot-origin to source-backed provider destinations; finite costs only.',
               'absent_pair_meaning': 'Unavailable/uncertain endpoint, disconnected or outside computed budget, never zero.',
               'inputs': {str(p.name): sha256(p) for p in frames}}
    (out / 'combined_costs_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    extract_parser = sub.add_parser('extract')
    route_parser = sub.add_parser('route')
    prepare_parser = sub.add_parser('prepare')
    combine_parser = sub.add_parser('combine')
    for parser in (prepare_parser, combine_parser):
        parser.add_argument('--output', type=Path, required=True)
        parser.add_argument('--supply', type=Path, nargs='+', required=True)
    prepare_parser.add_argument('--max-minutes', type=float, default=180)
    prepare_parser.add_argument('--all-providers', action='store_true')
    combine_parser.add_argument('--supplement', type=Path, required=True)
    for p in (extract_parser, route_parser):
        p.add_argument('--inputs', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
        p.add_argument('--origins', type=Path)
    extract_parser.add_argument('--catalog', type=Path, default=Path('data/catalog.json'))
    extract_parser.add_argument('--wide', type=Path, required=True)
    extract_parser.add_argument('--legacy-nodes', type=Path, required=True)
    extract_parser.add_argument('--regions', nargs='+')
    extract_parser.add_argument('--destinations', type=Path)
    extract_parser.add_argument('--only-index', action='store_true')
    route_parser.add_argument('--providers', type=Path, required=True)
    route_parser.add_argument('--provider-column', default='source_record_id_2021')
    route_parser.add_argument('--budget-column')
    route_parser.add_argument('--finite-only', action='store_true')
    route_parser.add_argument('--graph-dir', type=Path)
    route_parser.add_argument('--max-minutes', type=float, default=360)
    route_parser.add_argument('--origin-regions', nargs='+')
    route_parser.add_argument('--output-name', default='provider_costs')
    args = ap.parse_args()
    if args.command == 'route' and (args.origins is None or args.max_minutes <= 0):
        ap.error('route requires --origins and positive --max-minutes')
    {'extract': extract, 'route': route, 'prepare': prepare, 'combine': combine}[args.command](args)


if __name__ == '__main__':
    main()
