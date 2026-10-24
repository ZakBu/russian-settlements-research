from pathlib import Path
import sys,unittest,json
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from population_context import build_population_context

class PopulationContextTests(unittest.TestCase):
 def test_administrative_city_population_is_not_added_to_members(self):
  members=pd.DataFrame({'unit_id':['u','u','v'],'origin_id':['moscow','village','other']})
  reference=pd.DataFrame({'source_record_id':['moscow','village','other'],'name':['Москва','Деревня','Село'],
   'population_role':['external_context_nonadditive','ordinary_settlement_record','ordinary_settlement_record'],
   'population_2002':[10000000,50,30],'population_2010':[11000000,40,25],'population_2021':[13010112,30,20]})
  original=members.copy(deep=True);r=build_population_context(members,reference).set_index('unit_id')
  pd.testing.assert_frame_equal(members,original)
  self.assertTrue(r.loc['u','contains_nonadditive_city_context']);self.assertFalse(r.loc['v','contains_nonadditive_city_context'])
  c=json.loads(r.loc['u','city_population_context_json']);self.assertEqual(c[0]['population_2021_context'],13010112.)
  self.assertFalse(c[0]['added_to_ordinary_member_budget']);self.assertFalse(r.full_unit_population_established.any())

if __name__=='__main__':unittest.main()
