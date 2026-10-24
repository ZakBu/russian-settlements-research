import importlib.util
from pathlib import Path
import unittest
import pandas as pd

P=Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/atlas.py'
spec=importlib.util.spec_from_file_location('zero_atlas',P);a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


class AtlasMeaningTests(unittest.TestCase):
 def base(self):
  ref=pd.DataFrame({'source_record_id':['a','b','c','d'],'analysis_origin':[True]*4,'lat':[1.]*4,'lon':[2.]*4})
  members=pd.DataFrame({'origin_id':['a','b','c','d'],'unit_id':['u1','u1','u2','u3']})
  units=pd.DataFrame({'unit_id':['u1','u2','u3'],'inhabited_multi_np_service_area':[True,False,False]})
  return ref,members,units
 def test_noncentre_member_is_not_grey_unknown(self):
  ref,m,u=self.base();e=pd.DataFrame({'origin_id':['a','b','c','d'],'provider_settlement_id':['a','a','c',None],'cost_minutes':[0.,5.,0.,None],'l0_admitted':[True,True,True,False],'service_status':['local_service_present','near_candidate','local_service_present','unknown_route_or_inventory'],'origin_road_endpoint_accepted':[True]*4})
  o=a.classified_origins(ref,m,u,e).set_index('source_record_id')
  self.assertEqual(o.loc['b','display_status'],'multi');self.assertEqual(o.loc['c','display_status'],'own');self.assertEqual(o.loc['d','display_status'],'unknown')
 def test_finite_but_unqualified_object_is_not_called_distant(self):
  ref,m,u=self.base();e=pd.DataFrame({'origin_id':['d'],'provider_settlement_id':[None],'cost_minutes':[5.],'l0_admitted':[False],'service_status':['unknown_route_or_inventory'],'origin_road_endpoint_accepted':[True],'admission_limit_minutes':[20.]})
  o=a.classified_origins(ref,m,u,e).set_index('source_record_id');self.assertEqual(o.loc['d','display_status'],'unknown')
 def test_no_road_does_not_erase_own_service(self):
  ref,m,u=self.base();e=pd.DataFrame({'origin_id':['c','d'],'provider_settlement_id':['c',None],'cost_minutes':[0.,None],'l0_admitted':[True,False],'known_local_supply':[True,False],'origin_road_endpoint_accepted':[False,False]})
  o=a.classified_origins(ref,m,u,e).set_index('source_record_id');self.assertEqual(o.loc['c','display_status'],'own');self.assertEqual(o.loc['d','display_status'],'no_road')
 def test_far_is_a_separate_model_state_not_no_data(self):
  ref,m,u=self.base();e=pd.DataFrame({'origin_id':['d'],'provider_settlement_id':['a'],'cost_minutes':[80.],'l0_admitted':[False],'service_status':['far_known_candidate'],'origin_road_endpoint_accepted':[True],'admission_limit_minutes':[20.]})
  o=a.classified_origins(ref,m,u,e).set_index('source_record_id');self.assertEqual(o.loc['d','display_status'],'far')


if __name__=='__main__':unittest.main()
