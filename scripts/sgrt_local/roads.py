#!/usr/bin/env python3
"""Directed road costs for a small documented system, without a service radius.

The optional context distance selects a map/diagnostic frame, never service
membership. Destinations are the requested census nodes, not an inferred list
of providers. Service eligibility is a separate input to assignment.py.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

GRAPH_SHA256 = 'a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366'
SNAPSHOT = '2021-01-01T21:42:03Z'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    path = Path(path)
    return pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)


def haversine_km(lat1, lon1, lat2, lon2):
    a, b, c, d = map(np.radians, (lat1, lon1, lat2, lon2))
    v = np.sin((c-a)/2)**2 + np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(v, 0, 1)))


def load_graph(base):
    from scipy.sparse import load_npz
    buffer = io.BytesIO()
    digest = hashlib.sha256()
    parts = sorted((Path(base)/'graph_npz_parts').glob('part_*.bin'))
    if not parts:
        raise ValueError('No published graph parts')
    for path in parts:
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
                digest.update(block)
                buffer.write(block)
    if digest.hexdigest() != GRAPH_SHA256:
        raise ValueError('Graph parts differ from published national graph')
    buffer.seek(0)
    graph = load_npz(buffer)
    if np.any(~np.isfinite(graph.data)) or np.any(graph.data < 0):
        raise ValueError('Invalid nonnegative road weights')
    return graph


def census_frame(requested, wide, context_km=0):
    """Select exact requested IDs, optionally a geodesic context for diagnostics."""
    key = 'source_record_id_2021'
    reqkey = 'source_record_id' if 'source_record_id' in requested else key
    ids = requested[reqkey].dropna().astype(str)
    if ids.duplicated().any():
        raise ValueError('Requested census IDs must be unique')
    current = wide.loc[wide[key].notna()].copy()
    if current[key].duplicated().any():
        raise ValueError('Accepted census source IDs are not unique')
    if set(ids) - set(current[key]):
        raise ValueError('Requested ID absent from accepted census base')
    anchor_ids = ids
    if 'context_anchor' in requested:
        anchor_flag = requested.context_anchor.astype(str).str.lower().isin(['true', '1', 'yes'])
        anchor_ids = requested.loc[anchor_flag, reqkey].dropna().astype(str)
        if len(anchor_ids) == 0 and context_km > 0:
            raise ValueError('Context frame requested but no context anchors selected')
    anchors = current.loc[current[key].isin(anchor_ids)].copy()
    haspoint = current.accepted_point_present_2021.eq(True)
    current['distance_to_requested_km'] = np.inf
    for row in anchors.itertuples(index=False):
        if row.accepted_point_present_2021:
            distance = haversine_km(current.accepted_latitude_2021,
                                    current.accepted_longitude_2021,
                                    row.accepted_latitude_2021,
                                    row.accepted_longitude_2021)
            current['distance_to_requested_km'] = np.minimum(
                current.distance_to_requested_km, distance)
    keep = current[key].isin(ids)
    if context_km > 0:
        keep |= haspoint & current.distance_to_requested_km.le(context_km)
    current = current.loc[keep].copy()
    current['requested_destination'] = current[key].isin(ids)
    current['context_anchor'] = current[key].isin(anchor_ids)
    current['context_selection_only'] = ~current.requested_destination
    current['source_record_id'] = current[key]
    return current


def bridge(frame, legacy, origins):
    """Census identity requires both root and exact 2021 source ID."""
    keys = ['root', 'source_record_id_2021']
    if legacy.id.duplicated().any() or origins.id.duplicated().any():
        raise ValueError('Nonunique historical road IDs')
    old = legacy.rename(columns={'id': 'legacy_id', 'lat': 'legacy_lat', 'lon': 'legacy_lon'})
    old = old.loc[old.root.notna() & old.source_record_id_2021.notna(),
                  keys + ['legacy_id', 'legacy_lat', 'legacy_lon']]
    if old.duplicated(keys).any():
        raise ValueError('Nonunique historical census identities')
    joined = frame.merge(old, on=keys, how='left', validate='one_to_one')
    cols = ['id', 'road_node_index', 'snap_km', 'weak_component', 'accepted_snap',
            'road_snap_lat', 'road_snap_lon', 'network_source_timestamp_utc',
            'connector_scenario_kmh']
    joined = joined.merge(origins[cols], left_on='legacy_id', right_on='id',
                          how='left', validate='one_to_one')
    joined['coordinate_difference_km'] = haversine_km(
        joined.accepted_latitude_2021, joined.accepted_longitude_2021,
        joined.legacy_lat, joined.legacy_lon)
    joined['road_endpoint_status'] = 'no_exact_road_identity'
    identity = joined.legacy_id.notna()
    joined.loc[identity, 'road_endpoint_status'] = 'no_accepted_road_snap'
    coords = joined.accepted_point_present_2021.eq(True) & joined.coordinate_difference_km.le(.000001)
    accepted = (identity & coords & joined.accepted_snap.eq(True)
                & joined.road_node_index.notna() & joined.snap_km.between(0, 10))
    joined.loc[identity & ~coords, 'road_endpoint_status'] = 'census_coordinate_not_exact_road_point'
    joined.loc[accepted, 'road_endpoint_status'] = 'accepted_exact_census_road_endpoint'
    joined['road_endpoint_accepted'] = accepted
    joined['connector_over_2km'] = joined.snap_km.gt(2)
    joined['identity_basis'] = 'exact_root_and_source_record_id_2021_and_equal_coordinates'
    if not joined.loc[accepted, 'connector_scenario_kmh'].eq(15).all():
        raise ValueError('Historical connectors differ from declared 15km/h')
    return joined


def route(frame, graph):
    """All origins to requested destinations; infinite graph search, no radius."""
    from scipy.sparse.csgraph import dijkstra
    reverse = graph.transpose().tocsr()
    del graph
    valid = frame.road_endpoint_accepted
    indices = frame.loc[valid, 'road_node_index'].astype('int64').to_numpy()
    pairs = []
    for target in frame.loc[frame.requested_destination].itertuples(index=False):
        status = np.full(len(frame), 'unaccepted_origin_endpoint', dtype=object)
        network = np.full(len(frame), np.nan)
        connectors = np.full(len(frame), np.nan)
        total = np.full(len(frame), np.nan)
        if not target.road_endpoint_accepted:
            status[:] = 'unaccepted_destination_endpoint'
        else:
            distance = dijkstra(reverse, directed=True, indices=int(target.road_node_index))
            net = distance[indices]
            conn = 4 * (frame.loc[valid, 'snap_km'].to_numpy() + target.snap_km)
            costs = net + conn
            same = frame.loc[valid, 'source_record_id'].eq(target.source_record_id).to_numpy()
            net[same] = conn[same] = costs[same] = 0
            finite = np.isfinite(costs)
            net[~finite] = conn[~finite] = costs[~finite] = np.nan
            weak = frame.loc[valid, 'weak_component'].eq(target.weak_component).to_numpy()
            status[valid] = np.where(finite, 'routed_static_car_2021',
                                     np.where(weak, 'directed_disconnected', 'disconnected_weak_components'))
            network[valid], connectors[valid], total[valid] = net, conn, costs
        pairs.append(pd.DataFrame({
            'origin_id': frame.source_record_id,
            'provider_id': target.source_record_id,
            'destination_id': target.source_record_id,
            'network_minutes': network,
            'connector_minutes': connectors,
            'cost_minutes': total,
            'route_status': status,
            'origin_snap_km': frame.snap_km,
            'destination_snap_km': target.snap_km,
            'origin_connector_over_2km': frame.connector_over_2km,
            'destination_connector_over_2km': target.connector_over_2km,
            'same_settlement_zero_cost_assumption': frame.source_record_id.eq(target.source_record_id),
            'transport_source_id': 'OSM_GEOFABRIK_20210101_ACCESS_V2',
        }))
        print('routed', target.settlement_name_2021, flush=True)
    return pd.concat(pairs, ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--nodes', type=Path, required=True)
    ap.add_argument('--wide', type=Path, required=True)
    ap.add_argument('--legacy-nodes', type=Path, required=True)
    ap.add_argument('--road-origins', type=Path, required=True)
    ap.add_argument('--graph-dir', type=Path, required=True)
    ap.add_argument('--context-km', type=float, default=25,
                    help='Geodesic diagnostic/map frame around requested points, never service radius')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if not np.isfinite(args.context_km) or args.context_km < 0:
        ap.error('--context-km must be finite and nonnegative')
    args.output.mkdir(parents=True, exist_ok=True)
    requested = read(args.nodes)
    wide = pd.read_parquet(args.wide)
    current = census_frame(requested, wide, args.context_km)
    legacy = pd.read_parquet(args.legacy_nodes)
    origins = pd.read_parquet(args.road_origins)
    endpoints = bridge(current, legacy, origins)
    endpoints.to_parquet(args.output/'road_endpoints.parquet', index=False, compression='zstd')
    endpoints.to_csv(args.output/'road_endpoints.csv', index=False)
    snapshots = args.output/'inputs'
    snapshots.mkdir(exist_ok=True)
    requested.to_csv(snapshots/'requested_nodes.csv', index=False)
    selected_ids = set(endpoints.legacy_id.dropna())
    legacy.loc[legacy.id.isin(selected_ids)].to_parquet(
        snapshots/'legacy_nodes.parquet', index=False, compression='zstd')
    origins.loc[origins.id.isin(selected_ids)].to_parquet(
        snapshots/'road_origins.parquet', index=False, compression='zstd')
    graph = load_graph(args.graph_dir)
    graph_shape = graph.shape
    graph_arcs = graph.nnz
    costs = route(endpoints, graph)
    costs.to_parquet(args.output/'costs.parquet', index=False, compression='zstd')
    costs.to_csv(args.output/'costs.csv', index=False)
    names = endpoints.set_index('source_record_id').settlement_name_2021
    named = costs.copy()
    named['origin_name'] = named.origin_id.map(names)
    named['destination_name'] = named.destination_id.map(names)
    named.to_csv(args.output/'named_costs.csv', index=False)
    summary = {
        'graph_sha256': GRAPH_SHA256, 'road_snapshot_utc': SNAPSHOT,
        'vertices': graph_shape[0], 'directed_arcs': graph_arcs,
        'requested_destinations': int(endpoints.requested_destination.sum()),
        'origins_in_diagnostic_frame': len(endpoints),
        'accepted_endpoints': int(endpoints.road_endpoint_accepted.sum()),
        'context_selection_km': args.context_km,
        'context_distance_meaning': 'Map/diagnostic frame around context_anchor=True requested nodes (or all requested nodes if no anchor flag), not a catchment or service radius.',
        'routing_limit_minutes': None,
        'pairs': len(costs), 'finite_pairs': int(costs.cost_minutes.notna().sum()),
        'status_counts': {str(k): int(v) for k,v in costs.route_status.value_counts().items()},
        'max_cost_minutes': float(costs.cost_minutes.max()),
        'max_snap_km': float(endpoints.snap_km.max()),
        'endpoint_status_counts': {str(k): int(v) for k,v in endpoints.road_endpoint_status.value_counts().items()},
        'input_sha256': {key: sha256(getattr(args,key)) for key in ['nodes','wide','legacy_nodes','road_origins']},
        'minimal_bridge_input_sha256': {path.name: sha256(path) for path in sorted(snapshots.glob('*'))},
        'limitations': ['Static car profile, not observed trips or school-bus times.',
                       'Roads from 2021; institutional documents have separately recorded dates.',
                       'Straight connectors at 15km/h, maximum accepted snap10km; not mapped access roads.',
                       'Self cost zero is a settlement-scale co-location assumption.',
                       'No ferry or turn-restriction modelling in inherited graph.',
                       'Destination list is a diagnostic list of nodes; service eligibility must be supplied separately.',
                       'Full path geometry is not reconstructed: graph-vertex coordinates are absent from compact published graph.'],
    }
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
