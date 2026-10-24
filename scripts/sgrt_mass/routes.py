#!/usr/bin/env python3
"""One directed multisource Dijkstra per service class, without catchment radii.

Each eligible provider settlement gets a virtual source with a weighted edge
to its snapped road vertex. The weight is its destination connector. SciPy's
min_only Dijkstra on the reversed road graph therefore minimizes network time
plus destination connector exactly, rather than choosing a road vertex first
and incorrectly adding a provider connector afterwards. Origin connectors are
added after the search. Population and institution counts are never weights.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import resource
import sys
import time

import numpy as np
import pandas as pd

GRAPH_SHA256 = 'a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366'
SNAPSHOT = '2021-01-01T21:42:03Z'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    path = Path(path)
    return pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)


def haversine_km(lat1, lon1, lat2, lon2):
    a, b, c, d = map(np.radians, (lat1, lon1, lat2, lon2))
    value = np.sin((c-a)/2)**2 + np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(value, 0, 1)))


def prepare_endpoints(settlements, legacy, road_origins):
    """Preserve the ordinary spatial census frame, including unroutable points."""
    frame = settlements.copy()
    if not frame.source_record_id.is_unique:
        raise ValueError('Census source IDs must be unique')
    required = ['source_record_id', 'root', 'lat', 'lon']
    if frame[required].isna().any().any():
        raise ValueError('Ordinary spatial frame has missing identity or coordinates')
    if not legacy.id.is_unique or not road_origins.id.is_unique:
        raise ValueError('Historical road IDs are not unique')
    old = legacy.loc[legacy.root.notna() & legacy.source_record_id_2021.notna(),
                     ['id', 'root', 'source_record_id_2021', 'lat', 'lon']].copy()
    old = old.rename(columns={'id': 'road_legacy_id', 'source_record_id_2021': 'source_record_id',
                              'lat': 'road_legacy_lat', 'lon': 'road_legacy_lon'})
    if old.duplicated(['root', 'source_record_id']).any():
        raise ValueError('Historical exact census identities are not unique')
    frame = frame.merge(old, on=['root', 'source_record_id'], how='left', validate='one_to_one')
    if frame.road_legacy_id.dropna().duplicated().any():
        raise ValueError('Two census points claim the same historical road identity')
    cols = ['id', 'road_node_index', 'snap_km', 'weak_component', 'accepted_snap',
            'road_snap_lat', 'road_snap_lon', 'connector_scenario_kmh']
    frame = frame.merge(road_origins[cols], left_on='road_legacy_id', right_on='id',
                         how='left', validate='many_to_one')
    frame = frame.drop(columns=['id'])
    frame['road_coordinate_difference_km'] = haversine_km(
        frame.lat, frame.lon, frame.road_legacy_lat, frame.road_legacy_lon)
    identity = frame.road_legacy_id.notna()
    coordinates = frame.road_coordinate_difference_km.le(.000001)
    accepted = (identity & coordinates & frame.accepted_snap.eq(True)
                & frame.road_node_index.notna() & frame.snap_km.between(0, 10))
    frame['road_endpoint_status'] = 'no_exact_road_identity'
    frame.loc[identity, 'road_endpoint_status'] = 'no_accepted_road_snap'
    frame.loc[identity & ~coordinates, 'road_endpoint_status'] = 'accepted_census_point_differs_from_historical_road_point'
    frame.loc[accepted, 'road_endpoint_status'] = 'accepted_exact_census_road_endpoint'
    frame['road_endpoint_accepted'] = accepted
    frame['road_connector_over_2km'] = frame.snap_km.gt(2)
    frame['road_identity_basis'] = 'exact_root_and_source_record_id_and_equal_coordinates'
    if not frame.loc[accepted, 'connector_scenario_kmh'].eq(15).all():
        raise ValueError('Historical road connectors are not uniformly 15km/h')
    frame['origin_id'] = frame.source_record_id
    return frame


def apply_fresh_resnaps(endpoints, resnaps):
    """Explicit new geometry repairs, never a guessed historical identity."""
    required = {'source_record_id','root','lat','lon','road_node_index','snap_km',
                'road_snap_lat','road_snap_lon','weak_component','road_endpoint_accepted',
                'connector_scenario_kmh','census_identity_changed','legacy_identity_used'}
    if not required.issubset(resnaps):
        raise ValueError('Fresh resnaps missing identity/geometry provenance')
    if resnaps.source_record_id.duplicated().any():
        raise ValueError('Duplicate fresh resnap census IDs')
    if not set(resnaps.source_record_id).issubset(endpoints.source_record_id):
        raise ValueError('Fresh resnap refers to a point outside the ordinary census frame')
    if resnaps.census_identity_changed.ne(False).any() or resnaps.legacy_identity_used.ne(False).any():
        raise ValueError('Fresh resnap must not change census identity or claim historical identity reuse')
    current = endpoints.set_index('source_record_id').loc[resnaps.source_record_id]
    if not np.array_equal(current.root.to_numpy(), resnaps.root.to_numpy()):
        raise ValueError('Fresh resnap census roots differ')
    if not (np.allclose(current.lat.to_numpy(),resnaps.lat.to_numpy(),rtol=0,atol=1e-12)
            and np.allclose(current.lon.to_numpy(),resnaps.lon.to_numpy(),rtol=0,atol=1e-12)):
        raise ValueError('Fresh resnap does not use the accepted current census coordinates')
    repairs = resnaps.loc[resnaps.road_endpoint_accepted.eq(True)].copy().set_index('source_record_id')
    if not repairs.snap_km.between(0,10).all() or not repairs.connector_scenario_kmh.eq(15).all():
        raise ValueError('Fresh resnap violates declared snap/connector scenario')
    if not np.isfinite(repairs.road_node_index).all() or (repairs.road_node_index<0).any():
        raise ValueError('Fresh resnap has invalid road vertices')
    out = endpoints.copy().set_index('source_record_id')
    for col in ['road_endpoint_status','road_endpoint_accepted','road_node_index','snap_km']:
        target = 'historical_'+col
        if target not in out:
            out[target] = out[col]
    was_accepted = out.loc[repairs.index,'road_endpoint_accepted']
    was_fresh = out.loc[repairs.index,'road_identity_basis'].fillna('').str.startswith('fresh_')
    if (was_accepted & ~was_fresh).any():
        raise ValueError('Fresh repair would silently replace an already accepted historical road point')
    for col in ['road_node_index','snap_km','weak_component','road_snap_lat','road_snap_lon','connector_scenario_kmh']:
        out.loc[repairs.index,col] = repairs[col]
    out.loc[repairs.index,'road_endpoint_status'] = 'accepted_fresh_current_point_road_snap'
    out.loc[repairs.index,'road_endpoint_accepted'] = True
    out.loc[repairs.index,'accepted_snap'] = True
    out.loc[repairs.index,'road_identity_basis'] = 'fresh_great_circle_snap_of_current_accepted_census_point'
    out['road_connector_over_2km'] = out.snap_km.gt(2)
    return out.reset_index()


def load_graph(directory):
    from scipy.sparse import load_npz
    buffer = io.BytesIO()
    digest = hashlib.sha256()
    parts = sorted((Path(directory)/'graph_npz_parts').glob('part_*.bin'))
    if not parts:
        raise ValueError('No published graph parts')
    for path in parts:
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
                digest.update(block)
                buffer.write(block)
    if digest.hexdigest() != GRAPH_SHA256:
        raise ValueError('Graph SHA256 differs from published version')
    buffer.seek(0)
    graph = load_npz(buffer)
    if np.any(~np.isfinite(graph.data)) or np.any(graph.data < 0):
        raise ValueError('Road graph must have finite nonnegative weights')
    return graph


def weighted_multisource(reverse_graph, seed_nodes, seed_offsets):
    """Nearest seed labels with arbitrary nonnegative initial offsets.

    Returns two arrays on physical road vertices: total cost excluding the
    origin connector, and index into the caller's seed arrays (-1 unreachable).
    Ties select an optimum; this is not a uniqueness certificate.
    """
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    base = reverse_graph.tocsr(copy=False)
    nodes = np.asarray(seed_nodes, dtype=np.int64)
    offsets = np.asarray(seed_offsets, dtype=np.float64)
    if nodes.ndim != 1 or offsets.shape != nodes.shape or not len(nodes):
        raise ValueError('At least one seed and one offset per seed are required')
    if np.any(nodes < 0) or np.any(nodes >= base.shape[0]):
        raise ValueError('Seed road vertex outside graph')
    if np.any(~np.isfinite(offsets)) or np.any(offsets < 0):
        raise ValueError('Seed offsets must be finite and nonnegative')
    n, k = base.shape[0], len(nodes)
    if n+k >= np.iinfo(np.int32).max or base.nnz+k >= np.iinfo(np.int32).max:
        raise ValueError('Graph exceeds explicitly supported int32 CSR bounds')
    data = np.concatenate((base.data, offsets))
    indices = np.concatenate((base.indices, nodes.astype(np.int32)))
    indptr = np.concatenate((base.indptr, np.arange(base.nnz+1, base.nnz+k+1, dtype=np.int32)))
    augmented = csr_matrix((data, indices, indptr), shape=(n+k, n+k), copy=False)
    virtual = np.arange(n, n+k, dtype=np.int32)
    distance, predecessors, source = dijkstra(
        augmented, directed=True, indices=virtual, min_only=True, return_predecessors=True)
    del predecessors, augmented, data, indices, indptr
    distance = distance[:n]
    source = source[:n]
    selected = source.copy()
    selected -= n
    selected[source < n] = -1
    selected[~np.isfinite(distance)] = -1
    return distance, selected


def json_values(values):
    return json.dumps(sorted(set(str(value) for value in values if pd.notna(value))), ensure_ascii=False)


def provider_settlements(supply, endpoints, service_code, accepted_statuses=('observed',)):
    required = {'source_record_id', 'provider_id', 'service_code', 'supply_status'}
    if not required.issubset(supply.columns):
        raise ValueError('Supply requires ' + ','.join(sorted(required)))
    positive = supply.loc[supply.service_code.eq(service_code)
                          & supply.supply_status.isin(accepted_statuses)
                          & supply.source_record_id.notna()].copy()
    outside = positive.loc[~positive.source_record_id.isin(endpoints.source_record_id)].copy()
    positive = positive.loc[positive.source_record_id.isin(endpoints.source_record_id)]
    rows = []
    for source_id, group in positive.groupby('source_record_id', sort=True):
        row = {'source_record_id': source_id,
               'representative_provider_id': str(sorted(group.provider_id.dropna().astype(str))[0]),
               'provider_ids_json': json_values(group.provider_id),
               'provider_records': len(group),
               'observed_supply_in_np': bool(group.supply_status.eq('observed').any()),
               'supply_statuses_json': json_values(group.supply_status)}
        for col in ['source_id', 'source_year', 'observation_year', 'match_status']:
            if col in group:
                row[('match_statuses_json' if col == 'match_status' else col+'s_json')] = json_values(group[col])
        rows.append(row)
    if not rows:
        empty = pd.DataFrame(columns=['source_record_id','representative_provider_id','provider_ids_json',
                                      'provider_records','observed_supply_in_np','supply_statuses_json'])
        return empty.merge(endpoints, on='source_record_id', how='left'), outside
    providers = pd.DataFrame(rows).merge(endpoints, on='source_record_id', how='left', validate='one_to_one')
    return providers, outside


def nearest_for_service(endpoints, providers, reverse_graph, service_code):
    """Nearest known eligible provider NP, plus explicit within-NP self service."""
    metadata = [c for c in ['origin_id','source_record_id','root','name','region','lat','lon',
                           'population','population_raw','working_credit_present','credited_population_2021',
                           'road_endpoint_status','road_endpoint_accepted','road_connector_over_2km',
                           'snap_km','road_node_index'] if c in endpoints]
    out = endpoints[metadata].copy().reset_index(drop=True)
    out['service_code'] = service_code
    out['selected_provider_source_record_id'] = pd.Series([None]*len(out), dtype=object)
    out['cost_minutes'] = np.nan
    out['network_minutes'] = np.nan
    out['connector_minutes'] = np.nan
    out['provider_snap_km'] = np.nan
    out['route_status'] = 'origin_road_endpoint_unavailable'
    out['zero_cost_np_assumption'] = False
    out['known_local_supply'] = out.source_record_id.isin(providers.source_record_id)
    observed_local = out.source_record_id.isin(providers.loc[providers.observed_supply_in_np.eq(True), 'source_record_id'])
    out['local_supply_status'] = np.where(observed_local, 'observed_present',
                                         np.where(out.known_local_supply, 'proxy_present', 'unknown'))
    out['tie_status'] = 'no_supported_candidate'
    out['nearest_tie_count_lower_bound'] = pd.array([None]*len(out), dtype='Int64')
    seeds = providers.loc[providers.road_endpoint_accepted.eq(True)].copy().reset_index(drop=True)
    out['known_provider_settlements'] = len(providers)
    out['routable_known_provider_settlements'] = len(seeds)
    out['unroutable_known_provider_settlements'] = len(providers)-len(seeds)
    if len(seeds):
        seed_nodes = seeds.road_node_index.astype('int64').to_numpy()
        seed_offsets = seeds.snap_km.to_numpy(dtype=float)*4
        distances, selected = weighted_multisource(reverse_graph, seed_nodes, seed_offsets)
        valid = out.road_endpoint_accepted.eq(True)
        road_nodes = out.loc[valid, 'road_node_index'].astype('int64').to_numpy()
        labels = selected[road_nodes]
        reachable = labels >= 0
        out.loc[valid, 'route_status'] = 'no_directed_route_to_known_eligible_provider'
        positions = np.flatnonzero(valid.to_numpy())[reachable]
        chosen = seeds.iloc[labels[reachable]].reset_index(drop=True)
        origin_connectors = out.iloc[positions].snap_km.to_numpy(dtype=float)*4
        destination_connectors = chosen.snap_km.to_numpy(dtype=float)*4
        total_without_origin = distances[road_nodes[reachable]]
        out.loc[positions, 'selected_provider_source_record_id'] = chosen.source_record_id.to_numpy()
        out.loc[positions, 'cost_minutes'] = total_without_origin + origin_connectors
        out.loc[positions, 'network_minutes'] = np.maximum(0, total_without_origin-destination_connectors)
        out.loc[positions, 'connector_minutes'] = origin_connectors+destination_connectors
        out.loc[positions, 'provider_snap_km'] = chosen.snap_km.to_numpy()
        out.loc[positions, 'route_status'] = 'nearest_known_eligible_provider'
        out.loc[positions, 'tie_status'] = 'other_equal_geographic_paths_not_exhaustively_checked'
        out.loc[positions, 'nearest_tie_count_lower_bound'] = 1
        # Shared-road-node equal-offset seeds are a known subset of all ties.
        minimum = seeds.groupby('road_node_index').snap_km.transform('min').to_numpy()
        is_minimum = np.isclose(seeds.snap_km.to_numpy(), minimum, rtol=0, atol=2.5e-10)
        counts = seeds.loc[is_minimum].groupby('road_node_index').size()
        lower_bound = chosen.road_node_index.map(counts).fillna(1).astype(int).to_numpy()
        tied = lower_bound > 1
        out.loc[positions, 'nearest_tie_count_lower_bound'] = lower_bound
        out.loc[positions[tied], 'tie_status'] = 'known_shared_road_seed_tie_other_geographic_paths_not_exhaustively_checked'
        del distances, selected
    else:
        out['route_status'] = 'no_routable_known_eligible_provider' if len(providers) else 'no_known_eligible_provider'
    # Self service is an explicit settlement-scale convention, independent of
    # the road snap. It does not claim exact institution or household location.
    local = out.known_local_supply
    out.loc[local, 'selected_provider_source_record_id'] = out.loc[local, 'source_record_id']
    out.loc[local, ['cost_minutes','network_minutes','connector_minutes']] = 0.
    out.loc[local, 'provider_snap_km'] = out.loc[local, 'snap_km']
    out.loc[local, 'route_status'] = 'local_known_eligible_supply_np_zero_assumption'
    out.loc[local, 'zero_cost_np_assumption'] = True
    out.loc[local, 'tie_status'] = 'local_priority_np_scale_assumption_not_institution_choice'
    out.loc[local, 'nearest_tie_count_lower_bound'] = 1
    pindex = providers.set_index('source_record_id')
    for col in ['representative_provider_id','provider_ids_json','provider_records','supply_statuses_json',
                'source_ids_json','source_years_json','observation_years_json','match_statuses_json']:
        if col in providers:
            out['selected_'+col] = out.selected_provider_source_record_id.map(pindex[col])
    out['provider_id'] = out.get('selected_representative_provider_id', pd.Series(None, index=out.index, dtype=object))
    out['primary_cost_minutes'] = out.cost_minutes
    out['primary_candidate_id'] = out.selected_provider_source_record_id
    out['missing_local_supply_could_change_choice'] = ~observed_local
    out['provider_inventory_completeness'] = 'not_established'
    out['outside_or_unrecorded_providers_could_change_choice'] = ~observed_local
    out['observed_flow'] = False
    out['assignment_established'] = False
    out['geographic_ties_exhaustively_checked'] = False
    out['second_nearest_available'] = False
    out['road_snapshot_utc'] = SNAPSHOT
    out['routing_limit_minutes'] = np.nan
    return out


def site_providers(sites, service_code, accepted_statuses=('observed',)):
    """Actual institution points; no nearest-settlement identity is invented."""
    required = {'provider_id','service_code','supply_status','road_node_index','snap_km',
                'accepted_snap','site_lat','site_lon'}
    if not required.issubset(sites):
        raise ValueError('Site seeds require ' + ','.join(sorted(required)))
    out = sites.loc[sites.service_code.eq(service_code)
                    & sites.supply_status.isin(accepted_statuses)].copy()
    if out.provider_id.isna().any() or out.provider_id.duplicated().any():
        raise ValueError('Site provider IDs must be present and unique per service')
    if 'source_record_id' not in out:
        out['source_record_id'] = None
    out['road_endpoint_accepted'] = (out.accepted_snap.eq(True) & out.road_node_index.notna()
                                      & out.snap_km.between(0,10))
    return out.sort_values('provider_id').reset_index(drop=True)


def nearest_for_sites(endpoints, providers, reverse_graph, service_code):
    """Route to actual sites, retaining null NP identity and pre-overlay cost."""
    metadata = [c for c in ['origin_id','source_record_id','root','name','region','lat','lon',
                           'population','population_raw','working_credit_present','credited_population_2021',
                           'road_endpoint_status','road_endpoint_accepted','road_connector_over_2km',
                           'snap_km','road_node_index'] if c in endpoints]
    out = endpoints[metadata].copy().reset_index(drop=True)
    out['service_code'] = service_code
    out['selected_provider_id'] = pd.Series([None]*len(out), dtype=object)
    out['cost_minutes'] = np.nan
    out['network_minutes'] = np.nan
    out['connector_minutes'] = np.nan
    out['provider_snap_km'] = np.nan
    out['route_status'] = 'origin_road_endpoint_unavailable'
    out['tie_status'] = 'no_supported_candidate'
    out['nearest_tie_count_lower_bound'] = pd.array([None]*len(out), dtype='Int64')
    seeds = providers.loc[providers.road_endpoint_accepted.eq(True)].copy().reset_index(drop=True)
    out['known_provider_sites'] = len(providers)
    out['routable_known_provider_sites'] = len(seeds)
    if len(seeds):
        distances, selected = weighted_multisource(
            reverse_graph, seeds.road_node_index.astype('int64').to_numpy(),
            seeds.snap_km.to_numpy(dtype=float)*4)
        valid = out.road_endpoint_accepted.eq(True)
        indices = out.loc[valid, 'road_node_index'].astype('int64').to_numpy()
        labels = selected[indices]
        reachable = labels >= 0
        positions = np.flatnonzero(valid.to_numpy())[reachable]
        chosen = seeds.iloc[labels[reachable]].reset_index(drop=True)
        oc = out.iloc[positions].snap_km.to_numpy(dtype=float)*4
        dc = chosen.snap_km.to_numpy(dtype=float)*4
        out.loc[valid, 'route_status'] = 'no_directed_route_to_known_eligible_provider_site'
        out.loc[positions, 'selected_provider_id'] = chosen.provider_id.to_numpy()
        out.loc[positions, 'cost_minutes'] = distances[indices[reachable]]+oc
        out.loc[positions, 'network_minutes'] = np.maximum(0, distances[indices[reachable]]-dc)
        out.loc[positions, 'connector_minutes'] = oc+dc
        out.loc[positions, 'provider_snap_km'] = chosen.snap_km.to_numpy()
        out.loc[positions, 'route_status'] = 'nearest_known_eligible_provider_site'
        out.loc[positions, 'tie_status'] = 'other_equal_geographic_paths_not_exhaustively_checked'
        minimum = seeds.groupby('road_node_index').snap_km.transform('min').to_numpy()
        tied = seeds.loc[np.isclose(seeds.snap_km.to_numpy(), minimum, rtol=0, atol=2.5e-10)]
        counts = tied.groupby('road_node_index').size()
        lower_bound = chosen.road_node_index.map(counts).fillna(1).astype(int).to_numpy()
        out.loc[positions, 'nearest_tie_count_lower_bound'] = lower_bound
        out.loc[positions[lower_bound>1], 'tie_status'] = 'known_shared_road_seed_tie_other_geographic_paths_not_exhaustively_checked'
        del distances, selected
    else:
        out['route_status'] = 'no_routable_known_eligible_provider_site' if len(providers) else 'no_known_eligible_provider_site'
    # Keep the real site search visible, even when an explicit within-NP rule
    # subsequently replaces its chosen site and cost.
    out['unconstrained_nearest_site_provider_id'] = out.selected_provider_id
    out['unconstrained_nearest_site_cost_minutes'] = out.cost_minutes
    strict_local = providers.loc[providers.source_record_id.isin(out.source_record_id)].copy()
    strict_local = strict_local.sort_values('provider_id').drop_duplicates('source_record_id')
    own_provider = out.source_record_id.map(strict_local.set_index('source_record_id').provider_id)
    local = own_provider.notna()
    out['known_local_supply'] = local
    out['local_supply_status'] = np.where(local, 'observed_present_strict_np_identity', 'unknown')
    out['zero_cost_np_assumption'] = local
    out.loc[local, 'selected_provider_id'] = own_provider.loc[local]
    out.loc[local, ['cost_minutes','network_minutes','connector_minutes']] = 0.
    out.loc[local, 'route_status'] = 'local_known_eligible_site_strict_np_zero_assumption'
    out.loc[local, 'tie_status'] = 'local_priority_np_scale_assumption_not_institution_choice'
    out.loc[local, 'nearest_tie_count_lower_bound'] = 1
    pindex = providers.set_index('provider_id')
    mapping = {'source_record_id':'selected_provider_source_record_id',
               'site_lat':'selected_provider_site_lat','site_lon':'selected_provider_site_lon',
               'snap_km':'provider_snap_km'}
    for col in ['proxy_reference_source_record_id','nearest_reference_source_record_id',
                'source_id','source_year','observation_year','np_identity_basis','supply_status']:
        if col in providers:
            mapping[col] = 'selected_provider_'+col
    for source, target in mapping.items():
        out[target] = out.selected_provider_id.map(pindex[source])
    out['provider_id'] = out.selected_provider_id
    out['primary_candidate_id'] = out.selected_provider_id
    out['primary_cost_minutes'] = out.cost_minutes
    out['candidate_unit_kind'] = 'institution_site_not_settlement'
    out['missing_local_supply_could_change_choice'] = ~local
    out['outside_or_unrecorded_providers_could_change_choice'] = ~local
    out['provider_inventory_completeness'] = 'not_established'
    out['observed_flow'] = False
    out['assignment_established'] = False
    out['geographic_ties_exhaustively_checked'] = False
    out['second_nearest_available'] = False
    out['road_snapshot_utc'] = SNAPSHOT
    out['routing_limit_minutes'] = np.nan
    return out


def safe_name(code):
    value = re.sub('[^a-zA-Z0-9_.-]+', '_', str(code))
    if not value or value in {'.','..'}:
        raise ValueError('Unsafe service code')
    return value


def peak_rss_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(value / (1024*1024 if sys.platform == 'darwin' else 1024), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--settlements', type=Path)
    ap.add_argument('--legacy-nodes', type=Path)
    ap.add_argument('--road-origins', type=Path)
    ap.add_argument('--endpoints', type=Path, help='Reuse already prepared national endpoint table')
    ap.add_argument('--fresh-np-resnaps', type=Path, help='Explicit geometry-only repairs of previously unaccepted current census points')
    ap.add_argument('--graph-dir', type=Path)
    ap.add_argument('--supply', type=Path, nargs='*', default=[])
    ap.add_argument('--site-seeds', type=Path, nargs='*', default=[],
                    help='Actual institution points with graph seeds; source_record_id only for strict NP identity')
    ap.add_argument('--services', help='Optional comma-separated subset')
    ap.add_argument('--accepted-statuses', default='observed', help='Explicit eligible supply statuses; no unknowns or absences')
    ap.add_argument('--prepare-only', action='store_true')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.endpoints:
        endpoints = pd.read_parquet(args.endpoints)
        provenance = {'prepared_endpoints_sha256': sha256(args.endpoints)}
    else:
        if not all([args.settlements, args.legacy_nodes, args.road_origins]):
            ap.error('Provide --endpoints or all three raw endpoint inputs')
        endpoints = prepare_endpoints(read(args.settlements), read(args.legacy_nodes), read(args.road_origins))
        provenance = {key: sha256(getattr(args,key)) for key in ['settlements','legacy_nodes','road_origins']}
    if args.fresh_np_resnaps:
        endpoints = apply_fresh_resnaps(endpoints, read(args.fresh_np_resnaps))
        provenance['fresh_np_resnaps'] = sha256(args.fresh_np_resnaps)
    endpoints.to_parquet(args.output/'endpoints.parquet', index=False, compression='zstd')
    coverage = endpoints.groupby(['region','road_endpoint_status'], dropna=False).size().rename('settlements').reset_index()
    coverage.to_csv(args.output/'endpoint_coverage.csv', index=False)
    endpoint_summary = {
        'origins': len(endpoints), 'accepted_road_endpoints': int(endpoints.road_endpoint_accepted.sum()),
        'road_endpoint_status_counts': endpoints.road_endpoint_status.value_counts().astype(int).to_dict(),
        'input_sha256': provenance,
    }
    (args.output/'endpoint_summary.json').write_text(json.dumps(endpoint_summary, ensure_ascii=False, indent=2)+'\n')
    if not args.endpoints:
        (args.output/'endpoint_preparation.json').write_text(json.dumps(endpoint_summary, ensure_ascii=False, indent=2)+'\n')
    if args.prepare_only:
        print(json.dumps(endpoint_summary, ensure_ascii=False, indent=2))
        return
    if not args.graph_dir or not (args.supply or args.site_seeds):
        ap.error('Routing requires --graph-dir and --supply or --site-seeds')
    if args.supply and args.site_seeds:
        ap.error('Run NP supply and individual site seeds separately to preserve comparison')
    statuses = tuple(x.strip() for x in args.accepted_statuses.split(',') if x.strip())
    if not statuses or set(statuses)-{'observed','proxy'}:
        ap.error('Only explicitly observed/proxy positive supply statuses are permitted')
    input_paths = args.site_seeds or args.supply
    supply_hashes = {str(path): sha256(path) for path in input_paths}
    supply = pd.concat([read(path) for path in input_paths], ignore_index=True)
    if supply_hashes != {str(path): sha256(path) for path in input_paths}:
        raise ValueError('Supply inputs changed during loading; use immutable snapshots')
    services = args.services.split(',') if args.services else sorted(supply.service_code.dropna().unique())
    graph = load_graph(args.graph_dir)
    reverse = graph.transpose().tocsr()
    del graph
    class_summaries = []
    outdir = args.output/'nearest'
    outdir.mkdir(exist_ok=True)
    for service in services:
        tick = time.monotonic()
        if args.site_seeds:
            providers = site_providers(supply, service, statuses)
            outside = providers.loc[providers.source_record_id.notna()
                                    & ~providers.source_record_id.isin(endpoints.source_record_id)].copy()
            suffix = '_provider_sites.parquet'
        else:
            providers, outside = provider_settlements(supply, endpoints, service, statuses)
            suffix = '_provider_settlements.parquet'
        providers.to_parquet(args.output/(safe_name(service)+suffix), index=False, compression='zstd')
        if len(outside):
            outside.to_parquet(args.output/(safe_name(service)+'_outside_spatial_frame.parquet'), index=False, compression='zstd')
        result = (nearest_for_sites(endpoints, providers, reverse, service) if args.site_seeds
                  else nearest_for_service(endpoints, providers, reverse, service))
        path = outdir/(safe_name(service)+'.parquet')
        temporary = path.with_suffix('.parquet.partial')
        result.to_parquet(temporary, index=False, compression='zstd')
        temporary.replace(path)
        known = result.provider_id.notna()
        external = known & ~result.zero_cost_np_assumption
        stats = {
            'service_code': service, 'origins': len(result),
            'provider_unit': 'actual_institution_site' if args.site_seeds else 'settlement_function',
            'provider_settlements': int(providers.source_record_id.nunique()),
            'routable_provider_settlements': int(providers.loc[providers.road_endpoint_accepted.eq(True), 'source_record_id'].nunique()),
            'provider_sites_or_settlement_functions': len(providers),
            'routable_provider_sites_or_settlement_functions': int(providers.road_endpoint_accepted.sum()),
            'positive_supply_rows_outside_ordinary_spatial_frame': len(outside),
            'known_local': int(result.known_local_supply.sum()), 'external_candidate': int(external.sum()),
            'unresolved': int((~known).sum()),
            'external_cost_minutes': {str(k): float(v) for k,v in result.loc[external,'cost_minutes'].quantile([.5,.9,.99,1.]).items()},
            'route_status_counts': result.route_status.value_counts().astype(int).to_dict(),
            'elapsed_seconds': round(time.monotonic()-tick, 3), 'path': str(path.relative_to(args.output)),
            'source_supply_sha256': supply_hashes,
            'accepted_supply_statuses': list(statuses),
            'peak_process_rss_mib': peak_rss_mib(),
        }
        class_summaries.append(stats)
        (outdir/(safe_name(service)+'.summary.json')).write_text(json.dumps(stats, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(stats, ensure_ascii=False), flush=True)
        del result, providers, outside
    stored_classes = [json.loads(p.read_text()) for p in sorted(outdir.glob('*.summary.json'))]
    all_supply_hashes = {}
    for row in stored_classes:
        for path, digest in row['source_supply_sha256'].items():
            if path in all_supply_hashes and all_supply_hashes[path] != digest:
                raise ValueError('Stored classes refer to different versions of the same supply path; rerun affected classes')
            all_supply_hashes[path] = digest
    summary = {
        'graph_sha256': GRAPH_SHA256, 'road_snapshot_utc': SNAPSHOT,
        'endpoint_summary': endpoint_summary, 'supply_sha256': all_supply_hashes,
        'supply_sha256_current_run': supply_hashes,
        'provider_unit': 'actual_institution_site' if args.site_seeds else 'settlement_function',
        'accepted_supply_statuses': list(statuses), 'routing_limit_minutes': None,
        'method': 'one_exact_weighted_virtual_seed_min_only_dijkstra_per_service_on_reversed_directed_graph',
        'population_or_institution_count_used_as_route_weight': False,
        'second_nearest_computed': False, 'geographic_ties_exhaustively_checked': False,
        'classes': stored_classes,
        'current_run_classes': [row['service_code'] for row in class_summaries],
        'elapsed_seconds_current_run': round(time.monotonic()-started,3),
        'peak_process_rss_mib_current_run': peak_rss_mib(),
    }
    if supply_hashes != {str(path): sha256(path) for path in input_paths}:
        raise ValueError('Supply inputs changed during routing; output metadata must not be published')
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
