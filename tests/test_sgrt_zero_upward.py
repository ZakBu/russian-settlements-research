import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from upward import prepare_stage_edges,one_area_keys


def route(provider='p',cost=20.):
 return pd.DataFrame({'origin_id':['a'],'provider_settlement_id':[provider],'provider_site_id':['physical-'+provider],
  'provider_lat':[50.],'provider_lon':[40.],'cost_minutes':[cost],'source_id':['official2026'],'source_year':[2026]})


def status(key,ids):
 return pd.DataFrame([{key:k,'external_boundary_match_count':len(v),'external_efua_ids_json':str(v)} for k,v in ids.items()])


class UpwardTests(unittest.TestCase):
 def test_rural_direct_medical_does_not_require_an_urban_fua(self):
  stage={'name':'physician','families':['physician'],'guard':'direct_bounded_functional_medical_scenario','limit_minutes':30.,'source_role':'explicit_dated_transport_scenario'}
  d=prepare_stage_edges({'physician':route()},stage,status('source_record_id',{'a':[]}),status('point_key',{'physical-p':[]}))
  self.assertTrue(d.territorial_merge_admitted.iloc[0]);self.assertTrue(d.higher_admitted.iloc[0])

 def test_external_target_does_not_replace_real_supplier(self):
  stage={'name':'hospital','families':['hospital'],'guard':'same_external_estimated_efua2015','limit_minutes':90.,'source_role':'author_sensitivity'}
  d=prepare_stage_edges({'hospital':route()},stage,status('source_record_id',{'a':[123]}),status('point_key',{'physical-p':[123]}))
  self.assertEqual(d.provider_settlement_id.iloc[0],'p');self.assertEqual(d.provider_site_id.iloc[0],'physical-p')
  self.assertEqual(d.parent_target_key.iloc[0],'efua:123');self.assertEqual(d.parent_target_kind.iloc[0],'external_functional_area')
  self.assertTrue(d.territorial_merge_admitted.iloc[0]);self.assertFalse(d.external_reference_is_observed_commuting.iloc[0])

 def test_different_or_ambiguous_external_areas_do_not_merge(self):
  stage={'name':'hospital','families':['hospital'],'guard':'same_external_estimated_efua2015','limit_minutes':90.,'source_role':'author_sensitivity'}
  for source_ids,provider_ids in [([1],[2]),([1,2],[1]),([],[1]),([1],[])]:
   d=prepare_stage_edges({'hospital':route()},stage,status('source_record_id',{'a':source_ids}),status('point_key',{'physical-p':provider_ids}))
   self.assertFalse(d.territorial_merge_admitted.iloc[0]);self.assertTrue(d.higher_admitted.iloc[0])

 def test_long_connection_remains_evidence_without_territorial_admission(self):
  stage={'name':'hospital','families':['hospital'],'guard':'same_external_estimated_efua2015','limit_minutes':90.,'source_role':'author_sensitivity'}
  d=prepare_stage_edges({'hospital':route(cost=200.)},stage,status('source_record_id',{'a':[1]}),status('point_key',{'physical-p':[1]}))
  self.assertEqual(d.cost_minutes.iloc[0],200.);self.assertFalse(d.higher_admitted.iloc[0]);self.assertFalse(d.territorial_merge_admitted.iloc[0])

 def test_boundary_status_count_must_agree_with_ids(self):
  d=status('source_record_id',{'a':[1]});d.loc[0,'external_efua_ids_json']='[1,2]'
  with self.assertRaisesRegex(ValueError,'disagrees'):one_area_keys(d,'source_record_id')


if __name__=='__main__':unittest.main()
