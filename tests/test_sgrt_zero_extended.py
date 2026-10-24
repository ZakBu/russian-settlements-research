import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from extended import decide,provider_core_edges


def candidate(family,target='efua:1',complete=True,child='a'):
 return {'child_unit_id':child,'scenario_id':'test','service_family':family,'parent_target_key':target,
  'territorial_merge_admitted_for_all_child_members':complete,'real_provider_keys_json':'["np:p"]',
  'coverage_type':'complete_single_external_area_candidate' if complete else 'partial_higher_coverage'}

class ExtendedTests(unittest.TestCase):
 def test_rare_health_alone_cannot_create_general_urban_level(self):
  d,s=decide(pd.DataFrame([candidate('medical_hightech_licensed')]),'partial_positive_two_domains')
  self.assertTrue(d.parent_target_key.isna().all())

 def test_two_forms_of_medicine_are_one_domain(self):
  d,s=decide(pd.DataFrame([candidate('medical_inpatient'),candidate('medical_specialized')]),'partial_positive_two_domains')
  self.assertTrue(d.parent_target_key.isna().all())

 def test_partial_other_channel_is_recorded_not_imputed(self):
  c=pd.DataFrame([candidate('medical_specialized'),candidate('higher_education'),candidate('shopping_centre',complete=False)])
  d,s=decide(c,'partial_positive_two_domains');self.assertEqual(d.parent_target_key.iloc[0],'efua:1')
  self.assertTrue(d.partial_or_split_channel_present.iloc[0])
  strict,_=decide(c,'all_declared');self.assertTrue(strict.parent_target_key.isna().all())

 def test_complete_rival_is_never_outvoted(self):
  c=pd.DataFrame([candidate('medical_specialized'),candidate('higher_education'),candidate('shopping_centre','np:rival')])
  d,_=decide(c,'partial_positive_two_domains')
  self.assertEqual(d.decision_status.iloc[0],'retained_complete_competing_core')

 def test_children_cannot_pool_incomplete_functions(self):
  c=pd.DataFrame([candidate('medical_inpatient',child='a'),candidate('vocational_education',complete=False,child='a'),
   candidate('medical_inpatient',complete=False,child='b'),candidate('vocational_education',child='b')])
  d,_=decide(c,'partial_positive_two_domains');self.assertTrue(d.parent_target_key.isna().all())

 def test_origin_outside_core_allowed_rival_outside_preserved(self):
  r=pd.DataFrame({'origin_id':['rural','rural2'],'provider_settlement_id':['p','rival'],'provider_site_id':['s','s2'],
   'provider_lat':[50.,51.],'provider_lon':[40.,41.],'cost_minutes':[80.,20.],
   'source_id':['source','source'],'source_year':['2021','2026'],'location_precision':['settlement_point','object_point']})
  status=pd.DataFrame({'point_key':['s','s2'],'external_boundary_match_count':[1,0],'external_efua_ids_json':['[1]','[]']})
  d=provider_core_edges({'medical_inpatient':r},{'families':['medical_inpatient'],'limit_minutes':90.,'name':'test'},status)
  self.assertEqual(d.parent_target_key.tolist(),['efua:1','np:rival'])
  self.assertTrue(d.territorial_merge_admitted.all());self.assertFalse(d.provider_core_geometry_is_building_verified.any())

if __name__=='__main__':unittest.main()
