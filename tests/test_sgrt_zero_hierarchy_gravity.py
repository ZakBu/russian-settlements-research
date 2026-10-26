import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.sparse import csr_matrix
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from hierarchy_gravity_candidates import costs_to_targets, relative_potentials


class HierarchyGravityTests(unittest.TestCase):
    def test_reverse_search_preserves_directed_origin_to_destination_cost(self):
        # a->b=5; b->a=50. Reversing the query rather than the physical trip
        # must retain the five-minute origin a -> destination b relation.
        graph = csr_matrix(np.array([[0., 5.], [50., 0.]]))
        endpoints = pd.DataFrame({'source_record_id': ['a', 'b'], 'road_node_index': [0, 1],
                                  'snap_km': [0., 0.], 'road_endpoint_accepted': [True, True]})
        out = costs_to_targets(graph, endpoints, ['b'], network_limit_minutes=10)
        self.assertEqual(out.set_index('origin_id').cost_minutes['a'], 5.)
        self.assertEqual(out.set_index('origin_id').cost_minutes['b'], 0.)

    def test_unknown_mass_does_not_force_a_parent(self):
        profile = pd.DataFrame({'source_record_id': ['a', 'b'], 'addresses': [np.nan, 100.]})
        pairs = pd.DataFrame({'origin_id': ['a'], 'destination_id': ['b'], 'cost_minutes': [10.]})
        out = relative_potentials(profile, pairs, mass_column='addresses', half_life_minutes=20)
        self.assertTrue(pd.isna(out.relative_potential_to_local_reservation.iloc[0]))
        self.assertEqual(out.status.iloc[0], 'unknown_mass_not_zero')
        self.assertFalse(out.territorial_assignment_established.iloc[0])

    def test_weak_remote_candidate_does_not_win_by_being_the_only_option(self):
        profile = pd.DataFrame({'source_record_id': ['a', 'b'], 'addresses': [10., 11.]})
        pairs = pd.DataFrame({'origin_id': ['a'], 'destination_id': ['b'], 'cost_minutes': [120.]})
        out = relative_potentials(profile, pairs, mass_column='addresses', half_life_minutes=20)
        self.assertFalse(out.beats_local_proxy_reservation.iloc[0])
        self.assertFalse(out.territorial_assignment_established.iloc[0])


if __name__ == '__main__':
    unittest.main()
