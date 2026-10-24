"""Transport counterexamples: service presence, geometry and directed costs."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

spec=importlib.util.spec_from_file_location('zero_transport',Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/transport.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)


def endpoints():
    return pd.DataFrame({'source_record_id':['village','town','isolated'],'origin_id':['village','town','isolated'],
        'lat':[50.,50.001,51.],'lon':[40.,40.001,41.], 'road_node_index':[0,1,2], 'snap_km':[0.,0.,0.],
        'road_endpoint_accepted':[True]*3,'working_credit_present':[True]*3})


def provider(pid,npid,node,kind='mapped_site',external=True,status='observed'):
    return {'provider_id':pid,'source_record_id':npid,'service_code':'medical_basic_primary','supply_status':status,
        'site_lat':50.,'site_lon':40.,'input_kind':'sites' if kind=='mapped_site' else 'np',
        'location_precision':kind,'evidence_quality':'source_assertion','evidence_kind':'mapped' if kind=='mapped_site' else 'registry',
        'source_id':'fixture','source_year':'2026','source_snapshot':'2026-10-24','np_identity_basis':'explicit_source' if npid else 'unknown',
        'source_input':'test','source_object_id':pid,'operator':None,'provider_name':pid,
        'default_external_seed_eligible':external,'admitted_offer':True,'accepted_snap':True,
        'external_seed_eligible':external,'road_endpoint_accepted':external,'road_node_index':node,'snap_km':0.}


class ZeroTransportTests(unittest.TestCase):
    def test_direction_and_mixed_geometry_do_not_gain_city_mass(self):
        ep=endpoints();p=pd.DataFrame([provider('physical','town',1),provider('np-only','town',1,'settlement_point',False)])
        graph=csr_matrix(np.array([[0.,7.,0.],[20.,0.,0.],[0.,0.,0.]]))
        out=t.nearest_service(ep,p,graph.T.tocsr(),'medical_basic_primary').set_index('origin_id')
        self.assertEqual(out.loc['village','provider_site_id'],'physical')
        self.assertEqual(out.loc['village','cost_minutes'],7.)
        self.assertEqual(out.loc['village','location_precision'],'mapped_site')
        self.assertTrue(pd.isna(out.loc['isolated','cost_minutes']))
        self.assertTrue(out.raw_nearest_has_no_time_cutoff.all())

    def test_centroid_presence_is_not_an_external_seed(self):
        ep=endpoints();p=pd.DataFrame([provider('physical','town',1),provider('np-presence','village',0,'settlement_point',False)])
        graph=csr_matrix(np.array([[0.,7.,0.],[20.,0.,0.],[0.,0.,0.]]))
        out=t.nearest_service(ep,p,graph.T.tocsr(),'medical_basic_primary').set_index('origin_id')
        self.assertEqual(out.loc['village','cost_minutes'],0.)
        self.assertEqual(out.loc['village','unconstrained_nearest_provider_id'],'physical')
        self.assertEqual(out.loc['village','unconstrained_nearest_cost_minutes'],7.)
        self.assertTrue(out.loc['village','zero_cost_np_assumption'])
        self.assertEqual(out.loc['village','routable_external_provider_seeds'],1)

    def test_unknown_np_identity_does_not_become_local_service(self):
        ep=endpoints();p=pd.DataFrame([provider('site-unknown',None,1)])
        graph=csr_matrix(np.array([[0.,7.,0.],[20.,0.,0.],[0.,0.,0.]]))
        out=t.nearest_service(ep,p,graph.T.tocsr(),'medical_basic_primary').set_index('origin_id')
        self.assertTrue(pd.isna(out.loc['village','provider_settlement_id']))
        self.assertFalse(out.loc['village','known_local_supply'])
        self.assertEqual(out.loc['village','cost_minutes'],7.)

    def test_raw_far_relation_is_not_censored(self):
        ep=endpoints();p=pd.DataFrame([provider('far','town',1)])
        graph=csr_matrix(np.array([[0.,400.,0.],[0.,0.,0.],[0.,0.,0.]]))
        out=t.nearest_service(ep,p,graph.T.tocsr(),'medical_basic_primary').set_index('origin_id')
        self.assertEqual(out.loc['village','cost_minutes'],400.)
        self.assertTrue(out.loc['village','l0_membership_not_decided_by_transport'])

    def test_explicit_false_string_and_inactive_source_are_not_true(self):
        self.assertEqual(list(t.truth(pd.Series(['false','true',False,True,None]))),[False,True,False,True,False])
        raw=pd.DataFrame([{'provider_id':'x','service_code':'shop','source_record_id':None,'supply_status':'excluded_temporal',
                           'site_lat':50.,'site_lon':40.,'eligible':True}])
        out=t.prepare_provider_rows([('test',raw)],[],endpoints())
        self.assertFalse(out.admitted_offer.iloc[0])

    def test_historical_supplement_remains_dated_proxy_in_route_metadata(self):
        raw=pd.DataFrame([{'provider_id':'historical','service_code':'medical_physician_primary',
            'source_record_id':'town','supply_status':'proxy','source_year':'["2021"]',
            'historical_supply_proxy':True,'historical_source_only':True,
            'restriction_scope_unknown':True,'actual_operational_status_verified':False,
            'default_external_seed_eligible':True,'service_basis':'explicit_2021_registry_care_condition'}])
        p=t.prepare_provider_rows([],[('dated_2021',raw)],endpoints())
        self.assertTrue(p.historical_supply_proxy.iloc[0])
        self.assertTrue(p.restriction_scope_unknown.iloc[0])
        self.assertFalse(p.actual_operational_status_verified.iloc[0])
        self.assertEqual(p.source_year.iloc[0],'["2021"]')
        self.assertEqual(p.service_basis.iloc[0],'explicit_2021_registry_care_condition')

    def test_clinical_scope_flags_preserve_false_true_and_unknown(self):
        raw=pd.DataFrame([{'provider_id':'child','service_code':'medical_inpatient','supply_status':'proxy',
            'medical_need_scope':'literal_specialized_scope','general_adult_profile_evidence':False,
            'named_child_only_contingent':True,'universal_hospital_suitability_verified':False,
            'site_lat':50.,'site_lon':40.},
            {'provider_id':'unknown','service_code':'medical_inpatient','supply_status':'proxy',
             'site_lat':50.,'site_lon':40.}])
        p=t.prepare_provider_rows([('scope',raw)],[],endpoints()).set_index('provider_id')
        self.assertFalse(p.loc['child','general_adult_profile_evidence'])
        self.assertTrue(p.loc['child','named_child_only_contingent'])
        self.assertFalse(p.loc['child','universal_hospital_suitability_verified'])
        self.assertTrue(pd.isna(p.loc['unknown','named_child_only_contingent']))
        self.assertEqual(p.loc['child','medical_need_scope'],'literal_specialized_scope')

    def test_unknown_supply_is_not_automatically_admitted(self):
        raw=pd.DataFrame([{'provider_id':'x','service_code':'shop','source_record_id':None,'supply_status':'unknown',
                           'site_lat':50.,'site_lon':40.}])
        out=t.prepare_provider_rows([('test',raw)],[],endpoints())
        self.assertFalse(out.admitted_offer.iloc[0])

    def test_duplicate_identifier_with_different_point_is_an_error(self):
        raw=pd.DataFrame([{'provider_id':'x','service_code':'shop','source_record_id':None,'supply_status':'observed',
                           'site_lat':50.,'site_lon':40.},
                          {'provider_id':'x','service_code':'shop','source_record_id':None,'supply_status':'observed',
                           'site_lat':51.,'site_lon':40.}])
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):
            t.prepare_provider_rows([('test',raw)],[],endpoints())

    def test_directed_requested_pair_costs_keep_connector_and_limit_status(self):
        ep=endpoints();graph=csr_matrix(np.array([[0.,7.,0.],[20.,0.,0.],[0.,0.,0.]]))
        pairs=pd.DataFrame({'origin_id':['village','town','isolated'],'destination_id':['town','village','town']})
        out=t.bounded_pairs(ep,graph,pairs,10.).set_index('origin_id')
        self.assertEqual(out.loc['village','cost_minutes'],7.)
        self.assertTrue(pd.isna(out.loc['town','cost_minutes']))
        self.assertEqual(out.loc['town','pair_status'],'no_directed_road_path_within_numerical_search_limit')
        self.assertTrue(pd.isna(out.loc['isolated','cost_minutes']))

    def test_context_city_origin_is_nonadditive_and_base_identity_unchanged(self):
        ep=endpoints();roads=pd.DataFrame({'node_index':[0,1,2],'osm_id':[10,11,12],
                                         'lat':[50.,50.001,51.],'lon':[40.,40.001,41.]})
        context=pd.DataFrame({'source_record_id':['city_context'],'lat':[50.001],'lon':[40.001],
                              'budget_population_credit':[False]})
        out=t.additional_origins(ep,context,roads)
        pd.testing.assert_series_equal(out.source_record_id.iloc[:3].reset_index(drop=True),ep.source_record_id)
        c=out.iloc[-1]
        self.assertFalse(c.budget_population_credit)
        self.assertFalse(c.working_credit_present)
        self.assertTrue(c.origin_is_additional_context)
        self.assertEqual(c.road_node_index,1)

    def test_local_representative_prefers_official_evidence_without_reweighting_external_search(self):
        ep=endpoints();p=pd.DataFrame([provider('a-proxy','town',1,status='proxy'),
            provider('z-registry','town',1,'settlement_point',False,status='observed')])
        graph=csr_matrix(np.array([[0.,7.,0.],[20.,0.,0.],[0.,0.,0.]]))
        out=t.nearest_service(ep,p,graph.T.tocsr(),'medical_basic_primary').set_index('origin_id')
        self.assertEqual(out.loc['village','provider_site_id'],'a-proxy')
        self.assertEqual(out.loc['village','cost_minutes'],7.)
        self.assertEqual(out.loc['town','provider_site_id'],'z-registry')
        self.assertEqual(out.loc['town','cost_minutes'],0.)
        self.assertEqual(out.loc['town','location_precision'],'settlement_point')

    def test_grade_and_historical_evidence_survive_selected_provider_metadata(self):
        ep=endpoints();item=provider('physical','town',1)
        item['grades_known']=False;item['historical_supply_needs_current_confirmation']=True
        item['school_program_evidence_json']='{"complete_stage_offering_established":false}'
        p=pd.DataFrame([item]);graph=csr_matrix(np.array([[0.,7.,0.],[20.,0.,0.],[0.,0.,0.]]))
        out=t.nearest_service(ep,p,graph.T.tocsr(),'medical_basic_primary').iloc[0]
        self.assertFalse(out.provider_grades_known)
        self.assertTrue(out.provider_historical_supply_needs_current_confirmation)
        self.assertIn('false',out.provider_school_program_evidence_json)

    def test_geometric_fingerprint_changes_when_a_census_point_moves(self):
        ep=endpoints();moved=ep.copy();moved.loc[0,'lat']+=.001
        self.assertNotEqual(t.origin_geometry_fingerprint(ep),t.origin_geometry_fingerprint(moved))

    def test_reused_preparation_does_not_bypass_new_strict_source_scenario(self):
        items=pd.DataFrame([provider('proxy',None,1,status='proxy'),provider('official','town',1)])
        items['explicit_source_eligible']=True
        out=t.admit_prepared_providers(items,['observed']).set_index('provider_id')
        self.assertFalse(out.loc['proxy','admitted_offer'])
        self.assertFalse(out.loc['proxy','road_endpoint_accepted'])
        self.assertTrue(out.loc['official','admitted_offer'])

    def test_geometry_cache_preserves_new_service_and_eligibility(self):
        old=pd.DataFrame([provider('wb','town',1)])
        item=provider('wb','town',1,external=False);item['service_code']='wb_only'
        new=pd.DataFrame([item]).drop(columns=['road_node_index','snap_km','accepted_snap','road_endpoint_accepted'])
        out=t.reuse_prepared_geometry(new,old)
        self.assertEqual(out.service_code.iloc[0],'wb_only')
        self.assertEqual(out.road_node_index.iloc[0],1)
        self.assertFalse(out.external_seed_eligible.iloc[0])

    def test_geometry_cache_rejects_a_moved_physical_site(self):
        old=pd.DataFrame([provider('wb','town',1)])
        item=provider('wb','town',1);item['site_lat']+=.01
        new=pd.DataFrame([item]).drop(columns=['road_node_index','snap_km','accepted_snap','road_endpoint_accepted'])
        with self.assertRaisesRegex(ValueError,'new or moved'):
            t.reuse_prepared_geometry(new,old)

    def test_np_presence_role_id_change_reuses_exact_census_point_not_building_identity(self):
        old=pd.DataFrame([provider('old-np','town',1,'settlement_point',False)])
        item=provider('new-np','town',1,'settlement_point',False);item['service_code']='wb_only'
        new=pd.DataFrame([item]).drop(columns=['road_node_index','snap_km','accepted_snap','road_endpoint_accepted'])
        out=t.reuse_prepared_geometry(new,old)
        self.assertEqual(out.provider_id.iloc[0],'new-np')
        self.assertIn('not_building_identity',out.geometry_reuse_basis.iloc[0])
        self.assertFalse(out.external_seed_eligible.iloc[0])

    def test_unknown_coordinates_can_still_support_strict_local_presence(self):
        ep=endpoints();raw=pd.DataFrame([{'provider_id':'np','source_record_id':'village','service_code':'medical_basic_primary',
            'supply_status':'observed','default_external_seed_eligible':False}])
        rows=t.prepare_provider_rows([], [('source',raw)],ep)
        self.assertTrue(rows.coordinate_available.iloc[0])
        self.assertEqual(rows.site_lat.iloc[0],50.)
        self.assertFalse(rows.default_external_seed_eligible.iloc[0])


if __name__=='__main__':unittest.main()
