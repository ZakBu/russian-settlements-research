import sys
from pathlib import Path
import unittest
import importlib.util
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from logic_checks import (check_direct_admission, profile_coverage, check_profile_atoms,
    check_nested_unions, check_direct_core_cover, check_promotions, gpkg_wkb, provider_anchor,
    check_external_reference_parents, check_nontrivial_spatial_merges)
from logic_checks import locate_external_fua_points, check_external_provider_core_edges, check_relaxed_positive_assignments
from logic_checks import _ellipsoidal_extent, check_upper_need_scope_labels


class IndependentExtentTests(unittest.TestCase):
    def test_wgs84_radius_is_not_diameter_or_road_minutes(self):
        points=pd.DataFrame({'lat':[0.,0.,0.],'lon':[-1.,0.,1.]})
        extent=_ellipsoidal_extent(points,0.,0.)
        self.assertAlmostEqual(extent['anchor_max_distance_km'],111.31949079327357,places=8)
        self.assertAlmostEqual(extent['wgs84_member_diameter_km'],222.63898158654715,places=8)

    def test_conditional_child_offer_is_not_universal_patient_routing(self):
        d=pd.DataFrame({'service_family':['medical_inpatient'],'provider_named_child_only_contingent':[True],
                        'upper_medical_link_need_conditional':[True],
                        'universal_patient_suitability_established':[False],
                        'rare_service_is_agglomeration_proof':[False]})
        self.assertEqual(sum(check_upper_need_scope_labels(d).values()),0)
        d['universal_patient_suitability_established']=True
        self.assertEqual(check_upper_need_scope_labels(d)['unsupported_universal_patient_suitability_claim'],1)


class ExtendedCoreCounterexamples(unittest.TestCase):
    def edge(self,o,f,t='efua:1',cost=40.):
        return dict(origin_id=o,service_family=f,parent_target_key=t,provider_point_key='clinic',cost_minutes=cost,admission_limit_minutes=90.,higher_admitted=True)

    def test_outside_origin_is_allowed_but_outside_provider_is_not(self):
        # No origin-inside condition exists in this separately labelled scenario.
        e=pd.DataFrame([self.edge('village_outside2015','hospital')])
        points=pd.DataFrame({'point_key':['clinic'],'eFUA_ID':[1]})
        self.assertTrue(check_external_provider_core_edges(e,points).empty)
        points.eFUA_ID=2
        self.assertEqual(check_external_provider_core_edges(e,points).check.iloc[0],'provider_outside_claimed_external_core')

    def test_two_clinical_codes_are_not_two_domains(self):
        m=pd.DataFrame({'child_unit_id':['c'],'origin_id':['v']})
        a=pd.DataFrame({'child_unit_id':['c'],'parent_target_key':['efua:1']})
        e=pd.DataFrame([self.edge('v','hospital'),self.edge('v','hightech')])
        bad=check_relaxed_positive_assignments(m,a,e,{'hospital':'health','hightech':'health'})
        self.assertIn('insufficient_whole_child_positive_domains',set(bad.check))

    def test_unknown_health_is_preserved_with_two_other_positive_domains(self):
        m=pd.DataFrame({'child_unit_id':['c','c'],'origin_id':['v','w']})
        a=pd.DataFrame({'child_unit_id':['c'],'parent_target_key':['efua:1']})
        e=pd.DataFrame([self.edge(o,f)for o in ['v','w']for f in ['college','shopping']])
        self.assertTrue(check_relaxed_positive_assignments(m,a,e,{'college':'education','shopping':'commerce'}).empty)
        self.assertNotIn('hospital',set(e.service_family))

    def test_coverage_cannot_be_filled_by_different_members(self):
        m=pd.DataFrame({'child_unit_id':['c','c'],'origin_id':['v','w']})
        a=pd.DataFrame({'child_unit_id':['c'],'parent_target_key':['efua:1']})
        e=pd.DataFrame([self.edge('v','college'),self.edge('w','shopping')])
        self.assertIn('insufficient_whole_child_positive_domains',set(check_relaxed_positive_assignments(m,a,e,{'college':'education','shopping':'commerce'}).check))

    def test_competing_complete_service_cannot_be_hidden_by_majority(self):
        m=pd.DataFrame({'child_unit_id':['c'],'origin_id':['v']})
        a=pd.DataFrame({'child_unit_id':['c'],'parent_target_key':['efua:1']})
        e=pd.DataFrame([self.edge('v','college'),self.edge('v','shopping'),self.edge('v','hospital','np:small_town')])
        bad=check_relaxed_positive_assignments(m,a,e,{'college':'education','shopping':'commerce','hospital':'health'})
        self.assertIn('competing_complete_positive_core_ignored',set(bad.check))

    def test_long_direct_route_is_not_local_by_core_membership(self):
        e=pd.DataFrame([self.edge('v','hospital',cost=140.)])
        points=pd.DataFrame({'point_key':['clinic'],'eFUA_ID':[1]})
        self.assertIn('provider_core_link_without_direct_bounded_cost',set(check_external_provider_core_edges(e,points).check))


class ServiceLogicTests(unittest.TestCase):
    def test_distant_link_is_retained_without_becoming_local(self):
        edges=pd.DataFrame([dict(origin_id='village',service_family='health_basic',l0_admitted=False,
            provider_settlement_id='doctor_town',cost_minutes=95.)])
        self.assertTrue(check_direct_admission(edges,{'health_basic':30.}).empty)
        coverage=profile_coverage(edges,['village'],['health_basic','school'])
        self.assertEqual(coverage.evidence_state.iloc[0],'no_supported_local_service_link')
        self.assertTrue(pd.isna(coverage.all_needs_satisfied.iloc[0]))
        self.assertFalse(coverage.absence_of_service_established.iloc[0])

    def test_chain_cannot_reconstruct_missing_direct_cost(self):
        members=pd.DataFrame({'unit_id':['u']*4,'origin_id':['a','b','c','d']})
        cores=pd.DataFrame({'unit_id':['u'],'core_id':['a']})
        # b→a and c→b and d→c do not establish c→a or d→a.
        costs=pd.DataFrame({'origin_id':['a','b','c','d'],'core_id':['a','a','b','c'],'cost_minutes':[0.,10.,10.,10.]})
        bad=check_direct_core_cover(members,cores,costs,30.)
        self.assertEqual(set(bad.origin_id),{'c','d'})

    def test_reverse_route_is_not_origin_to_core(self):
        members=pd.DataFrame({'unit_id':['u'],'origin_id':['v']})
        cores=pd.DataFrame({'unit_id':['u'],'core_id':['town']})
        backwards=pd.DataFrame({'origin_id':['town'],'core_id':['v'],'cost_minutes':[5.]})
        self.assertEqual(len(check_direct_core_cover(members,cores,backwards,30.)),1)

    def test_multicore_union_is_not_single_common_core(self):
        members=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b']})
        cores=pd.DataFrame({'unit_id':['u','u'],'core_id':['x','y']})
        costs=pd.DataFrame({'origin_id':['a','b'],'core_id':['x','y'],'cost_minutes':[5.,5.]})
        self.assertTrue(check_direct_core_cover(members,cores,costs,30.).empty)
        self.assertEqual(check_direct_core_cover(members,cores,costs,30.,common_core_required=True).check.iloc[0],
                         'no_single_common_core_covers_all_members')

    def test_walking_metres_are_not_automobile_minutes(self):
        e=pd.DataFrame([dict(origin_id='v',service_family='preschool',l0_admitted=True,
            provider_site_id='s',cost_minutes=4.,point_separation_km=.8)])
        bad=check_direct_admission(e,{'preschool':.5},{'preschool':'point_separation_km'})
        self.assertEqual(bad.check.iloc[0],'direct_cost_exceeds_function_bound')

    def test_nonfinite_and_negative_costs_fail_local_admission(self):
        e=pd.DataFrame([dict(origin_id=str(i),service_family='school',l0_admitted=True,
            provider_site_id='s',cost_minutes=v) for i,v in enumerate([np.nan,-1.,np.inf,'not measured'])])
        self.assertEqual(len(check_direct_admission(e,{'school':30.})),4)

    def test_population_does_not_change_direct_service_admission(self):
        e=pd.DataFrame([dict(origin_id='v',service_family='school',l0_admitted=True,
            provider_settlement_id='p',cost_minutes=8.,population=50)])
        a=check_direct_admission(e,{'school':30.})
        e['population']=2_000_000
        pd.testing.assert_frame_equal(a,check_direct_admission(e,{'school':30.}))

    def test_all_unknown_origins_cannot_form_giant_atom(self):
        m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b']})
        e=pd.DataFrame({'origin_id':['a','b'],'service_family':['school','school'],'l0_admitted':[False,False]})
        self.assertIn('all_unknown_origins_merged',set(check_profile_atoms(m,e,['school']).check))

    def test_school_fap_split_is_retained(self):
        m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b']})
        e=pd.DataFrame([dict(origin_id=o,service_family=f,l0_admitted=True,provider_settlement_id=p)
            for o,f,p in [('a','school','school_centre'),('a','health_basic','fap'),
                          ('b','school','school_centre'),('b','health_basic','other_fap')]])
        self.assertIn('atom_mixes_distinct_service_profiles',set(check_profile_atoms(m,e,['school','health_basic']).check))

    def test_physical_site_does_not_inherit_nearest_np_identity(self):
        row=pd.Series({'provider_site_id':'osm:node:1','source_id':'OSM2026','nearest_reference_source_record_id':'village'})
        self.assertEqual(provider_anchor(row),'site:OSM2026:osm:node:1')

    def test_parent_cannot_split_child_or_acquire_untraced_member(self):
        children=pd.DataFrame({'child_unit_id':['c','c'],'origin_id':['a','b']})
        assignment=pd.DataFrame({'child_unit_id':['c'],'parent_unit_id':['p']})
        parent=pd.DataFrame({'parent_unit_id':['p','p'],'origin_id':['a','x']})
        bad=check_nested_unions(children,assignment,parent)
        self.assertEqual(bad.check.iloc[0],'parent_is_not_exact_union_of_children')
        self.assertIn('"b"',bad.detail.iloc[0]);self.assertIn('"x"',bad.detail.iloc[0])

    def test_overlapping_children_can_have_a_valid_union(self):
        children=pd.DataFrame({'child_unit_id':['a','a','b','b'],'origin_id':['x','y','y','z']})
        assignment=pd.DataFrame({'child_unit_id':['a','b'],'parent_unit_id':['p','p']})
        parent=pd.DataFrame({'parent_unit_id':['p']*3,'origin_id':['x','y','z']})
        self.assertTrue(check_nested_unions(children,assignment,parent).empty)

    def test_same_service_or_population_rank_cannot_prove_new_order(self):
        e=pd.DataFrame([dict(parent_unit_id='p',child_unit_id='c',promotion_basis='higher_service_order',
            evidence_source_id='school_inventory',child_service_orders_json='["school"]',new_service_order='school'),
            dict(parent_unit_id='moscow',child_unit_id='c',promotion_basis='population_cluster_rank',evidence_source_id='census')])
        bad=check_promotions(e)
        self.assertIn('same_function_order_reused_as_higher_level',set(bad.check))
        self.assertIn('promotion_without_new_functional_or_external_evidence',set(bad.check))

    def test_estimated_global_boundary_is_not_observed_russian_flow(self):
        e=pd.DataFrame([dict(parent_unit_id='p',child_unit_id='c',promotion_basis='external_estimated_fua_reference',
            evidence_source_id='GHS_FUA2015_R2019A',is_observed_flow=True)])
        self.assertEqual(check_promotions(e).check.iloc[0],'estimated_fua_mislabelled_as_observed_flow')

    def test_geopackage_header_not_confused_with_wkb(self):
        wkb=b'example';header=b'GP'+bytes([0,3])+b'\x00'*4+b'\x00'*32
        self.assertEqual(gpkg_wkb(header+wkb),wkb)
        with self.assertRaises(ValueError):gpkg_wkb(b'NOT A GEOPACKAGE')

    def test_multiple_providers_inside_same_reference_parent_are_preserved(self):
        m=pd.DataFrame({'parent_unit_id':['p','p'],'origin_id':['a','b'],'eFUA_ID':[7,7]})
        edges=pd.DataFrame({'parent_unit_id':['p','p'],'origin_id':['a','b'],'provider_point_key':['clinic_x','college_y']})
        lookup=pd.DataFrame({'point_key':['a','b','clinic_x','college_y'],'eFUA_ID':[7]*4})
        self.assertTrue(check_external_reference_parents(m,edges,lookup).empty)
        self.assertEqual(set(edges.provider_point_key),{'clinic_x','college_y'})

    def test_shared_reference_for_origins_does_not_excuse_remote_provider(self):
        m=pd.DataFrame({'parent_unit_id':['p'],'origin_id':['a'],'eFUA_ID':[7]})
        edges=pd.DataFrame({'parent_unit_id':['p'],'origin_id':['a'],'provider_point_key':['remote_hospital']})
        lookup=pd.DataFrame({'point_key':['a','remote_hospital'],'eFUA_ID':[7,8]})
        self.assertEqual(check_external_reference_parents(m,edges,lookup).check.iloc[0],
            'higher_provider_outside_claimed_external_reference')

    def test_repeating_same_boundary_is_not_a_new_spatial_merge(self):
        child=pd.DataFrame({'child_unit_id':['u','u'],'origin_id':['a','b']})
        assignment=pd.DataFrame({'child_unit_id':['u'],'parent_unit_id':['renamed']})
        parent=pd.DataFrame({'parent_unit_id':['renamed','renamed'],'origin_id':['a','b']})
        self.assertEqual(check_nontrivial_spatial_merges(child,assignment,parent).check.iloc[0],
            'unchanged_membership_relabelled_as_new_spatial_merge')

    @unittest.skipUnless(importlib.util.find_spec('shapely') and importlib.util.find_spec('pyproj'),'optional geometry dependencies')
    def test_boundary_lookup_preserves_ambiguity_and_unknown_geometry(self):
        from shapely import box,to_wkb
        polys=pd.DataFrame({'eFUA_ID':[1,2],'geometry_wkb':[to_wkb(box(0,0,2,2)),to_wkb(box(1,1,3,3))],
            'geometry_crs':['EPSG:4326']*2})
        points=pd.DataFrame({'point_key':['single','overlap','absent','unknown'],'lat':[.5,1.5,10.,np.nan],'lon':[.5,1.5,10.,np.nan]})
        links,states=locate_external_fua_points(points,polys)
        self.assertEqual(links.loc[links.point_key.eq('overlap'),'eFUA_ID'].tolist(),[1,2])
        indexed=states.set_index('point_key')
        self.assertEqual(indexed.loc['overlap','external_boundary_match_count'],2)
        self.assertIn('unknown_or_invalid',indexed.loc['unknown','external_boundary_status'])
        self.assertIn('not_evidence_of_isolation',indexed.loc['absent','external_boundary_status'])

    @unittest.skipUnless(importlib.util.find_spec('shapely') and importlib.util.find_spec('pyproj'),'optional geometry dependencies')
    def test_np_anchor_cannot_silently_replace_conflicting_building_locations(self):
        from shapely import box,to_wkb
        polys=pd.DataFrame({'eFUA_ID':[1],'geometry_wkb':[to_wkb(box(0,0,2,2))],'geometry_crs':['EPSG:4326']})
        points=pd.DataFrame({'point_key':['same_np','same_np'],'lat':[.5,1.5],'lon':[.5,1.5]})
        with self.assertRaisesRegex(ValueError,'conflicting geometries'):locate_external_fua_points(points,polys)


if __name__=='__main__':unittest.main()
