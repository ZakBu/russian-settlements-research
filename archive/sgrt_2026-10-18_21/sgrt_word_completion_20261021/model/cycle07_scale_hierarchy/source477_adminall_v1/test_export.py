"""Actual export counterexample: historical source-only row stays visible atomic."""
import tempfile
from pathlib import Path
import numpy as np,pandas as pd
from scipy import sparse
from route_field import RouteField
from forest import Forest
from run import stage_export

def run():
 ids=list('ABCDxy');positions=np.array([0,1,2,3,.5,2.5]);t=np.abs(positions[:,None]-positions[:4]).astype('float32')
 routes=sparse.coo_matrix((t.ravel(),(np.repeat(np.arange(6),4),np.tile(np.arange(4),6))),shape=(6,4)).tocsr()
 field=RouteField(routes,pd.DataFrame({'canonical_id':ids}),pd.DataFrame({'id':list('ABCD'),'population_2021':[10]*4}),np.ones(4))
 f=Forest(field,ids,'protocol',gamma=.1);stages=[f.one_cap(1),f.one_cap(2)]
 nodes=pd.DataFrame({'id':ids+['Z'],'name':ids+['Z'],'lat':[50.]*7,'lon':[40.]*7,'region':['region']*7,'population_2021':[10]*6+[None],'source_record_id_2021':ids+[None],'_population_axis_row':[True]*7})
 with tempfile.TemporaryDirectory() as tmp:
  out=Path(tmp);stage_export(out,f,stages,nodes)
  for cap in [1,2]:
   u=pd.read_parquet(out/f'cap_{cap:03}_raw_units.parquet');m=pd.read_parquet(out/f'cap_{cap:03}_raw_memberships.parquet')
   for partition in m.partition_role.unique():
    x=m.loc[m.partition_role==partition];assert set(x.id)==set(ids+['Z']);assert x.id.is_unique
   historical=u.loc[u.core_id=='Z'];assert len(historical)==2
   assert historical.unit_role.eq('protected_carry').all() and historical.core_population_2021.isna().all()
   assert not historical.extent_complete.any()
   assert all(u.loc[u.unit_role=='territorial_unit','max_member_direct_minutes']<=cap+1e-4)
 print('Full exporter: allsourceatoms once/partition, historicalNA carry, actualdirectextent counterexamples PASS')
if __name__=='__main__':run()
