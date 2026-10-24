"""Mass-screen regressions: units remain conditional, service rules stay separate."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

SPEC=importlib.util.spec_from_file_location('mass_audit',Path(__file__).resolve().parents[1]/'scripts/sgrt_mass/audit.py')
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)


class MassAuditTests(unittest.TestCase):
    def setUp(self):
        self.nodes=pd.DataFrame({'source_record_id':['rural','town','far','near'], 'name':['Rural','Town','Far','Near'],
            'region':['A']*4, 'settlement_type':['деревня','город','село','деревня'],
            'lat':[55.,55.1,57.,55.0001], 'lon':[40.,40.,40.,40.]})
        self.rows=pd.DataFrame({'origin_id':['rural','town','far'],
            'provider_settlement_id':['town','town','town'],
            'service_code':['medical_basic_primary']*3,
            'cost_minutes':[20.,0.,150.],
            'local_supply_status':['unknown','known_service_present','unknown']})

    def test_long_fap_link_is_preserved_but_not_a_screened_unit_member(self):
        result=audit.classify_service_screen(self.rows,self.nodes)
        self.assertEqual(result.loc[result.origin_id.eq('far'),'screen_class'].iloc[0],'outside_transport_benchmark')
        self.assertFalse(result.loc[result.origin_id.eq('far'),'screened_external_candidate'].iloc[0])
        self.assertEqual(len(result),3)
        units=audit.aggregate_units(result)
        self.assertEqual(units.external_records.iloc[0],1)
        self.assertFalse(units.established_sgrt.any())

    def test_short_unknown_local_remains_conditional(self):
        result=audit.classify_service_screen(self.rows,self.nodes)
        row=result.loc[result.origin_id.eq('rural')].iloc[0]
        self.assertEqual(row.screen_class,'conditional_within_transport_benchmark')
        self.assertTrue(row.local_supply_unknown)
        self.assertFalse(row.raw_nearest_is_established_attachment)

    def test_preschool_uses_meters_not_car_time(self):
        rows=self.rows.iloc[[0]].copy();rows['service_code']='preschool';rows['cost_minutes']=1.
        result=audit.classify_service_screen(rows,self.nodes)
        self.assertEqual(result.planning_benchmark_point_radius_km.iloc[0],.5)
        self.assertEqual(result.screen_class.iloc[0],'outside_spatial_necessary_screen')
        self.assertTrue(pd.isna(result.planning_benchmark_minutes.iloc[0]))

    def test_preschool_close_points_are_only_necessary_screen(self):
        rows=self.rows.iloc[[0]].copy();rows['service_code']='preschool';rows['provider_settlement_id']='near';rows['cost_minutes']=1.
        result=audit.classify_service_screen(rows,self.nodes)
        self.assertEqual(result.screen_class.iloc[0],'conditional_within_spatial_necessary_screen')
        self.assertFalse(result.same_settlement_access_to_building_estimated.iloc[0])

    def test_primary_school_and_upper_school_have_different_benchmarks(self):
        one=self.rows.iloc[[0]].copy();one['cost_minutes']=20.
        two=one.copy();one['service_code']='school_primary';two['service_code']='school_upper'
        result=audit.classify_service_screen(pd.concat([one,two]),self.nodes)
        self.assertEqual(list(result.screen_class),['outside_transport_benchmark','conditional_within_transport_benchmark'])

    def test_generic_healthcare_is_not_given_fap_rule(self):
        rows=self.rows.iloc[[0]].copy();rows['service_code']='healthcare'
        result=audit.classify_service_screen(rows,self.nodes)
        self.assertEqual(result.screen_class.iloc[0],'service_screen_not_defined')
        self.assertFalse(result.screened_external_candidate.iloc[0])

    def test_known_local_cannot_be_sent_to_other_center(self):
        self.rows.loc[self.rows.origin_id.eq('rural'),'local_supply_status']='known_service_present'
        errors=audit.check_assignments(self.rows,self.nodes)
        self.assertIn('known_same_service_local_not_retained',set(errors.check))

    def test_selected_service_must_exist_at_same_provider(self):
        supply=pd.DataFrame({'source_record_id':['town'],'service_code':['medical_specialized'],'supply_status':['observed']})
        errors=audit.check_assignments(self.rows,self.nodes,supply)
        self.assertEqual((errors.check=='selected_service_not_backed_by_supply').sum(),3)

    def test_no_promotion_to_observed_flow(self):
        self.rows['observed_flow']=True
        errors=audit.check_assignments(self.rows,self.nodes)
        self.assertEqual((errors.check=='model_row_claimed_as_observed_or_established:observed_flow').sum(),3)

    def test_duplicate_origin_service_is_not_hidden_in_aggregation(self):
        errors=audit.check_assignments(pd.concat([self.rows,self.rows.iloc[[0]]]),self.nodes)
        self.assertEqual((errors.check=='duplicate_origin_service').sum(),2)

    def test_cost_components_must_reconcile(self):
        self.rows['network_minutes']=0.;self.rows['connector_minutes']=0.
        errors=audit.check_assignments(self.rows,self.nodes)
        self.assertEqual((errors.check=='network_connector_cost_mismatch').sum(),2)

    def test_repeated_municipal_total_cannot_be_summed_as_village_values(self):
        metrics=pd.DataFrame({'measure_id':['sown','jobs'],'source_grain':['municipality','settlement'],'aggregation_method':['sum_over_settlements']*2})
        errors=audit.check_metric_aggregation(metrics)
        self.assertEqual(list(errors.measure_id),['sown'])

    def test_point_radius_is_true_geography_not_travel_time(self):
        result=audit.classify_service_screen(self.rows,self.nodes)
        self.assertAlmostEqual(result.loc[result.origin_id.eq('rural'),'point_separation_km'].iloc[0],11.1195,places=3)
        self.assertEqual(result.loc[result.origin_id.eq('town'),'point_separation_km'].iloc[0],0.)

    def test_general_school_stage_unknown_is_separate_from_explicit_stage(self):
        rows=self.rows.copy();rows['service_code']='school_general';rows.loc[0,'cost_minutes']=10.;rows.loc[2,'cost_minutes']=25.
        result=audit.classify_service_screen(rows,self.nodes)
        self.assertEqual(result.loc[result.origin_id.eq('rural'),'screen_class'].iloc[0],'conditional_school_stage_unknown_within_primary_time_screen')
        self.assertEqual(result.loc[result.origin_id.eq('far'),'screen_class'].iloc[0],'conditional_school_stage_unknown_within_basic_time_screen')
        self.assertTrue(result.school_stage_unknown.all())

    def test_roads_may_keep_source_id_and_origin_id(self):
        rows=self.rows.copy();rows['source_record_id']=rows.origin_id
        result=audit.classify_service_screen(rows,self.nodes)
        self.assertEqual(len(result),3)

    def test_physical_object_without_census_match_is_not_discarded(self):
        rows=self.rows.iloc[[0]].copy();rows['provider_settlement_id']=None;rows['selected_provider_id']='osm:node123';rows['selected_provider_lat']=55.01;rows['selected_provider_lon']=40.
        result=audit.classify_service_screen(rows,self.nodes)
        self.assertEqual(result.screen_class.iloc[0],'conditional_within_transport_benchmark')
        self.assertEqual(result.center_identity_status.iloc[0],'unresolved_center_settlement_identity')
        self.assertTrue(result.screened_external_candidate.iloc[0])
        self.assertTrue(result.screened_candidate_np_relation_unknown.iloc[0])
        self.assertFalse(result.screened_external_identity_confirmed.iloc[0])
        self.assertTrue(result.point_separation_km.iloc[0]>0)
        units=audit.aggregate_units(result)
        self.assertEqual(units.unit_type.iloc[0],'unresolved_center_settlement_identity')
        self.assertTrue(pd.isna(units.provider_settlement_id.iloc[0]))
        self.assertFalse(units.established_sgrt.iloc[0])
        self.assertEqual(units.external_records.iloc[0],0)
        self.assertEqual(units.associated_origin_records.iloc[0],1)
        self.assertEqual(len(audit.check_assignments(rows,self.nodes)),0)

    def test_physical_object_supply_can_back_choice_without_np_identity(self):
        rows=self.rows.iloc[[0]].copy();rows['provider_settlement_id']=None;rows['selected_provider_id']='osm:node123'
        supply=pd.DataFrame({'source_record_id':[None],'provider_id':['osm:node123'],'service_code':['medical_basic_primary'],'supply_status':['observed']})
        self.assertEqual(len(audit.check_assignments(rows,self.nodes,supply)),0)

    def test_actual_building_inside_np_can_have_nonzero_travel_time(self):
        rows=self.rows.iloc[[1]].copy();rows['cost_minutes']=4.;rows['selected_provider_site_lat']=55.11;rows['selected_provider_site_lon']=40.
        errors=audit.check_assignments(rows,self.nodes)
        self.assertNotIn('same_np_baseline_not_zero',set(errors.check))

    def test_cached_provider_card_does_not_invent_observation_year_or_closure(self):
        text='L40: 【3†ФАП д. Пример】\nL41: \nL42: 456883, д. Пример, ул. Солнечная, 8\nL43: Временно недоступен\n'
        result=audit.extract_argayash_provider_cards(text)
        self.assertEqual(len(result),1)
        self.assertTrue(pd.isna(result.observation_year.iloc[0]))
        self.assertFalse(result.actual_operational_status_checked.iloc[0])
        self.assertFalse(result.original_html_downloaded.iloc[0])
        self.assertEqual(result.literal_ambiguous_status.iloc[0],'Временно недоступен')

    def test_named_provider_card_without_address_is_not_silently_fabricated(self):
        with self.assertRaisesRegex(ValueError,'lacks a literal postal address'):
            audit.extract_argayash_provider_cards('L40: 【3†ФАП д. Пример】\nL41: Телефон отсутствует')

    def test_school_nurse_role_cannot_be_admitted_as_general_primary(self):
        evidence=pd.DataFrame({'object_id':['a'],'service_code':['medical_basic_primary']})
        raw=pd.DataFrame({'object_id':['a'],'subdivision_name':['Отделение организации медицинской помощи несовершеннолетним в образовательных организациях']})
        violations=audit.check_service_evidence(evidence,raw)
        self.assertEqual(list(violations.check),['school_limited_care_not_general_primary_offer'])

    def test_excluded_source_site_cannot_be_admitted_into_any_service(self):
        evidence=pd.DataFrame({'object_id':['a'],'service_code':['medical_inpatient']})
        raw=pd.DataFrame({'object_id':['a'],'subdivision_name':['Стационар'],'registered_exclusion_present':[True]})
        violations=audit.check_service_evidence(evidence,raw)
        self.assertEqual(list(violations.check),['source_exclusion_not_respected:registered_exclusion_present'])

    def test_source_evidence_foreign_key_cannot_silently_disappear(self):
        evidence=pd.DataFrame({'object_id':['missing'],'service_code':['medical_basic_primary']})
        raw=pd.DataFrame({'object_id':['a'],'subdivision_name':['ФАП']})
        violations=audit.check_service_evidence(evidence,raw)
        self.assertEqual(list(violations.check),['service_evidence_missing_raw_source_row'])

    def test_zero_population_geographic_record_is_not_a_populated_external_member(self):
        self.rows['credited_population_2021']=[0.,100.,2.]
        result=audit.classify_service_screen(self.rows,self.nodes)
        units=audit.aggregate_units(result)
        self.assertEqual(units.external_records.iloc[0],1)
        self.assertEqual(units.external_positive_credited_records.iloc[0],0)

    def test_proxy_supplier_cannot_silently_back_strict_observed_route(self):
        supply=pd.DataFrame({'source_record_id':['town'],'service_code':['medical_basic_primary'],'supply_status':['proxy']})
        errors=audit.check_assignments(self.rows,self.nodes,supply)
        self.assertEqual((errors.check=='selected_service_not_backed_by_supply').sum(),3)
        alternate=audit.check_assignments(self.rows,self.nodes,supply,accepted_supply_statuses=('observed','proxy'))
        self.assertEqual(len(alternate),0)

    def test_federal_provider_context_does_not_expand_ordinary_origins(self):
        rows=self.rows.iloc[[0]].copy();rows['provider_settlement_id']='federal'
        errors=audit.check_assignments(rows,self.nodes,allowed_provider_context_ids=['federal'])
        self.assertEqual(len(errors),0)
        rows['origin_id']='federal'
        errors=audit.check_assignments(rows,self.nodes,allowed_provider_context_ids=['federal'])
        self.assertIn('unknown_origin',set(errors.check))

    def test_explicit_nonadditive_provider_is_not_an_ordinary_center_unit(self):
        rows=self.rows.iloc[[0]].copy();rows['provider_settlement_id']='federal';rows['selected_provider_site_lat']=55.01;rows['selected_provider_site_lon']=40.
        screened=audit.classify_service_screen(rows,self.nodes,nonadditive_context_ids=['federal'])
        units=audit.aggregate_units(screened)
        self.assertEqual(units.unit_type.iloc[0],'external_context_nonadditive')
        self.assertEqual(units.center_population_role.iloc[0],'external_context_nonadditive')

    def test_shkolnoye_locality_and_shkolnaya_street_are_not_school_nurse_roles(self):
        evidence=pd.DataFrame({'object_id':['a','b'],'service_code':['medical_basic_primary']*2})
        raw=pd.DataFrame({'object_id':['a','b'],'subdivision_name':['Школьненский ФАП','Нижненарыкарский ФАП'],'activity_address':['с. Школьное, улица Школьная','Нижние Нарыкары,ул.Школьная,1']})
        self.assertEqual(len(audit.check_service_evidence(evidence,raw)),0)

    def test_route_aliases_are_supported(self):
        rows=self.rows.rename(columns={'provider_settlement_id':'selected_provider_source_record_id','cost_minutes':'primary_cost_minutes'})
        result=audit.classify_service_screen(rows,self.nodes)
        self.assertEqual(len(result),3)
        self.assertEqual(result.loc[result.origin_id.eq('far'),'cost_minutes'].iloc[0],150.)

    def test_normative_comparison_separates_coverage_from_agreement_and_missing_origins(self):
        pairs=pd.DataFrame({'origin_id':['near','missing'],'destination_id':['other','town']})
        supply=pd.DataFrame({'source_record_id':['other','town'],'service_code':['medical_basic_primary']*2,'supply_status':['observed','proxy']})
        result=audit.compare_normative_pairs(pairs,self.rows,supply).set_index('origin_id')
        self.assertTrue(result.loc['near','any_normative_provider_in_observed_service_supply'])
        self.assertFalse(result.loc['near','agreement'])
        self.assertFalse(result.loc['missing','any_normative_provider_in_observed_service_supply'])
        self.assertFalse(result.loc['missing','origin_in_model_frame'])
        self.assertFalse(result.preregistered_blind_holdout.any())

    def test_unresolved_origin_stays_out_of_candidate_units(self):
        self.rows.loc[self.rows.origin_id.eq('far'),['provider_settlement_id','cost_minutes']]=[None,np.nan]
        result=audit.classify_service_screen(self.rows,self.nodes)
        self.assertEqual(result.loc[result.origin_id.eq('far'),'screen_class'].iloc[0],'unresolved_no_known_candidate_or_route')
        self.assertEqual(audit.aggregate_units(result).external_records.iloc[0],1)


if __name__=='__main__':unittest.main()
