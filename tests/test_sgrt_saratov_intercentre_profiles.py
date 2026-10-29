import unittest,json
import pandas as pd
from scripts.sgrt_saratov.intercentre_profiles import build


def choice(origin,family,targets):
 return dict(origin_id=origin,family=family,evidence_scenario='all',inventory_scenario='test',
  cost_minutes=5.,coequal_primary_keys_json=json.dumps(targets),known_local_supply=False,
  provider_settlement_id=targets[0][3:] if targets[0].startswith('np:') else None,
  ambiguous_primary=len(targets)>1)

class DirectCentreRelations(unittest.TestCase):
 def profiles(self):return pd.DataFrame([dict(centre_id=i,evidence_scenario='all',centre_in_regional_roster=True) for i in ['a','b','c']])
 def test_transitive_chain_does_not_create_a_direct_relation(self):
  links=pd.DataFrame([choice('a','doctor',['np:b']),choice('b','doctor',['np:c']),choice('c','doctor',['np:c'])])
  _,e,_,pairs=build(self.profiles(),links)
  self.assertFalse(((e.origin_id=='a')&(e.destination_np_id=='c')).any());self.assertTrue(pairs.empty)
 def test_cross_function_reciprocity_retains_both_centre_roles(self):
  links=pd.DataFrame([choice('a','doctor',['np:b']),choice('b','school',['np:a']),choice('c','doctor',['np:c'])])
  _,e,_,pairs=build(self.profiles(),links)
  self.assertEqual(len(pairs),1);self.assertFalse(pairs.merge_into_one_system.any());self.assertFalse(e.actual_intercentre_flow_observed.any())
 def test_ties_and_unidentified_physical_sites_survive(self):
  links=pd.DataFrame([choice('a','doctor',['np:b','site:x']),choice('b','doctor',['np:c']),choice('c','doctor',['np:c'])])
  _,e,_,_=build(self.profiles(),links);a=e[e.origin_id=='a']
  self.assertEqual(len(a),2);self.assertFalse(a.model_choice_unique.any());self.assertEqual(a.destination_np_id.isna().sum(),1)

if __name__=='__main__':unittest.main()
