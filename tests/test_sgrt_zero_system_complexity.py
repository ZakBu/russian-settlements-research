import sys
import unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from system_complexity import describe_systems, education_external_boundary_examples


def fixtures():
    members=pd.DataFrame({'scenario_id':['main']*3,'unit_id':['u','u','v'],'origin_id':['a','b','c']})
    base=dict(UIDSPMO='sub1',IDADDRESS='addr1',service_code='medical_basic_primary',source_record_id='a',np_identity_accepted=True,medical_need_scope='терапии',named_child_only_contingent=False,general_adult_profile_evidence=True,restriction_scope_unknown=False)
    medical=pd.DataFrame([base,dict(base,service_code='medical_physician_primary'),dict(base,UIDSPMO='sub2',service_code='medical_inpatient',medical_need_scope='акушерству и гинекологии',general_adult_profile_evidence=False),dict(base,IDADDRESS='addr2',source_record_id='b',named_child_only_contingent=True,medical_need_scope='педиатрии',general_adult_profile_evidence=False)])
    education=pd.DataFrame([dict(source_record_id='a',provider_id='school1',service_code='school_general',eligible_site_supply=True,supply_status='observed',grades_known=False),dict(source_record_id=None,provider_id='unknown',service_code='higher_education',eligible_site_supply=True,supply_status='observed',grades_known=False)])
    return members,medical,education


class ComplexityTests(unittest.TestCase):
    def test_deduplicates_address_across_profiles_services_and_subdivisions(self):
        m,h,e=fixtures();d,a=describe_systems(m,h,e);u=d.set_index('unit_id').loc['u']
        self.assertEqual(u.medical_registered_care_address_ids_known,2)
        self.assertEqual(u.medical_registered_subdivisions_known,2)
        self.assertEqual(u.medical_profile_breadth_known,3)
        self.assertEqual(u.medical_child_only_care_address_ids_known,1)
        self.assertIn('гинекологии',u.medical_age_and_sex_scope_evidence_json)
        self.assertIn('педиатрии',u.medical_need_scopes_json)

    def test_no_records_are_unresolved_not_lowest_rank(self):
        m,h,e=fixtures();d,a=describe_systems(m,h,e);v=d.set_index('unit_id').loc['v']
        self.assertEqual(v.medical_registered_care_address_ids_known,0)
        self.assertEqual(v.functional_evidence_quality_class,'insufficient_multidomain_records')
        self.assertTrue(v.zero_means_no_accepted_source_record_not_physical_absence)
        self.assertFalse(v.functional_rank_established)
        self.assertFalse(a['clustering_or_functional_rank_attempted'])

    def test_unknown_np_and_external_provider_do_not_inflate_members(self):
        m,h,e=fixtures();h.loc[h.source_record_id.eq('a'),'source_record_id']='outside'
        e['nearest_reference_source_record_id']='c'
        d,a=describe_systems(m,h,e);v=d.set_index('unit_id').loc['v']
        self.assertEqual(v.education_higher_features_known,0)
        self.assertEqual(v.medical_registered_care_address_ids_known,0)
        self.assertEqual(a['education_observed_features_with_accepted_np'],1)

    def test_population_and_merge_depth_are_not_features(self):
        m,h,e=fixtures();one,_=describe_systems(m,h,e)
        m['population']=10**9;m['effective_merge_depth']=100
        two,_=describe_systems(m,h,e);pd.testing.assert_frame_equal(one,two)

    def test_scope_json_is_canonical_under_source_order(self):
        m,h,e=fixtures();one,_=describe_systems(m,h,e)
        two,_=describe_systems(m,h.iloc[::-1],e.iloc[::-1])
        pd.testing.assert_frame_equal(one,two)

    def test_rejects_nonpartition_and_missing_address_identity(self):
        m,h,e=fixtures()
        with self.assertRaisesRegex(ValueError,'partition'):describe_systems(pd.concat([m,m.iloc[:1]]),h,e)
        h.loc[0,'IDADDRESS']=None
        with self.assertRaisesRegex(ValueError,'address key'):describe_systems(m,h,e)

    def test_historical_or_other_operator_does_not_become_fresh_wb(self):
        m,h,e=fixtures();c=pd.DataFrame([dict(source_record_id='c',provider_id='wrong',service_code='parcel_pickup',supply_status='observed'),dict(source_record_id='a',provider_id='wb',service_code='parcel_pickup_wildberries_current',supply_status='observed')]);d,a=describe_systems(m,h,e,c)
        self.assertEqual(d.set_index('unit_id').loc['v','wildberries_2026_mapped_pickup_features_known'],0)
        self.assertEqual(d.set_index('unit_id').loc['u','wildberries_2026_mapped_pickup_features_known'],1)

    def test_external_polygon_control_counts_unknown_np_without_assigning_ownership(self):
        from shapely.geometry import box
        from shapely import to_wkb
        _,_,e=fixtures();e['site_lat']=[1.,1.5];e['site_lon']=[1.,1.5]
        polygons=pd.DataFrame({'eFUA_ID':[1],'eFUA_name':['comparison'],'geometry_wkb':[to_wkb(box(0,0,2,2))],'geometry_crs':['EPSG:4326']})
        cities=pd.DataFrame({'source_record_id':['city','neighbour'],'name':['City','Neighbour'],'lat':[.5,.75],'lon':[.5,.75]})
        before=e.copy(deep=True)
        out=education_external_boundary_examples(e,polygons,cities)
        self.assertTrue(out.education_mapped_features_known.eq(2).all())
        self.assertTrue(out.education_higher_features_known.eq(1).all())
        self.assertTrue(out.education_mapped_features_np_identity_unresolved.eq(1).all())
        self.assertTrue(out.counts_are_inside_external_polygon_not_owned_by_city.all())
        self.assertFalse(out.external_polygon_is_formed_system.any())
        pd.testing.assert_frame_equal(e,before)
