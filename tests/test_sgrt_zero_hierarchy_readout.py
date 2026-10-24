import importlib.util
from pathlib import Path
import tempfile
import unittest

import pandas as pd

SPEC=importlib.util.spec_from_file_location('hierarchy_readout',Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/hierarchy_readout.py')
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)


class ReadoutTests(unittest.TestCase):
    def fixture(self,path):
        reference=pd.DataFrame({'source_record_id':['a','b','c','m',None,None],
          'name':['А','Б','В','Москва','old','old2'],'region':['r','r','r','москва','r','r'],
          'settlement_type_2021':['село','село','село','город',None,None],
          'analysis_origin':[True,True,True,True,False,False],
          'lat':[55.,55.01,56.,55.75,None,None],'lon':[37.,37.01,38.,37.61,None,None],
          'population_2021':[100.,40.,20.,13010112.,None,None],
          'population_role':['ordinary_settlement_record']*3+['external_context_nonadditive','other','other'],
          'credit_2021':[True,True,True,False,False,False]})
        members=pd.DataFrame({'unit_id':['ab','ab','c','m'],'origin_id':['a','b','c','m']})
        units=pd.DataFrame({'unit_id':['ab','c','m'],'member_records':[2,1,1],
          'positive_credited_member_records':[2,1,0],
          'member_population_2021_credited_sum':[140.,20.,None],
          'member_geodesic_diameter_km':[2.,0.,0.],'known_daily_families':[3,0,3],
          'all_core_daily_families_have_candidate':[True,False,True]})
        members.to_parquet(path/'level0_memberships.parquet',index=False)
        units.to_parquet(path/'level0_units.parquet',index=False)
        return reference

    def test_counts_and_city_context_are_separate_and_files_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);reference=self.fixture(path)
            before={p.name:MODULE.digest(p) for p in path.iterdir()}
            result=MODULE.describe(path,reference,True)
            self.assertEqual(result['inhabited_multi_np_service_groups'],1)
            self.assertEqual(result['inhabited_multi_np_with_all_three_core_families'],1)
            self.assertEqual(result['units_with_one_member_record'],2)
            self.assertEqual(result['no_admitted_daily_link_units'],1)
            self.assertEqual(result['ordinary_credited_population_2021_all_units'],160.)
            self.assertEqual(result['named_cases'][0]['name'],'Москва')
            self.assertEqual(before,{p.name:MODULE.digest(p) for p in path.iterdir()})

    def test_missing_origin_fails_instead_of_reporting_partial_frame(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);reference=self.fixture(path)
            members=pd.read_parquet(path/'level0_memberships.parquet').iloc[:-1]
            members.to_parquet(path/'level0_memberships.parquet',index=False)
            with self.assertRaisesRegex(ValueError,'exact partition'):MODULE.describe(path,reference,True)

    def test_extent_is_kilometres_and_anchor_radius_is_not_diameter(self):
        points=pd.DataFrame({'lat':[0.,0.],'lon':[-1.,1.]})
        anchor=pd.Series({'lat':0.,'lon':0.})
        result=MODULE.extent(points,anchor)
        self.assertAlmostEqual(result['wgs84_member_diameter_km'],222.6389816,places=5)
        self.assertAlmostEqual(result['anchor_max_distance_km'],111.3194908,places=5)


if __name__=='__main__':unittest.main()
