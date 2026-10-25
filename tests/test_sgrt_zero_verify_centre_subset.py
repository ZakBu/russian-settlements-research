import sys
import unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from verify_centre_subset import expected_pairs,verify,LIMITS


class IndependentSubsetTests(unittest.TestCase):
    def test_missing_function_cannot_be_replaced_by_two_satellites(self):
        ref=pd.DataFrame({'source_record_id':['a','b','c'],'name':['A','B','C'],
            'population_2021':[10.,10.,20.],'analysis_origin':True,
            'population_role':'ordinary_settlement_record','budget_population_credit':True})
        rows=pd.DataFrame([{'origin_id':o,'service_family':f,'provider_settlement_id':'c',
            'provider_site_id':f,'cost_minutes':3.,'local_service_present':o=='c'}
            for o,fs in [('a',['school','grocery']),('b',['medical_basic']),('c',['school','grocery','medical_basic'])] for f in fs])
        self.assertEqual(expected_pairs(rows,ref,LIMITS['daily_20_school30_wb']),set())

    def test_extra_member_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'extra 1'):
            verify({('a','c'),('c','c')},pd.DataFrame({'origin_id':['a','b','c'],'centre_settlement_id':['c']*3}))
