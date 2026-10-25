import sys
from pathlib import Path
import unittest
import json
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from hierarchy import demographic_summaries,inherit_provider_metadata
from type_readout import centre_periphery


def reference(rows):
    result=[]
    for ident,name,start,middle,end in rows:
        r={'source_record_id':ident,'name':name,'lat':50.,'lon':40.,'population_role':'ordinary_settlement_record','settlement_type_2021':'деревня'}
        for y,v in [(2002,start),(2010,middle),(2021,end)]:r[f'population_{y}']=v;r[f'credit_{y}']=v is not None
        result.append(r)
    return pd.DataFrame(result)


class TypeReadoutTests(unittest.TestCase):
    def test_cholkhov_unknown_live_population_cannot_be_stable_from_empty_markovshchina(self):
        ref=reference([('a','Чолхов',503,None,344),('b','Марковщина',2,0,0)])
        m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b']})
        x=demographic_summaries(m,ref).iloc[0]
        self.assertEqual(x.member_direction_2010_2021,'unknown')
        self.assertEqual(x.comparable_cohort_direction_2010_2021,'unchanged')
        self.assertEqual(x.comparable_cohort_population_2010_2021_start_sum,0)
        self.assertEqual(x.comparable_cohort_population_2010_2021_end_sum,0)
        self.assertEqual(x.member_population_2021_credited_sum,344)

    def test_zarechnoe_decline_is_explicit_partial_cohort_not_group_label(self):
        ref=reference([('a','Заречное',99,98,94),('b','Стригуны',None,1917,1751)])
        x=demographic_summaries(pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b']}),ref).iloc[0]
        self.assertEqual(x.member_direction_2002_2021,'unknown')
        self.assertEqual(x.comparable_cohort_direction_2002_2021,'decline')
        self.assertEqual(x.comparable_cohort_population_2002_2021_start_sum,99)
        self.assertEqual(x.comparable_cohort_population_2002_2021_end_sum,94)
        self.assertEqual(x.member_population_2021_credited_sum,1845)

    def test_observed_zero_to_zero_remains_known_when_complete(self):
        ref=reference([('a','Empty',0,0,0)])
        x=demographic_summaries(pd.DataFrame({'unit_id':['u'],'origin_id':['a']}),ref).iloc[0]
        self.assertEqual(x.member_direction_2002_2021,'unchanged')

    def test_retained_parent_keeps_actual_offers_and_separates_operation(self):
        children=pd.DataFrame({'unit_id':['a'],'cumulative_provider_keys_json':['["np:centre"]']})
        parents=pd.DataFrame({'unit_id':['p'],'new_territorial_merger':[False]})
        cross=pd.DataFrame({'child_unit_id':['a'],'unit_id':['p']})
        got=inherit_provider_metadata(parents,children,cross,{})
        self.assertEqual(got.operation_code.iloc[0],'retained_subsystem')
        self.assertEqual(got.type_code.iloc[0],'retained_subsystem')
        self.assertEqual(got.functional_type_code.iloc[0],'monocentric_service_profile')
        self.assertEqual(json.loads(got.cumulative_provider_keys_json.iloc[0]),['np:centre'])
        self.assertEqual(got.real_provider_keys_json.iloc[0],'[]')
        self.assertEqual(got.current_layer_provider_keys_json.iloc[0],'[]')
        next_layer=inherit_provider_metadata(parents,children,cross,{'p':['site:unknown']})
        self.assertEqual(next_layer.functional_type_code.iloc[0],'supplier_settlement_identity_partial_or_unknown')

    def test_external_malinki_centre_grows_but_surrounding_demand_shrinks(self):
        ref=reference([('c','Малинки',333,350,417),('a','Самара',11,5,2),('b','Рябцево',9,4,1)])
        u=pd.DataFrame({'unit_id':['u'],'provider_keys_json':['["np:c"]']});m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b']})
        x=centre_periphery(u,m,ref).iloc[0]
        self.assertFalse(x.centre_inside_demand_group)
        self.assertEqual(x.joint_centre_surrounding_direction_2002_2021,'growth__decline')
        self.assertEqual(x.surrounding_population_2021_known_sum,3)
        self.assertEqual(x.centre_population_2021,417)
        self.assertFalse(x.centre_population_added_to_member_budget)
        self.assertTrue(x.centre_is_descriptive_context)
        self.assertEqual(x.centre_reference_population_role,'ordinary_settlement_record')
        self.assertFalse(x.centre_is_nonadditive_city_aggregate)
        inside=pd.concat([m,pd.DataFrame({'unit_id':['u'],'origin_id':['c']})],ignore_index=True)
        ordinary_inside=centre_periphery(u,inside,ref).iloc[0]
        self.assertTrue(ordinary_inside.centre_inside_demand_group)
        self.assertFalse(ordinary_inside.centre_is_nonadditive_city_aggregate)
        self.assertEqual(ordinary_inside.surrounding_population_2021_known_sum,3)

    def test_moscow_administrative_aggregate_is_separate_from_an_ordinary_anchor(self):
        ref=reference([('c','Москва',10126424,11503501,13010112),('a','Village',10,9,8)])
        ref.loc[ref.source_record_id.eq('c'),'population_role']='external_context_nonadditive'
        u=pd.DataFrame({'unit_id':['u'],'provider_keys_json':['["np:c"]']})
        m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['c','a']})
        x=centre_periphery(u,m,ref).iloc[0]
        self.assertTrue(x.centre_is_descriptive_context)
        self.assertTrue(x.centre_inside_demand_group)
        self.assertEqual(x.centre_reference_population_role,'external_context_nonadditive')
        self.assertTrue(x.centre_is_nonadditive_city_aggregate)
        self.assertTrue(pd.isna(x.centre_population_2021))
        self.assertEqual(x.surrounding_population_2021_known_sum,8)
        self.assertEqual(x.centre_direction_2002_2021,'unknown')
        self.assertFalse(x.centre_population_added_to_member_budget)

    def test_nasurovo_declines_while_surrounding_grows_and_unknown_site_blocks_unique_centre(self):
        ref=reference([('c','Насурово',701,680,665),('a','Вешки',7,9,12),('b','Подлесное',10,12,17)])
        u=pd.DataFrame({'unit_id':['u'],'provider_keys_json':['["np:c"]']});m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b']})
        self.assertEqual(centre_periphery(u,m,ref).iloc[0].joint_centre_surrounding_direction_2002_2021,'decline__growth')
        u['provider_keys_json']='["np:c","site:unknown"]'
        x=centre_periphery(u,m,ref).iloc[0]
        self.assertFalse(x.unique_np_centre_established)
        self.assertEqual(x.joint_centre_surrounding_direction_2002_2021,'unknown')


if __name__=='__main__':unittest.main()
