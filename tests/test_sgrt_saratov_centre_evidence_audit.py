import unittest
from unittest.mock import patch
import pandas as pd
from scripts.sgrt_saratov.centre_evidence_audit import audit


class CentreEvidence(unittest.TestCase):
    def data(self):
        profiles=pd.DataFrame([
            {'evidence_scenario':'all_dated_known','centre_in_regional_roster':True,'centre_id':'a','external_positive_origin_count':1,'known_own_basic_function_count':1},
            {'evidence_scenario':'all_dated_known','centre_in_regional_roster':True,'centre_id':'b','external_positive_origin_count':1,'known_own_basic_function_count':3},
            {'evidence_scenario':'nonhistorical_evidence_only','centre_in_regional_roster':True,'centre_id':'a','external_positive_origin_count':1,'known_own_basic_function_count':1}])
        members=pd.DataFrame([
            {'evidence_scenario':'all_dated_known','population_2021_published':100,'centre_id':'a','origin_id':'x','contributing_basic_family_count':1},
            {'evidence_scenario':'all_dated_known','population_2021_published':100,'centre_id':'b','origin_id':'y','contributing_basic_family_count':2}])
        return profiles,members

    def test_three_own_functions_do_not_mean_three_external_directions(self):
        profiles,members=self.data()
        with patch('scripts.sgrt_saratov.centre_evidence_audit.pd.read_parquet',side_effect=[profiles,members,profiles]):
            rows,s=audit('/unused')
        self.assertEqual(s['regional_model_candidates'],2)
        self.assertEqual(s['at_least_one_external_origin_in_two_basic_families'],1)
        self.assertEqual(s['at_least_one_external_origin_in_three_basic_families'],0)
        self.assertEqual(s['retained_without_historical_only_sources'],1)
        self.assertIsNone(s['independently_confirmed_centre_count'])

    def test_self_membership_cannot_establish_external_centre(self):
        profiles,members=self.data();members.loc[0,'origin_id']='a'
        with patch('scripts.sgrt_saratov.centre_evidence_audit.pd.read_parquet',side_effect=[profiles,members]):
            with self.assertRaises(ValueError):audit('/unused')
