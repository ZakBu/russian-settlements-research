import sys
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from common_economic_context import describe, AGRI, WORKFORCE


def inputs():
    members = pd.DataFrame({'origin_id': ['a', 'b', 'c'], 'unit_id': ['u', 'u', None],
                            'positive_whole_origin': [True, True, True]})
    units = pd.DataFrame({'unit_id': ['u']})
    context = pd.DataFrame({'source_record_id': ['a', 'b', 'c'],
        'agri_municipality_code': ['m', 'm', 'n'], 'agri_parent_match_status': 'matched',
        AGRI[0]: [100., 100., None], AGRI[1]: [None, None, None],
        AGRI[2]: [20., 20., None], WORKFORCE: [0., None, 5.],
        'partial_workforce_status': ['observed_partial_organisation_workforce', 'source_suppressed',
                                     'observed_partial_organisation_workforce'],
        'partial_workforce_observation_year': [2025, None, 2025],
        'partial_workforce_source_id': 'source'})
    return members, units, context


class EconomicContextTests(unittest.TestCase):
    def test_repeated_municipality_remains_one_context_not_200_ha(self):
        tables, summary = describe(*inputs())
        profile = tables['unit_municipal_context']
        self.assertEqual(len(profile), 1)
        self.assertEqual(profile[AGRI[0]].iloc[0], 100.)
        self.assertEqual(profile.member_records_sharing_context.iloc[0], 2)
        self.assertFalse(summary['municipal_values_or_workforce_values_summed'])

    def test_zero_is_observation_suppression_and_unassigned_are_retained(self):
        tables, summary = describe(*inputs())
        desc = tables['unit_economic_context'].iloc[0]
        self.assertEqual(desc.members_with_partial_workforce_2025_observation, 1)
        self.assertEqual(desc.members_with_suppressed_workforce_2025, 1)
        self.assertEqual(desc.members_with_cattle_2021_context, 0)
        self.assertEqual(summary['unassigned_origin_records'], 1)
        self.assertEqual(len(tables['economic_memberships']), 3)
        self.assertTrue(pd.isna(tables['unit_municipal_context'][AGRI[1]].iloc[0]))

    def test_duplicate_source_identity_is_rejected_before_join(self):
        members, units, context = inputs()
        with self.assertRaisesRegex(ValueError, 'join multiplication'):
            describe(members, units, pd.concat([context, context.iloc[[0]]]))

    def test_conflicting_municipal_values_are_not_silently_chosen(self):
        members, units, context = inputs()
        context.loc[1, AGRI[0]] = 200.
        with self.assertRaisesRegex(ValueError, 'Conflicting values'):
            describe(members, units, context)

    def test_wrong_observation_year_does_not_become_2025(self):
        members, units, context = inputs()
        context.loc[0, 'partial_workforce_observation_year'] = 2024
        with self.assertRaisesRegex(ValueError, 'actual year 2025'):
            describe(members, units, context)


if __name__ == '__main__':
    unittest.main()
