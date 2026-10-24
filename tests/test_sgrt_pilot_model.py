"""Scientific failure modes: compulsory attachment, missing=0, duplicate supply."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location('sgrt_pilot_model', Path(__file__).resolve().parents[1]/'scripts/sgrt_pilot/model.py')
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


class FunctionalScenarioTests(unittest.TestCase):
    def setUp(self):
        self.settlements = pd.DataFrame({'source_record_id': ['rural', 'town', 'remote', 'unknown'], 'population': [20., 500., 10., 30.]})
        self.supply = pd.DataFrame({'center_id': ['rural', 'town', 'unknown'], 'function': ['medical']*3, 'service_order': ['primary']*3,
            'supply_value': [1., 2., np.nan], 'supply_status': ['proxy', 'proxy', 'unknown'], 'population': [20., 500., 30.]})
        self.costs = pd.DataFrame({'origin_id': ['rural', 'town', 'unknown', 'unknown', 'remote'], 'destination_id': ['town', 'rural', 'town', 'rural', 'town'],
            'cost_minutes': [10., 10., 12., 12., 500.], 'route_status': ['routed']*5})

    def run_model(self, **kwargs):
        origins, supply, costs = model.prepare_inputs(self.settlements, self.supply, self.costs, 'medical', 'primary')
        config = dict(function='medical', service_order='primary', model='functional', family='exponential', half_life_minutes=30., kernel_floor=.05)
        config.update(kwargs)
        return model.evaluate_scenario(origins, supply, costs, **config)

    def test_missing_local_supply_never_becomes_absent(self):
        result, _ = self.run_model()
        row = result.set_index('source_record_id').loc['unknown']
        self.assertEqual(row.local_supply_status, 'unknown')
        self.assertTrue(row.missing_local_supply_could_change_choice)
        self.assertEqual(row.outcome, 'external_candidate_local_supply_unknown')
        self.assertFalse(result.established_external_link.any())

    def test_remote_origin_not_forced_to_relative_winner(self):
        result, _ = self.run_model()
        remote = result.set_index('source_record_id').loc['remote']
        self.assertTrue(pd.isna(remote.primary_candidate_id))
        self.assertEqual(remote.outcome, 'no_positive_candidate_after_scenario_screen')

    def test_no_recorded_route_is_unknown_not_unreachable(self):
        self.costs = self.costs.loc[self.costs.origin_id != 'remote']
        result, _ = self.run_model()
        remote = result.set_index('source_record_id').loc['remote']
        self.assertEqual(remote.outcome, 'no_recorded_route_to_known_supply')
        self.assertTrue(remote.outside_route_sample_unknown)

    def test_local_provider_is_option_not_compulsory_external_attachment(self):
        result, _ = self.run_model(model='nearest')
        row = result.set_index('source_record_id').loc['rural']
        self.assertEqual(row.primary_candidate_id, 'rural')
        self.assertEqual(row.outcome, 'local_candidate_preferred')

    def test_competing_directions_are_kept(self):
        _, links = self.run_model()
        candidates = links.loc[links.origin_id == 'unknown']
        self.assertEqual(set(candidates.destination_id), {'rural', 'town'})
        self.assertAlmostEqual(candidates.conditional_share.sum(), 1.)
        self.assertTrue((candidates.conditional_share > 0).all())

    def test_supply_does_not_change_after_attracting_demand(self):
        before = self.supply.copy(deep=True)
        self.run_model()
        pd.testing.assert_frame_equal(before, self.supply)

    def test_duplicate_center_rejected(self):
        self.supply = pd.concat([self.supply, self.supply.iloc[[0]]])
        with self.assertRaises(ValueError):
            self.run_model()

    def test_kernel_families_share_half_life_but_not_tail(self):
        for family in ['exponential', 'power']:
            np.testing.assert_allclose(model.decay([0, 30], 30, family), [1., .5])
        self.assertNotAlmostEqual(model.decay([150.], 30, 'exponential')[0], model.decay([150.], 30, 'power')[0])

    def test_uncredited_population_is_unknown_mass_not_zero(self):
        self.supply['working_credit_present'] = [False, True, False]
        _, providers, _ = model.prepare_inputs(self.settlements, self.supply, self.costs, 'medical', 'primary')
        self.assertTrue(pd.isna(providers.set_index('center_id').loc['rural', 'population']))
        self.assertEqual(providers.set_index('center_id').loc['rural', 'supply_value'], 1.)

    def test_external_nonadditive_context_can_supply_but_not_become_origin(self):
        self.supply['working_credit_present'] = [True, True, False]
        self.supply['population_role'] = 'settlement_census_observation'
        context = pd.DataFrame({'center_id': ['ctx:city'], 'function': ['medical'], 'service_order': ['primary'], 'supply_value': [2.],
            'supply_status': ['proxy'], 'population': [1000000.], 'working_credit_present': [False], 'population_role': ['external_context_nonadditive']})
        self.supply = pd.concat([self.supply, context], ignore_index=True)
        self.costs = pd.concat([self.costs, pd.DataFrame({'origin_id': ['rural'], 'destination_id': ['ctx:city'], 'cost_minutes': [15.], 'route_status': ['routed']})])
        result, _ = self.run_model(model='population')
        self.assertNotIn('ctx:city', result.source_record_id.tolist())
        self.assertEqual(result.set_index('source_record_id').loc['rural', 'primary_candidate_id'], 'ctx:city')

    def test_positive_value_with_unknown_status_is_not_known_supply(self):
        self.supply.loc[self.supply.center_id == 'unknown', 'supply_value'] = 99.
        result, links = self.run_model()
        self.assertNotIn('unknown', links.destination_id.tolist())
        self.assertEqual(result.set_index('source_record_id').loc['unknown', 'local_supply_status'], 'unknown')

    def test_zero_confirmed_absence_does_not_create_a_provider(self):
        self.supply.loc[self.supply.center_id == 'unknown', ['supply_value', 'supply_status']] = [0., 'confirmed_absent']
        result, links = self.run_model()
        self.assertNotIn('unknown', links.destination_id.tolist())
        self.assertEqual(result.set_index('source_record_id').loc['unknown', 'local_supply_status'], 'confirmed_absent')

    def test_finite_cost_cannot_claim_unreachable(self):
        self.costs.loc[0, 'route_status'] = 'unreachable'
        with self.assertRaises(ValueError):
            self.run_model()

    def test_stability_does_not_become_observed_link(self):
        a, _ = self.run_model(half_life_minutes=15.)
        b, _ = self.run_model(half_life_minutes=60.)
        stability = model.scenario_stability(pd.concat([a, b], ignore_index=True))
        self.assertFalse(stability.established_external_link.any())
        self.assertTrue((stability.scenario_count == 2).all())


if __name__ == '__main__':
    unittest.main()
