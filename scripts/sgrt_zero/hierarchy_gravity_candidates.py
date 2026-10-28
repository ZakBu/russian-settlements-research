#!/usr/bin/env python3
"""Exact pilot inter-centre road costs and explicitly conditional potentials.

This module never assigns a territorial hierarchy from an argmax. A known
local reservation is retained, missing masses/routes stay unknown, and the
candidate set is not assumed exhaustive. The origin may have local services;
that does not delete its possible relation with a larger centre.
"""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.routes import load_graph


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def exact_city_ids(reference, names):
    """Explicit named regional city examples, without confusing namesakes.

    Population is used only to select the real named city for this audit.
    It is not an attraction weight. Every returned ID is an exact accepted
    reference identity, including the three nonadditive federal-city contexts.
    """
    result = []
    for name in names:
        subset = reference[reference.name.eq(name) & reference.source_record_id.notna()]
        if not len(subset):
            raise ValueError('No exact reference city: ' + name)
        pop = pd.to_numeric(subset.population_2021, errors='coerce')
        if not pop.notna().any():
            raise ValueError('Cannot disambiguate named city without a known reference population')
        result.append(str(subset.loc[pop.idxmax(), 'source_record_id']))
    return result


def costs_to_targets(graph, endpoints, target_ids, *, network_limit_minutes, held_ids=()):
    """One reverse directed Dijkstra per exact current target, all origins.

    Current endpoint IDs/nodes replace historical Moscow/Petersburg context
    coordinates. An absent path inside the numerical search radius remains an
    unknown route, never an assertion of no travel or zero attraction.
    """
    from scipy.sparse.csgraph import dijkstra
    if not np.isfinite(network_limit_minutes) or network_limit_minutes <= 0:
        raise ValueError('Require a positive finite network search limit')
    if not endpoints.source_record_id.is_unique:
        raise ValueError('Endpoint source identities must be unique')
    required = {'source_record_id', 'road_node_index', 'snap_km', 'road_endpoint_accepted'}
    if not required <= set(endpoints):
        raise ValueError('Endpoint columns missing')
    ep = endpoints.set_index('source_record_id')
    held_ids = set(held_ids)
    accepted = (ep.road_endpoint_accepted.fillna(False).eq(True)
                & ep.road_node_index.notna() & np.isfinite(pd.to_numeric(ep.snap_km, errors='coerce'))
                & ~ep.index.isin(held_ids))
    if not accepted.loc[list(target_ids)].all():
        raise ValueError('An intended target has an unknown/rejected/held current road endpoint')
    reverse = graph.T.tocsr()
    origin_positions = np.flatnonzero(accepted.to_numpy())
    nodes = ep.loc[accepted, 'road_node_index'].to_numpy(dtype='int64')
    if len(nodes) and (nodes.min() < 0 or nodes.max() >= graph.shape[0]):
        raise ValueError('Endpoint vertex outside frozen road graph')
    snap = pd.to_numeric(ep.snap_km, errors='coerce').to_numpy(dtype=float)
    parts = []
    for target in target_ids:
        target_row = ep.loc[target]
        distances = dijkstra(reverse, directed=True, indices=int(target_row.road_node_index),
                             limit=float(network_limit_minutes))
        network = np.full(len(ep), np.nan)
        network[origin_positions] = distances[nodes]
        finite = accepted.to_numpy() & np.isfinite(network)
        network[~finite] = np.nan
        connector = np.where(finite, (snap + float(target_row.snap_km)) * 4., np.nan)
        total = network + connector
        same = ep.index == target
        network[same] = connector[same] = total[same] = 0.
        status = np.where(~accepted.to_numpy(), 'current_endpoint_unknown_or_held',
                          np.where(finite, 'current_exact_endpoint_directed_cost',
                                   'not_found_inside_network_search_bound_not_evidence_of_isolation'))
        parts.append(pd.DataFrame({'origin_id': ep.index, 'destination_id': target,
                                   'cost_minutes': total, 'network_minutes': network,
                                   'connector_minutes': connector, 'pair_status': status,
                                   'network_search_limit_minutes': float(network_limit_minutes),
                                   'network_epoch': '2021-01-01', 'connector_scenario_kmh': 15.,
                                   'observed_trip': False}))
        del distances
        gc.collect()
    return pd.concat(parts, ignore_index=True)


def relative_potentials(profiles, pairs, *, mass_column, half_life_minutes, transform='linear'):
    """Compare known inter-centre potential with a local reservation of one.

    Counts of registered addresses are proxies, not staff, beds or jobs. A
    monotone transform is an explicit sensitivity choice, never fitted to a
    desired boundary. Outputs are unnormalised conditional scores, not trip
    probabilities and not accepted territorial memberships.
    """
    if not profiles.source_record_id.is_unique:
        raise ValueError('Profile identities must be unique')
    if pairs.duplicated(['origin_id', 'destination_id']).any():
        raise ValueError('Duplicate directed pilot pair')
    if not np.isfinite(half_life_minutes) or half_life_minutes <= 0:
        raise ValueError('Half-life must be positive and finite')
    if transform not in {'linear', 'log1p'}:
        raise ValueError('Unknown explicit mass transform')
    mass = pd.to_numeric(profiles.set_index('source_record_id')[mass_column], errors='coerce')
    # No zero imputation: unrecorded/zero proxy cannot identify a local
    # reservation, so its potential comparison is held rather than forced.
    valid_mass = mass.gt(0) & np.isfinite(mass)
    effective = mass.where(valid_mass)
    if transform == 'log1p':
        effective = np.log1p(effective)
    out = pairs.copy()
    out['origin_mass_proxy'] = out.origin_id.map(mass)
    out['destination_mass_proxy'] = out.destination_id.map(mass)
    a = out.origin_id.map(effective)
    b = out.destination_id.map(effective)
    cost = pd.to_numeric(out.cost_minutes, errors='coerce')
    valid = a.notna() & b.notna() & np.isfinite(cost) & cost.ge(0)
    out['relative_potential_to_local_reservation'] = np.where(
        valid, b / a * np.exp2(-cost / half_life_minutes), np.nan)
    out['local_reservation'] = 1.
    out['half_life_minutes_scenario'] = float(half_life_minutes)
    out['mass_transform_scenario'] = transform
    out['mass_field'] = mass_column
    out['beats_local_proxy_reservation'] = (out.relative_potential_to_local_reservation.gt(1.)
                                          & out.origin_id.ne(out.destination_id))
    out['status'] = np.where(a.isna() | b.isna(), 'unknown_mass_not_zero',
                            np.where(~np.isfinite(cost), 'unknown_road_cost_not_zero',
                                     'conditional_potential_not_delimited_system'))
    out['candidate_pool_completeness_established'] = False
    out['observed_flow_calibration_established'] = False
    out['territorial_assignment_established'] = False
    return out


def road_cli(args):
    reference = pd.read_parquet(args.reference)
    targets = exact_city_ids(reference, args.cities)
    endpoints = pd.read_parquet(args.endpoints)
    held = json.loads(args.coordinate_holds.read_text())['records'] if args.coordinate_holds else []
    paths = [args.reference, args.endpoints, Path(__file__)]
    if args.coordinate_holds:
        paths.append(args.coordinate_holds)
    before = {str(path): digest(path) for path in paths}
    graph = load_graph(args.graph_directory)
    costs = costs_to_targets(graph, endpoints, targets, network_limit_minutes=args.network_limit,
                            held_ids=[r['source_record_id'] for r in held])
    args.output.mkdir(parents=True, exist_ok=True)
    costs.to_parquet(args.output / 'pilot_current_city_costs.parquet', index=False)
    target_rows = reference.set_index('source_record_id').loc[targets, ['name', 'region', 'lat', 'lon', 'population_role']]
    summary = {'target_points': target_rows.reset_index().to_dict('records'),
               'pairs': len(costs), 'origin_records': endpoints.source_record_id.nunique(),
               'network_search_limit_minutes': args.network_limit,
               'cost_status_counts': costs.pair_status.value_counts().to_dict(),
               'same_settlement_self_cost_is_zero': True,
               'old_context_coordinates_reused': False,
               'observed_trips': False,
               'input_sha256': before}
    if before != {str(path): digest(path) for path in paths}:
        raise RuntimeError('Input changed during pilot routing')
    (args.output / 'road_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    road = sub.add_parser('road-costs')
    for field in ['reference', 'endpoints', 'graph-directory', 'output']:
        road.add_argument('--' + field, type=Path, required=True)
    road.add_argument('--coordinate-holds', type=Path)
    road.add_argument('--cities', nargs='+', default=['Москва', 'Санкт-Петербург', 'Саратов', 'Челябинск', 'Екатеринбург', 'Казань'])
    road.add_argument('--network-limit', type=float, default=180.)
    potentials = sub.add_parser('potentials')
    potentials.add_argument('--profiles', type=Path, required=True)
    potentials.add_argument('--pairs', type=Path, required=True)
    potentials.add_argument('--mass-column', required=True)
    potentials.add_argument('--half-life', type=float, required=True)
    potentials.add_argument('--transform', choices=['linear', 'log1p'], default='linear')
    potentials.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'road-costs':
        road_cli(args)
    else:
        result = relative_potentials(pd.read_parquet(args.profiles), pd.read_parquet(args.pairs),
                                    mass_column=args.mass_column, half_life_minutes=args.half_life,
                                    transform=args.transform)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(args.output, index=False)
