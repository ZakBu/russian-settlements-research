import unittest

import pandas as pd

from scripts.sgrt_saratov.system_primary2010 import compare_profiles


class Primary2010Sensitivity(unittest.TestCase):
    def test_newly_available_trajectory_is_not_counted_as_a_changed_comparable_type(self):
        rows = []
        for identity in ['a', 'b']:
            row = dict(system_id=identity, family='documented_school_assignment_2025',
                       centre_id='core-' + identity, regional_external_origins=1,
                       documented_membership_complete=True,
                       centre_trajectory_2002_2010_2021_accepted='decline__decline' if identity=='a' else 'unknown',
                       rural_external_trajectory_2002_2010_2021_accepted='unchanged__decline' if identity=='a' else 'decline__decline',
                       centre_trajectory_2002_2010_2021_strict='unknown',
                       rural_external_trajectory_2002_2010_2021_strict='unknown',
                       classifiable_full_documented_three_census_system_strict=False)
            for mode in ['accepted','strict']:
                for scope in ['centre','external','rural_external']:
                    row[f'{scope}_direction_2002_2021_{mode}'] = 'decline'
            rows.append(row)
        baseline = pd.DataFrame(rows)
        auxiliary = baseline.copy()
        for column in ['centre_trajectory_2002_2010_2021_accepted',
                       'rural_external_trajectory_2002_2010_2021_accepted',
                       'centre_trajectory_2002_2010_2021_strict',
                       'rural_external_trajectory_2002_2010_2021_strict']:
            auxiliary[column] = 'decline__decline'
        auxiliary['classifiable_full_documented_three_census_system_strict'] = True
        # Filtering a mixed documented/model Parquet may change only this
        # column's dtype; semantic equality must not reject identical geometry.
        baseline['documented_membership_complete'] = baseline.documented_membership_complete.astype(object)
        comparison, summary = compare_profiles(baseline,auxiliary)
        counts = summary['documented_school_assignment_2025']
        self.assertEqual(counts['accepted_trajectory_comparable_geocoded_subsets'],1)
        self.assertEqual(counts['accepted_trajectory_changed_geocoded_subsets'],1)
        self.assertEqual(counts['primary_numeric_three_census_full_document_baseline'],0)
        self.assertEqual(counts['primary_numeric_three_census_full_document_auxiliary'],2)
        newly_known = comparison.set_index('system_id').loc['b']
        self.assertFalse(newly_known.accepted_trajectory_comparable_in_both)
        self.assertFalse(newly_known.accepted_trajectory_changed_among_comparable)


if __name__ == '__main__':
    unittest.main()
