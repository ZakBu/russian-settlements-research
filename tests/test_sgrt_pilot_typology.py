"""Population accounting and honest unknown classes for fixed candidate zones."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
spec=importlib.util.spec_from_file_location("pilot_typology",Path(__file__).parents[1]/"scripts/sgrt_pilot/typology.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class CandidateZoneTypes(unittest.TestCase):
    def frame(self):
        s=pd.DataFrame({"source_record_id":["C","A","B"],"root":["c","a","b"],"population":[100,12,0]})
        w=pd.DataFrame({"root":["c","a","b"],"effective_population_2002":[80,20,np.nan],"effective_population_2010":[90,10,np.nan],"effective_population_2021":[100,12,0],"population_2002":[80,20,np.nan],"population_2010":[90,15,np.nan],"population_2021":[100,12,0]})
        a=pd.DataFrame({"origin_id":["C","A","B"],"center_id":["C","C","C"],"scenario":["x"]*3,"function":["medicine"]*3,"service_order":["primary"]*3})
        return a,s,w
    def test_unknown_history_not_zero_and_center_not_double_counted(self):
        a,s,w=self.frame();r=m.classify_units(a,s,w).iloc[0]
        self.assertEqual(r.external_members,2)
        self.assertEqual(r.external_comparable_histories,1)
        self.assertEqual(r.surroundings_comparable_effective_population_2002,20)
        self.assertEqual(r.center_effective_population_2002,80)
        self.assertEqual(r.temporal_coverage_status,"partial_or_missing_numeric_history")
        self.assertEqual(r.type_code,"center_growth__surroundings_decline")
    def test_no_external_members_is_not_stable_periphery(self):
        a,s,w=self.frame();r=m.classify_units(a.iloc[:1],s,w).iloc[0]
        self.assertEqual(r.type_code,"node_without_external_members")
        self.assertTrue(pd.isna(r.surroundings_comparable_effective_population_2021))
    def test_duplicate_members_rejected(self):
        a,s,w=self.frame()
        with self.assertRaises(ValueError):m.classify_units(pd.concat([a,a.iloc[:1]]),s,w)
    def test_missing_center_history_has_explicit_type(self):
        a,s,w=self.frame();w.loc[0,"effective_population_2002"]=np.nan
        self.assertEqual(m.classify_units(a,s,w).iloc[0].type_code,"insufficient_comparable_demography")
    def test_uncredited_observations_excluded_from_additive_demography(self):
        a,s,w=self.frame();s["working_credit_present"]=[True,False,False]
        for y in (2002,2010,2021):w[f"working_credit_present_{y}"]=[True,False,False]
        r=m.classify_units(a,s,w).iloc[0]
        self.assertEqual(r.external_comparable_histories,0)
        self.assertTrue(pd.isna(r.external_current_population))
        self.assertEqual(r.type_code,"node_without_known_populated_external_members")
        self.assertEqual(r.inhabited_external_zone_status,"external_inhabited_zone_unresolved")
    def test_external_context_center_has_no_invented_ordinary_history(self):
        a,s,w=self.frame();ctx=pd.DataFrame({"source_record_id":["ctx:SPB"],"root":["external_context:SPB"],"population":[5601911],"working_credit_present":[False]})
        s=pd.concat([s,ctx],ignore_index=True);a["center_id"]="ctx:SPB"
        r=m.classify_units(a,s,w).iloc[0]
        self.assertTrue(r.center_is_external_context)
        self.assertTrue(pd.isna(r.center_effective_population_2021))
        self.assertEqual(r.external_members,3)
        self.assertEqual(r.type_code,"external_context_not_ordinary_settlement")
        self.assertIsNone(r.center_root)
    def test_empty_external_settlements_do_not_make_inhabited_zone(self):
        a,s,w=self.frame();s.loc[1:,"population"]=0;s["working_credit_present"]=True
        r=m.classify_units(a,s,w).iloc[0]
        self.assertEqual(r.external_members,2)
        self.assertEqual(r.external_positive_credited_settlements,0)
        self.assertEqual(r.inhabited_external_zone_status,"no_populated_external_zone_in_scenario")
        self.assertEqual(r.type_code,"node_without_known_populated_external_members")
    def test_null_population_is_not_zero_change(self):
        self.assertEqual(m.direction(np.nan,0),"unknown")
        self.assertEqual(m.direction(0,0),"unchanged")
if __name__=="__main__":unittest.main()
