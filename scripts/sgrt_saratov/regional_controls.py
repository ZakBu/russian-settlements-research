"""Compare field ascent with nearest access to exactly the same sampled peaks.

The comparison uses the same uniquely resolved origin cohort and no document
or service information. It preserves tied nearest peaks and excludes censored
origins; it is not an alternative claim about observed settlement systems.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd


def nearest_same_peaks(membership, roster, costs):
    roster = roster.sort_values('row_index').reset_index(drop=True)
    if not np.array_equal(roster.row_index, np.arange(len(roster))):
        raise ValueError('Unexpected regional cost axis')
    if costs.shape != (len(roster), len(roster)):
        raise ValueError('Regional costs and roster differ')
    axis = roster.set_index('source_record_id').row_index.to_dict()
    lookup = roster.set_index('source_record_id')
    records, comparisons = [], []
    for scenario, group in membership.groupby('scenario_id', sort=True):
        resolved = group[group.status.eq('resolved_regional_peak') &
                         group.assignment_unique.eq(True) & group.core_id.notna()]
        if resolved.source_record_id.duplicated().any():
            raise ValueError('Repeated supposedly unique assignment')
        cores = sorted(resolved.core_id.unique())
        if not set(cores) <= set(axis):
            raise ValueError('A resolved regional peak is outside the regional axis')
        columns = [axis[c] for c in cores]
        known = resolved.set_index('source_record_id')
        for origin, rows in group.groupby('source_record_id', sort=True):
            row = rows.iloc[0].to_dict()
            control = scenario+'__nearest_same_peaks'
            row.update(scenario_id=control, topology=str(row['topology'])+'__nearest_same_peaks',
                baseline_parent_scenario=scenario, direct_nearest_same_peaks_control=True,
                comparison_path_is_shortest_origin_peak_route=False,
                is_observed_flow=False, proves_functional_system=False)
            # Original ascent-path attributes do not describe the control.
            for key in list(row):
                if key.startswith('path_') or key.startswith('terminal_national_'):
                    row[key] = None
            row['robust_to_known_source_bounds'] = None
            if origin not in known.index or not cores:
                row.update(core_id=None, core_name=None, core_population_2021=None,
                    basin_id=None, terminal_id=None, exit_id=None,
                    status='comparison_cohort_excluded', assignment_unique=False,
                    assignment_status='comparison_cohort_excluded', reachable_terminal_count=0)
                records.append(row)
                continue
            distances = np.asarray(costs[axis[origin], columns], dtype=float)
            finite = np.isfinite(distances) & (distances >= 0)
            if not finite.any():
                row.update(core_id=None, core_name=None, basin_id=None, terminal_id=None,
                    status='comparison_cost_unknown', assignment_unique=False,
                    assignment_status='comparison_cost_unknown', reachable_terminal_count=0)
                records.append(row)
                continue
            minimum = float(distances[finite].min())
            winners = np.flatnonzero(finite & np.isclose(distances, minimum, atol=1e-7, rtol=0))
            original_core = known.loc[origin, 'core_id']
            original_time = float(costs[axis[origin], axis[original_core]])
            excess = original_time-minimum if np.isfinite(original_time) else None
            if excess is not None and excess < -1e-7:
                raise ValueError('A same-peak nearest control lost the selected peak')
            comparisons.append({'scenario_id': scenario, 'source_record_id': origin,
                'ascent_core_id': original_core, 'nearest_core_ids_json': json.dumps([cores[i] for i in winners]),
                'selected_ascent_core_is_one_of_nearest': original_core in {cores[i] for i in winners},
                'nearest_peak_minutes': minimum,
                'direct_ascent_peak_minutes': original_time if np.isfinite(original_time) else None,
                'excess_to_ascent_peak_minutes': excess,
                'country_scope': 'archived_v2_costs_not_complete_domestic_route_revalidation'})
            for index in winners:
                core = cores[index]
                item = row.copy()
                item.update(core_id=core, core_name=str(lookup.loc[core, 'name']),
                    core_population_2021=float(lookup.loc[core, 'population_2021']),
                    basin_id=control+'|peak:'+core, terminal_id=core, exit_id=None,
                    status='resolved_regional_peak', assignment_unique=len(winners)==1,
                    assignment_status='unique_nearest_control' if len(winners)==1 else 'multiple_nearest_control',
                    reachable_terminal_count=len(winners))
                records.append(item)
    output = pd.DataFrame(records)
    pairs = pd.DataFrame(comparisons, columns=['scenario_id', 'source_record_id',
        'ascent_core_id', 'nearest_core_ids_json', 'selected_ascent_core_is_one_of_nearest',
        'nearest_peak_minutes', 'direct_ascent_peak_minutes',
        'excess_to_ascent_peak_minutes', 'country_scope'])
    return output, pairs


def run(membership_path, roster_path, costs_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    membership = pd.read_parquet(membership_path)
    control, pairs = nearest_same_peaks(membership, pd.read_parquet(roster_path),
                                        np.load(costs_path, mmap_mode='r'))
    control.to_parquet(output/'nearest_same_peaks_membership.parquet', index=False, compression='zstd')
    pairs.to_parquet(output/'nearest_same_peaks_comparison.parquet', index=False, compression='zstd')
    summary = []
    for scenario in sorted(membership.scenario_id.unique()):
        g = pairs[pairs.scenario_id.eq(scenario)]
        finite = pd.to_numeric(g.excess_to_ascent_peak_minutes, errors='coerce').dropna()
        summary.append({'scenario_id': scenario, 'compared_origins': len(g),
            'ascent_peak_is_nearest': int(g.selected_ascent_core_is_one_of_nearest.sum()),
            'different_nearest_peak': int((~g.selected_ascent_core_is_one_of_nearest).sum()),
            'known_excess_cost_origins': int(g.excess_to_ascent_peak_minutes.notna().sum()),
            'median_excess_minutes': float(finite.median()) if len(finite) else None,
            'maximum_excess_minutes': float(finite.max()) if len(finite) else None})
    pd.DataFrame(summary).to_csv(output/'nearest_same_peaks_summary.csv', index=False)
    result = {'schema': 'sgrt.regional.same_peaks_control.v1', 'scenarios': len(summary),
        'compared_origin_scenarios': len(pairs),
        'different_nearest_peak_origin_scenarios': int((~pairs.selected_ascent_core_is_one_of_nearest).sum()),
        'same_peaks_and_same_resolved_input_origin_cohort_before_ties': True,
        'final_unique_cohorts_may_differ_due_to_nearest_ties': True,
        'documents_used_to_construct_control': False, 'observed_flows_established': False}
    (output/'control_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result
