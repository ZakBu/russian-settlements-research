"""External checks of population-field partitions, including trivial baselines.

Documents are controls, never inputs to the partitions.  Agreement concerns
settlement membership, not observed trips. Unknown/halo/ambiguous assignments
never form a synthetic common basin. School supply-enrichment leakage and the
selected, cross-date medical document remain explicit limitations.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.sgrt_saratov.system_structure import apply_identity_overrides, truth

RESOLVED = 'resolved_regional_peak'
SCENARIO_COLUMNS = ('kernel', 'half_time', 'neighbour_count', 'topology')


def frame(path):
    return pd.read_parquet(path) if str(path).endswith('.parquet') else pd.read_csv(path)


def adjusted_rand(reference, predicted):
    """ARI on actual resolved records only; missing labels are not a cluster."""
    a, b = list(reference), list(predicted)
    if len(a) != len(b):
        raise ValueError('Partition labels have different lengths')
    if len(a) < 2:
        return None
    if any(pd.isna(x) for x in a+b):
        raise ValueError('Unknown assignment cannot be a partition label')
    choose2 = lambda n: n*(n-1)/2
    cells = Counter(zip(a, b))
    rows, cols = Counter(a), Counter(b)
    joint = sum(choose2(n) for n in cells.values())
    row = sum(choose2(n) for n in rows.values())
    col = sum(choose2(n) for n in cols.values())
    pairs = choose2(len(a))
    expected = row*col/pairs
    maximum = (row+col)/2
    if abs(maximum-expected) < 1e-12:
        return 1. if abs(joint-maximum) < 1e-12 else 0.
    return float((joint-expected)/(maximum-expected))


def partition_pair_scores(reference, predicted):
    a, b = np.asarray(reference, dtype=object), np.asarray(predicted, dtype=object)
    if len(a) != len(b):
        raise ValueError('Partition labels have different lengths')
    i, j = np.triu_indices(len(a), k=1)
    same_reference = a[i] == a[j]
    same_model = b[i] == b[j]
    within = int(same_reference.sum())
    between = int((~same_reference).sum())
    true_same = int((same_reference & same_model).sum())
    false_same = int((~same_reference & same_model).sum())
    sensitivity = true_same/within if within else None
    specificity = 1-false_same/between if between else None
    return {'labelled_resolved_np': len(a),
        'within_document_pairs': within, 'within_document_same_basin': true_same,
        'between_document_pairs': between, 'between_document_same_basin': false_same,
        'within_document_same_basin_rate': sensitivity,
        'between_document_false_merge_rate': false_same/between if between else None,
        'balanced_pair_accuracy': (sensitivity+specificity)/2
            if sensitivity is not None and specificity is not None else None,
        'adjusted_rand_index': adjusted_rand(a, b)}


def documented_controls(school, medical, overrides, roster):
    """Keep own members for partition checks, external living pairs for links."""
    if roster.source_record_id.duplicated().any():
        raise ValueError('Repeated regional population identity')
    population = roster.set_index('source_record_id').population_2021
    schools = school.rename(columns={'campus_id': 'core_id'}).copy()
    schools['family'] = 'school'
    schools['admitted'] = schools.origin_id.notna() & schools.core_id.notna()
    if len(overrides):
        medical = apply_identity_overrides(medical, overrides, roster)
    else:
        medical = medical.copy()
    medical['admitted'] = medical.accepted.map(truth) & medical.origin_id.notna() & medical.core_id.notna()
    output = []
    for kind, data in [('school', schools), ('medical', medical)]:
        for r in data[data.admitted].to_dict('records'):
            origin, core = str(r['origin_id']), str(r['core_id'])
            if origin not in population.index or core not in population.index:
                raise ValueError('Admitted control has no regional identity')
            if not pd.notna(population[origin]) or population[origin] <= 0:
                continue
            output.append({'origin_id': origin, 'core_id': core,
                'family': r['family'], 'control_kind': kind,
                'source_id': r['source_id'], 'external_relation': origin != core,
                'independence_scope': ('same_document_used_for_school_supply_enrichment'
                    if kind == 'school' else 'new_assignment_document_not_used_to_enrich_v2_supply'),
                'sampling_scope': ('one_selected_administrative_district'
                    if kind == 'school' else 'named_territories_in_building_modernisation_programme'),
                'observed_trip_flow': False})
    return pd.DataFrame(output).drop_duplicates(['origin_id', 'core_id', 'family', 'source_id']).reset_index(drop=True)


def _distance(lat, lon, target_lat, target_lon):
    a, b = np.radians(lat), np.radians(lon)
    c, d = math.radians(target_lat), math.radians(target_lon)
    q = np.sin((a-c)/2)**2 + np.cos(a)*math.cos(c)*np.sin((b-d)/2)**2
    return 6371.0088*2*np.arcsin(np.sqrt(np.clip(q, 0, 1)))


def _scenario_metadata(group):
    info = {'scenario_id': str(group.scenario_id.iloc[0])}
    for key in SCENARIO_COLUMNS:
        if key in group:
            if group[key].nunique(dropna=False) != 1:
                raise ValueError('Scenario metadata changes inside one scenario: '+key)
            value = group[key].iloc[0]
            info[key] = value.item() if isinstance(value, np.generic) else value
    return info


def _resolved_assignments(group, roster):
    if not set(group.source_record_id) <= set(roster.source_record_id):
        raise ValueError('Origin is outside the declared regional population axis')
    # Equal steepest-ascent paths may legitimately reach multiple terminals.
    # They are not probability weights and cannot be selected lexicographically.
    duplicates = group.source_record_id.duplicated(keep=False)
    simple = group.loc[~duplicates].copy()
    if 'assignment_unique' in simple:
        ambiguous = simple.status.eq(RESOLVED) & ~simple.assignment_unique.map(truth)
        simple.loc[ambiguous, ['basin_id', 'core_id']] = None
        simple.loc[ambiguous, 'status'] = 'multiple_terminal_assignment'
    collapsed = []
    for _, records in group.loc[duplicates].groupby('source_record_id', sort=False):
        row = records.iloc[0].to_dict()
        declared_unique = (records.assignment_unique.map(truth)
                           if 'assignment_unique' in records else pd.Series(True, index=records.index))
        if len(records) > 1 and declared_unique.any():
            raise ValueError('Repeated origins require explicitly non-unique terminal assignment')
        if len(records) > 1 or not declared_unique.all():
            row.update(status='multiple_terminal_assignment', core_id=None, basin_id=None,
                       assignment_unique=False, terminal_rows=len(records))
        collapsed.append(row)
    normalised = pd.concat([simple, pd.DataFrame(collapsed)], ignore_index=True) if collapsed else simple
    aligned = normalised.set_index('source_record_id').reindex(roster.source_record_id)
    valid = aligned.status.eq(RESOLVED) & aligned.basin_id.notna() & aligned.core_id.notna()
    if (aligned.status.eq(RESOLVED) & ~valid).any():
        raise ValueError('A resolved basin requires basin and regional core identities')
    if not set(aligned.loc[valid, 'core_id']) <= set(roster.source_record_id):
        raise ValueError('Halo exits cannot be labelled resolved regional peaks')
    return aligned, valid.to_numpy()


def evaluate_partitions(memberships, roster, controls):
    """Return whole-region diagnostics, pair controls and label agreement."""
    required = {'scenario_id', 'source_record_id', 'basin_id', 'core_id', 'status'}
    if not required <= set(memberships):
        raise ValueError('Missing structure assignment fields')
    roster = roster.reset_index(drop=True)
    ids = roster.source_record_id.to_numpy()
    position = {sid: i for i, sid in enumerate(ids)}
    district_column = 'district_norm' if 'district_norm' in roster else 'district'
    districts = roster[district_column].fillna('').astype(str).to_numpy()
    population = pd.to_numeric(roster.population_2021, errors='coerce').to_numpy()
    living = np.isfinite(population) & (population > 0)
    lat, lon = roster.lat.to_numpy(float), roster.lon.to_numpy(float)
    distances = {}
    for core in controls.core_id.unique():
        c = roster.iloc[position[core]]
        distances[core] = _distance(lat, lon, c.lat, c.lon)
    diagnostics, pair_rows, label_rows = [], [], []
    external = controls[controls.external_relation]
    # Ambiguous document labels are held, not resolved by lexicographic choice.
    labels = controls.groupby(['family', 'origin_id']).core_id.agg(lambda x: sorted(set(x))).reset_index()
    scenarios = []
    common = np.ones(len(roster), dtype=bool)
    for _, group in memberships.groupby('scenario_id', sort=True):
        assignment, valid = _resolved_assignments(group, roster)
        scenarios.append((_scenario_metadata(group), group, assignment, valid))
        common &= valid
    for meta, group, assignment, valid in scenarios:
        options = group[group.status.eq(RESOLVED) & group.core_id.notna()].groupby(
            'source_record_id').core_id.agg(lambda x: set(x)).to_dict()
        basin = assignment.basin_id.to_numpy(object)
        sizes = Counter(basin[valid])
        weights = np.asarray(list(sizes.values()), dtype=float)
        shares = weights/weights.sum() if len(weights) else np.asarray([])
        known_mass = np.where(np.isfinite(population) & (population >= 0), population, 0.)
        mass = Counter()
        for b, p in zip(basin[valid], known_mass[valid]):
            mass[b] += float(p)
        resolved_mass = sum(mass.values())
        diagnostics.append({**meta, 'regional_records': len(roster),
            'resolved_regional_records': int(valid.sum()),
            'resolved_inhabited_records': int((valid & living).sum()),
            'inhabited_regional_records': int(living.sum()),
            'common_all_input_scenarios_resolved_records': int(common.sum()),
            'common_all_input_scenarios_resolved_inhabited_records': int((common & living).sum()),
            'assignment_status_counts_json': json.dumps(assignment.status.fillna('assignment_missing').value_counts().to_dict()),
            'regional_basins': len(sizes),
            'single_record_basins': sum(n == 1 for n in sizes.values()),
            'effective_basin_number_by_record_entropy': float(np.exp(-(shares*np.log(shares)).sum())) if len(shares) else None,
            'largest_basin_record_share_among_resolved': float(shares.max()) if len(shares) else None,
            'largest_basin_known_population_share_among_resolved': max(mass.values())/resolved_mass if resolved_mass else None,
            'resolved_known_population': resolved_mass,
            'all_regional_known_population': float(known_mass.sum()),
            'status_is_geographic_model_not_observed_system': True})
        for r in external.itertuples(index=False):
            i, j = position[r.origin_id], position[r.core_id]
            known = bool(valid[i] and valid[j])
            same = bool(basin[i] == basin[j]) if known else None
            district_null = radial_null = None
            district_candidates = radial_candidates = 0
            if known and districts[i]:
                pool = living & valid & (districts == districts[i]) & (ids != r.core_id)
                district_candidates = int(pool.sum())
                if district_candidates:
                    district_null = float((basin[pool] == basin[j]).mean())
                distance = distances[r.core_id]
                if np.isfinite(distance[i]):
                    local = pool & np.isfinite(distance) & (distance <= distance[i]+1e-9)
                    radial_candidates = int(local.sum())
                    if radial_candidates:
                        radial_null = float((basin[local] == basin[j]).mean())
            pair_rows.append({**meta, 'origin_id': r.origin_id, 'core_id': r.core_id,
                'family': r.family, 'control_kind': r.control_kind,
                'independence_scope': r.independence_scope,
                'sampling_scope': r.sampling_scope,
                'origin_assignment_status': assignment.iloc[i].status,
                'core_assignment_status': assignment.iloc[j].status,
                'both_resolved_regional': known, 'same_population_basin': same,
                'both_resolved_in_all_input_scenarios': bool(common[i] and common[j]),
                'known_common_regional_terminal_option': bool(options.get(r.origin_id, set()) & options.get(r.core_id, set())),
                'district_random_origin_same_core_basin_expectation': district_null,
                'district_random_origin_candidates': district_candidates,
                'no_farther_origin_same_core_basin_expectation': radial_null,
                'no_farther_origin_candidates': radial_candidates,
                'observed_trip_flow': False})
        for family, cohort in labels.groupby('family', sort=True):
            unique = cohort[cohort.core_id.map(len).eq(1)]
            chosen = [(r.origin_id, r.core_id[0]) for r in unique.itertuples(index=False)
                      if valid[position[r.origin_id]]]
            reference = [core for _, core in chosen]
            predicted = [basin[position[origin]] for origin, _ in chosen]
            common_chosen = [(r.origin_id, r.core_id[0]) for r in unique.itertuples(index=False)
                             if common[position[r.origin_id]]]
            common_scores = partition_pair_scores([core for _, core in common_chosen],
                [basin[position[origin]] for origin, _ in common_chosen])
            label_rows.append({**meta, 'family': family,
                'document_labelled_inhabited_np': len(cohort),
                'document_label_ambiguous_np': int(cohort.core_id.map(len).gt(1).sum()),
                'partition_validation_scope': 'selected_document_labels_not_all_province',
                **partition_pair_scores(reference, predicted),
                **{'common_cohort_'+key: value for key, value in common_scores.items()},
                'common_cohort_definition': 'intersection_of_resolved_origins_in_this_input_scenario_set'})
    pairs = pd.DataFrame(pair_rows)
    aggregates = []
    for (scenario, family), group in pairs.groupby(['scenario_id', 'family'], sort=True):
        known = group[group.both_resolved_regional]
        row = {'scenario_id': scenario, 'family': family,
            'external_document_relations': len(group), 'both_endpoints_resolved': len(known),
            'same_basin_relations': int(known.same_population_basin.eq(True).sum()),
            'same_basin_rate_among_resolved': float(known.same_population_basin.mean()) if len(known) else None}
        for key, prefix in [('district_random_origin_same_core_basin_expectation', 'district'),
                            ('no_farther_origin_same_core_basin_expectation', 'distance_conditioned')]:
            comparable = known[known[key].notna()]
            row[prefix+'_baseline_compared_relations'] = len(comparable)
            row[prefix+'_baseline_expected_same_basin_rate'] = float(comparable[key].mean()) if len(comparable) else None
            row[prefix+'_observed_minus_expected_same_basin_rate'] = float((comparable.same_population_basin.astype(float)-comparable[key]).mean()) if len(comparable) else None
        aggregates.append(row)
    return pd.DataFrame(diagnostics), pairs, pd.DataFrame(aggregates), pd.DataFrame(label_rows)


def evaluate_paired_methods(ascent, nearest, roster, controls):
    """Compare each pair only on its own common uniquely resolved origins.

    This is not the intersection across all spatial scales. Excluded records
    retain their identity and an explicit status, never a synthetic cluster.
    """
    comparison, document_pairs, document_labels = [], [], []
    for scenario, original in ascent.groupby('scenario_id', sort=True):
        control_id = scenario+'__nearest_same_peaks'
        control = nearest[nearest.scenario_id.eq(control_id)]
        if control.empty:
            raise ValueError('Missing paired nearest control: '+scenario)
        a, av = _resolved_assignments(original, roster)
        b, bv = _resolved_assignments(control, roster)
        common = av & bv
        common_ids = set(roster.loc[common, 'source_record_id'])
        same_core = a.loc[common, 'core_id'].to_numpy() == b.loc[common, 'core_id'].to_numpy()
        comparison.append({'scenario_id': scenario, 'ascent_unique_records': int(av.sum()),
            'nearest_unique_records': int(bv.sum()), 'paired_unique_records': int(common.sum()),
            'same_core_records': int(same_core.sum()),
            'different_core_records': int((~same_core).sum()),
            'between_methods_adjusted_rand': adjusted_rand(a.loc[common, 'basin_id'], b.loc[common, 'basin_id']),
            'paired_cohort_definition': 'unique_resolved_intersection_for_this_scenario_pair'})
        for method, raw in [('population_ascent', original), ('nearest_same_peaks', control)]:
            held = raw.copy()
            excluded = ~held.source_record_id.isin(common_ids)
            held.loc[excluded, ['basin_id', 'core_id']] = None
            held.loc[excluded, 'status'] = 'paired_cohort_excluded'
            # All common records are known unique by construction.
            held['assignment_unique'] = held.source_record_id.isin(common_ids)
            held = held.drop_duplicates('source_record_id')
            _, _, pairs, labels = evaluate_partitions(held, roster, controls)
            for frame in [pairs, labels]:
                frame['parent_scenario_id'] = scenario
                frame['method'] = method
                frame['paired_unique_records'] = int(common.sum())
            document_pairs.append(pairs)
            document_labels.append(labels)
    return pd.DataFrame(comparison), pd.concat(document_pairs, ignore_index=True), pd.concat(document_labels, ignore_index=True)


def evaluate_functions(memberships, roster, links):
    """Functional locality is a diagnostic; shared geography is not trip proof."""
    selected = links[links.evidence_scenario.eq('all_dated_known')]
    if selected.duplicated(['origin_id', 'family']).any():
        raise ValueError('Repeated functional outcome in preferred source inventory')
    population = roster.set_index('source_record_id').population_2021.to_dict()
    records = []
    for r in selected.itertuples(index=False):
        if r.origin_id not in population:
            continue
        keys = json.loads(r.coequal_primary_keys_json) if pd.notna(r.coequal_primary_keys_json) else []
        records.append((r.origin_id, r.family, keys, truth(r.known_local_supply),
                        bool(pd.notna(population[r.origin_id]) and population[r.origin_id] > 0)))
    region_rows, basin_frames = [], []
    for _, group in memberships.groupby('scenario_id', sort=True):
        meta = _scenario_metadata(group)
        assignment, valid = _resolved_assignments(group, roster)
        resolved = assignment.loc[valid, 'basin_id'].to_dict()
        status = assignment.status.fillna('assignment_missing').to_dict()
        global_counts, local_counts = Counter(), Counter()
        for origin, family, keys, own, living in records:
            origin_basin = resolved.get(origin)
            scopes = []
            for key in keys:
                if not key.startswith('np:'):
                    scope = 'physical_site_np_unresolved'
                else:
                    target = key[3:]
                    if target == origin:
                        scope = 'own_point_model'
                    elif origin_basin is None:
                        scope = 'origin_population_structure_unresolved'
                    elif target not in population:
                        scope = 'destination_beyond_pilot_membership_censored'
                    elif target not in resolved:
                        scope = 'destination_population_structure_unresolved'
                    else:
                        scope = 'nonlocal_within_basin' if resolved[target] == origin_basin else 'nonlocal_other_regional_basin'
                scopes.append(scope)
            kinds = sorted(set(scopes))
            result = 'functional_destination_unknown' if not kinds else kinds[0] if len(kinds) == 1 else 'coequal_mixed_scope'
            global_counts[(family, result, status.get(origin, 'assignment_missing'), own, living)] += 1
            if origin_basin is not None:
                local_counts[(origin_basin, family, result, own, living)] += 1
        for (family, result, structure_status, own, living), count in global_counts.items():
            region_rows.append({**meta, 'family': family, 'destination_scope': result,
                'origin_structure_status': structure_status, 'known_local_supply': own,
                'inhabited_np': living, 'np_records': count,
                'shared_transport_geography_not_independent_trip_validation': True})
        local_rows = []
        for (basin, family, result, own, living), count in local_counts.items():
            local_rows.append({**meta, 'basin_id': basin, 'family': family,
                'destination_scope': result, 'known_local_supply': own,
                'inhabited_np': living, 'np_records': count,
                'observed_trip_flow': False})
        local_frame = pd.DataFrame(local_rows)
        for column in ['scenario_id', 'basin_id', 'family', 'destination_scope']:
            if column in local_frame:
                local_frame[column] = local_frame[column].astype('category')
        basin_frames.append(local_frame)
    return pd.DataFrame(region_rows), pd.concat(basin_frames, ignore_index=True) if basin_frames else pd.DataFrame()


def run(memberships, roster, functional_links, documented_school, documented_medical,
        overrides, output, paired_nearest=None):
    membership, population, links = frame(memberships), frame(roster), frame(functional_links)
    controls = documented_controls(frame(documented_school), frame(documented_medical),
                                   frame(overrides), population)
    diagnostics, pairs, doc_summary, label_scores = evaluate_partitions(membership, population, controls)
    function_summary, basin_function_summary = evaluate_functions(membership, population, links)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    tables = {'scenario_diagnostics': diagnostics, 'document_control_relations': controls,
        'document_pair_population_assignment': pairs, 'document_pair_summary': doc_summary,
        'document_label_partition_scores': label_scores,
        'functional_scope_summary': function_summary,
        'basin_functional_scope_summary': basin_function_summary}
    if paired_nearest is not None:
        paired = evaluate_paired_methods(membership, frame(paired_nearest), population, controls)
        tables.update(dict(zip(['paired_method_comparison', 'paired_document_summary',
                                'paired_document_partition_scores'], paired)))
    for name, data in tables.items():
        data.to_parquet(output/(name+'.parquet'), index=False, compression='zstd')
    report = {'schema': 'sgrt.saratov.population_structure_validation.v1',
        'population_scenarios': int(membership.scenario_id.nunique()),
        'external_inhabited_controls_by_family': controls[controls.external_relation].family.value_counts().to_dict(),
        'document_controls_used_to_construct_population_partitions': False,
        'best_scale_selected_using_document_scores': False,
        'school_inventory_enriched_using_same_document': True,
        'medical_controls_are_selected_cross_date_np_assignments_not_flows': True,
        'unknown_and_halo_assignments_are_common_basins': False,
        'functional_locality_infers_observed_trips': False,
        'all_scenarios_reported_without_count_fit': True,
        'scenarios_are_sensitivity_not_independent_replicates': True,
        'conditional_scores_use_scenario_specific_resolved_cohorts': True,
        'common_cohort_score_columns_provided_for_comparable_records': True,
        'table_rows': {name: len(data) for name, data in tables.items()},
        'limitations': ['Administrative service documents are selected controls, not a representative province-wide travel sample.',
            'Co-location can become trivial in a single large basin; between-document pair errors, ARI and null expectations are reported.',
            'The functional and population models share transport geography; functional locality is not independent evidence of trips.',
            'A destination outside the regional membership axis is censored, not automatically outside the complete spatial system.',
            'School enrichment reused its document; medical matching concerns NP destinations across source dates, not buildings, capacity or observed choice.']}
    (output/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['memberships', 'roster', 'functional-links', 'documented-school',
                'documented-medical', 'overrides', 'output']:
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--paired-nearest', type=Path, default=None)
    a = parser.parse_args()
    print(json.dumps(run(a.memberships, a.roster, a.functional_links, a.documented_school,
                         a.documented_medical, a.overrides, a.output, a.paired_nearest), ensure_ascii=False, indent=2))
