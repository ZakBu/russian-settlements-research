import unittest
import json
import numpy as np
import pandas as pd
from scripts.sgrt_saratov.regional_controls import nearest_same_peaks


class SamePeaksControls(unittest.TestCase):
    def test_preserves_ties_and_does_not_resolve_the_censored_cohort(self):
        roster = pd.DataFrame([{'source_record_id': c, 'name': c, 'population_2021': 10,
                               'row_index': i} for i, c in enumerate('ABCD')])
        members = pd.DataFrame([{'scenario_id': 's', 'source_record_id': c,
            'core_id': core, 'status': status, 'assignment_unique': unique,
            'topology': 'radius', 'path_min_hops': 2} for c, core, status, unique in
            [('A','A','resolved_regional_peak',True), ('B','B','resolved_regional_peak',True),
             ('C','B','resolved_regional_peak',True), ('D',None,'external_halo_exit',True)]])
        costs = np.array([[0,5,8,9],[5,0,8,9],[3,3,0,9],[1,2,9,0]], dtype=float)
        control, pairs = nearest_same_peaks(members, roster, costs)
        c = control[control.source_record_id.eq('C')]
        self.assertEqual(set(c.core_id), {'A','B'})
        self.assertFalse(c.assignment_unique.any())
        self.assertTrue(c.path_min_hops.isna().all())
        d = control[control.source_record_id.eq('D')]
        self.assertEqual(d.status.tolist(), ['comparison_cohort_excluded'])
        self.assertTrue(d.core_id.isna().all())
        self.assertTrue(pairs[pairs.source_record_id.eq('C')].selected_ascent_core_is_one_of_nearest.all())

    def test_all_censored_does_not_create_a_single_control_basin(self):
        roster = pd.DataFrame([{'source_record_id': 'A', 'name': 'A',
                               'population_2021': 10, 'row_index': 0}])
        members = pd.DataFrame([{'scenario_id': 's', 'source_record_id': 'A',
            'core_id': None, 'status': 'external_halo_exit',
            'assignment_unique': True, 'topology': 'radius'}])
        control, pairs = nearest_same_peaks(members, roster, np.zeros((1,1)))
        self.assertTrue(pairs.empty)
        self.assertIn('selected_ascent_core_is_one_of_nearest', pairs)
        self.assertTrue(control.basin_id.isna().all())


if __name__ == '__main__':
    unittest.main()
