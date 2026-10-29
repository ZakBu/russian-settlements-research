import unittest
import numpy as np
import pandas as pd
from scripts.sgrt_saratov.compare_school_addition import compare_tables


def example(school_times):
    rows=[]
    for family,times in [('school',school_times),('grocery',[5.,15.])]:
        for origin,pop,time in zip(['a','b'],[50.,100.],times):
            rows.append({'origin_id':origin,'family':family,'evidence_scenario':'all_dated_known',
                'cost_minutes':time,'population_2021':pop})
    return pd.DataFrame(rows)


class SchoolAdditionComparisonTests(unittest.TestCase):
    def test_aggregate_improvement_cannot_hide_one_worsening_origin(self):
        before=example([10.,30.]);after=example([11.,0.])
        self.assertLess(after[after.family.eq('school')].cost_minutes.median(),
                        before[before.family.eq('school')].cost_minutes.median())
        result=compare_tables(before,after)
        self.assertEqual(result['increased_rows'],1)
        self.assertGreater(result['violations'],0)

    def test_unknown_cost_stays_unknown_instead_of_becoming_zero(self):
        result=compare_tables(example([np.nan,30.]),example([np.nan,20.]))
        self.assertEqual(result['violations'],0)
        self.assertEqual(result['unavailable_cost_rows_before'],1)
        self.assertEqual(result['known_before_and_after_rows'],1)
        self.assertEqual(result['strictly_decreased_rows'],1)
        changed=compare_tables(example([np.nan,30.]),example([0.,20.]))
        self.assertFalse(changed['NA_masks_identical'])
        self.assertEqual(changed['newly_known_cost_rows'],1)
        self.assertGreater(changed['violations'],0)

    def test_other_function_changes_are_rejected(self):
        before=example([10.,30.]);after=example([5.,20.])
        after.loc[after.family.eq('grocery')&after.origin_id.eq('a'),'cost_minutes']=6.
        result=compare_tables(before,after)
        self.assertFalse(result['other_functions_all_columns_exact'])
        self.assertGreater(result['violations'],0)

    def test_missing_or_duplicate_origin_identity_is_rejected(self):
        before=example([10.,30.])
        with self.assertRaises(ValueError):compare_tables(before,before.iloc[:-1])
        with self.assertRaises(ValueError):compare_tables(before,pd.concat([before,before.iloc[:1]]))

if __name__=='__main__':unittest.main()
