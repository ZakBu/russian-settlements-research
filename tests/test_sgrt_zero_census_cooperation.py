import sys
import unittest
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from census_cooperation_diagnostics import identified_parent_share_bounds, partitioned_parent_upper_bound,run


class CensusCooperationTests(unittest.TestCase):
    def test_high_outbound_share_does_not_name_destination(self):
        lower,upper=identified_parent_share_bounds(100,40,5)
        self.assertEqual(lower,0.)
        self.assertEqual(upper,.45)

    def test_one_parent_cannot_receive_two_subject_categories(self):
        # Real published Kamensk2010 margins. Outbound alone permits15%,
        # while the subject partition excludes every individual Russian NP.
        _,loose=identified_parent_share_bounds(2783,459,27)
        sharp=partitioned_parent_upper_bound(2783,381,78,27)
        self.assertGreater(loose,.15)
        self.assertLess(sharp,.15)

    def test_unknown_workplace_is_not_zero(self):
        self.assertGreater(partitioned_parent_upper_bound(100,10,0,10),.15)

    def test_unknown_origin_denominator_rejected(self):
        with self.assertRaises(ValueError):
            partitioned_parent_upper_bound(0,10,0,0)

    def test_inconsistent_margins_are_not_clipped_to_one(self):
        with self.assertRaises(ValueError):
            identified_parent_share_bounds(100,90,20)
        with self.assertRaises(ValueError):
            partitioned_parent_upper_bound(100,50,40,20)

    def test_nonfinite_margin_is_rejected(self):
        with self.assertRaises(ValueError):
            identified_parent_share_bounds(float('nan'),10,0)

    def test_invalid_threshold_is_rejected_before_reading_data(self):
        for threshold in [-.1,1.1,float('nan')]:
            with self.assertRaises(ValueError):
                run(SimpleNamespace(threshold=threshold))


if __name__=='__main__':
    unittest.main()
