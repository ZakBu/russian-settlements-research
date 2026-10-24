import importlib.util
from pathlib import Path
import unittest
import pandas as pd

spec=importlib.util.spec_from_file_location('zero_city_context_tested',Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/city_context.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class CityContextTests(unittest.TestCase):
    def fixture(self):
        ref=pd.DataFrame({'source_record_id':['village','city'],'name':['Село','Город'],
            'lat':[51.,float('nan')],'lon':[46.,float('nan')],
            'population_role':['ordinary_settlement_record']*2,'ordinary_spatial_2021':[True,False],
            'credit_2002':[True,True],'credit_2010':[True,True],'credit_2021':[True,True]})
        context=pd.DataFrame({'source_record_id':['city'],'lat':[59.95],'lon':[30.31],
            'source_id':['fixed_public_city_reference'],'coordinate_precision_degrees':[.016]})
        return ref,context

    def test_city_has_geometry_but_cannot_duplicate_population_budget(self):
        ref,context=self.fixture();before=ref.copy(deep=True)
        out=module.enrich_reference(ref,context)
        pd.testing.assert_frame_equal(ref,before)
        self.assertEqual(out.analysis_origin.sum(),2)
        self.assertEqual(out.ordinary_spatial_2021.sum(),1)
        self.assertEqual(out.budget_population_credit.sum(),1)
        self.assertFalse(out.loc[1,'credit_2021'])
        self.assertEqual(out.loc[1,'population_role'],'external_context_nonadditive')
        self.assertEqual(out.loc[0,'lat'],51.)

    def test_unknown_city_identity_is_not_created_as_a_census_record(self):
        ref,context=self.fixture();context['source_record_id']='invented'
        with self.assertRaisesRegex(ValueError,'absent'):module.enrich_reference(ref,context)

    def test_duplicate_context_does_not_multiply_an_origin(self):
        ref,context=self.fixture()
        with self.assertRaisesRegex(ValueError,'Duplicate'):module.enrich_reference(ref,pd.concat([context,context]))


if __name__=='__main__':unittest.main()
