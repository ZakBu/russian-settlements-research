"""Regression tests for service-level local accessibility, not empirical SGRT."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location('sgrt_local_assignment', Path(__file__).resolve().parents[1]/'scripts/sgrt_local/assignment.py')
assignment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assignment)


class ServiceAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.origins = pd.DataFrame({'source_record_id': ['village', 'hamlet', 'town']})
        self.supply = pd.DataFrame({
            'provider_id': ['village_school', 'town_school', 'town_hospital'],
            'source_record_id': ['village', 'town', 'town'],
            'service_code': ['school_primary', 'school_primary', 'medical_specialist'],
            'supply_status': ['observed']*3,
            'capacity_total': [np.nan, 1000., 100.],
            'object_count': [1, 100, 20],
        })
        self.costs = pd.DataFrame({
            'origin_id': ['village', 'village', 'hamlet', 'hamlet', 'hamlet'],
            'provider_id': ['town_school', 'town_hospital', 'village_school', 'town_school', 'town_hospital'],
            'cost_minutes': [90., 95., 8., 80., 85.],
        })

    def run_baseline(self, **kwargs):
        return assignment.assign_nearest(self.origins, self.supply, self.costs, **kwargs)

    def one(self, outcomes, origin, service):
        return outcomes.loc[outcomes.origin_id.eq(origin) & outcomes.service_code.eq(service)].iloc[0]

    def test_hundred_city_schools_do_not_displace_local_school(self):
        out, candidates = self.run_baseline()
        row = self.one(out, 'village', 'school_primary')
        self.assertEqual(row.selected_provider_id, 'village_school')
        self.assertEqual(row.assignment_status, 'local_candidate')
        self.assertEqual(row.route_basis, 'same_settlement_zero_assumption')
        self.assertTrue(pd.isna(row.selected_capacity_total))
        self.assertEqual(row.selected_capacity_status, 'unknown')
        self.assertFalse(row.established_flow)

    def test_hamlet_chooses_small_nearby_site_not_large_distant_town(self):
        out, _ = self.run_baseline()
        self.assertEqual(self.one(out, 'hamlet', 'school_primary').selected_provider_id, 'village_school')

    def test_higher_service_is_additional_and_does_not_erase_local(self):
        out, _ = self.run_baseline()
        village = out.loc[out.origin_id.eq('village')]
        self.assertEqual(len(village), 2)
        self.assertEqual(self.one(out, 'village', 'school_primary').selected_provider_id, 'village_school')
        self.assertEqual(self.one(out, 'village', 'medical_specialist').selected_provider_id, 'town_hospital')
        self.assertEqual(self.one(out, 'village', 'medical_specialist').assignment_status, 'external_candidate')

    def test_medical_site_does_not_supply_school_service(self):
        self.supply.loc[self.supply.provider_id.eq('town_hospital'), 'capacity_total'] = 100000.
        self.costs.loc[self.costs.provider_id.eq('town_hospital'), 'cost_minutes'] = 1.
        out, candidates = self.run_baseline()
        self.assertFalse(((candidates.service_code == 'school_primary') & (candidates.provider_id == 'town_hospital')).any())
        self.assertEqual(self.one(out, 'hamlet', 'school_primary').selected_provider_id, 'village_school')

    def test_unlisted_needed_service_remains_unresolved(self):
        out, _ = self.run_baseline(service_codes=['school_primary', 'medical_dentist'])
        row = self.one(out, 'hamlet', 'medical_dentist')
        self.assertTrue(pd.isna(row.selected_provider_id))
        self.assertEqual(row.assignment_status, 'unresolved_no_known_eligible_provider')
        self.assertEqual(row.local_supply_status, 'unknown')

    def test_unknown_presence_does_not_become_absence_or_provider(self):
        self.supply.loc[self.supply.provider_id.eq('village_school'), 'supply_status'] = 'unknown'
        out, _ = self.run_baseline()
        row = self.one(out, 'village', 'school_primary')
        self.assertEqual(row.selected_provider_id, 'town_school')
        self.assertEqual(row.local_supply_status, 'unknown')
        self.assertTrue(row.local_supply_unknown_could_change_choice)

    def test_proxy_supply_requires_explicit_sensitivity(self):
        self.supply.loc[self.supply.provider_id.eq('village_school'), 'supply_status'] = 'proxy'
        out, _ = self.run_baseline()
        self.assertEqual(self.one(out, 'hamlet', 'school_primary').selected_provider_id, 'town_school')
        alternate, _ = self.run_baseline(allow_proxy=True)
        self.assertEqual(self.one(alternate, 'hamlet', 'school_primary').selected_provider_id, 'village_school')

    def test_capacity_is_not_allocated_or_assumed_infinite(self):
        out, candidates = self.run_baseline()
        self.assertTrue((out.capacity_feasibility == 'not_estimated').all())
        self.assertTrue((candidates.capacity_feasibility == 'not_estimated').all())
        self.assertTrue(candidates.loc[candidates.provider_id.eq('village_school'), 'capacity_total'].isna().all())

    def test_equal_cost_is_not_broken_by_identifier_or_population(self):
        self.costs.loc[(self.costs.origin_id == 'hamlet') & self.costs.provider_id.eq('town_school'), 'cost_minutes'] = 8.
        out, candidates = self.run_baseline()
        row = self.one(out, 'hamlet', 'school_primary')
        self.assertEqual(row.assignment_status, 'unresolved_equal_cost_candidates')
        self.assertEqual(row.tied_count, 2)
        self.assertTrue(pd.isna(row.selected_provider_id))
        selected = candidates.loc[candidates.origin_id.eq('hamlet') & candidates.service_code.eq('school_primary') & candidates.selected_nearest]
        self.assertEqual(set(selected.provider_id), {'village_school', 'town_school'})

    def test_missing_route_does_not_become_unreachable(self):
        self.costs = self.costs.loc[~self.costs.origin_id.eq('hamlet')]
        out, _ = self.run_baseline()
        row = self.one(out, 'hamlet', 'school_primary')
        self.assertEqual(row.assignment_status, 'unresolved_no_admissible_recorded_cost')
        self.assertTrue(row.outside_known_supply_unknown)

    def test_explicit_missing_local_route_is_not_replaced_with_zero(self):
        self.costs.loc[len(self.costs)] = ['village', 'village_school', np.nan]
        out, candidates = self.run_baseline()
        row = self.one(out, 'village', 'school_primary')
        self.assertEqual(row.selected_provider_id, 'town_school')
        self.assertEqual(row.local_supply_status, 'known_service_present')
        self.assertFalse(((candidates.origin_id == 'village') & candidates.provider_id.eq('village_school')).any())

    def test_confirmed_absence_is_distinct_from_unknown(self):
        self.supply.loc[self.supply.provider_id.eq('village_school'), 'supply_status'] = 'confirmed_absent'
        out, _ = self.run_baseline()
        self.assertEqual(self.one(out, 'village', 'school_primary').local_supply_status, 'confirmed_absent_in_input')
        self.assertEqual(self.one(out, 'hamlet', 'school_primary').local_supply_status, 'unknown')

    def test_explicit_screen_does_not_force_distant_assignment(self):
        out, _ = self.run_baseline(max_cost_minutes=60)
        row = self.one(out, 'village', 'medical_specialist')
        self.assertEqual(row.assignment_status, 'unresolved_no_admissible_recorded_cost')
        self.assertEqual(row.max_cost_minutes, 60.)

    def test_recorded_np_zero_assumption_and_transport_metadata_remain_visible(self):
        self.costs['same_settlement_zero_cost_assumption'] = False
        self.costs['transport_source_id'] = 'test_graph_not_observed_trips'
        self.costs.loc[len(self.costs)] = ['village', 'village_school', 0., True, 'test_graph_not_observed_trips']
        out, candidates = self.run_baseline()
        row = self.one(out, 'village', 'school_primary')
        self.assertEqual(row.route_basis, 'same_settlement_zero_assumption')
        local = candidates.loc[candidates.origin_id.eq('village') & candidates.provider_id.eq('village_school')].iloc[0]
        self.assertEqual(local.transport_source_id, 'test_graph_not_observed_trips')
        self.assertTrue(local.same_settlement_zero_cost_assumption)
        self.assertFalse(local.route_is_observed_trip)

    def test_duplicate_supply_is_not_counted_as_extra_mass(self):
        self.supply = pd.concat([self.supply, self.supply.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, 'duplicate provider/service'):
            self.run_baseline()

    def test_service_specific_route_does_not_leak_between_services(self):
        self.costs['service_code'] = ['school_primary', 'medical_specialist', 'school_primary', 'school_primary', 'medical_dentist']
        out, candidates = self.run_baseline()
        self.assertEqual(self.one(out, 'hamlet', 'medical_specialist').assignment_status, 'unresolved_no_admissible_recorded_cost')
        self.assertEqual(self.one(out, 'hamlet', 'school_primary').selected_provider_id, 'village_school')


if __name__ == '__main__':
    unittest.main()
