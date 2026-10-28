import unittest
import pandas as pd
from scripts.sgrt_saratov.source_inventory import prepare, PREFIX, ANCHORS


def fixture():
    records=[]
    for name,n in ANCHORS.items():
        records.append(dict(source_record_id=PREFIX+str(n),name=name,region='саратовская',
            ordinary_spatial_2021=True,accepted_point_present=True,
            settlement_type_2021='село' if name=='Питерка' else 'город',population_2021=10.,
            credit_2021=True,budget_population_credit=True))
    records.extend([
        dict(source_record_id='zero',name='Пустая',region='саратовская',ordinary_spatial_2021=True,
             accepted_point_present=True,settlement_type_2021='деревня',population_2021=0.,credit_2021=True,budget_population_credit=True),
        dict(source_record_id='uncredited',name='Число опубликовано',region='саратовская',ordinary_spatial_2021=True,
             accepted_point_present=True,settlement_type_2021='деревня',population_2021=7.,credit_2021=False,budget_population_credit=False),
        dict(source_record_id='no_geometry',name='Без координат',region='саратовская',ordinary_spatial_2021=False,
             accepted_point_present=False,settlement_type_2021='деревня',population_2021=5.,credit_2021=False,budget_population_credit=False),
        dict(source_record_id=None,name='Историческая цепочка',region='саратовская',ordinary_spatial_2021=False,
             accepted_point_present=False,settlement_type_2021=None,population_2021=None,credit_2021=False,budget_population_credit=False)])
    r=pd.DataFrame(records)
    e=pd.DataFrame([dict(source_record_id=x.source_record_id,road_node_index=i,snap_km=.01,
        road_endpoint_accepted=True,verified_component_id=2,verified_component_node_count=100)
        for i,x in enumerate(r.itertuples()) if x.source_record_id])
    u=pd.DataFrame([dict(centre_settlement_id=PREFIX+str(118372),is_registered_external_serving_centre=True,external_participant_count=2)])
    edges=pd.DataFrame([dict(origin_id=x.source_record_id,service_family=f,known_local_supply=(f=='medical_basic'),
        provider_historical_source_only=(f=='medical_basic'))
        for x in r.itertuples() if x.source_record_id for f in ['school','medical_basic','grocery']])
    return r,e,u,edges


class SourceInventoryTests(unittest.TestCase):
    def test_zero_and_uncredited_are_retained_separate_from_missing_geometry(self):
        r,e,u,s=fixture();before=r.copy(deep=True)
        region,p,excluded,h,anchors,edges=prepare(r,e,u,s)
        self.assertEqual(len(p),8)
        self.assertEqual(p.set_index('source_record_id').loc['zero','population_2021'],0)
        self.assertEqual(p.set_index('source_record_id').loc['uncredited','population_2021'],7)
        self.assertEqual(excluded.source_record_id.tolist(),['no_geometry'])
        self.assertEqual(len(h),1)
        pd.testing.assert_frame_equal(r,before)

    def test_station_cannot_replace_the_village(self):
        r,e,u,s=fixture()
        r.loc[r.source_record_id.eq(PREFIX+'117733'),'settlement_type_2021']='железнодорожный объект'
        with self.assertRaisesRegex(ValueError,'identity/type'):
            prepare(r,e,u,s)

    def test_missing_school_evidence_is_unknown_not_a_positive_school(self):
        r,e,u,s=fixture();s=s[s.service_family.ne('school')]
        _,p,_,_,_,_=prepare(r,e,u,s)
        self.assertFalse(p.school_source_row_known.any())
        self.assertFalse(p.school_known_local_presence.any())
        self.assertTrue(p.medical_basic_known_historical_only.all())
        self.assertTrue(p.known_local_basic_function_count.eq(1).all())

    def test_conflicting_duplicate_outcomes_fail_instead_of_silent_coalescing(self):
        r,e,u,s=fixture();s=pd.concat([s,s.iloc[[0]]],ignore_index=True)
        with self.assertRaisesRegex(ValueError,'service outcome'):
            prepare(r,e,u,s)


if __name__=='__main__':unittest.main()
