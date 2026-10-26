import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from urban_cooperation_candidates import whole_footprint_guard, territorial_comparison, COMPONENTS


class UrbanCooperationTests(unittest.TestCase):
    def test_core_inside_does_not_hide_remote_functional_member(self):
        footprint = pd.DataFrame({'unit_id':['u','u'], 'origin_id':['core','far']})
        out = whole_footprint_guard(footprint, {'core'}, pd.Series({'core':10.,'far':15.}), 30.)
        self.assertFalse(out.loc['u','whole_footprint_inside'])
        self.assertTrue(out.loc['u','whole_footprint_within_time'])

    def test_unknown_route_is_not_zero_travel(self):
        footprint = pd.DataFrame({'unit_id':['u','u'], 'origin_id':['core','unrouted']})
        out = whole_footprint_guard(footprint, {'core','unrouted'}, pd.Series({'core':10.}), 30.)
        self.assertFalse(out.loc['u','whole_footprint_road_known'])
        self.assertFalse(out.loc['u','whole_footprint_within_time'])

    def test_fast_core_does_not_hide_far_member_time(self):
        footprint = pd.DataFrame({'unit_id':['u','u'], 'origin_id':['core','far']})
        out = whole_footprint_guard(footprint, {'core','far'}, pd.Series({'core':10.,'far':75.}), 60.)
        self.assertTrue(out.loc['u','whole_footprint_inside'])
        self.assertFalse(out.loc['u','whole_footprint_within_time'])
        self.assertEqual(out.loc['u','maximum_checked_minutes'],75.)

    def test_same_municipality_never_proves_np_hierarchy(self):
        profiles = pd.DataFrame([[100.,100.,100.]],index=['m'],columns=COMPONENTS)
        self.assertEqual(territorial_comparison('m','m',profiles),
                         'same_municipal_actor_np_rank_unidentified')

    def test_unknown_worker_count_never_proves_dominance(self):
        profiles = pd.DataFrame([[np.nan,1.,10.],[100.,100.,100.]],index=['a','b'],columns=COMPONENTS)
        self.assertEqual(territorial_comparison('a','b',profiles), 'incomplete_territorial_profile')

if __name__ == '__main__':
    unittest.main()
