import sys
from pathlib import Path
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from service_agreement import analyse, CORE


class AgreementTests(unittest.TestCase):
    def evaluate(self, profiles):
        edges = pd.DataFrame([dict(origin_id=o, service_family=f, provider_settlement_id=p,
                                  l0_admitted=admitted)
                              for o, values in profiles.items()
                              for f, (p, admitted) in zip(CORE, values)])
        # Provider IDs, not (provider, admission) tuples, belong in the reference.
        ids = set(profiles) | {p for values in profiles.values() for p, _ in values if p}
        ref = pd.DataFrame(dict(source_record_id=sorted(ids), name=sorted(ids), region='r', lat=50., lon=40.,
                                population_2021=10., budget_population_credit=True,
                                population_role='ordinary_settlement_record', analysis_origin=True))
        return analyse(edges, ref)

    def test_unknown_identity_is_not_unanimity_or_absence(self):
        frame, _ = self.evaluate({'a': [('b', True), (None, True), ('b', True)]})
        self.assertEqual(frame.agreement_class.iloc[0], 'unknown_provider_settlement')
        self.assertTrue(pd.isna(frame.unanimous_destination_id.iloc[0]))

    def test_local_supply_limits_external_unanimity(self):
        frame, _ = self.evaluate({'a': [('b', True), ('a', True), ('b', True)]})
        self.assertEqual(frame.agreement_class.iloc[0], 'two_destinations')

    def test_rejected_route_does_not_become_third_vote(self):
        frame, _ = self.evaluate({'a': [('b', True), ('b', True), ('b', False)]})
        self.assertEqual(frame.agreement_class.iloc[0], 'partial_admission')

    def test_chain_is_not_merged_into_one_system(self):
        frame, result = self.evaluate({'a': [('b', True)] * 3, 'b': [('c', True)] * 3,
                                       'c': [('c', True)] * 3})
        self.assertEqual(result['unanimous_external_destination_count'], 2)
        self.assertEqual(dict(zip(frame.origin_id, frame.unanimous_destination_id)),
                         {'a': 'b', 'b': 'c', 'c': 'c'})
        self.assertFalse(result['exclusive_sgrt_partition_created'])


if __name__ == '__main__':
    unittest.main()
