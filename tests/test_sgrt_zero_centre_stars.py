import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from centre_stars import build_centre_stars


def reference():
    return pd.DataFrame(dict(source_record_id=['a','b','c','d'],name=['A','B','C','D'],region='region',district='district',
        lat=[50.,50.01,50.02,50.03],lon=[40.,40.01,40.02,40.03],population_2021=[10.,100.,200.,300.],
        population_role='ordinary_settlement_record',budget_population_credit=True,analysis_origin=True))


def edges(profiles):
    return pd.DataFrame([dict(origin_id=o,service_family=f,provider_settlement_id=p,provider_site_id='site-'+str(p),
        cost_minutes=5.,l0_admitted=True,admission_basis='explicit_test',scenario_id='test',school_stage_unknown=f=='school')
        for o,v in profiles.items() for f,p in v.items()])


class DirectCentreStarsTests(unittest.TestCase):
    def test_chain_does_not_percolate_and_centre_added_once(self):
        t,s=build_centre_stars(edges({'a':{'medical_basic':'b'},'b':{'school':'c'},'c':{'grocery':'d'}}),reference())
        members=t['centre_memberships']
        self.assertEqual(set(members[members.centre_settlement_id=='b'].origin_id),{'a','b'})
        self.assertEqual(set(members[members.centre_settlement_id=='c'].origin_id),{'b','c'})
        self.assertFalse(members.duplicated(['star_id','origin_id']).any())
        self.assertFalse(t['centre_stars'].transitive_closure_used.any())

    def test_two_core_stratum_uses_same_origin_not_different_satellites(self):
        t,_=build_centre_stars(edges({'a':{'medical_basic':'c'},'b':{'school':'c'}}),reference())
        self.assertEqual(t['centre_stars'].two_or_more_core_external_positive_whole.iloc[0],0)
        t,_=build_centre_stars(edges({'a':{'medical_basic':'c','school':'c','parcel_pickup':'c'}}),reference())
        st=t['centre_stars'].iloc[0]
        self.assertEqual(st.two_or_more_core_external_positive_whole,1)
        self.assertEqual(st.all_three_core_external_positive_whole,0)
        self.assertEqual(st.support_type,'two_core_direct_star')

    def test_unknown_np_physical_star_survives_without_inventing_np(self):
        e=edges({'a':{'school':None}});e['provider_site_id']='physical-school'
        t,s=build_centre_stars(e,reference())
        self.assertEqual(s['unknown_np_physical_functional_stars'],1)
        self.assertEqual(len(t['functional_links']),1)
        self.assertEqual(len(t['centre_stars']),0)
        self.assertIn('star_id',t['strict_three_core_memberships'])
        self.assertIn('strict_geodesic_diameter_km',t['strict_three_core_stars'])
        self.assertIn('strict_road_component_quality_unknown',t['strict_three_core_stars'])

    def test_population_does_not_change_selection_and_nonadditive_context_is_not_budgeted(self):
        e=edges({'a':{'medical_basic':'c','school':'c'}});r=reference()
        r.loc[r.source_record_id=='c',['population_role','population_2021']]=['external_context_nonadditive',10000000.]
        t,_=build_centre_stars(e,r)
        m=t['centre_memberships'].set_index('origin_id')
        self.assertTrue(pd.isna(m.loc['c','budget_population_within_star']))
        self.assertEqual(m.loc['a','budget_population_within_star'],10.)
        self.assertTrue(t['centre_stars'].centre_population_is_nonadditive_context.iloc[0])

    def test_source_parts_do_not_count_as_whole_external_places(self):
        r=reference();r.loc[r.source_record_id=='a','name']='A (часть 1)'
        t,_=build_centre_stars(edges({'a':{'medical_basic':'c','school':'c','grocery':'c'}}),r)
        self.assertEqual(t['centre_stars'].external_positive_whole_records.iloc[0],0)
        self.assertEqual(t['centre_stars'].all_three_core_external_positive_whole.iloc[0],0)

    def test_centre_outside_analysis_reference_kept_but_not_budgeted(self):
        r=reference();r.loc[r.source_record_id=='c','analysis_origin']=False
        t,_=build_centre_stars(edges({'a':{'medical_basic':'c'}}),r)
        st=t['centre_stars'].iloc[0];m=t['centre_memberships'].set_index('origin_id')
        self.assertFalse(st.centre_in_analysis_origin)
        self.assertIn('c',m.index)
        self.assertTrue(pd.isna(m.loc['c','budget_population_within_star']))

    def test_partial_overlap_preserved_and_parcel_not_second_core(self):
        t,_=build_centre_stars(edges({'a':{'medical_basic':'b','school':'c','parcel_pickup':'b'}}),reference())
        m=t['centre_memberships'];self.assertEqual(len(m[m.origin_id=='a']),2)
        self.assertEqual(t['centre_stars'].two_or_more_core_external_positive_whole.sum(),0)

    def test_strict_three_family_subset_does_not_inherit_weaker_satellites(self):
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},
                 'b':{'school':'c','grocery':'c'},
                 'c':{'medical_basic':'c','school':'c','grocery':'c'}})
        t,s=build_centre_stars(e,reference())
        self.assertEqual(s['strict_three_core_model_screened_stars'],1)
        self.assertEqual(set(t['strict_three_core_memberships'].origin_id),{'a','c'})
        self.assertEqual(t['strict_three_core_stars'].strict_member_count.iloc[0],2)
        self.assertEqual(t['centre_stars'].member_records.iloc[0],3)

    def test_strict_three_family_needs_centre_own_three_and_whole_external(self):
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},'c':{'medical_basic':'c','school':'c'}})
        t,s=build_centre_stars(e,reference())
        self.assertEqual(s['strict_three_core_model_screened_stars'],0)
        self.assertEqual(t['centre_stars'].all_three_core_external_positive_whole.iloc[0],1)

    def test_strict_does_not_accept_source_part_centre(self):
        r=reference();r.loc[r.source_record_id=='c','name']='C (часть 1)'
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},'c':{'medical_basic':'c','school':'c','grocery':'c'}})
        _,s=build_centre_stars(e,r)
        self.assertEqual(s['strict_three_core_model_screened_stars'],0)

    def test_audited_small_component_is_flag_not_automatic_group_removal(self):
        ep=pd.DataFrame(dict(source_record_id=['a','c'],road_endpoint_accepted=True,audit_component_size=[3,1000]))
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},'c':{'medical_basic':'c','school':'c','grocery':'c'}})
        t,s=build_centre_stars(e,reference(),ep)
        self.assertEqual(s['strict_three_core_model_screened_stars'],1)
        self.assertTrue(t['strict_three_core_stars'].strict_any_component_lt100_diagnostic.iloc[0])
        self.assertFalse(t['strict_three_core_stars'].strict_road_component_quality_unknown.iloc[0])
        self.assertFalse(t['strict_three_core_stars'].any_strict_road_endpoint_review.iloc[0])

    def test_unknown_population_role_is_not_nonadditive_city_context(self):
        r=reference();r.loc[r.source_record_id=='c',['population_role','budget_population_credit']]=[None,pd.NA]
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},'c':{'medical_basic':'c','school':'c','grocery':'c'}})
        t,s=build_centre_stars(e,r)
        self.assertEqual(s['strict_three_core_model_screened_stars'],0)
        self.assertFalse(t['centre_stars'].centre_population_is_nonadditive_context.iloc[0])
        self.assertIn('strict_member_count',t['strict_three_core_stars'])

    def test_member_batches_preserve_all_tables_across_many_centres(self):
        rows=[];profiles={}
        for n in range(45):
            centre=f'centre{n:03d}';satellite=f'satellite{n:03d}'
            for origin,offset in [(centre,0.),(satellite,.001)]:
                rows.append(dict(source_record_id=origin,name=origin,region='region',district='district',
                    lat=50+n*.01+offset,lon=40+n*.01,population_2021=100. if offset==0 else 10.,
                    population_role='ordinary_settlement_record',budget_population_credit=True,analysis_origin=True))
                profiles[origin]={'medical_basic':centre,'school':centre,'grocery':centre}
            profiles[satellite]['parcel_pickup']=f'centre{(n+1)%45:03d}'
        r=pd.DataFrame(rows);r.loc[3,'name']='part (часть 1)'
        r.loc[7,'population_2021']=0.
        e=edges(profiles)
        full,fullsummary=build_centre_stars(e,r,member_batch_size=10000)
        batched,summary=build_centre_stars(e,r,member_batch_size=3)
        self.assertGreater(len(full['centre_stars']),40)
        self.assertEqual(fullsummary,summary)
        for name in full:
            pd.testing.assert_frame_equal(full[name],batched[name])
        with self.assertRaisesRegex(ValueError,'positive integer'):
            build_centre_stars(e,r,member_batch_size=0)

    def test_unknown_identity_rejected_instead_of_added_to_census(self):
        with self.assertRaisesRegex(ValueError,'provider settlement'):
            build_centre_stars(edges({'a':{'medical_basic':'missing'}}),reference())


if __name__=='__main__':unittest.main()
