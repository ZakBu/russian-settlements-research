#!/usr/bin/env python3
"""Settlement-sampled, directed road potential; no inferred service districts.

The route search runs on the complete published road graph. Small geographic
windows select evaluation locations only: every credited national settlement
with a known population and accepted road endpoint remains a possible source.
Finite search truncation and unavailable source geometry are reported, not
silently converted into an observed absence of interaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def kernel(cost, half_time: float, family: str = 'exponential'):
    """Both families equal 1/2 at half_time; NaN remains unknown."""
    if not np.isfinite(half_time) or half_time <= 0:
        raise ValueError('half_time must be finite and positive')
    c = np.asarray(cost, dtype=float)
    if np.any(c < 0):
        raise ValueError('Negative travel cost')
    if family == 'exponential':
        return np.exp2(-c / half_time)
    if family == 'gaussian':
        return np.exp2(-(c / half_time) ** 2)
    raise ValueError('Unknown kernel family')


def field_from_costs(cost, populations, half_time, family='exponential', *,
                     own_source_indices=None, include_self=True):
    """Return known contribution, count and mass with unknown travel cost.

    NaN denotes uncomputed/unavailable cost, +inf a confirmed infinite cost of
    this particular graph model. Keeping these cases distinct is essential.
    Unknown population is not accepted as a source weight; the inventory must
    report it separately instead of converting it to a population of zero.
    """
    c = np.asarray(cost, dtype=float)
    p = np.asarray(populations, dtype=float)
    if c.ndim != 2 or p.ndim != 1 or c.shape[1] != len(p):
        raise ValueError('cost must be origins by sources')
    if np.any(~np.isfinite(p)) or np.any(p < 0):
        raise ValueError('Source populations must be known, finite, nonnegative')
    k = kernel(c, half_time, family)
    unknown = np.isnan(c)
    known = np.where(unknown, 0., k) * p
    if not include_self:
        if own_source_indices is None or len(own_source_indices) != len(c):
            raise ValueError('Explicit source identity indices required for self exclusion')
        for i, j in enumerate(own_source_indices):
            if j >= 0:
                if j >= len(p):
                    raise ValueError('Own source index outside population array')
                known[i, j] = 0.
                unknown[i, j] = False
    return (known.sum(axis=1), unknown.sum(axis=1), unknown @ p)


def neighbor_edges(cost, ids, k=3):
    """Union of directed k-nearest finite neighbors, as an undirected relation.

    Travel costs are NEVER symmetrized in the potential itself. Symmetrization
    here is an explicit choice of the comparison relation used to detect peaks.
    All neighbors tied at the kth cost are retained; row order cannot select a
    different geographic relation. Infinite/unknown routes do not create edges.
    """
    c = np.asarray(cost, dtype=float)
    ids = np.asarray(ids, dtype=str)
    if c.shape != (len(ids), len(ids)) or len(set(ids)) != len(ids):
        raise ValueError('Unique identities and square comparison cost required')
    if k < 1 or int(k) != k:
        raise ValueError('k must be a positive integer')
    edges = set()
    incomplete = np.zeros(len(ids), dtype=bool)
    kth = np.full(len(ids), np.nan)
    for i, row in enumerate(c):
        good = np.isfinite(row) & (np.arange(len(row)) != i)
        available = np.flatnonzero(good)
        incomplete[i] = len(available) < k
        if not len(available):
            continue
        threshold = np.sort(row[available])[min(k, len(available)) - 1]
        kth[i] = threshold
        for j in available[row[available] <= threshold + 1e-10]:
            edges.add(tuple(sorted((int(i), int(j)))))
    return sorted(edges), incomplete, kth


def plateau_peaks(values, edges, ids, *, atol=1e-9, rtol=1e-12):
    """Connected equal-value plateaus; a peak has no strictly higher neighbor.

    Isolated sampled points are flagged as untestable rather than maxima.
    Plateau identifiers use stable source identities, never input row order.
    """
    v = np.asarray(values, dtype=float)
    ids = np.asarray(ids, dtype=str)
    if v.ndim != 1 or len(v) != len(ids) or len(set(ids)) != len(ids):
        raise ValueError('One finite value per unique sampled source identity required')
    if np.any(~np.isfinite(v)):
        raise ValueError('Nonfinite field cannot establish a peak')
    parents = np.arange(len(v))
    adjacent = [set() for _ in v]
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for a, b in edges:
        if a == b or a < 0 or b < 0 or a >= len(v) or b >= len(v):
            raise ValueError('Invalid neighbor edge')
        adjacent[a].add(b)
        adjacent[b].add(a)
        if np.isclose(v[a], v[b], atol=atol, rtol=rtol):
            parents[find(a)] = find(b)
    components = {}
    for i in range(len(v)):
        components.setdefault(find(i), []).append(i)
    records = []
    for indices in components.values():
        members = set(indices)
        outside = set().union(*(adjacent[i] for i in indices)) - members
        # All compared edges of the plateau must not rise. A chain of tolerance
        # equalities cannot override a strictly higher boundary neighbor.
        rises = any(v[j] > v[i] and not np.isclose(v[j], v[i], atol=atol, rtol=rtol)
                    for i in indices for j in adjacent[i] if j not in members)
        isolated = not outside and not any(adjacent[i] for i in indices)
        identifier = min(ids[indices])
        span_exceeds_tolerance = not np.isclose(v[indices].min(), v[indices].max(), atol=atol, rtol=rtol)
        for i in indices:
            records.append({'source_record_id': ids[i], 'plateau_id': identifier,
                            'plateau_size': len(indices),
                            'tolerance_chain_span_exceeds_tolerance': span_exceeds_tolerance,
                            'is_sampled_local_maximum': not rises and not isolated,
                            'comparison_isolated': isolated,
                            'comparison_neighbors': len(adjacent[i])})
    return pd.DataFrame(records).sort_values('source_record_id').reset_index(drop=True)


def prepare_sources(reference, endpoints):
    """Preserve credit status; federal-city contexts cannot duplicate mass."""
    required = {'source_record_id', 'population_2021', 'credit_2021',
                'budget_population_credit', 'ordinary_spatial_2021'}
    if not required.issubset(reference):
        raise ValueError(f'Missing source fields: {required-set(reference)}')
    if reference.source_record_id.dropna().duplicated().any():
        raise ValueError('Current source identity is nonunique')
    if endpoints.source_record_id.duplicated().any():
        raise ValueError('Road endpoint identity is nonunique')
    out = reference.copy()
    keep = ['source_record_id', 'road_endpoint_accepted', 'road_node_index', 'snap_km']
    # Rows without a 2021 source identity occur many times in the immutable
    # historical reference. They remain inventory rows, never mass sources.
    out = out.merge(endpoints[keep], on='source_record_id', how='left', validate='many_to_one')
    p = pd.to_numeric(out.population_2021, errors='coerce')
    out['population_known_credited'] = (out.credit_2021.eq(True)
                                      & out.budget_population_credit.eq(True)
                                      & p.ge(0) & np.isfinite(p))
    out['source_mass_2021'] = p.where(out.population_known_credited)
    out['positive_source_mass'] = out.population_known_credited & p.gt(0)
    out['accepted_source_endpoint'] = (out.road_endpoint_accepted.eq(True)
                                       & np.isfinite(out.road_node_index)
                                       & out.snap_km.between(0, 10))
    out['is_routed_mass_source'] = out.positive_source_mass & out.accepted_source_endpoint
    return out


def audit_national_neighbors(reference_path, endpoints_path, evaluation_inventory_path,
                             graph_dir, output, *, cutoff_minutes=240., neighbor_counts=(3,6)):
    """Check whether the sampled windows contain the actual national kNN.

    Unlike the demographic source set, this comparison includes known-zero and
    uncredited settlements with accepted endpoints: population does not control
    which settlement locations are eligible to be comparison neighbors.
    """
    from scipy.sparse.csgraph import dijkstra
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sgrt_local.roads import load_graph
    sources = prepare_sources(pd.read_parquet(reference_path), pd.read_parquet(endpoints_path))
    national = sources.loc[sources.ordinary_spatial_2021.eq(True) & sources.accepted_source_endpoint].copy()
    evaluation = pd.read_parquet(evaluation_inventory_path)
    evaluation = evaluation.loc[evaluation.evaluated].copy()
    node = national.road_node_index.astype('int64').to_numpy()
    ids = national.source_record_id.astype(str).to_numpy()
    connectors = 4. * national.snap_km.to_numpy(dtype=float)
    frames = {p:set(g.source_record_id.astype(str)) for p,g in evaluation.groupby('pilot_id')}
    graph = load_graph(graph_dir)
    records = []
    for i,row in enumerate(evaluation.itertuples(index=False)):
        distance = dijkstra(graph, directed=True, indices=int(row.road_node_index), limit=cutoff_minutes)
        cost = distance[node] + connectors + 4. * row.snap_km
        usable = np.isfinite(cost) & (cost <= cutoff_minutes) & (ids != row.source_record_id)
        values = cost[usable]
        identities = ids[usable]
        for k in neighbor_counts:
            enough = len(values) >= k
            threshold = float(np.partition(values, min(k,len(values))-1)[min(k,len(values))-1]) if len(values) else np.nan
            selected = identities[values <= threshold + 1e-10] if len(values) else []
            external = sorted(str(s) for s in selected if s not in frames[row.pilot_id])
            records.append({'source_record_id': row.source_record_id, 'pilot_id': row.pilot_id,
                            'evaluation_core': bool(row.evaluation_core), 'neighbor_count': k,
                            'enough_national_neighbors_reached': enough,
                            'national_kth_neighbor_cost_minutes': threshold,
                            'national_neighbor_count_including_ties': len(selected),
                            'national_neighbor_count_outside_sampled_window': len(external),
                            'national_neighbors_all_within_sampled_window': enough and not external,
                            'external_neighbor_ids_json': json.dumps(external)})
        if i % 100 == 0:
            print(json.dumps({'neighbor_coverage_processed': i+1, 'of':len(evaluation)}), flush=True)
    result = pd.DataFrame(records)
    result.to_parquet(output, index=False, compression='zstd')
    return result


def summarize_sampling(output, input_summary_path):
    """Derive core, edge-coverage and finite published-reference diagnostics.

    This changes no computed field value or peak classification. The excluded
    published-value envelope is deliberately allowed to double-count, and is
    not a population estimate or a bound on unrecorded reality.
    """
    output = Path(output)
    summary = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    inputs = json.loads(Path(input_summary_path).read_text(encoding='utf-8'))
    accounting = inputs['population_accounting']
    summary['population_accounting'] = accounting
    summary['input_summary_sha256'] = digest(input_summary_path)
    summary['evaluation_scope'] = 'Settlement records including zero-population and uncredited records; not a count of inhabited settlements'
    summary['limitations'] = [s.replace('Unmapped known mass and unknown population',
                                       'Unmapped known mass, uncredited published records and omitted geography')
                              for s in summary['limitations']]
    evaluation = pd.read_parquet(output/'evaluation_inventory.parquet')
    coverage = pd.read_parquet(output/'national_neighbor_coverage.parquet')
    # kNN is directed. The peak relation uses its within-window undirected
    # union; checking national outgoing neighbors cannot rule out incoming
    # union edges from unevaluated exterior points.
    coverage['national_neighbor_check_scope'] = 'outgoing_k_nearest_only_external_incoming_union_edges_not_checked'
    coverage['external_incoming_comparison_edges_checked'] = False
    coverage.to_parquet(output/'national_neighbor_coverage.parquet', index=False, compression='zstd')
    fields = pd.read_parquet(output/'fields.parquet')
    peaks = pd.read_parquet(output/'peaks.parquet')
    key = ['source_record_id','pilot_id']
    identity = evaluation[[*key, 'name','lat','lon','population_2021','evaluation_core']]
    peaks = peaks.merge(identity, on=key, how='left', validate='many_to_one')
    peaks = peaks.merge(coverage[[*key, 'neighbor_count','national_neighbors_all_within_sampled_window',
                                'national_neighbor_count_outside_sampled_window']],
                        on=[*key,'neighbor_count'], how='left', validate='many_to_one')
    scenario = ['pilot_id','kernel','half_time_minutes','include_self','neighbor_count']
    core_counts = []
    for keys,g in peaks.loc[peaks.evaluation_core].groupby(scenario):
        safe = g.national_neighbors_all_within_sampled_window
        peak = g.is_sampled_local_maximum
        core_counts.append({**dict(zip(scenario, keys)),
                            'core_evaluation_records':len(g),
                            'core_records_national_neighbors_covered':int(safe.sum()),
                            'core_sampled_peak_points':int(peak.sum()),
                            'core_sampled_peak_points_with_national_neighbors_covered':int((safe & peak).sum()),
                            'core_sampled_peak_points_robust_known_mass_bounds':int((peak & g.peak_robust_to_known_mass_tail_and_unmapped).sum())})
    core_counts = pd.DataFrame(core_counts)
    core_counts.to_csv(output/'core_peak_counts.csv', index=False)
    named = peaks.loc[peaks.is_sampled_local_maximum].merge(fields[[*key,'kernel','half_time_minutes','include_self',
                                                                  'known_routed_potential','known_mass_potential_upper']],
                                                          on=[*key,'kernel','half_time_minutes','include_self'],
                                                          how='left', validate='many_to_one')
    named.to_csv(output/'named_sampled_peaks.csv', index=False)
    transitions = []
    restricted = peaks.loc[peaks.evaluation_core & peaks.national_neighbors_all_within_sampled_window]
    for keys,g in restricted.groupby(['pilot_id','kernel','include_self','neighbor_count']):
        previous = None
        for h,group in g.groupby('half_time_minutes', sort=True):
            current = set(group.loc[group.is_sampled_local_maximum, 'source_record_id'])
            if previous is not None:
                transitions.append({'pilot_id':str(keys[0]),'kernel':str(keys[1]),'include_self':bool(keys[2]),'neighbor_count':int(keys[3]),
                                    'from_half_time_minutes':float(prev_h), 'to_half_time_minutes':float(h),
                                    'new_core_peak_source_ids_json':json.dumps(sorted(current-previous)),
                                    'lost_core_peak_source_ids_json':json.dumps(sorted(previous-current)),
                                    'new_core_peak_points':len(current-previous), 'lost_core_peak_points':len(previous-current)})
            previous,prev_h = current,h
    pd.DataFrame(transitions).to_parquet(output/'core_peak_transitions.parquet', index=False, compression='zstd')
    envelope = accounting['conservative_excluded_published_raw_sum_upper_bound_may_double_count']
    bounds = fields[[*key,'kernel','half_time_minutes','include_self','known_routed_potential',
                     'known_mass_potential_upper', *[c for c in ['omitted_published_routed_potential_upper',
                        'omitted_published_censored_potential_upper','omitted_published_unmapped_potential_upper',
                        'published_reference_potential_upper'] if c in fields]]].copy()
    bounds['excluded_published_reference_potential_upper'] = envelope
    bounds['published_reference_envelope_upper'] = bounds.known_mass_potential_upper + envelope
    bounds['envelope_may_double_count_not_population_estimate'] = True
    bounds.to_parquet(output/'published_reference_envelope.parquet', index=False, compression='zstd')
    summary['published_reference_envelope'] = {
        'excluded_published_values_upper': envelope,
        'scope': accounting['excluded_mass_bound_scope'],
        'finite_within_published_reference_not_a_complete_true_national_population_bound':True,
        'output':'published_reference_envelope.parquet'}
    if 'published_reference_potential_upper' in fields:
        summary['published_reference_envelope']['tighter_bound'] = 'Existing published omitted values use accepted road endpoints and actual costs when reached; cutoff bound when not reached; raw-value bound only without accepted endpoint. They remain outside base mass.'
        if summary.get('omitted_published_raw_population_sum_not_added') != envelope:
            raise ValueError('Published omitted source ledger differs from source inventory envelope')
    summary['core_peak_counts'] = core_counts.to_dict('records')
    summary['core_transitions_with_national_neighbors_covered'] = transitions
    summary['national_neighbor_window_coverage'] = coverage.groupby(['pilot_id','evaluation_core','neighbor_count']).agg(
        records=('source_record_id','size'),
        national_neighbors_within_window=('national_neighbors_all_within_sampled_window','sum')).reset_index().to_dict('records')
    summary['national_neighbor_check_scope'] = 'National outgoing k-nearest points only. Exterior incoming edges of the symmetrized comparison union were not checked; covered outgoing neighbors do not certify a complete national union neighborhood.'
    summary['tail_upper_by_kernel_half_time'] = fields.groupby(['kernel','half_time_minutes']).agg(
        max_censored_mass_potential_upper=('censored_routed_mass_potential_upper','max'),
        min_censored_mass_potential_upper=('censored_routed_mass_potential_upper','min')).reset_index().to_dict('records')
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return summary


def run(reference_path, endpoints_path, evaluation_path, graph_dir, output, *,
        half_times=(10., 20., 40., 80.), neighbor_counts=(3, 6), cutoff_minutes=240.):
    from scipy.sparse.csgraph import dijkstra
    import pyarrow as pa
    import pyarrow.parquet as pq
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sgrt_local.roads import load_graph, GRAPH_SHA256
    if not np.isfinite(cutoff_minutes) or cutoff_minutes <= 0:
        raise ValueError('Positive finite search limit required')
    if not half_times or any(not np.isfinite(h) or h <= 0 for h in half_times):
        raise ValueError('Positive finite half-times required')
    if not neighbor_counts or any(int(k) != k or k < 1 for k in neighbor_counts):
        raise ValueError('Positive integer neighbor counts required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reference = pd.read_parquet(reference_path)
    endpoints = pd.read_parquet(endpoints_path)
    evaluation = (pd.read_parquet(evaluation_path) if str(evaluation_path).endswith('.parquet')
                  else pd.read_csv(evaluation_path))
    if 'pilot_id' not in evaluation and 'pilot' in evaluation:
        evaluation = evaluation.rename(columns={'pilot': 'pilot_id'})
    if evaluation.source_record_id.duplicated().any():
        # The same physical sampled NP can be in two pilot frames; compute once
        # only if that is represented by a separate frame mapping instead.
        raise ValueError('Evaluation identities must be unique across pilot frames')
    if 'pilot_id' not in evaluation:
        raise ValueError('Evaluation rows require pilot_id')
    sources = prepare_sources(reference, endpoints)
    eval_ids = evaluation.source_record_id.astype(str)
    if not set(eval_ids).issubset(set(sources.source_record_id.dropna().astype(str))):
        raise ValueError('Evaluation identity absent from reference')
    indexed = sources.set_index('source_record_id')
    sampled = indexed.loc[eval_ids].reset_index()
    sampled = sampled.merge(evaluation, on='source_record_id', how='left', validate='one_to_one', suffixes=('', '_evaluation'))
    sampled['evaluated'] = sampled.accepted_source_endpoint
    sampled.to_parquet(output/'evaluation_inventory.parquet', index=False, compression='zstd')
    eval_frame = sampled.loc[sampled.evaluated].reset_index(drop=True)
    positive = sources.loc[sources.is_routed_mass_source].reset_index(drop=True)
    positive[[c for c in ['source_record_id','name','region','lat','lon','source_mass_2021',
                          'road_node_index','snap_km'] if c in positive]].to_parquet(output/'national_mass_sources.parquet', index=False, compression='zstd')
    source_nodes = positive.road_node_index.astype('int64').to_numpy()
    source_connectors = 4. * positive.snap_km.to_numpy(dtype=float)
    source_weights = positive.source_mass_2021.to_numpy(dtype=float)
    if np.any(source_weights != np.floor(source_weights)):
        raise ValueError('Census population sources must be integer counts')
    source_ids = positive.source_record_id.astype(str).to_numpy()
    source_index = {s: j for j, s in enumerate(source_ids)}
    unmapped_known_mass = float(sources.loc[sources.positive_source_mass & ~sources.accepted_source_endpoint, 'source_mass_2021'].sum())
    raw_population = pd.to_numeric(sources.population_2021, errors='coerce')
    # These values remain OUTSIDE the base mass. They support only an upper
    # sensitivity envelope over existing published reference rows, with possible
    # overlap/double count deliberately retained.
    omitted = sources.loc[sources.source_record_id.notna() & ~sources.population_known_credited
                          & raw_population.gt(0) & np.isfinite(raw_population)].copy()
    omitted['published_raw_population_2021'] = raw_population.loc[omitted.index]
    omitted = omitted.reset_index(drop=True)
    omitted[[c for c in ['source_record_id','name','region','population_2021','population_role',
                         'ordinary_spatial_2021','road_node_index','snap_km','accepted_source_endpoint',
                         'published_raw_population_2021'] if c in omitted]].to_parquet(
        output/'omitted_published_sources.parquet', index=False, compression='zstd')
    omitted_routable = omitted.loc[omitted.accepted_source_endpoint].reset_index(drop=True)
    omitted_nodes = omitted_routable.road_node_index.astype('int64').to_numpy()
    omitted_connectors = 4. * omitted_routable.snap_km.to_numpy(dtype=float)
    omitted_weights = omitted_routable.published_raw_population_2021.to_numpy(dtype=float)
    if np.any(omitted_weights != np.floor(omitted_weights)):
        raise ValueError('Published reference population counts must be integers')
    omitted_ids = omitted_routable.source_record_id.astype(str).to_numpy()
    omitted_index = {s:j for j,s in enumerate(omitted_ids)}
    omitted_unmapped = float(omitted.loc[~omitted.accepted_source_endpoint, 'published_raw_population_2021'].sum())
    eval_nodes = eval_frame.road_node_index.astype('int64').to_numpy()
    graph = load_graph(graph_dir)
    if source_nodes.max(initial=0) >= graph.shape[0] or eval_nodes.max(initial=0) >= graph.shape[0]:
        raise ValueError('Endpoint outside published graph')
    print(json.dumps({'graph_shape': graph.shape, 'graph_arcs': graph.nnz,
                      'evaluations': len(eval_frame), 'national_positive_routable_sources': len(positive)}, ensure_ascii=False), flush=True)
    eval_costs = np.full((len(eval_frame), len(eval_frame)), np.nan)
    rows, route_meta = [], []
    writer, omitted_writer = None, None
    started = time.monotonic()
    try:
        for i, row in enumerate(eval_frame.itertuples(index=False)):
            # This is the ORIGINAL full directed graph, never an induced window.
            distances = dijkstra(graph, directed=True, indices=int(row.road_node_index), limit=cutoff_minutes)
            net = distances[source_nodes]
            conn = source_connectors + 4. * row.snap_km
            costs = net + conn
            own = source_index.get(str(row.source_record_id), -1)
            if own >= 0:
                costs[own], net[own], conn[own] = 0., 0., 0.
            routed = np.isfinite(costs) & (costs <= cutoff_minutes)
            known_mass = float(source_weights[routed].sum())
            not_within = float(source_weights[~routed].sum())
            route_frame = pd.DataFrame({'origin_id': str(row.source_record_id),
                                        'source_id': source_ids[routed],
                                        'cost_minutes': costs[routed],
                                        'source_population_2021': source_weights[routed].astype('int64')})
            if writer is None:
                writer = pq.ParquetWriter(output/'routed_contributions.parquet', pa.Table.from_pandas(route_frame, preserve_index=False).schema, compression='zstd')
            writer.write_table(pa.Table.from_pandas(route_frame, preserve_index=False))
            omitted_costs = distances[omitted_nodes] + omitted_connectors + 4. * row.snap_km
            own_omitted = omitted_index.get(str(row.source_record_id), -1)
            if own_omitted >= 0:
                omitted_costs[own_omitted] = 0.
            omitted_reached = np.isfinite(omitted_costs) & (omitted_costs <= cutoff_minutes)
            omitted_route_frame = pd.DataFrame({'origin_id':str(row.source_record_id),
                                                'source_id':omitted_ids[omitted_reached],
                                                'cost_minutes':omitted_costs[omitted_reached],
                                                'published_raw_population_2021':omitted_weights[omitted_reached].astype('int64')})
            if omitted_writer is None:
                omitted_writer = pq.ParquetWriter(output/'omitted_routed_contributions.parquet',
                                                   pa.Table.from_pandas(omitted_route_frame, preserve_index=False).schema,
                                                   compression='zstd')
            omitted_writer.write_table(pa.Table.from_pandas(omitted_route_frame, preserve_index=False))
            compare = distances[eval_nodes] + 4. * (row.snap_km + eval_frame.snap_km.to_numpy(dtype=float))
            compare[i] = 0.
            compare[(~np.isfinite(compare)) | (compare > cutoff_minutes)] = np.nan
            eval_costs[i] = compare
            own_population = source_weights[own] if own >= 0 else 0.
            for family in ('exponential', 'gaussian'):
                for half_time in half_times:
                    value = float(np.dot(source_weights[routed], kernel(costs[routed], half_time, family)))
                    tail = not_within * float(kernel(cutoff_minutes, half_time, family))
                    omitted_routed = float(np.dot(omitted_weights[omitted_reached], kernel(omitted_costs[omitted_reached], half_time, family)))
                    omitted_tail = float(omitted_weights[~omitted_reached].sum()) * float(kernel(cutoff_minutes, half_time, family))
                    for include_self in (True, False):
                        lower = value - (0. if include_self else own_population)
                        omitted_known = omitted_routed - (float(omitted_weights[own_omitted]) if not include_self and own_omitted >= 0 else 0.)
                        rows.append({'source_record_id': str(row.source_record_id), 'pilot_id': row.pilot_id,
                                     'kernel': family, 'half_time_minutes': half_time,
                                     'include_self': include_self,
                                     'known_routed_potential': lower,
                                     'own_known_population': float(own_population),
                                     'censored_routed_mass_potential_upper': tail,
                                     'known_mass_without_road_potential_upper': unmapped_known_mass,
                                     'known_mass_potential_upper': lower + tail + unmapped_known_mass,
                                     'omitted_published_routed_potential_upper': omitted_known,
                                     'omitted_published_censored_potential_upper': omitted_tail,
                                     'omitted_published_unmapped_potential_upper': omitted_unmapped,
                                     'published_reference_potential_upper': lower + tail + unmapped_known_mass + omitted_known + omitted_tail + omitted_unmapped,
                                     'complete_population_field_upper': np.nan,
                                     'known_within_cutoff_population': known_mass,
                                     'not_reached_within_cutoff_population': not_within,
                                     'routed_source_count': int(routed.sum())})
            route_meta.append({'source_record_id': str(row.source_record_id), 'pilot_id': row.pilot_id,
                               'routed_source_count': int(routed.sum()),
                               'known_within_cutoff_population': known_mass,
                               'not_reached_within_cutoff_population': not_within})
            if i % 20 == 0 or i == len(eval_frame)-1:
                print(json.dumps({'processed': i+1, 'of': len(eval_frame), 'elapsed_seconds': round(time.monotonic()-started, 2)}, ensure_ascii=False), flush=True)
    finally:
        if writer is not None:
            writer.close()
        if omitted_writer is not None:
            omitted_writer.close()
    values = pd.DataFrame(rows)
    values.to_parquet(output/'fields.parquet', index=False, compression='zstd')
    pd.DataFrame(route_meta).to_parquet(output/'route_accounting.parquet', index=False, compression='zstd')
    # Complete evaluation-by-evaluation table: unavailable/censored costs remain
    # NaN; they are not interchangeable with infinite confirmed disconnected.
    compare_table = pd.DataFrame({'origin_id': np.repeat(eval_frame.source_record_id.to_numpy(), len(eval_frame)),
                                  'destination_id': np.tile(eval_frame.source_record_id.to_numpy(), len(eval_frame)),
                                  'cost_minutes': eval_costs.ravel()})
    compare_table['route_status'] = np.where(compare_table.cost_minutes.notna(), 'routed_within_cutoff', 'not_reached_within_cutoff_not_proven_isolated')
    compare_table.to_parquet(output/'evaluation_costs.parquet', index=False, compression='zstd')
    peak_frames, edge_frames = [], []
    for pilot_id, group in eval_frame.groupby('pilot_id', sort=True):
        positions = group.index.to_numpy()
        local_ids = group.source_record_id.astype(str).to_numpy()
        local_costs = eval_costs[np.ix_(positions, positions)]
        for n in neighbor_counts:
            edges, incomplete, kth = neighbor_edges(local_costs, local_ids, n)
            edge_frames.extend({'pilot_id': pilot_id, 'neighbor_count': n,
                                'source_id_a': local_ids[a], 'source_id_b': local_ids[b]} for a,b in edges)
            for keys, field in values.loc[values.pilot_id.eq(pilot_id)].groupby(['kernel', 'half_time_minutes', 'include_self'], sort=True):
                v = field.set_index('source_record_id').loc[local_ids, 'known_routed_potential'].to_numpy()
                peaks = plateau_peaks(v, edges, local_ids).set_index('source_record_id').loc[local_ids].reset_index()
                peaks['pilot_id'] = pilot_id
                peaks['kernel'], peaks['half_time_minutes'], peaks['include_self'] = keys
                peaks['neighbor_count'] = n
                peaks['fewer_than_k_reached_neighbors'] = incomplete
                peaks['kth_neighbor_cost_minutes'] = kth
                peaks['is_certified_complete_field_peak'] = False
                upper = field.set_index('source_record_id').loc[local_ids, 'known_mass_potential_upper'].to_numpy()
                robust = np.ones(len(local_ids), dtype=bool)
                for a, b in edges:
                    if v[a] <= upper[b] + 1e-9:
                        robust[a] = False
                    if v[b] <= upper[a] + 1e-9:
                        robust[b] = False
                peaks['peak_robust_to_known_mass_tail_and_unmapped'] = robust & peaks.is_sampled_local_maximum.to_numpy()
                reference_upper = field.set_index('source_record_id').loc[local_ids, 'published_reference_potential_upper'].to_numpy()
                robust_reference = np.ones(len(local_ids), dtype=bool)
                for a,b in edges:
                    if v[a] <= reference_upper[b] + 1e-9:
                        robust_reference[a] = False
                    if v[b] <= reference_upper[a] + 1e-9:
                        robust_reference[b] = False
                peaks['peak_robust_to_published_reference_envelope'] = robust_reference & peaks.is_sampled_local_maximum.to_numpy()
                peak_frames.append(peaks)
    peaks = pd.concat(peak_frames, ignore_index=True)
    peaks.to_parquet(output/'peaks.parquet', index=False, compression='zstd')
    pd.DataFrame(edge_frames).to_parquet(output/'comparison_edges.parquet', index=False, compression='zstd')
    transitions = []
    for keys, g in peaks.groupby(['pilot_id', 'kernel', 'include_self', 'neighbor_count']):
        previous = None
        for scale, at_scale in g.groupby('half_time_minutes', sort=True):
            current = set(at_scale.loc[at_scale.is_sampled_local_maximum, 'source_record_id'])
            if previous is not None:
                transitions.append({'pilot_id': keys[0], 'kernel': keys[1], 'include_self': keys[2], 'neighbor_count': keys[3],
                                    'from_half_time_minutes': prev_scale, 'to_half_time_minutes': scale,
                                    'continuing_peak_points': len(previous & current),
                                    'new_peak_points': len(current-previous),
                                    'lost_peak_points': len(previous-current),
                                    'new_peak_source_ids_json': json.dumps(sorted(current-previous)),
                                    'lost_peak_source_ids_json': json.dumps(sorted(previous-current))})
            previous, prev_scale = current, scale
    pd.DataFrame(transitions).to_parquet(output/'peak_transitions.parquet', index=False, compression='zstd')
    summary = {'status': 'settlement_sampled_truncated_known_mass_pilot_not_service_systems',
               'graph_sha256': GRAPH_SHA256, 'graph_nodes': graph.shape[0], 'graph_arcs': graph.nnz,
               'road_source_timestamp_utc': '2021-01-01T21:42:03Z',
               'road_cost_model': 'directed_static_car_minutes_plus_endpoint_connectors_15kmh',
               'evaluation_rows': len(eval_frame), 'evaluation_rows_without_accepted_endpoint': int((~sampled.evaluated).sum()),
               'population_year': 2021, 'known_credited_mass': float(sources.source_mass_2021.sum()),
               'routed_mass_sources': len(positive), 'routed_mass_source_population': float(source_weights.sum()),
               'omitted_published_positive_sources':len(omitted),
               'omitted_published_raw_population_sum_not_added':float(omitted.published_raw_population_2021.sum()),
               'omitted_published_positive_sources_with_accepted_endpoint':len(omitted_routable),
               'omitted_published_population_without_accepted_endpoint':omitted_unmapped,
               'known_positive_mass_without_accepted_endpoint': float(sources.loc[sources.positive_source_mass & ~sources.accepted_source_endpoint, 'source_mass_2021'].sum()),
               'ordinary_records_without_known_credited_population': int((sources.ordinary_spatial_2021.eq(True) & ~sources.population_known_credited).sum()),
               'search_cutoff_minutes': cutoff_minutes, 'kernel_half_times_minutes': list(half_times),
               'neighborhoods': list(neighbor_counts), 'self_variants': [True, False],
               'field_rows': len(values), 'peak_rows': len(peaks),
               'reference_sha256': digest(reference_path), 'endpoints_sha256': digest(endpoints_path),
               'evaluation_sha256': digest(evaluation_path),
               'limitations': ['No observed journeys or calibrated decay parameters.',
                               'Evaluation only at existing settlement points, not a continuous raster.',
                               'Unmapped known mass, uncredited published records and omitted geography prevent certification of complete-field maxima.',
                               'k-nearest sampled comparison graph is distinct from the road graph; edge and sampling sensitivity remain.',
                               'Scale transitions do not imply an intrinsic hierarchy or monotone disappearance of maxima.']}
    counts = peaks.loc[peaks.is_sampled_local_maximum].groupby(['pilot_id', 'kernel', 'half_time_minutes', 'include_self', 'neighbor_count']).agg(peak_points=('source_record_id', 'size'), peak_plateaus=('plateau_id', 'nunique')).reset_index()
    counts.to_csv(output/'peak_counts.csv', index=False)
    summary['peak_counts'] = counts.to_dict('records')
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--endpoints', type=Path, required=True)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--graph-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--half-times', type=float, nargs='+', default=[10., 20., 40., 80.])
    parser.add_argument('--neighbor-counts', type=int, nargs='+', default=[3, 6])
    parser.add_argument('--cutoff-minutes', type=float, default=240.)
    parser.add_argument('--coverage-only', action='store_true', help='Audit national-neighbor window coverage of an already computed pilot')
    parser.add_argument('--summaries-only', action='store_true', help='Derive core/envelope summaries from already computed fields and neighbor audit')
    parser.add_argument('--input-summary', type=Path)
    args = parser.parse_args()
    input_summary_path = args.input_summary or args.evaluation.parent/'input_summary.json'
    if args.summaries_only:
        summarize_sampling(args.output, input_summary_path)
        return
    if args.coverage_only:
        result = audit_national_neighbors(args.reference, args.endpoints, args.output/'evaluation_inventory.parquet',
                                          args.graph_dir, args.output/'national_neighbor_coverage.parquet',
                                          cutoff_minutes=args.cutoff_minutes, neighbor_counts=args.neighbor_counts)
        print(result.groupby(['pilot_id','evaluation_core','neighbor_count']).national_neighbors_all_within_sampled_window.agg(['sum','count']).to_string())
        summarize_sampling(args.output, input_summary_path)
        return
    summary = run(args.reference, args.endpoints, args.evaluation, args.graph_dir, args.output,
                  half_times=args.half_times, neighbor_counts=args.neighbor_counts, cutoff_minutes=args.cutoff_minutes)
    audit_national_neighbors(args.reference, args.endpoints, args.output/'evaluation_inventory.parquet',
                             args.graph_dir, args.output/'national_neighbor_coverage.parquet',
                             cutoff_minutes=args.cutoff_minutes, neighbor_counts=args.neighbor_counts)
    summary = summarize_sampling(args.output, input_summary_path)
    print(json.dumps({k:v for k,v in summary.items() if k!='peak_counts'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
