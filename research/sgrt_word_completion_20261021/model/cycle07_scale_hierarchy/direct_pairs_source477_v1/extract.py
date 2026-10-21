"""Actual source-directed member→focal time witnesses for every bounded scenario.
Unassigned atomic self IDs never become fabricated route0/dependent evidence.
"""
from pathlib import Path
import json,hashlib,argparse
import pandas as pd,numpy as np,pyarrow as pa,pyarrow.parquet as pq
from scipy import sparse
HERE=Path(__file__).resolve().parent;BASE=next(x for x in HERE.parents if (x/'transport').is_dir() and (x/'model').is_dir());ENGINE=HERE.parent

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--partition',choices=['supported_end_forest','candidate_knee_or_fallback'],default='supported_end_forest');a=ap.parse_args()
 source=a.source;cache=a.cache;out=a.output
 if out.exists() and any(out.iterdir()):raise ValueError('fresh pair output required')
 out.mkdir(parents=True,exist_ok=True);bind=json.load(open(source/'pre_execution_binding.json'))
 inputs={str(source/'pre_execution_binding.json'):sha(source/'pre_execution_binding.json')}
 for name,expected in bind['numeric_cache_source_hashes'].items():
  p=cache/name
  if sha(p)!=expected:raise ValueError('sourcecache byte mismatch')
  inputs[str(p)]=expected
 nodespath=BASE/bind['protocol']['source_nodes']
 if sha(nodespath)!=bind['inputs'][str(nodespath.relative_to(BASE))]:raise ValueError('sourceaxis changed')
 nodes=pd.read_parquet(nodespath,columns=['id','source_record_id_2021','population_2021','accepted_statistical_rural_role2021','_population_axis_row']).rename(columns={'population_2021':'source_population_2021','accepted_statistical_rural_role2021':'statistical_rural_role2021','_population_axis_row':'is_population_axis_member'})
 routes=sparse.load_npz(cache/'routes_180.npz');o=pd.read_parquet(cache/'origin_mapping.parquet',columns=['canonical_id']);p=pd.read_parquet(cache/'provider_mapping.parquet',columns=['id']);omap=pd.Series(np.arange(len(o)),index=o.canonical_id);dmap=pd.Series(np.arange(len(p)),index=p.id)
 dest=out/'directed_member_to_focal_pairs.parquet';writer=None;summary=[]
 try:
  for cap in [30,45,60,90,120]:
   up=source/f'cap_{cap:03}_raw_units.parquet';mp=source/f'cap_{cap:03}_raw_memberships.parquet';inputs[str(up)]=sha(up);inputs[str(mp)]=sha(mp)
   u=pd.read_parquet(up);u=u.loc[u.partition_role.eq(a.partition),['unit_id','core_id','unit_role','kind']]
   m=pd.read_parquet(mp);m=m.loc[m.partition_role.eq(a.partition),['unit_id','id']].merge(u,on='unit_id',validate='many_to_one').merge(nodes,on='id',validate='one_to_one')
   m['candidate_cap']=cap;m['partition_role']=a.partition;m['member_source2021_observed']=m.source_record_id_2021.notna();m['center_is_external_context']=m.core_id.isin(['ctx:RU-FED-MOW','ctx:RU-FED-SPB']);m['is_focal_id']=m.id.eq(m.core_id)
   oi=m.id.map(omap).fillna(-1).to_numpy('int64');di=m.core_id.map(dmap).fillna(-1).to_numpy('int64');dep=m.unit_role.eq('territorial_unit').to_numpy();struct=m.kind.eq('provider_core_seed').to_numpy()
   if np.any(dep&((oi<0)|(di<0))):raise ValueError('territorial member/focal absent from admittedsourcecache')
   active=dep|struct
   if np.any(active&((oi<0)|(di<0))):raise ValueError('sourceproviderstructuralself absent fromcache')
   t=np.full(len(m),np.nan,dtype='float64');t[active]=np.asarray(routes[oi[active],di[active]]).ravel()
   for k in np.flatnonzero(active&(t==0)):
    lo,hi=routes.indptr[oi[k]:oi[k]+2];idx=routes.indices[lo:hi];z=np.searchsorted(idx,di[k])
    if z==len(idx) or idx[z]!=di[k]:raise ValueError('sparse absent pair would fabricate0')
   if np.any(t[dep]>cap+1e-4) or np.any(t[active]<0):raise ValueError('source direct envelope violation')
   m['direct_network_minutes']=t;m['origin_index']=pd.array(np.where(oi>=0,oi,None),dtype='Int64');m['destination_index']=pd.array(np.where(di>=0,di,None),dtype='Int64')
   m['direct_route_status']=np.select([dep&m.is_focal_id.to_numpy(),dep,struct],['actual_focal_source_self_not_trip','actual_member_to_focal_bounded_route','provider_only_structural_self_no_dependent_field'],default='atomic_unattached_no_functional_route_assignment')
   m['is_dependent_origin_evidence']=dep&~m.is_focal_id.to_numpy();m['observed_trip_claim']=False
   table=pa.Table.from_pandas(m,preserve_index=False)
   if writer is None:writer=pq.ParquetWriter(dest,table.schema,compression='zstd')
   writer.write_table(table)
   summary.append(dict(candidate_cap=cap,n_rows=len(m),n_dependent_origins=int(m.is_dependent_origin_evidence.sum()),n_known_rural_dependents=int((m.is_dependent_origin_evidence&m.statistical_rural_role2021.fillna(False)).sum()),route_status_counts=m.direct_route_status.value_counts().to_dict(),max_dependent_minutes=float(m.loc[m.is_dependent_origin_evidence,'direct_network_minutes'].max())))
 finally:
  if writer is not None:writer.close()
 if any(sha(Path(p))!=h for p,h in inputs.items()):raise ValueError('input bytes changed during pair extraction')
 receipt=dict(partition_role=a.partition,status='ACTUAL_DIRECTED_TIMES_COMPUTED_NO_DYNAMICS_FIT',inputs=inputs,code_sha256=sha(Path(__file__)),output_sha256=sha(dest),summary=summary,source2010_population_not_copied=True,cohort_rule='Consumer must use exact focal exclusion + accepted2021statisticalruralrole + its admitted2010sourcequality view; purecarry/atomic rows not functional gradients',direction='sourceNP_to_own_actual_focal_center',nearest_large_city_context_is_separate=True,observed_flows=False)
 (out/'directed_member_focal_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
