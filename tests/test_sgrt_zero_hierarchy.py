import sys
from pathlib import Path
import unittest
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from hierarchy import build_level_zero,canonical_edges,higher_candidates,promote_layer


def reference(ids=('a','b','c','d')):
    d=pd.DataFrame({'source_record_id':list(ids),'name':list(ids),'lat':np.arange(len(ids),dtype=float)*.01+50,
        'lon':np.arange(len(ids),dtype=float)*.01+40,'ordinary_spatial_2021':True,'population_role':'ordinary_settlement_record'})
    for y in [2002,2010,2021]:d[f'population_{y}']=100.;d[f'credit_{y}']=True
    return d


def edges(profiles,admission='l0_admitted',guard=None):
    rows=[]
    for origin,p in profiles.items():
        for family,provider in p.items():
            row={'scenario_id':'test','origin_id':origin,'service_family':family,
                'provider_settlement_id':provider,'provider_site_id':('site-'+str(provider)) if provider else None,
                'cost_minutes':5. if provider else np.nan,admission:provider is not None,
                'admission_basis':'dated_transport_scenario','admission_limit_minutes':30.,
                'source_id':'primary','source_year':2026,'provider_lat':50.,'provider_lon':40.}
            if guard is not None:row.update(territorial_merge_admitted=guard,territorial_guard_basis='independent_efua2015')
            rows.append(row)
    return pd.DataFrame(rows)


class HierarchyTests(unittest.TestCase):
    def test_same_np_anchors_ignore_object_counts_and_site_names(self):
        e=edges({'a':{'health':'c','shop':'c'},'b':{'health':'c','shop':'c'}})
        e.loc[e.origin_id=='b','provider_site_id']='different-actual-building'
        u,m,a,raw=build_level_zero(e,reference(),['health','shop'])
        self.assertEqual(m.set_index('origin_id').loc['a','unit_id'],m.set_index('origin_id').loc['b','unit_id'])
        x=u[u.member_records.eq(2)].iloc[0]
        self.assertEqual(x.type_code,'monocentric_service_profile')
        self.assertTrue(a.provider_site_ids_json.str.contains('different-actual-building').any())

    def test_shared_one_function_is_not_a_multifunction_system(self):
        e=edges({'a':{'health':'c','shop':'a'},'b':{'health':'c','shop':'b'}})
        _,m,_,_=build_level_zero(e,reference(),['health','shop'])
        self.assertNotEqual(m.set_index('origin_id').loc['a','unit_id'],m.set_index('origin_id').loc['b','unit_id'])

    def test_chain_of_overlaps_does_not_merge(self):
        e=edges({'a':{'health':'a','shop':'b'},'b':{'health':'b','shop':'c'},'c':{'health':'c','shop':'d'}})
        u,m,_,_=build_level_zero(e,reference(),['health','shop'])
        self.assertEqual(m.unit_id.nunique(),4)

    def test_all_unknown_origins_are_separate(self):
        e=edges({'a':{'health':None},'b':{'health':None}})
        u,m,_,_=build_level_zero(e,reference(),['health','shop'])
        self.assertEqual(m.unit_id.nunique(),4)
        self.assertTrue(u.type_code.eq('no_supported_daily_link').all())

    def test_population_never_changes_level_zero_assignment(self):
        e=edges({'a':{'health':'c'},'b':{'health':'c'}})
        r=reference();_,m1,_,_=build_level_zero(e,r,['health'])
        r.loc[r.source_record_id=='c','population_2021']=10000000
        _,m2,_,_=build_level_zero(e,r,['health'])
        pd.testing.assert_frame_equal(m1,m2)

    def test_far_connection_is_retained_but_not_expands_level_zero(self):
        e=edges({'a':{'health':'c'}});e.loc[:,'cost_minutes']=90.;e.loc[:,'l0_admitted']=False
        u,m,_,raw=build_level_zero(e,reference(),['health'])
        self.assertEqual(raw.cost_minutes.iloc[0],90.)
        self.assertTrue(u.type_code.eq('no_supported_daily_link').all())

    def test_own_service_bound_is_enforced(self):
        e=edges({'a':{'health':'c'}});e.loc[:,'cost_minutes']=90.
        with self.assertRaisesRegex(ValueError,'exceeds'):build_level_zero(e,reference(),['health'])

    def test_bad_known_provider_identity_does_not_pass_as_a_new_centre(self):
        e=edges({'a':{'health':'not-an-accepted-settlement'}})
        with self.assertRaisesRegex(ValueError,'identity reference'):build_level_zero(e,reference(),['health'])

    def test_multiple_source_scenarios_are_not_silently_minimized(self):
        e=edges({'a':{'health':'c'}})
        with self.assertRaisesRegex(ValueError,'More than one'):build_level_zero(pd.concat([e,e]),reference(),['health'])

    def test_unknown_site_does_not_inherit_nearest_np_identity(self):
        e=edges({'a':{'health':'c'}});e.loc[:,'provider_settlement_id']=None;e.loc[:,'provider_site_id']='real-fap-site'
        e['nearest_reference_source_record_id']='c'
        u,m,a,_=build_level_zero(e,reference(),['health'])
        self.assertEqual(a.provider_key.iloc[0],'site:real-fap-site')
        self.assertTrue(pd.isna(a.provider_settlement_id.iloc[0]))

    def test_federal_context_can_be_an_origin_without_additive_population(self):
        r=reference();r['analysis_origin']=True;r.loc[r.source_record_id=='d','ordinary_spatial_2021']=False
        r.loc[r.source_record_id=='d','population_role']='external_context_nonadditive'
        r.loc[r.source_record_id=='d','population_2021']=10000000
        u,m,_,_=build_level_zero(edges({'a':{'health':'d'},'d':{'health':'d'}}),r,['health'])
        x=u[u.member_records.eq(2)].iloc[0]
        self.assertEqual(x.member_population_2021_credited_sum,100.)
        self.assertEqual(len(m),4)

    def test_rare_service_alone_does_not_absorb_half_region(self):
        r=reference();u,m,_,_=build_level_zero(edges({'a':{'health':'a'},'b':{'health':'b'}}),r,['health'])
        h=edges({x:{'hospital':'c'} for x in ['a','b','c','d']},'higher_admitted',False)
        c=higher_candidates(m,h,r);pu,pm,cross,stop=promote_layer(u,m,c,1,['health'])
        self.assertTrue(stop['stop']);self.assertEqual(pu.child_units.max(),1)
        self.assertTrue(pu.effective_merge_depth.eq(0).all())
        self.assertEqual(set(pm.origin_id),set(m.origin_id))

    def test_guarded_complete_new_function_merges_children_and_retains_crosswalk(self):
        r=reference();u,m,_,_=build_level_zero(edges({'a':{'health':'a'},'b':{'health':'b'}}),r,['health'])
        h=edges({x:{'physician':'c'} for x in ['a','b','c','d']},'higher_admitted',True)
        c=higher_candidates(m,h,r);pu,pm,cross,stop=promote_layer(u,m,c,1,['health'])
        self.assertFalse(stop['stop']);self.assertEqual(pu.child_units.max(),4)
        self.assertEqual(pu.effective_merge_depth.iloc[0],1)
        self.assertEqual(len(cross),len(u));self.assertEqual(pm.origin_id.nunique(),4)

    def test_split_child_not_forced_to_larger_or_majority_parent(self):
        r=reference();u,m,_,_=build_level_zero(edges({'a':{'health':'c'},'b':{'health':'c'}}),r,['health'])
        h=edges({'a':{'physician':'c'},'b':{'physician':'d'},'c':{'physician':'c'},'d':{'physician':'d'}},'higher_admitted',True)
        c=higher_candidates(m,h,r)
        child=m.set_index('origin_id').loc['a','unit_id']
        self.assertTrue(c[c.child_unit_id.eq(child)].coverage_type.eq('split_higher_candidates').all())
        _,_,cross,_=promote_layer(u,m,c,1,['health'])
        self.assertEqual(cross[cross.child_unit_id.eq(child)].promotion_status.iloc[0],'retained_without_forced_parent')

    def test_optional_pickup_not_required_for_core_service_completeness(self):
        e=edges({'a':{'health':'c','school':'c','grocery':'c','pickup':None}})
        u,m,_,_=build_level_zero(e,reference(),['health','school','grocery','pickup'],['health','school','grocery'])
        uid=m.set_index('origin_id').loc['a','unit_id'];x=u[u.unit_id.eq(uid)].iloc[0]
        self.assertTrue(x.all_core_daily_families_have_candidate)
        self.assertFalse(x.all_declared_daily_families_have_candidate)
        self.assertTrue(pd.isna(x.daily_needs_actually_satisfied))

    def test_external_reference_target_retains_multiple_real_providers(self):
        r=reference();u,m,_,_=build_level_zero(edges({'a':{'health':'a'},'b':{'health':'b'}}),r,['health'])
        h=edges({'a':{'physician':'c'},'b':{'physician':'d'},'c':{'physician':'c'},'d':{'physician':'d'}},'higher_admitted',True)
        h['parent_target_key']='efua:independent2015-area';h['parent_target_kind']='external_functional_area'
        c=higher_candidates(m,h,r);p,pm,cross,stop=promote_layer(u,m,c,1,['health'])
        self.assertFalse(stop['stop']);self.assertTrue(p.boundary_depends_on_external_reference.all())
        self.assertEqual(p.known_provider_np_count.iloc[0],2)
        self.assertIn('np:c',p.real_provider_keys_json.iloc[0]);self.assertIn('np:d',p.real_provider_keys_json.iloc[0])
        self.assertFalse(p.independently_discovered_agglomeration_boundary.any())
        # Relabeling another service inside the same external area cannot
        # manufacture a further merger of an already grouped member set.
        h2=h.copy();h2['service_family']='higher_education'
        c2=higher_candidates(pm,h2,r);p2,_,_,stop2=promote_layer(p,pm,c2,2,['health','physician'])
        self.assertTrue(stop2['stop'])
        self.assertTrue(p2.boundary_depends_on_external_reference.all())
        self.assertEqual(p2.effective_merge_depth.iloc[0],1)

    def test_external_polygon_cannot_masquerade_as_one_clinic(self):
        r=reference();_,m,_,_=build_level_zero(edges({'a':{'health':'a'}}),r,['health'])
        h=edges({x:{'physician':'c'} for x in ['a','b','c','d']},'higher_admitted',True)
        h['parent_target_key']='efua:123'
        with self.assertRaisesRegex(ValueError,'masquerade'):higher_candidates(m,h,r)

    def test_repeated_function_does_not_manufacture_new_level(self):
        r=reference();u,m,_,_=build_level_zero(edges({'a':{'health':'a'}}),r,['health'])
        h=edges({x:{'health':'c'} for x in ['a','b','c','d']},'higher_admitted',True)
        c=higher_candidates(m,h,r)
        with self.assertRaisesRegex(ValueError,'Repeated'):promote_layer(u,m,c,1,['health'])


if __name__=='__main__':unittest.main()
