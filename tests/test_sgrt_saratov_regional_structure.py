import unittest
import numpy as np
import pandas as pd
from scripts.sgrt_saratov.regional_structure import ascent_scenario, full_radius_edges


class PopulationAscentScenarios(unittest.TestCase):
    def calculate(self, values, arcs, *, k=1, h=10, topology='fixed_knn', halo=None):
        roster = pd.DataFrame([{'source_record_id': i, 'name': i,
                               'population_2021': max(0, v)} for i, v in values.items()])
        field = pd.DataFrame([{'source_record_id': i, 'value': v,
                              'accepted_mass_field_upper': v} for i, v in values.items()])
        outside = pd.DataFrame([{'source_record_id': i, 'value': v,
                               'accepted_mass_field_upper': v} for i, v in (halo or {}).items()],
                              columns=['source_record_id', 'value', 'accepted_mass_field_upper'])
        neighbours = pd.DataFrame([{'origin_id': a, 'destination_id': b, 'minutes': t,
                                    'in_k1': True, 'in_k2': True, 'in_k6': True}
                                   for a, b, t in arcs])
        return ascent_scenario(roster, field, outside, neighbours, kernel='exponential',
            half_time=h, neighbour_count=k, topology=topology)

    def test_local_graph_can_stop_a_long_comparison_jump_but_is_not_a_service_proof(self):
        values = {'A': 1, 'B': 10, 'C': 100}
        arcs = [('A', 'B', 1), ('A', 'C', 101), ('B', 'A', 1),
                ('B', 'C', 100), ('C', 'A', 101), ('C', 'B', 100)]
        fixed, _ = self.calculate(values, arcs, k=2)
        local, _ = self.calculate(values, arcs, k=2, topology='scale_local')
        self.assertEqual(fixed.set_index('source_record_id').loc['A', 'core_id'], 'C')
        self.assertEqual(local.set_index('source_record_id').loc['A', 'core_id'], 'B')
        c = local[local.source_record_id.eq('C')].iloc[0]
        self.assertEqual(c.status, 'no_neighbours_at_scale')
        self.assertTrue(pd.isna(c.core_id))
        self.assertFalse(local.proves_functional_system.any())

    def test_equal_best_slopes_retain_both_peaks_without_id_tiebreak(self):
        m, e = self.calculate({'A': 1, 'B': 3, 'C': 3},
            [('A', 'B', 1), ('A', 'C', 1), ('B', 'A', 1), ('C', 'A', 1)])
        a = m[m.source_record_id.eq('A')]
        self.assertEqual(set(a.core_id), {'B', 'C'})
        self.assertFalse(a.assignment_unique.any())
        self.assertEqual(set(e[e.origin_id.eq('A')].destination_id), {'B', 'C'})

    def test_flat_and_zero_time_comparisons_are_explicitly_ambiguous(self):
        plateau, _ = self.calculate({'A': 2, 'B': 2}, [('A', 'B', 1), ('B', 'A', 1)])
        self.assertTrue(plateau.status.eq('plateau_ambiguous').all())
        self.assertTrue(plateau.core_id.isna().all())
        coincident, _ = self.calculate({'A': 1, 'B': 2}, [('A', 'B', 0), ('B', 'A', 1)])
        self.assertEqual(coincident.set_index('source_record_id').loc['A', 'status'],
                         'zero_cost_comparison_ambiguous')

    def test_halo_exit_is_not_an_external_peak_or_a_complete_basin(self):
        m, _ = self.calculate({'A': 1}, [('A', 'H', 1)], halo={'H': 5})
        self.assertEqual(m.iloc[0].status, 'external_halo_exit')
        self.assertEqual(m.iloc[0].exit_id, 'H')
        self.assertTrue(pd.isna(m.iloc[0].core_id))
        self.assertTrue(pd.isna(m.iloc[0].basin_id))

    def test_unknown_field_and_incomplete_comparison_do_not_become_peaks(self):
        m, _ = self.calculate({'A': 1, 'B': np.nan}, [('A', 'B', 1), ('B', 'A', 1)])
        self.assertEqual(m.set_index('source_record_id').loc['A', 'status'], 'comparison_incomplete')
        self.assertEqual(m.set_index('source_record_id').loc['B', 'status'], 'unknown_field')
        sparse, _ = self.calculate({'A': 2, 'B': 1}, [('A', 'B', 100), ('B', 'A', 100)],
                                  k=2, topology='scale_local')
        self.assertTrue(sparse.status.eq('comparison_incomplete').all())

    def test_equal_gradient_paths_to_same_peak_keep_their_cost_range(self):
        m, _ = self.calculate({'A': 0, 'B': 2, 'C': 4, 'D': 5},
            [('A', 'B', 1), ('A', 'C', 2), ('B', 'D', 1), ('C', 'D', 1), ('D', 'C', 1)])
        a = m[m.source_record_id.eq('A')].iloc[0]
        self.assertTrue(a.assignment_unique)
        self.assertEqual(a.core_id, 'D')
        self.assertEqual(a.path_min_comparison_minutes, 2)
        self.assertEqual(a.path_max_comparison_minutes, 3)
        self.assertFalse(a.comparison_path_is_shortest_origin_peak_route)

    def test_full_radius_removes_a_false_knn_sink_without_population_count_fit(self):
        roster = pd.DataFrame([{'source_record_id': i, 'name': i, 'population_2021': v,
                                'row_index': j} for j, (i, v) in enumerate([('A', 1), ('B', 5), ('C', 10)])])
        field = pd.DataFrame([{'source_record_id': r.source_record_id, 'value': r.population_2021,
                               'accepted_mass_field_upper': r.population_2021}
                              for r in roster.itertuples(index=False)])
        halo = field.iloc[:0].copy()
        reference = pd.DataFrame([{'origin_id': a, 'destination_id': b, 'minutes': t,
                                   'in_k1': True, 'in_k6': True}
                                  for a, b, t in [('A', 'B', 1), ('B', 'A', 1), ('C', 'B', 1)]])
        fixed, _ = ascent_scenario(roster, field, halo, reference, kernel='exponential',
            half_time=3, neighbour_count=1, topology='fixed_knn')
        costs = np.array([[0., 1., 2.], [1., 0., 1.], [2., 1., 0.]])
        radius, _ = ascent_scenario(roster, field, halo, full_radius_edges(roster, costs, 3),
            kernel='exponential', half_time=3, neighbour_count=0, topology='full_radius',
            national_neighbour_reference=reference)
        self.assertEqual(fixed.set_index('source_record_id').loc['B', 'core_id'], 'B')
        self.assertEqual(radius.set_index('source_record_id').loc['B', 'core_id'], 'C')

    def test_full_radius_border_censor_and_uncompared_sample_are_distinct(self):
        roster = pd.DataFrame([{'source_record_id': 'A', 'name': 'A', 'population_2021': 100}])
        field = pd.DataFrame([{'source_record_id': 'A', 'value': 100., 'accepted_mass_field_upper': 100.}])
        halo = field.iloc[:0].copy()
        reference = pd.DataFrame(columns=['origin_id', 'destination_id', 'minutes', 'in_k6'])
        arcs = full_radius_edges(roster, np.array([[0.]]), 10)
        singleton, _ = ascent_scenario(roster, field, halo, arcs, kernel='exponential',
            half_time=10, neighbour_count=0, topology='full_radius', national_neighbour_reference=reference)
        self.assertEqual(singleton.iloc[0].status, 'sampled_peak_without_nonself_comparators')
        self.assertEqual(singleton.iloc[0].core_id, 'A')
        self.assertFalse(singleton.iloc[0].terminal_has_nonself_comparison_support)
        censored, _ = ascent_scenario(roster, field, halo, arcs, kernel='exponential',
            half_time=10, neighbour_count=0, topology='full_radius',
            national_neighbour_reference=reference, censored_origins={'A'})
        self.assertEqual(censored.iloc[0].status, 'external_neighbourhood_censored')
        self.assertTrue(pd.isna(censored.iloc[0].core_id))
        self.assertTrue(pd.isna(censored.iloc[0].exit_id))


if __name__ == '__main__':
    unittest.main()
