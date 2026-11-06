import json
import unittest

import numpy as np
import pandas as pd

from scripts.sgrt_saratov.regional_validation import (
    adjusted_rand, evaluate_partitions, evaluate_functions, evaluate_paired_methods)


class PopulationStructureControls(unittest.TestCase):
    def setUp(self):
        self.roster = pd.DataFrame([
            {'source_record_id': s, 'name': s, 'district_norm': 'district',
             'population_2021': 100, 'lat': 51., 'lon': 45.+i*.01}
            for i, s in enumerate('ABCD')])
        self.controls = pd.DataFrame([
            {'origin_id': s, 'core_id': core, 'family': 'school', 'control_kind': 'school',
             'source_id': 'doc', 'external_relation': s != core,
             'independence_scope': 'same_document_enrichment', 'sampling_scope': 'selected'}
            for s, core in [('A', 'A'), ('B', 'A'), ('C', 'C'), ('D', 'C')]])

    def assignments(self, groups, status='resolved_regional_peak'):
        return pd.DataFrame([
            {'scenario_id': 'scenario', 'source_record_id': s,
             'basin_id': basin, 'core_id': core, 'status': status,
             'assignment_unique': True}
            for s, basin, core in groups])

    def test_one_giant_basin_has_perfect_colocation_but_zero_adjusted_agreement(self):
        assignments = self.assignments([(s, 'giant', 'A') for s in 'ABCD'])
        diagnostics, pairs, summary, labels = evaluate_partitions(assignments, self.roster, self.controls)
        self.assertEqual(summary.iloc[0].same_basin_rate_among_resolved, 1.)
        self.assertEqual(summary.iloc[0].district_observed_minus_expected_same_basin_rate, 0.)
        self.assertEqual(summary.iloc[0].distance_conditioned_observed_minus_expected_same_basin_rate, 0.)
        self.assertEqual(labels.iloc[0].adjusted_rand_index, 0.)
        self.assertEqual(labels.iloc[0].between_document_false_merge_rate, 1.)
        self.assertEqual(labels.iloc[0].balanced_pair_accuracy, .5)
        self.assertEqual(diagnostics.iloc[0].effective_basin_number_by_record_entropy, 1.)

    def test_common_unknown_or_halo_exit_is_never_a_common_system(self):
        assignments = self.assignments([(s, 'same_exit', None) for s in 'ABCD'], 'external_halo_exit')
        diagnostics, pairs, summary, labels = evaluate_partitions(assignments, self.roster, self.controls)
        self.assertEqual(diagnostics.iloc[0].regional_basins, 0)
        self.assertEqual(summary.iloc[0].both_endpoints_resolved, 0)
        self.assertEqual(labels.iloc[0].labelled_resolved_np, 0)
        self.assertIsNone(labels.iloc[0].adjusted_rand_index)
        self.assertTrue(pairs.same_population_basin.isna().all())

    def test_false_unique_flag_preserves_unresolved_reason(self):
        assignments = self.assignments([(s, None, None) for s in 'ABCD'],
                                       'comparison_cohort_excluded')
        assignments['assignment_unique'] = False
        assignments.loc[assignments.source_record_id.eq('A'), 'status'] = 'external_halo_exit'
        diagnostics, _, _, _ = evaluate_partitions(assignments, self.roster, self.controls)
        statuses = json.loads(diagnostics.iloc[0].assignment_status_counts_json)
        self.assertEqual(statuses, {'comparison_cohort_excluded': 3, 'external_halo_exit': 1})

    def test_equal_terminal_options_are_not_forced_to_one_peak(self):
        assignments = self.assignments([('A', 'a', 'A'), ('B', 'a', 'A'),
                                        ('B', 'c', 'C'), ('C', 'c', 'C'), ('D', 'c', 'C')])
        assignments.loc[assignments.source_record_id.eq('B'), 'assignment_unique'] = False
        _, pairs, _, labels = evaluate_partitions(assignments, self.roster, self.controls)
        b = pairs[pairs.origin_id.eq('B')].iloc[0]
        self.assertFalse(b.both_resolved_regional)
        self.assertTrue(b.known_common_regional_terminal_option)
        self.assertIsNone(b.same_population_basin)
        self.assertEqual(labels.iloc[0].labelled_resolved_np, 3)

    def test_function_own_external_unknown_and_halo_membership_are_separate(self):
        assignments = self.assignments([(s, 'a' if s in 'AB' else 'c', 'A' if s in 'AB' else 'C') for s in 'ABCD'])
        links = pd.DataFrame([
            {'origin_id': s, 'family': 'medical_basic', 'evidence_scenario': 'all_dated_known',
             'known_local_supply': s == 'A', 'coequal_primary_keys_json': json.dumps(keys)}
            for s, keys in [('A', ['np:A']), ('B', ['np:HALO']), ('C', ['site:no_np']), ('D', [])]])
        region, basins = evaluate_functions(assignments, self.roster, links)
        found = region.set_index('destination_scope').np_records.to_dict()
        self.assertEqual(found, {'own_point_model': 1,
            'destination_beyond_pilot_membership_censored': 1,
            'physical_site_np_unresolved': 1, 'functional_destination_unknown': 1})
        self.assertEqual(int(region.np_records.sum()), 4)
        self.assertEqual(int(basins.np_records.sum()), 4)

    def test_paired_comparison_uses_only_same_scenario_unique_intersection(self):
        ascent = self.assignments([(s, 'a' if s in 'AB' else 'c',
                                    'A' if s in 'AB' else 'C') for s in 'ABCD'])
        nearest = ascent.copy()
        nearest['scenario_id'] += '__nearest_same_peaks'
        nearest.loc[nearest.source_record_id.eq('D'), ['core_id', 'basin_id']] = None
        nearest.loc[nearest.source_record_id.eq('D'), 'status'] = 'comparison_cohort_excluded'
        nearest.loc[nearest.source_record_id.eq('D'), 'assignment_unique'] = False
        comparison, pairs, labels = evaluate_paired_methods(ascent, nearest, self.roster, self.controls)
        self.assertEqual(comparison.iloc[0].paired_unique_records, 3)
        self.assertEqual(comparison.iloc[0].different_core_records, 0)
        self.assertTrue(labels.labelled_resolved_np.eq(3).all())
        self.assertTrue(labels.adjusted_rand_index.eq(1.).all())
        self.assertTrue(pairs.both_endpoints_resolved.eq(1).all())

    def test_adjusted_rand_rejects_missing_labels(self):
        with self.assertRaises(ValueError):
            adjusted_rand(['A', 'B'], ['a', None])
        # Published scikit-learn documentation example: crossed two-by-two
        # partitions agree less than chance, rather than merely scoring zero.
        self.assertAlmostEqual(adjusted_rand([0, 0, 1, 1], [0, 1, 0, 1]), -.5, places=12)

    def test_better_conditional_ari_from_dropped_records_is_not_model_improvement(self):
        first = self.assignments([(s, 'giant', 'A') for s in 'ABCD'])
        first['scenario_id'] = 'first'
        second = self.assignments([(s, 'giant' if s in 'AB' else None,
                                    'A' if s in 'AB' else None) for s in 'ABCD'])
        second['scenario_id'] = 'second'
        second.loc[second.source_record_id.isin(['C', 'D']), 'status'] = 'external_halo_exit'
        _, _, _, scores = evaluate_partitions(pd.concat([first, second]), self.roster, self.controls)
        scores = scores.set_index('scenario_id')
        self.assertEqual(scores.loc['first', 'adjusted_rand_index'], 0.)
        self.assertEqual(scores.loc['second', 'adjusted_rand_index'], 1.)
        self.assertTrue(scores.common_cohort_labelled_resolved_np.eq(2).all())
        self.assertTrue(scores.common_cohort_adjusted_rand_index.eq(1.).all())


if __name__ == '__main__':
    unittest.main()
