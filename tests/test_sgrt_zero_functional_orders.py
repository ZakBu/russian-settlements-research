import sys
import unittest
import tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from functional_orders import direct_promotion, functional_guard_members, read_route


def members(owners):
    return pd.DataFrame([{'origin_id': origin, 'unit_id': unit} for origin, unit in owners.items()])


def route(destinations):
    return pd.DataFrame([{'origin_id': origin, 'provider_settlement_id': target,
                          'cost_minutes': cost, 'road_endpoint_accepted': True}
                         for origin, (target, cost) in destinations.items()])


class FunctionalOrderTests(unittest.TestCase):
    def test_chain_does_not_silently_attach_a_to_c(self):
        m = members({'a': 'A', 'b': 'B', 'c': 'C'})
        r = route({'a': ('b', 10), 'b': ('c', 10), 'c': ('c', 0)})
        out, cross, _, _, _ = direct_promotion(m, {'f': r}, ['f'], 30, stage='f')
        mapped = out.set_index('origin_id').unit_id
        self.assertEqual(mapped['a'], 'A')
        self.assertEqual(mapped['b'], mapped['c'])
        self.assertNotEqual(mapped['a'], mapped['c'])

    def test_one_far_member_prevents_whole_child_merger(self):
        m = members({'a': 'A', 'aa': 'A', 'b': 'B'})
        r = route({'a': ('b', 5), 'aa': ('b', 31), 'b': ('b', 0)})
        out, _, c, _, _ = direct_promotion(m, {'f': r}, ['f'], 30, stage='f')
        self.assertEqual(out.set_index('origin_id').unit_id['a'], 'A')
        self.assertEqual(c.set_index('child_unit_id').candidate_status['A'], 'partial_member_or_function_coverage')

    def test_unknown_np_and_unresolved_child_are_not_invented(self):
        m = members({'a': 'A', 'b': 'B', 'unknown': None})
        r = route({'a': (None, 5), 'b': ('unknown', 5), 'unknown': ('unknown', 0)})
        out, _, _, _, _ = direct_promotion(m, {'f': r}, ['f'], 30, stage='f')
        self.assertEqual(out.unit_id.notna().sum(), 2)
        self.assertTrue(pd.isna(out.set_index('origin_id').unit_id['unknown']))
        self.assertEqual(out.set_index('origin_id').unit_id['b'], 'B')

    def test_competing_functions_do_not_become_weighted_vote(self):
        m = members({'a': 'A', 'b': 'B', 'c': 'C'})
        f = route({'a': ('b', 5), 'b': ('b', 0), 'c': ('c', 0)})
        g = route({'a': ('c', 5), 'b': ('b', 0), 'c': ('c', 0)})
        out, _, c, _, _ = direct_promotion(m, {'f': f, 'g': g}, ['f', 'g'], 30, stage='fg')
        self.assertEqual(out.set_index('origin_id').unit_id['a'], 'A')
        self.assertEqual(c.set_index('child_unit_id').candidate_status['A'], 'split_destination_systems')

    def test_actual_complete_direct_star_merges_and_preserves_origins(self):
        m = members({'a': 'A', 'aa': 'A', 'b': 'B'})
        r = route({'a': ('b', 5), 'aa': ('b', 20), 'b': ('b', 0)})
        out, cross, _, links, meta = direct_promotion(m, {'f': r}, ['f'], 30, stage='f')
        self.assertEqual(out.unit_id.nunique(), 1)
        self.assertTrue(out.origin_id.equals(m.origin_id))
        self.assertEqual(out.effective_merge_depth.tolist(), [1, 1, 1])
        self.assertTrue(links.admitted_parent_association.all())
        self.assertEqual(cross.child_unit_id.nunique(), 2)

    def test_explicit_child_only_doctor_is_not_general_provider(self):
        m = members({'a': 'A', 'b': 'B'})
        r = route({'a': ('b', 5), 'b': ('b', 0)})
        r['provider_named_child_only_contingent'] = True
        out, _, _, _, _ = direct_promotion(m, {'f': r}, ['f'], 30, stage='f')
        self.assertEqual(out.unit_id.nunique(), 2)

    def test_original_functional_overlap_is_checked_without_reassigning_it(self):
        m = members({'a': 'A', 'aa': 'OTHER', 'b': 'B'})
        # aa is a primary member of OTHER but belongs to A's original school
        # footprint. Its distant higher trip must block A, not disappear.
        service = pd.DataFrame({'centre_settlement_id': ['a', 'a'], 'origin_id': ['a', 'aa']})
        guard = functional_guard_members(m, service)
        r = route({'a': ('b', 5), 'aa': ('b', 31), 'b': ('b', 0)})
        out, _, c, _, _ = direct_promotion(m, {'f': r}, ['f'], 30, stage='f', guard_members=guard)
        self.assertEqual(out.set_index('origin_id').unit_id['a'], 'A')
        self.assertEqual(out.set_index('origin_id').unit_id['aa'], 'OTHER')
        self.assertEqual(c.set_index('child_unit_id').additional_functional_constraint_records['A'], 1)

    def test_route_projection_keeps_rejected_endpoint_and_unknown_endpoint_holds(self):
        m = members({'a': 'A', 'b': 'B'})
        r = route({'a': ('b', 5), 'b': ('b', 0)})
        r.loc[r.origin_id.eq('a'), 'road_endpoint_accepted'] = False
        r['known_local_supply'] = r.origin_id.eq('b')
        r['road_endpoint_status'] = ['rejected', 'local_proxy']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'routes.parquet'
            r.to_parquet(path, index=False)
            projected = read_route(path)
        self.assertIn('road_endpoint_status', projected)
        out, _, _, _, _ = direct_promotion(m, {'f': projected}, ['f'], 30, stage='f')
        self.assertEqual(out.unit_id.nunique(), 2)

        missing = projected.drop(columns=['road_endpoint_accepted'])
        out, _, _, _, _ = direct_promotion(m, {'f': missing}, ['f'], 30, stage='f')
        self.assertEqual(out.unit_id.nunique(), 2)

    def test_ghost_context_cannot_manufacture_a_higher_level(self):
        m = members({'a': 'A', 'ghost': 'G'})
        r = route({'a': ('a', 0), 'ghost': ('a', 5)})
        out, _, c, _, _ = direct_promotion(m, {'f': r}, ['f'], 30, stage='f',
                                           demand_origin_ids={'a'}, eligible_child_units={'A'})
        self.assertEqual(out.unit_id.nunique(), 2)
        self.assertEqual(out.effective_merge_depth.max(), 0)
        self.assertEqual(c.set_index('child_unit_id').candidate_status['G'], 'lower_unit_not_eligible_as_child')

    def test_zero_population_satellite_does_not_block_confirmed_living_demand(self):
        m = members({'a': 'A', 'zero': 'A', 'b': 'B'})
        r = route({'a': ('b', 5), 'zero': ('b', 80), 'b': ('b', 0)})
        out, _, c, _, _ = direct_promotion(m, {'f': r}, ['f'], 30, stage='f',
                                           demand_origin_ids={'a', 'b'}, eligible_child_units={'A', 'B'})
        self.assertEqual(out.unit_id.nunique(), 1)
        self.assertEqual(out.origin_id.tolist(), ['a', 'zero', 'b'])
        self.assertEqual(c.set_index('child_unit_id').active_primary_demand_records['A'], 1)


if __name__ == '__main__':
    unittest.main()
