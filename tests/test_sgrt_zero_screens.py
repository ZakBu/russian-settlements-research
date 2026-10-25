import sys
from pathlib import Path
import tempfile
import unittest
import json

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.screens import canonical, with_admission, spatial_diagnostic, run, SCENARIOS, RAW_CODES, DEFAULT_SCENARIOS


def reference():
    return pd.DataFrame({'source_record_id':['a','b','c'],'name':['А','Б','В'],'region':['r']*3,
        'analysis_origin':[True]*3,'ordinary_spatial_2021':[True]*3,
        'lat':[55.,55.01,55.02],'lon':[40.,40.01,40.02],
        'population_2021':[1_000_000.,100.,0.],'credit_2021':[True]*3,
        'budget_population_credit':[True]*3,'settlement_type_2021':['село','город','населённый пункт']})


def raw():
    return pd.DataFrame({'origin_id':['a','b','c'],'provider_settlement_id':['b','a',None],
        'provider_site_id':['site-b','site-a','site-unknown'],'provider_lat':[55.01,55.,55.03],
        'provider_lon':[40.01,40.,40.03],'cost_minutes':[25.,25.,5.],
        'point_separation_km':[1.,1.,0.1],'known_local_supply':[False]*3,
        'zero_cost_np_assumption':[False]*3,'road_endpoint_accepted':[True]*3,
        'route_status':['nearest_known_eligible_provider_site']*3,
        'source_id':['official','["OSM"]',None],'source_year':[2026,'["2026"]',None],
        'known_offer_records':[10]*3,'routable_external_provider_seeds':[10]*3,
        'provider_operator':[None]*3,'provider_grades_known':[False]*3})


def admit(d,family='medical_basic',limit=30.,code='medical_basic_primary'):
    return with_admission(d,family,code,'test',limit,'test_scenario')


class ZeroScreensTest(unittest.TestCase):
    def test_historical_address_does_not_become_verified_current_operation(self):
        x=raw()
        x['provider_historical_source_only']=[True,False,None]
        x['provider_actual_operational_status_verified']=[False,False,None]
        x['provider_restriction_scope_unknown']=[True,False,None]
        x['provider_medical_need_scope']=['онкология','терапия',None]
        x['provider_education_need_scope']=[None,'general_daytime_school_proxy_admission_not_verified',None]
        x['provider_universal_hospital_suitability_verified']=[False,False,None]
        x.loc[0,'source_year']='["2021"]'
        d=admit(canonical(x,reference()))
        self.assertTrue(d.provider_historical_source_only.iloc[0])
        self.assertFalse(d.provider_actual_operational_status_verified.iloc[0])
        self.assertTrue(d.provider_restriction_scope_unknown.iloc[0])
        self.assertEqual(json.loads(d.source_year.iloc[0]),['2021'])
        self.assertTrue(pd.isna(d.provider_historical_source_only.iloc[2]))
        self.assertTrue(pd.isna(d.provider_source_status_semantics_verified.iloc[0]))
        self.assertEqual(d.provider_medical_need_scope.iloc[0],'онкология')
        self.assertFalse(d.provider_universal_hospital_suitability_verified.iloc[0])
        self.assertEqual(d.provider_education_need_scope.iloc[1],'general_daytime_school_proxy_admission_not_verified')
        self.assertTrue(pd.isna(d.provider_education_need_scope.iloc[2]))

    def test_population_does_not_change_daily_travel_limit(self):
        d=admit(canonical(raw(),reference()),'grocery',20,'daily_grocery')
        self.assertEqual(d.service_status.tolist(),['far_known_candidate','far_known_candidate','near_candidate'])
        self.assertFalse(d.population_or_object_count_used_as_attraction_weight.any())
        self.assertTrue(d.origin_positive_population.tolist()==[True,True,False])

    def test_far_known_dependency_is_retained_not_independence(self):
        x=raw();x.loc[0,'cost_minutes']=95.
        d=admit(canonical(x,reference()))
        self.assertEqual(len(d),3)
        self.assertEqual(d.service_status.iloc[0],'far_known_candidate')
        self.assertFalse(d.l0_admitted.iloc[0])
        self.assertFalse(d.origin_independence_established.any())

    def test_no_road_is_unknown_even_when_inventory_has_providers(self):
        x=raw();x.loc[0,['cost_minutes','provider_site_id','provider_settlement_id']]=[np.nan,None,None]
        x.loc[0,'road_endpoint_accepted']=False
        d=admit(canonical(x,reference()))
        self.assertEqual(d.status.iloc[0],'unknown_route_or_inventory')
        self.assertEqual(d.unknown_reason.iloc[0],'origin_road_endpoint_unavailable_other_modes_unknown')
        self.assertFalse(d.l0_admitted.iloc[0])
        self.assertFalse(d.origin_independence_established.iloc[0])

    def test_known_local_presence_does_not_require_an_external_road(self):
        x=raw();x.loc[0,'known_local_supply']=True;x.loc[0,'zero_cost_np_assumption']=True
        x.loc[0,'road_endpoint_accepted']=False;x.loc[0,'cost_minutes']=0.
        x.loc[0,'provider_settlement_id']='a'
        d=admit(canonical(x,reference()))
        self.assertTrue(d.l0_admitted.iloc[0])
        self.assertEqual(d.service_status.iloc[0],'local_service_present')
        self.assertFalse(d.external_np_identity_proven.iloc[0])

    def test_unresolved_provider_np_is_not_proven_external_relation(self):
        d=admit(canonical(raw(),reference()))
        self.assertTrue(d.l0_admitted.iloc[2])
        self.assertIsNone(d.provider_settlement_id.iloc[2])
        self.assertEqual(d.origin_provider_np_relation.iloc[2],'unknown_settlement_identity')
        self.assertFalse(d.external_np_identity_proven.iloc[2])

    def test_arrow_nullable_identity_preserves_unknown_without_comparison_error(self):
        x=raw();x['provider_settlement_id']=x.provider_settlement_id.astype('string')
        d=admit(canonical(x,reference()))
        self.assertIsNone(d.provider_settlement_id.iloc[2])
        self.assertEqual(d.origin_provider_np_relation.iloc[2],'unknown_settlement_identity')

    def test_fifteen_minute_school_sensitivity_is_not_a_claim_of_primary_programme(self):
        c=canonical(raw(),reference())
        main=admit(c,'school',30,'school_general');cautious=admit(c,'school',15,'school_general')
        self.assertTrue(main.l0_admitted.iloc[0])
        self.assertFalse(cautious.l0_admitted.iloc[0])
        self.assertTrue(cautious.school_stage_unknown.all())
        self.assertFalse(main.school_screen_is_programme_eligibility_proof.any())
        self.assertTrue(main.school_car_cost_is_proxy_not_measured_school_bus_time.all())

    def test_mixed_source_metadata_are_portable_json_strings(self):
        d=canonical(raw(),reference())
        self.assertEqual(d.source_year.tolist(),['[2026]','["2026"]',None])
        self.assertEqual(d.source_id.tolist(),['["official"]','["OSM"]',None])

    def test_formal_type_not_population_selects_spatial_limit(self):
        c=canonical(raw(),reference())
        d=spatial_diagnostic(c,'grocery','daily_grocery','spatial',2000,800)
        self.assertEqual(d.necessary_point_distance_limit_m.iloc[0],2000)
        self.assertEqual(d.necessary_point_distance_limit_m.iloc[1],800)
        self.assertTrue(pd.isna(d.necessary_point_distance_limit_m.iloc[2]))
        self.assertEqual(d.necessary_spatial_condition_met.iloc[0],True)
        self.assertEqual(d.necessary_spatial_condition_met.iloc[1],False)
        self.assertTrue(pd.isna(d.necessary_spatial_condition_met.iloc[2]))

    def test_spatial_necessary_condition_does_not_use_car_time_as_walking(self):
        a=raw();a.loc[0,'cost_minutes']=120.;a.loc[0,'point_separation_km']=0.3
        c=canonical(a,reference())
        d=spatial_diagnostic(c,'grocery','daily_grocery','spatial',2000,800)
        self.assertTrue(d.necessary_spatial_condition_met.iloc[0])
        self.assertFalse(d.walking_access_established.any())
        self.assertFalse(d.car_minutes_used_as_walking_minutes.any())
        self.assertFalse(admit(c,'grocery',20,'daily_grocery').l0_admitted.iloc[0])

    def test_operator_specific_pickup_cannot_silently_accept_another_operator(self):
        a=raw();a.loc[0,'provider_operator']='Ozon';c=canonical(a,reference())
        with self.assertRaisesRegex(ValueError,'Non-Wildberries'):
            admit(c,'parcel_pickup',20,'parcel_pickup_wildberries_current')
        alternative=admit(c,'parcel_pickup',20,'parcel_pickup')
        self.assertTrue(alternative.parcel_operator_scope.eq('mixed_mapped_operators_no_interoperability_proof').all())
        self.assertFalse(alternative.pickup_operators_are_interchangeable.any())

    def test_input_identity_and_route_contradictions_fail(self):
        for modify in ['missing_origin','duplicate_origin','foreign_provider','negative_cost','observed_flow']:
            d=raw()
            if modify=='missing_origin':d=d.iloc[:2]
            elif modify=='duplicate_origin':d.loc[2,'origin_id']='a'
            elif modify=='foreign_provider':d.loc[0,'provider_settlement_id']='not_in_reference'
            elif modify=='negative_cost':d.loc[0,'cost_minutes']=-1.
            else:d['observed_flow']=True
            with self.assertRaises(ValueError):canonical(d,reference())

    def test_missing_fresh_operator_layer_does_not_fallback_or_destroy_previous_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);routes=root/'routes';routes.mkdir();output=root/'screens';output.mkdir()
            (output/'previous.txt').write_text('keep')
            for code in ['medical_basic_primary','school_general','daily_grocery']:(routes/(code+'.parquet')).touch()
            with self.assertRaisesRegex(FileNotFoundError,'parcel_pickup_wildberries_current'):
                run(routes,root/'missing_ref.parquet',output)
            self.assertEqual((output/'previous.txt').read_text(),'keep')

    def test_complete_recipe_keeps_all_scenario_outcomes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);routes=root/'nearest';routes.mkdir();reference().to_parquet(root/'ref.parquet')
            for code in [*RAW_CODES.values(),'preschool','parcel_pickup']:
                d=raw();d['service_code']=code
                d['source_year']=d.source_year.map(lambda x:None if x is None else str(x))
                if code=='parcel_pickup_wildberries_current':d['provider_operator']='Wildberries'
                d.to_parquet(routes/(code+'.parquet'))
            summary=run(routes,root/'ref.parquet',root/'out')
            d=pd.read_parquet(root/'out/daily_edges.parquet')
            self.assertEqual(len(d),(4+4+4+3)*3)
            self.assertEqual(set(d.scenario_id),set(DEFAULT_SCENARIOS))
            self.assertEqual(len(summary['scenarios']['core3_20_school30']['expected_families']),3)
            self.assertTrue((root/'out/distance_diagnostics.parquet').exists())
            self.assertTrue((root/'out/mixed_operator_pickup_alternative.parquet').exists())
            for p in summary['source_input_sha256']:self.assertTrue(Path(p).is_file())

    def test_current_positive_grocery_override_retains_its_date_and_one_channel(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);routes=root/'nearest';routes.mkdir();reference().to_parquet(root/'ref.parquet')
            for code in ['medical_basic_primary','school_general','daily_grocery']:
                d=raw();d['service_code']=code
                d['source_year']=d.source_year.map(lambda x:None if x is None else str(x))
                d.to_parquet(routes/(code+'.parquet'))
            original=(routes/'daily_grocery.parquet').read_bytes()
            current=pd.read_parquet(routes/'daily_grocery.parquet')
            current['service_code']='daily_grocery_evidence_union'
            current.loc[0,'cost_minutes']=5.;current.loc[0,'source_year']='["2026"]'
            current.to_parquet(root/'combined_grocery.parquet')
            run(routes,root/'ref.parquet',root/'out',['core3_20_school30'],grocery_nearest_path=root/'combined_grocery.parquet')
            edges=pd.read_parquet(root/'out/daily_edges.parquet')
            row=edges[edges.service_family.eq('grocery')&edges.origin_id.eq('a')].iloc[0]
            self.assertTrue(row.l0_admitted)
            self.assertEqual(json.loads(row.source_year),['2026'])
            self.assertEqual(row.source_route_service_code,'daily_grocery_evidence_union')
            self.assertEqual(edges.service_family.nunique(),3)
            self.assertEqual(original,(routes/'daily_grocery.parquet').read_bytes())

    def test_corrected_medical_route_override_is_used_and_old_input_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);routes=root/'nearest';routes.mkdir();reference().to_parquet(root/'ref.parquet')
            for code in ['medical_basic_primary','school_general','daily_grocery']:
                d=raw();d['service_code']=code;d['source_year']=None
                d.to_parquet(routes/(code+'.parquet'))
            revised=raw();revised['provider_site_id']='corrected-public-provider';revised['service_code']='medical_basic_primary';revised['source_year']=None
            revised.to_parquet(root/'corrected.parquet')
            summary=run(routes,root/'ref.parquet',root/'out',['core3_20_school30'],medical_nearest_path=root/'corrected.parquet')
            d=pd.read_parquet(root/'out/daily_edges.parquet')
            self.assertTrue(d.loc[d.service_family.eq('medical_basic'),'provider_site_id'].eq('corrected-public-provider').all())
            self.assertIn(str(root/'corrected.parquet'),summary['source_input_sha256'])
            self.assertNotIn(str(routes/'medical_basic_primary.parquet'),summary['source_input_sha256'])
            self.assertEqual(pd.read_parquet(routes/'medical_basic_primary.parquet').provider_site_id.iloc[0],'site-b')

    def test_yandex_is_separate_operator_scenario_and_not_an_extra_channel(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);routes=root/'nearest';routes.mkdir();reference().to_parquet(root/'ref.parquet')
            for code in RAW_CODES.values():
                d=raw();d['service_code']=code;d['source_year']=None
                if code=='parcel_pickup_wildberries_current':d['provider_operator']='Wildberries'
                d.to_parquet(routes/(code+'.parquet'))
            y=raw();y['service_code']='parcel_pickup_yandex_current';y['source_year']=None;y['provider_operator']='Yandex Market and partners'
            y.to_parquet(root/'yandex.parquet')
            summary=run(routes,root/'ref.parquet',root/'out',yandex_nearest_path=root/'yandex.parquet')
            d=pd.read_parquet(root/'out/daily_edges.parquet')
            self.assertEqual(len(d),(4+4+4+3+4)*3)
            self.assertEqual(set(d.scenario_id),set(SCENARIOS))
            a=d[d.scenario_id.eq('daily_20_school30_yandex')&d.service_family.eq('parcel_pickup')]
            self.assertTrue(a.source_service_code.eq('parcel_pickup_yandex_current').all())
            b=d[d.scenario_id.eq('daily_20_school30_wb')&d.service_family.eq('parcel_pickup')]
            self.assertTrue(b.source_service_code.eq('parcel_pickup_wildberries_current').all())
            self.assertEqual(summary['scenarios']['daily_20_school30_yandex']['expected_families'],summary['scenarios']['daily_20_school30_wb']['expected_families'])
            self.assertFalse(a.pickup_operators_are_interchangeable.any())


if __name__=='__main__':unittest.main()
