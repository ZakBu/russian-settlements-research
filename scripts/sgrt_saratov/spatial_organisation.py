"""Multiscale concentration diagnostics; never a service-district hierarchy.

Outgoing national neighbours and their halo fields are explicit inputs.  A
cross-scale correspondence is a nearest *comparison* peak, not a parent city,
an inferred journey, or permission to merge service catchments transitively.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


SCENARIO = ['kernel', 'half_time', 'include_self']


def point_maxima(fields, halo_fields, neighbours, roster, counts=(3, 6)):
    required = {'source_record_id', *SCENARIO, 'value', 'accepted_mass_field_upper'}
    if not required.issubset(fields):
        raise ValueError('Missing field identities, values or uncertainty bounds')
    all_fields = pd.concat([fields, halo_fields], ignore_index=True)
    if all_fields.duplicated(['source_record_id', *SCENARIO]).any():
        raise ValueError('Regional and halo fields must have unique scenario identities')
    if roster.source_record_id.duplicated().any():
        raise ValueError('Regional identities are not unique')
    regional_ids = roster.source_record_id.tolist()
    edges_by_k = {}
    for k in counts:
        chosen = neighbours.loc[neighbours[f'in_k{k}'].eq(True)]
        if chosen.duplicated(['origin_id', 'destination_id']).any():
            raise ValueError('Repeated comparison edge')
        edges_by_k[k] = chosen.groupby('origin_id').destination_id.agg(list).to_dict()
    records = []
    for key, group in all_fields.groupby(SCENARIO, sort=True):
        values = group.set_index('source_record_id')['value'].to_dict()
        upper = group.set_index('source_record_id')['accepted_mass_field_upper'].to_dict()
        for k, adjacency in edges_by_k.items():
            for source in regional_ids:
                value = values.get(source, np.nan)
                adjacent = adjacency.get(source, [])
                known = [(j, values.get(j, np.nan)) for j in adjacent]
                missing = sum(not np.isfinite(x) for _, x in known)
                enough = len(adjacent) >= k
                testable = np.isfinite(value) and enough and missing == 0
                tolerance = lambda x: 1e-9 + 1e-12 * max(abs(value), abs(x))
                peak = testable and all(x <= value + tolerance(x) for _, x in known)
                strict = peak and all(value > x + tolerance(x) for _, x in known)
                ties = sum(abs(value-x) <= tolerance(x) for _, x in known) if testable else 0
                bounds = [upper.get(j, np.nan) for j, _ in known]
                bounded = testable and all(np.isfinite(x) for x in bounds)
                robust = bounded and all(value > x + tolerance(x) for x in bounds)
                records.append(dict(zip(SCENARIO, key), source_record_id=source,
                    neighbour_count=k, value=value, comparison_neighbours=len(adjacent),
                    neighbour_values_missing=missing, requested_k_available=enough,
                    point_comparison_testable=testable, sampled_point_maximum=peak,
                    strict_sampled_point_maximum=strict, equal_outgoing_neighbours=ties,
                    known_source_uncertainty_robust=robust,
                    comparison_scope='outgoing_national_k_nearest_with_explicit_halo',
                    common_population_surface=bool(key[2]),
                    origin_specific_external_mass_diagnostic=not bool(key[2]),
                    proves_functional_centre=False, proves_complete_surface_maximum=False))
    return pd.DataFrame(records)


def scale_changes(peaks, roster):
    """Retain births and losses; never enforce monotone peak counts."""
    output, intervals = [], []
    names = roster.set_index('source_record_id').name.to_dict()
    for key, family in peaks.groupby(['kernel', 'include_self', 'neighbour_count'], sort=True):
        previous = None
        begin = None
        last_scale = None
        for h, group in family.groupby('half_time', sort=True):
            present = set(group.loc[group.sampled_point_maximum, 'source_record_id'])
            if previous is not None:
                for source in sorted(previous | present):
                    event = 'retained' if source in previous & present else 'appeared' if source in present else 'disappeared'
                    output.append(dict(zip(['kernel', 'include_self', 'neighbour_count'], key),
                        from_half_time=last_scale, to_half_time=h, source_record_id=source,
                        name=names.get(source), event=event, imposes_nested_hierarchy=False))
            if previous is None or present != previous:
                if previous is not None:
                    intervals.append(dict(zip(['kernel', 'include_self', 'neighbour_count'], key),
                        from_half_time=begin, to_half_time=last_scale,
                        peak_count=len(previous), peak_ids=sorted(previous),
                        is_empirical_functional_level=False))
                begin = h
            previous, last_scale = present, h
        if previous is not None:
            intervals.append(dict(zip(['kernel', 'include_self', 'neighbour_count'], key),
                from_half_time=begin, to_half_time=last_scale,
                peak_count=len(previous), peak_ids=sorted(previous),
                is_empirical_functional_level=False))
    return pd.DataFrame(output), pd.DataFrame(intervals)


def cross_scale_correspondence(peaks, roster, regional_costs):
    """Direct-time comparison among peaks, not a transitive service assignment."""
    ids = roster.source_record_id.tolist()
    if regional_costs.shape != (len(ids), len(ids)):
        raise ValueError('Cost matrix does not match the fixed regional row axis')
    index = {source: i for i, source in enumerate(ids)}
    records = []
    for key, family in peaks.groupby(['kernel', 'include_self', 'neighbour_count'], sort=True):
        scales = sorted(family.half_time.unique())
        for small, large in zip(scales[:-1], scales[1:]):
            fine = sorted(family.loc[family.half_time.eq(small) & family.sampled_point_maximum, 'source_record_id'])
            coarse = sorted(family.loc[family.half_time.eq(large) & family.sampled_point_maximum, 'source_record_id'])
            for source in fine:
                candidates = [(target, regional_costs[index[source], index[target]]) for target in coarse]
                finite = [(target, float(cost)) for target, cost in candidates if np.isfinite(cost)]
                chosen = []
                if finite:
                    minimum = min(cost for _, cost in finite)
                    chosen = [(target, cost) for target, cost in finite if abs(cost-minimum) <= 1e-9]
                for target, cost in chosen or [(None, np.nan)]:
                    records.append(dict(zip(['kernel', 'include_self', 'neighbour_count'], key),
                        from_half_time=small, to_half_time=large, origin_peak_id=source,
                        comparison_peak_id=target, directed_minutes=cost,
                        retained_same_peak=source == target,
                        tied_comparison_peaks=len(chosen),
                        status='directed_nearest_coarser_comparison' if chosen else 'no_comparison_within_computed_cost_scope',
                        is_parent_system_assignment=False, is_observed_flow=False))
    return pd.DataFrame(records)


def scale_neighbourhood_maxima(fields, roster, costs, nearest_external, factors=(.5, 1., 2.)):
    """Compare a growing travel-time neighbourhood, with explicit border censoring.

    Fixed k-nearest tests can retain tiny road-accessibility bumps at every
    scale. This independent comparison varies its neighbourhood with h. The
    radius is a comparison scale, never a service boundary. A regional peak
    without every reachable external competitor is not a complete peak.
    """
    ids = roster.source_record_id.tolist()
    records = []
    for key, group in fields.groupby(SCENARIO, sort=True):
        values = group.set_index('source_record_id').value.reindex(ids).to_numpy(float)
        for factor in factors:
            radius = float(key[1])*factor
            if radius > 480:
                raise ValueError('Comparison radius exceeds computed route horizon')
            for i, source in enumerate(ids):
                mask = np.isfinite(costs[i]) & (costs[i] <= radius)
                mask[i] = False
                others = values[mask]
                testable = np.isfinite(values[i]) and len(others)>0 and np.isfinite(others).all()
                peak = testable and bool(np.all(others <= values[i]+1e-9+1e-12*np.maximum(abs(others),abs(values[i]))))
                border_complete = bool(np.isfinite(costs[i, i]) and nearest_external[i] > radius)
                records.append(dict(zip(SCENARIO, key), source_record_id=source,
                    comparison_radius_factor=factor, comparison_minutes=radius,
                    regional_comparators=int(mask.sum()), regional_comparison_testable=bool(testable),
                    regional_scale_maximum=bool(peak), external_comparison_complete=border_complete,
                    complete_scale_comparison_testable=bool(testable and border_complete),
                    complete_routable_point_scale_maximum=bool(peak and border_complete),
                    nearest_external_routable_np_minutes=float(nearest_external[i]),
                    common_population_surface=bool(key[2]),
                    comparison_scope='routable_settlement_points_with_explicit_regional_border_censoring',
                    proves_functional_level=False))
    return pd.DataFrame(records)


def external_neighbour_times(matrix, destinations, roster):
    """Absent pairs remain unreachable/censored; no dense zero filling."""
    regions = set(roster.region.dropna().astype(str))
    if len(regions) != 1:
        raise ValueError('One regional roster required')
    external = ~destinations.region.astype(str).isin(regions).to_numpy()
    result = np.full(len(roster), np.inf)
    for i in range(len(roster)):
        a, b = matrix.indptr[i:i+2]
        selected = external[matrix.indices[a:b]]
        if selected.any():
            result[i] = matrix.data[a:b][selected].min()
    return result


def run(folder, output):
    folder, output = Path(folder), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    roster = pd.read_parquet(folder/'regional_roster.parquet').sort_values('row_index')
    fields = pd.read_parquet(folder/'fields.parquet')
    halo = pd.read_parquet(folder/'halo_fields.parquet')
    neighbours = pd.read_parquet(folder/'national_neighbors.parquet')
    peaks = point_maxima(fields, halo, neighbours, roster)
    changes, intervals = scale_changes(peaks, roster)
    costs = np.load(folder/'regional_costs.npy', mmap_mode='r')
    correspondences = cross_scale_correspondence(peaks, roster, costs)
    from scipy.sparse import load_npz
    nearest_external = external_neighbour_times(load_npz(folder/'destination_costs.npz'),
        pd.read_parquet(folder/'destinations.parquet'), roster)
    growing = scale_neighbourhood_maxima(fields, roster, costs, nearest_external)
    tables = {'point_maxima': peaks, 'scale_changes': changes,
              'stable_sampled_scale_intervals': intervals,
              'cross_scale_peak_correspondences': correspondences,
              'scale_neighbourhood_maxima': growing}
    for name, data in tables.items():
        data.to_parquet(output/(name+'.parquet'), index=False, compression='zstd')
    summary = peaks.groupby([*SCENARIO, 'neighbour_count'], as_index=False).agg(
        regional_records=('source_record_id', 'size'),
        testable_points=('point_comparison_testable', 'sum'),
        sampled_maxima=('sampled_point_maximum', 'sum'),
        strict_maxima=('strict_sampled_point_maximum', 'sum'),
        robust_to_known_source_bounds=('known_source_uncertainty_robust', 'sum'))
    summary.to_csv(output/'peak_counts.csv', index=False)
    growing.groupby([*SCENARIO, 'comparison_radius_factor'], as_index=False).agg(
        regional_maxima=('regional_scale_maximum','sum'),
        testable_points=('regional_comparison_testable','sum'),
        complete_border_scope_points=('external_comparison_complete','sum'),
        testable_complete_comparisons=('complete_scale_comparison_testable','sum'),
        complete_scale_maxima=('complete_routable_point_scale_maximum','sum')).to_csv(
            output/'scale_neighbourhood_counts.csv', index=False)
    report = {'schema': 'sgrt.saratov.multiscale_organisation.v1',
        'regional_records': len(roster), 'scenario_point_comparisons': len(peaks),
        'compared_scales_minutes': sorted(fields.half_time.unique().tolist()),
        'cross_scale_correspondence_rows': len(correspondences),
        'birth_events': int(changes.event.eq('appeared').sum()) if len(changes) else 0,
        'loss_events': int(changes.event.eq('disappeared').sum()) if len(changes) else 0,
        'method': 'Outgoing neighbour comparisons; explicit external halo; direct-time comparison between successive smoothing scenarios.',
        'interpretation': 'Concentration diagnostics; no service membership or mandatory nested functional hierarchy follows from these tables.'}
    (output/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fields', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.fields, args.output), ensure_ascii=False, indent=2))
