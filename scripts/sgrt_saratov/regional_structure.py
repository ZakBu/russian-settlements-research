"""Transport-neighbour ascent basins of the *common* population potential.

These are concentration scenarios, not observed service systems. Strict uphill
steps give a DAG. Equal best slopes retain all outcomes, flat plateaus stay
ambiguous, and leaving the regional frame ends at a censored Russian halo node.
The primary full-radius comparison uses every known routable regional point
within t<=h; external incomplete neighbourhoods are censored. Earlier fixed-k
and k-restricted local comparisons remain explicit stress tests. The half-time
h is neither a fitted service radius nor a cap on a whole basin's extent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def tolerance(a, b):
    return 1e-9 + 1e-12 * max(abs(float(a)), abs(float(b)))


def scenario_name(kernel, half_time, k, topology):
    if topology == 'full_radius':
        return f'{kernel}__h{float(half_time):g}__full_radius'
    return f'{kernel}__h{float(half_time):g}__k{k}__{topology}'


def ascent_scenario(roster, field, halo_field, neighbours, *, kernel, half_time,
                    neighbour_count, topology, national_neighbour_reference=None,
                    censored_origins=None):
    """Resolve every regional sample point, without arbitrarily breaking ties."""
    if topology not in {'fixed_knn', 'scale_local', 'full_radius'}:
        raise ValueError('Unknown comparison topology')
    if not np.isfinite(half_time) or half_time <= 0:
        raise ValueError('A positive smoothing half-time is required')
    if roster.source_record_id.isna().any() or roster.source_record_id.duplicated().any():
        raise ValueError('Regional identity axis is not unique')
    regional = set(roster.source_record_id)
    if set(field.source_record_id) - regional:
        raise ValueError('Regional field contains external identities')
    if regional & set(halo_field.source_record_id):
        raise ValueError('Regional and halo axes overlap')
    all_fields = pd.concat([field, halo_field], ignore_index=True)
    if all_fields.source_record_id.duplicated().any():
        raise ValueError('Repeated field observation in one scenario')
    if 'include_self' in all_fields and not all_fields.include_self.eq(True).all():
        raise ValueError('Only the common include-self population surface is allowed')
    values = all_fields.set_index('source_record_id').value.to_dict()
    upper = all_fields.set_index('source_record_id').accepted_mass_field_upper.to_dict()
    if any(np.isfinite(v) and v < 0 for v in values.values()):
        raise ValueError('Negative common population potential')
    selected = (neighbours.copy() if topology == 'full_radius' else
                neighbours[neighbours[f'in_k{neighbour_count}'].eq(True)].copy())
    if selected.duplicated(['origin_id', 'destination_id']).any():
        raise ValueError('Repeated national comparison edge')
    if (~np.isfinite(selected.minutes) | selected.minutes.lt(0)).any():
        raise ValueError('Invalid national-neighbour time')
    adjacency = {i: g[['destination_id', 'minutes']].to_dict('records')
                 for i, g in selected.groupby('origin_id', sort=False)}
    if selected.origin_id.eq(selected.destination_id).any():
        raise ValueError('A national comparison neighbour cannot be the origin itself')
    reference = national_neighbour_reference if national_neighbour_reference is not None else neighbours
    national6 = reference[reference.in_k6.eq(True)].groupby('origin_id')
    reference6 = {}
    for origin in roster.source_record_id:
        other = national6.get_group(origin).destination_id.tolist() if origin in national6.groups else []
        value = values.get(origin, np.nan)
        testable = (np.isfinite(value) and len(other) >= 6 and
                    all(np.isfinite(values.get(j, np.nan)) for j in other))
        reference6[origin] = (bool(testable), bool(testable and all(
            values[j] <= value + tolerance(value, values[j]) for j in other)))
    sid = scenario_name(kernel, half_time, neighbour_count, topology)
    local, steps = {}, []
    censored_origins = set(censored_origins or [])
    for origin in roster.source_record_id:
        value = values.get(origin, np.nan)
        raw = adjacency.get(origin, [])
        allowed = [e for e in raw if topology == 'fixed_knn' or e['minutes'] <= half_time]
        state = {'status': None, 'edges': [], 'raw_neighbours': len(raw),
                 'eligible_neighbours': len(allowed), 'peak_robust': False}
        if not np.isfinite(value):
            state['status'] = 'unknown_field'
        elif origin in censored_origins:
            state['status'] = 'external_neighbourhood_censored'
        elif len(raw) < neighbour_count:
            state['status'] = 'comparison_incomplete'
        elif any(not np.isfinite(values.get(e['destination_id'], np.nan)) for e in allowed):
            state['status'] = 'comparison_incomplete'
        elif not allowed:
            state['status'] = ('sampled_peak_without_nonself_comparators'
                               if topology == 'full_radius' else 'no_neighbours_at_scale')
        else:
            zero = [e for e in allowed if e['minutes'] == 0]
            # A gradient per minute is undefined at coincident travel points.
            # A potentially relevant coincident point is never selected by ID.
            relevant_zero = [e for e in zero if values[e['destination_id']] >=
                            value - tolerance(value, values[e['destination_id']])]
            if relevant_zero:
                state['status'] = 'zero_cost_comparison_ambiguous'
            else:
                higher = [(e, (values[e['destination_id']] - value) / e['minutes'])
                          for e in allowed if e['minutes'] > 0 and
                          values[e['destination_id']] > value + tolerance(value, values[e['destination_id']])]
                if higher:
                    best = max(slope for _, slope in higher)
                    chosen = [(e, slope) for e, slope in higher
                              if np.isclose(slope, best, atol=1e-12, rtol=1e-10)]
                    for edge, slope in sorted(chosen, key=lambda x: x[0]['destination_id']):
                        target = edge['destination_id']
                        robust = (np.isfinite(upper.get(origin, np.nan)) and
                                  values[target] > upper[origin] + tolerance(upper[origin], values[target]))
                        state['edges'].append((target, float(edge['minutes']), bool(robust)))
                        steps.append({'scenario_id': sid, 'origin_id': origin,
                            'destination_id': target, 'minutes': float(edge['minutes']),
                            'origin_field': float(value), 'destination_field': float(values[target]),
                            'potential_gain_per_minute': float(slope),
                            'coequal_best_steps': len(chosen), 'destination_in_regional_frame': target in regional,
                            'ascent_robust_to_known_source_bounds': bool(robust),
                            'is_observed_trip': False})
                    state['status'] = 'strict_ascent'
                elif any(abs(values[e['destination_id']] - value) <=
                         tolerance(value, values[e['destination_id']]) for e in allowed):
                    state['status'] = 'plateau_ambiguous'
                else:
                    state['status'] = 'resolved_regional_peak'
                    state['peak_robust'] = all(np.isfinite(upper.get(e['destination_id'], np.nan)) and
                        value > upper[e['destination_id']] + tolerance(value, upper[e['destination_id']])
                        for e in allowed)
        local[origin] = state
    # Children always have strictly larger potential, so descending field order
    # resolves the DAG without a recursion-depth dependency.
    ordered = sorted(regional, key=lambda i: (-values[i] if np.isfinite(values.get(i, np.nan))
                                              else np.inf, i))
    resolved = {}
    for origin in ordered:
        state = local[origin]
        terminal = {}
        if state['status'] != 'strict_ascent':
            terminal[(state['status'], origin)] = (0., 0., 0., bool(state['peak_robust']), 0, 0)
        else:
            for target, minutes, robust in state['edges']:
                if target in regional:
                    if target not in resolved:
                        raise ValueError('Ascent failed to be a strictly increasing DAG')
                    downstream = resolved[target]
                else:
                    downstream = {('external_halo_exit', target): (0., 0., 0., False, 0, 0)}
                for key, (low, high, max_edge, path_robust, hops_low, hops_high) in downstream.items():
                    candidate = (low + minutes, high + minutes, max(max_edge, minutes),
                                 bool(robust and path_robust), hops_low + 1, hops_high + 1)
                    if key in terminal:
                        old = terminal[key]
                        candidate = (min(old[0], candidate[0]), max(old[1], candidate[1]),
                            max(old[2], candidate[2]), bool(old[3] and candidate[3]),
                            min(old[4], candidate[4]), max(old[5], candidate[5]))
                    terminal[key] = candidate
        resolved[origin] = terminal
    rows = []
    population = roster.set_index('source_record_id').population_2021.to_dict()
    names = roster.set_index('source_record_id')['name'].to_dict()
    for origin in roster.source_record_id:
        terminals = resolved[origin]
        unique = len(terminals) == 1
        for (status, endpoint), (low, high, max_edge, robust, hops_low, hops_high) in sorted(terminals.items()):
            core = endpoint if status in {'resolved_regional_peak',
                'sampled_peak_without_nonself_comparators'} else None
            rows.append({'scenario_id': sid, 'kernel': kernel, 'half_time': float(half_time),
                'neighbour_count': neighbour_count, 'topology': topology,
                'source_record_id': origin, 'name': names.get(origin),
                'population_2021': population.get(origin),
                'basin_id': sid+'|peak:'+core if core is not None else None,
                'core_id': core, 'core_name': names.get(core),
                'core_population_2021': population.get(core),
                'exit_id': endpoint if status == 'external_halo_exit' else None,
                'terminal_id': endpoint, 'status': status,
                'origin_comparison_status': local[origin]['status'],
                'terminal_has_nonself_comparison_support': status == 'resolved_regional_peak',
                'assignment_unique': unique, 'reachable_terminal_count': len(terminals),
                'assignment_status': ('unique_sampled_basin_without_peak_comparators'
                    if unique and status == 'sampled_peak_without_nonself_comparators' else
                    'unique_regional_basin' if unique and core is not None else
                    status if unique else 'multiple_coequal_outcomes'),
                'raw_comparison_neighbours': local[origin]['raw_neighbours'],
                'scale_eligible_neighbours': local[origin]['eligible_neighbours'],
                'origin_national_k6_peak_testable': reference6[origin][0],
                'origin_national_k6_sampled_peak': reference6[origin][1],
                'terminal_national_k6_peak_testable': reference6.get(core, (False, False))[0],
                'terminal_national_k6_sampled_peak': reference6.get(core, (False, False))[1],
                'path_min_comparison_minutes': float(low), 'path_max_comparison_minutes': float(high),
                'path_max_edge_minutes': float(max_edge), 'path_min_hops': hops_low,
                'path_max_hops': hops_high, 'path_exceeds_smoothing_half_time': bool(high > half_time),
                'robust_to_known_source_bounds': bool(robust),
                'comparison_path_is_shortest_origin_peak_route': False,
                'is_observed_flow': False, 'proves_functional_system': False})
    return pd.DataFrame(rows), pd.DataFrame(steps, columns=['scenario_id', 'origin_id',
        'destination_id', 'minutes', 'origin_field', 'destination_field',
        'potential_gain_per_minute', 'coequal_best_steps', 'destination_in_regional_frame',
        'ascent_robust_to_known_source_bounds', 'is_observed_trip'])


def basin_summary(members):
    rows = []
    for (scenario, core), group in members[members.core_id.notna()].groupby(['scenario_id', 'core_id'], sort=True):
        definite = group[group.assignment_unique].drop_duplicates('source_record_id')
        possible = group.drop_duplicates('source_record_id')
        rows.append({'scenario_id': scenario, 'kernel': group.kernel.iloc[0],
            'half_time': float(group.half_time.iloc[0]), 'neighbour_count': int(group.neighbour_count.iloc[0]),
            'topology': group.topology.iloc[0], 'core_id': core, 'core_name': group.core_name.iloc[0],
            'core_population_2021': group.core_population_2021.iloc[0],
            'core_has_nonself_comparison_support': bool(group.terminal_has_nonself_comparison_support.iloc[0]),
            'definite_member_records': len(definite), 'possible_member_records': len(possible),
            'definite_inhabited_members': int(definite.population_2021.gt(0).sum()),
            'possible_inhabited_members': int(possible.population_2021.gt(0).sum()),
            'definite_population_known_subset': float(definite.population_2021.sum(min_count=1)),
            'possible_population_known_subset': float(possible.population_2021.sum(min_count=1)),
            'maximum_comparison_path_minutes': float(possible.path_max_comparison_minutes.max()),
            'maximum_single_comparison_edge_minutes': float(possible.path_max_edge_minutes.max()),
            'members_with_path_exceeding_half_time': int(possible.path_exceeds_smoothing_half_time.sum()),
            'possible_members_must_not_be_summed_across_overlapping_basins': True,
            'is_empirical_service_system': False})
    return pd.DataFrame(rows)


def scale_overlap(members):
    """Adjacent scales may split, merge, disappear or exit; no parent is forced."""
    records = []
    unique = members[members.assignment_unique & members.core_id.notna()]
    for key, group in unique.groupby(['kernel', 'neighbour_count', 'topology'], sort=True):
        scales = sorted(members[(members.kernel.eq(key[0])) &
            members.neighbour_count.eq(key[1]) & members.topology.eq(key[2])].half_time.unique())
        for fine, coarse in zip(scales[:-1], scales[1:]):
            a = group[group.half_time.eq(fine)][['source_record_id', 'core_id', 'population_2021']]
            b = group[group.half_time.eq(coarse)][['source_record_id', 'core_id']]
            joined = a.merge(b, on='source_record_id', suffixes=('_fine', '_coarse'), validate='one_to_one')
            size_a = a.groupby('core_id').size(); size_b = b.groupby('core_id').size()
            counts = joined.groupby(['core_id_fine', 'core_id_coarse']).agg(
                shared_records=('source_record_id', 'size'),
                shared_population_known_subset=('population_2021', 'sum')).reset_index()
            for r in counts.itertuples(index=False):
                records.append({'kernel': key[0], 'neighbour_count': key[1], 'topology': key[2],
                    'fine_half_time': float(fine), 'coarse_half_time': float(coarse),
                    'fine_core_id': r.core_id_fine, 'coarse_core_id': r.core_id_coarse,
                    'shared_records': int(r.shared_records),
                    'fine_definite_records': int(size_a[r.core_id_fine]),
                    'coarse_definite_records': int(size_b[r.core_id_coarse]),
                    'jaccard_definite_members': float(r.shared_records / (
                        size_a[r.core_id_fine] + size_b[r.core_id_coarse] - r.shared_records)),
                    'shared_population_known_subset': float(r.shared_population_known_subset),
                    'is_parent_assignment': False})
    return pd.DataFrame(records)


def run(input_root, output):
    root, output = Path(input_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    roster = pd.read_parquet(root/'regional_roster.parquet').sort_values('row_index')
    fields = pd.read_parquet(root/'fields.parquet')
    halo = pd.read_parquet(root/'halo_fields.parquet')
    neighbours = pd.read_parquet(root/'national_neighbors.parquet')
    # Halo identities are explicit and cannot be mistaken for regional peaks.
    halo_roster = pd.read_parquet(root/'halo_roster.parquet')
    if not set(halo.source_record_id) <= set(halo_roster.source_record_id):
        raise ValueError('Halo field lacks explicit identity metadata')
    common = fields[fields.include_self.eq(True)]
    halo_common = halo[halo.include_self.eq(True)]
    members, edges = [], []
    for (kernel, half_time), field in common.groupby(['kernel', 'half_time'], sort=True):
        halo_field = halo_common[halo_common.kernel.eq(kernel) & halo_common.half_time.eq(half_time)]
        for k in [3, 6]:
            for topology in ['fixed_knn', 'scale_local']:
                m, e = ascent_scenario(roster, field, halo_field, neighbours,
                    kernel=kernel, half_time=half_time, neighbour_count=k, topology=topology)
                members.append(m); edges.append(e)
    membership = pd.concat(members, ignore_index=True)
    steps = pd.concat(edges, ignore_index=True)
    if membership.groupby('scenario_id').source_record_id.nunique().ne(len(roster)).any():
        raise ValueError('A scenario omitted regional records')
    basins = basin_summary(membership)
    overlap = scale_overlap(membership)
    for name, frame in [('basin_membership', membership), ('ascent_steps', steps),
                        ('basins', basins), ('cross_scale_overlap', overlap)]:
        frame.to_parquet(output/(name+'.parquet'), index=False, compression='zstd')
    origin_status = membership.drop_duplicates(['scenario_id', 'source_record_id'])
    summary = origin_status.groupby(['scenario_id', 'kernel', 'half_time', 'neighbour_count',
        'topology', 'assignment_status'], dropna=False).agg(
        origin_records=('source_record_id', 'size'),
        inhabited_origin_records=('population_2021', lambda x: int(x.gt(0).sum()))).reset_index()
    summary.to_csv(output/'scenario_status_counts.csv', index=False)
    report = {'schema': 'sgrt.saratov.regional_population_basins.v1',
        'regional_records': len(roster), 'scenarios': membership.scenario_id.nunique(),
        'origin_scenario_records': len(origin_status), 'membership_rows_including_equal_outcomes': len(membership),
        'ascent_step_rows': len(steps), 'regional_basin_scenario_rows': len(basins),
        'cross_scale_overlap_rows': len(overlap),
        'scenario_origin_status_counts': summary.to_dict('records'),
        'common_population_surface_include_self': True,
        'field_numeric_tolerance': '1e-9 + 1e-12 * max(abs(a), abs(b))',
        'slope_tie_tolerance': {'absolute': 1e-12, 'relative': 1e-10},
        'observed_functional_systems_established': False,
        'nested_hierarchy_imposed': False,
        'service_radius_estimated': False,
        'country_transit_revalidated_for_archived_fields': False,
        'limitations': ['Regional halo exit is censored, not an external peak or proved isolation.',
            'Neighbour graph and h-limited graph are sensitivity choices, not established settlement-system boundaries.',
            'Strict ascent only; numerically flat and zero-time comparisons stay explicitly ambiguous.',
            'Summed comparison-edge times are neither a shortest whole trip nor a service travel budget.',
            'Scale-local edges can chain beyond h; large basins are not validated service areas.',
            'Documented functional centres survive separately even when not population maxima.']}
    (output/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def full_radius_edges(roster, costs, half_time):
    """All known regional nonself peers within h, never only nearest k."""
    if costs.shape != (len(roster), len(roster)):
        raise ValueError('Regional cost matrix does not match the row axis')
    eligible = np.isfinite(costs) & (costs <= half_time)
    np.fill_diagonal(eligible, False)
    i, j = np.nonzero(eligible)
    ids = roster.source_record_id.to_numpy()
    return pd.DataFrame({'origin_id': ids[i], 'destination_id': ids[j],
                         'minutes': np.asarray(costs[i, j], dtype=float)})


def run_full_radius(input_root, output):
    """Correct kNN-created sinks using complete routable radius comparisons.

    A point within h of the external frame is censored conservatively: unknown
    external potential comparisons cannot be replaced by a regional maximum.
    A valid isolated sampling point may form a singleton concentration branch,
    explicitly without nonself comparison or evidence of external servicing.
    """
    root, output = Path(input_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    roster = pd.read_parquet(root/'regional_roster.parquet').sort_values('row_index')
    if not np.array_equal(roster.row_index, np.arange(len(roster))):
        raise ValueError('Regional cost row indices differ')
    fields = pd.read_parquet(root/'fields.parquet')
    halo = pd.read_parquet(root/'halo_fields.parquet')
    neighbours = pd.read_parquet(root/'national_neighbors.parquet')
    costs = np.load(root/'regional_costs.npy', mmap_mode='r')
    reference = pd.read_parquet(root.parent/'organisation/scale_neighbourhood_maxima.parquet')
    reference = reference[reference.include_self.eq(True) & reference.comparison_radius_factor.eq(1.)]
    members, edges, consistency = [], [], []
    for (kernel, half_time), field in fields[fields.include_self.eq(True)].groupby(['kernel', 'half_time'], sort=True):
        known = reference[reference.kernel.eq(kernel) & reference.half_time.eq(half_time)]
        if known.source_record_id.duplicated().any() or set(known.source_record_id) != set(roster.source_record_id):
            raise ValueError('Complete-radius reference axis differs')
        censored = set(known.loc[~known.external_comparison_complete.eq(True), 'source_record_id'])
        halo_field = halo[halo.include_self.eq(True) & halo.kernel.eq(kernel) & halo.half_time.eq(half_time)]
        m, e = ascent_scenario(roster, field, halo_field,
            full_radius_edges(roster, costs, float(half_time)), kernel=kernel,
            half_time=float(half_time), neighbour_count=0, topology='full_radius',
            national_neighbour_reference=neighbours, censored_origins=censored)
        members.append(m); edges.append(e)
        peaks = m[m.source_record_id.eq(m.core_id) & m.status.eq('resolved_regional_peak')]
        lookup = known.set_index('source_record_id')
        inconsistent = [i for i in peaks.core_id if not bool(lookup.loc[i, 'complete_routable_point_scale_maximum'])]
        if inconsistent:
            raise ValueError('Full-radius ascent sink is not a full-radius sampled maximum')
        consistency.append({'kernel': kernel, 'half_time': float(half_time),
            'resolved_peaks_with_nonself_support': len(peaks),
            'sinks_failing_published_complete_radius_peak_check': len(inconsistent),
            'singleton_samples_without_nonself_comparators': int(
                m[m.source_record_id.eq(m.core_id)].status.eq('sampled_peak_without_nonself_comparators').sum()),
            'reference_complete_nonstrict_maxima': int(known.complete_routable_point_scale_maximum.sum())})
    membership = pd.concat(members, ignore_index=True)
    steps = pd.concat(edges, ignore_index=True)
    if membership.groupby('scenario_id').source_record_id.nunique().ne(len(roster)).any():
        raise ValueError('A full-radius scenario omitted regional records')
    basins, overlap = basin_summary(membership), scale_overlap(membership)
    for name, frame in [('basin_membership', membership), ('ascent_steps', steps),
                        ('basins', basins), ('cross_scale_overlap', overlap)]:
        frame.to_parquet(output/(name+'.parquet'), index=False, compression='zstd')
    origins = membership.drop_duplicates(['scenario_id', 'source_record_id'])
    status = origins.groupby(['scenario_id', 'kernel', 'half_time', 'assignment_status'], dropna=False).agg(
        origin_records=('source_record_id', 'size'),
        inhabited_origin_records=('population_2021', lambda x: int(x.gt(0).sum()))).reset_index()
    status.to_csv(output/'scenario_status_counts.csv', index=False)
    report = {'schema': 'sgrt.saratov.full_radius_population_basins.v1',
        'regional_records': len(roster), 'scenarios': membership.scenario_id.nunique(),
        'origin_scenario_records': len(origins), 'membership_rows_including_equal_outcomes': len(membership),
        'ascent_step_rows': len(steps), 'regional_basin_scenario_rows': len(basins),
        'cross_scale_overlap_rows': len(overlap),
        'scenario_origin_status_counts': status.to_dict('records'),
        'published_radius_peak_consistency': consistency,
        'knn_sinks_replaced_by_all_routable_radius_comparisons': True,
        'external_neighbourhoods_conservatively_censored': True,
        'common_population_surface_include_self': True,
        'nested_hierarchy_imposed': False, 'observed_functional_systems_established': False,
        'service_radius_estimated': False, 'country_transit_revalidated_for_archived_fields': False,
        'limitations': ['Full radius is complete only for known routable settlement points of the archived matrix.',
            'A regional sample without nonself peers forms a labelled singleton, not a proved external service centre.',
            'External comparisons are censored when the known external frame begins within h.',
            'The half-time is a field/comparison scale, not a maximum whole-basin travel time.',
            'Population basins still require independent functional and geographic validation.']}
    (output/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--full-radius', action='store_true')
    a = p.parse_args()
    producer = run_full_radius if a.full_radius else run
    print(json.dumps(producer(a.input_root, a.output), ensure_ascii=False, indent=2))
