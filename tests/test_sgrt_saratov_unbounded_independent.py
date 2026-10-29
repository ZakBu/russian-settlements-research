import json
import hashlib
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from scripts.sgrt_saratov.regional_independent_checks import independent_full_cost_rows,kernel_scalar,GRAPH_SHA256
from scripts.sgrt_saratov.unbounded_independent_checks import source_mass_oracle,lower_time_minutes


class UnboundedIndependentTests(unittest.TestCase):
    def test_mass_uses_credit_not_spatial_budget_and_never_adds_third_city(self):
        reference=pd.DataFrame({'source_record_id':['v','matan39','moscow','spb','sev'],
            'population_role':['ordinary_settlement_record']*2+['external_context_nonadditive']*3,
            'population_2021':[100.,39.,1000.,500.,2000.],
            'credit_2021':[True,True,False,False,False],
            'budget_population_credit':[True,False,False,False,False]})
        federal=pd.DataFrame({'census_year':[2021,2021], 'territory_key':['RU-FED-MOW','RU-FED-SPB'],
            'population_source_record_id':['moscow','spb'],'territory_population':[1000.,500.]})
        ordinary,aggregate,pop=source_mass_oracle(reference,federal)
        self.assertEqual(float(pop[ordinary|aggregate].sum()),1639.)
        self.assertEqual(float(pop[aggregate].sum()),1500.)
        with self.assertRaises(ValueError):source_mass_oracle(reference,pd.concat([federal,federal.iloc[:1]]))
        reference.loc[2,'population_role']='ordinary_settlement_record';reference.loc[2,'credit_2021']=True
        with self.assertRaises(ValueError):source_mass_oracle(reference,federal)

    def test_full_cost_reader_distinguishes_infinity_nan_and_beyond480(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fields=root/'fields';cache=root/'cache';fields.mkdir();cache.mkdir()
            dest=pd.DataFrame({'destination_index':[0,1,2],'source_record_id':['a','b','c']})
            dest.to_parquet(fields/'destinations.parquet',index=False);dest.to_parquet(cache/'destination_axis.parquet',index=False)
            pd.DataFrame({'full_row_index':[0,1],'source_record_id':['a','unknown'],'accepted_source_endpoint':[True,False]}).to_parquet(cache/'origin_axis.parquet',index=False)
            for name in ['national_reference_with_endpoints.parquet','regional_roster.parquet','halo_roster.parquet']:(fields/name).write_text('immutable fixture')
            contract={'graph_sha256':GRAPH_SHA256}
            for key,name in [('reference_sha256','national_reference_with_endpoints.parquet'),('regional_roster_sha256','regional_roster.parquet'),('halo_roster_sha256','halo_roster.parquet'),('destinations_sha256','destinations.parquet')]:contract[key]=hashlib.sha256((fields/name).read_bytes()).hexdigest()
            (cache/'contract.json').write_text(json.dumps(contract))
            (cache/'complete.json').write_text(json.dumps({'complete':True}))
            x=np.array([[0.,604.,np.inf],[np.nan,np.nan,np.nan]]);np.save(cache/'full_destination_costs.npy',x)
            rows=independent_full_cost_rows(fields,cache)
            self.assertGreater(kernel_scalar(rows['a'][1],120.,'exp'),0.)
            self.assertEqual(kernel_scalar(rows['a'][2],120.,'exp'),0.)
            self.assertIsNone(kernel_scalar(rows['unknown'][1],120.,'exp'))
            x[0,2]=np.nan;np.save(cache/'full_destination_costs.npy',x)
            with self.assertRaises(ValueError):independent_full_cost_rows(fields,cache)

    def test_selected_control_origin_axis_cannot_be_silently_reordered(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fields=root/'fields';scope=root/'scope';fields.mkdir();scope.mkdir()
            pd.DataFrame({'destination_index':[0],'source_record_id':['a']}).to_parquet(fields/'destinations.parquet',index=False)
            pd.DataFrame({'full_row_index':[3],'source_record_id':['a']}).to_parquet(scope/'selected_unbounded_origin_axis.parquet',index=False)
            (scope/'selected_unbounded_cost_control.json').write_text(json.dumps({
                'destination_count':1,'destination_source_record_ids_sha256':hashlib.sha256(b'["a"]').hexdigest(),
                'destinations_parquet_sha256':hashlib.sha256((fields/'destinations.parquet').read_bytes()).hexdigest(),
                'selected_origin_id_by_full_row_index':{'3':'a'}}))
            np.savez(scope/'selected_unbounded_full_costs.npz',costs=np.array([[0.]]),full_row_indices=np.array([4]))
            with self.assertRaises(ValueError):independent_full_cost_rows(fields,controls_root=scope)

    def test_unlocated_source_is_upper_bound_not_zero_population(self):
        self.assertEqual(lower_time_minutes(50.,45.,math.nan,math.nan),0.)
        self.assertEqual(39.*kernel_scalar(lower_time_minutes(50.,45.,math.nan,math.nan),120.,'exp'),39.)
        self.assertGreater(lower_time_minutes(50.,45.,51.,45.),0.)

if __name__=='__main__':unittest.main()
