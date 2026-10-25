import json
import sys
import tempfile
from pathlib import Path
import unittest
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from centre_stars import build_centre_stars
from centre_readout import readout


class CentreReadoutTests(unittest.TestCase):
    def fixture(self,root,admit=True,missing_past=False):
        sid='daily_20_school30_wb'
        ref=pd.DataFrame({'source_record_id':['a','c'],'name':['Village','Centre'],
            'region':['region']*2,'district':['district']*2,'lat':[50.,50.02],'lon':[40.,40.02],
            'population_role':['ordinary_settlement_record']*2,'population_2021':[10.,100.],
            'budget_population_credit':[True]*2,'analysis_origin':[True]*2,
            'settlement_type_2021':['село']*2})
        for y in [2002,2010,2021]:
            ref[f'credit_{y}']=True
            if y!=2021:ref[f'population_{y}']=[20.,200.]
        if missing_past:ref.loc[ref.source_record_id.eq('a'),'population_2002']=float('nan')
        rows=pd.DataFrame([{'origin_id':o,'service_family':f,'provider_settlement_id':'c',
            'provider_site_id':f+'-site','cost_minutes':0. if o=='c' else 3.,
            'l0_admitted':admit,'admission_basis':'test','scenario_id':sid}
            for o in ['a','c'] for f in ['medical_basic','school','grocery']])
        tables,_=build_centre_stars(rows,ref)
        folder=root/'scenarios'/sid;folder.mkdir(parents=True)
        for name in ['strict_three_core_stars','strict_three_core_memberships','centre_stars']:
            tables[name].to_parquet(folder/(name+'.parquet'),index=False)
        rows.to_parquet(folder/'daily_edges.parquet',index=False)
        (folder/'summary.json').write_text(json.dumps({'scenario_id':sid}))
        path=root/'reference.parquet';ref.to_parquet(path,index=False)
        return path

    def test_empty_subset_is_a_valid_negative_result(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ref=self.fixture(root,admit=False)
            result=readout(root,ref)
            self.assertEqual(result['strict_model_groups'],0)
            self.assertEqual(result['diameter_km']['max'],None)
            self.assertEqual(result['joint_centre_surrounding_2002_2021'],{})

    def test_missing_surrounding_history_never_becomes_total_decline(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ref=self.fixture(root,missing_past=True)
            result=readout(root,ref)
            self.assertEqual(result['joint_centre_surrounding_2002_2021'],{'unknown':1})
            self.assertEqual(result['joint_centre_surrounding_2010_2021'],{'decline__decline':1})
            self.assertTrue((root/'checked_model_centres.csv').exists())

    def test_historical_rows_without_current_identity_do_not_duplicate_join(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=self.fixture(root)
            ref=pd.read_parquet(path)
            historic=ref.iloc[[0,0]].copy();historic['source_record_id']=None
            pd.concat([ref,historic],ignore_index=True).to_parquet(path,index=False)
            self.assertEqual(readout(root,path)['strict_model_groups'],1)
