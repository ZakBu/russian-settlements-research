import unittest
from pathlib import Path
import numpy as np,pandas as pd
from run_model import xyz,km,huff,nearest
O=Path(__file__).resolve().parent
class Invariants(unittest.TestCase):
 def test_spherical_known_distance(self):
  c=xyz(np.array([0,0]),np.array([0,1]));self.assertAlmostEqual(km(np.linalg.norm(c[0]-c[1])),111.1950802335329,places=8)
 def test_raw_huff_and_nearest_are_distinct(self):
  c=xyz(np.array([55,55,55]),np.array([37,37.1,37.05]));ci=np.array([0,1]);m=np.array([100,10000,20]);r=huff(c,ci,m);a,_=nearest(c,ci,100);self.assertEqual(a[0],0);self.assertEqual(r['raw_huff_winner'][0],1);self.assertAlmostEqual(r['raw_huff_pmax'][2]+r['raw_huff_psecond'][2],1,places=12)
 def test_zero_weights_do_not_win(self):
  c=xyz(np.array([55,55]),np.array([37,37.1]));r=huff(c,np.array([0]),np.array([0,0]));self.assertTrue((r['raw_huff_winner']==-1).all());self.assertTrue((r['raw_huff_pmax']==0).all())
 def test_exact_population_with_residual(self):
  s=pd.read_parquet(O/'nearest_membership.parquet');z=pd.read_parquet(O/'zone_trajectories.parquet');p=pd.read_parquet(O.parent/'data/panel.parquet');self.assertEqual(len(s),len(p));self.assertEqual(int(s.population_2010.eq(0).sum()),int(p.population_2010.eq(0).sum()))
  for y in [2002,2010,2021]:self.assertEqual(s[f'population_{y}'].sum(),z[f'population_{y}'].sum())
 def test_no_cycle_and_nested_balance(self):
  c=pd.read_parquet(O/'centers.parquet');mass=dict(zip(c.id,c.population_2010))
  for _,r in c[c.parent_id.notna()].iterrows():self.assertGreater(mass[r.parent_id],r.population_2010)
  s=pd.read_parquet(O/'nearest_membership.parquet');n=pd.read_parquet(O/'nested_aggregates.parquet')
  for _,a in n.groupby('aggregation_step'):
   for y in [2002,2010,2021]:self.assertEqual(a[f'population_{y}'].sum(),s[f'population_{y}'].sum())
 def test_exact_symmetric_decomposition(self):
  d=pd.read_parquet(O/'fixed_dynamic_decomposition.parquet');s=pd.read_parquet(O/'nearest_membership.parquet');delta=d.symmetric_demographic_effect+d.symmetric_reallocation_effect-d.observed_dynamic_change;self.assertLess(abs(delta).max(),1e-6)
  for base,a in d.groupby('baseline_year'):self.assertLess(abs(a.symmetric_reallocation_effect.sum()),1e-6);self.assertEqual(a.observed_dynamic_change.sum(),(s.population_2021-s[f'population_{base}']).sum())
if __name__=='__main__':unittest.main(verbosity=2)
