"""Exact primary focal/seed distinction + raw hierarchy-to-normalized bridge.
Runs after the separate all-population-cells central-set readback.
"""
import argparse,hashlib,json
from pathlib import Path
import pandas as pd
from classify_complete import truth

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sethash(ids):return hashlib.sha256(json.dumps(sorted(str(x) for x in ids),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def serialize(v):
 if hasattr(v,'tolist'):v=v.tolist()
 if not isinstance(v,(list,dict)) and pd.isna(v):v=None
 return json.dumps(v,ensure_ascii=False,default=str,sort_keys=True)
def ids(v):
 if isinstance(v,str):return json.loads(v)
 if hasattr(v,'tolist'):return v.tolist()
 return list(v)
def main():
 p=argparse.ArgumentParser();p.add_argument('--contract',required=True);p.add_argument('--output',required=True);a=p.parse_args();c=json.loads(Path(a.contract).read_text());out=Path(a.output)
 if out.exists():raise FileExistsError('Fresh audit output required')
 for key in ('raw_units','normalized_units','memberships','effective_nodes','population_readback'):
  assert sha(c[key+'_path'])==c[key+'_sha256']
 raw=pd.read_parquet(c['raw_units_path']).set_index('unit_id',drop=False);norm=pd.read_parquet(c['normalized_units_path']).set_index('unit_id',drop=False);m=pd.read_parquet(c['memberships_path']);nodes=pd.read_parquet(c['effective_nodes_path']).set_index('id',drop=False)
 readback=json.loads(Path(c['population_readback_path']).read_text());assert readback['all_checks_passed'] is True and str(readback['status']).startswith('ACCEPTED');assert readback['units_sha256']==c['normalized_units_sha256'] and readback['nodes_sha256']==c['effective_nodes_sha256']
 assert raw.index.is_unique and norm.index.is_unique and set(raw.index)==set(norm.index)
 assert not m.duplicated(['unit_id','id']).any();groups=m.groupby('unit_id',sort=False).id.agg(list).to_dict();rows=[];retained=[]
 source_seed_col=c['provider_seed_ids_column'];assert source_seed_col in raw,'Full raw provider seed inventory required'
 fields=[f for f in ['unit_id','kind','unit_role','core_id','resolution_index','parent_unit_id',source_seed_col] if f in raw]
 for uid,r in raw.iterrows():
  n=norm.loc[uid]
  for field in fields:
   normfield='raw_kind' if field=='kind' else field
   assert serialize(r[field])==serialize(n[normfield]),f'Raw hierarchy field changed: {uid}/{field}'
  expectedkind={'provider_core_seed':'atomic_settlement','atomic_residual':'atomic_settlement'}.get(r.kind,r.kind)
  assert n.kind==expectedkind
  focal=str(r.core_id);actual=ids(n.central_object_ids_json);assert actual==[focal]
  assert n.central_object_definition==('own_atomic' if expectedkind=='atomic_settlement' else 'one_focal_core'),'Primary all-provider core pool forbidden'
  members=nodes.loc[groups[uid]];additive=members.loc[members._population_axis_row.map(lambda x:truth(x) is True)]
  external=additive.loc[additive.index!=focal];rural=external.loc[external.accepted_statistical_rural_role2021.map(lambda x:truth(x) is True)]
  assert n.rural_external_members_set_sha256==sethash(rural.index),'Wrong rural set (including possible provider-seed exclusion)'
  assert n.additive_whole_members_set_sha256==sethash(additive.index),'Changed whole source member set'
  assert n.central_object_set_sha256==sethash([focal])
  seeds=set(ids(r[source_seed_col]));other=seeds & set(rural.index)
  for ident in sorted(other):retained.append({'unit_id':uid,'provider_seed_id':ident,'focal_core_id':focal,'retained_in_rural_basis':True})
  rows.append({'unit_id':uid,'unit_role':n.unit_role,'n_provider_seeds':len(seeds),'n_other_rural_provider_seeds_retained':len(other),'n_rural_members':len(rural),'primary_focal_singleton_correct':True,'rural_set_hash_correct':True})
 out.mkdir(parents=True);pd.DataFrame(rows).to_parquet(out/'primary_bridge_all_units.parquet',index=False);pd.DataFrame(retained,columns=['unit_id','provider_seed_id','focal_core_id','retained_in_rural_basis']).to_parquet(out/'other_rural_provider_seeds_retained.parquet',index=False)
 receipt={'status':'ACCEPTED_PRIMARY_FOCAL_NORMALIZATION_BRIDGE','all_checks_passed':True,'accepted_units_sha256':c['normalized_units_sha256'],'raw_units_sha256':c['raw_units_sha256'],'nodes_sha256':c['effective_nodes_sha256'],'n_units':len(rows),'n_other_rural_provider_seed_memberships_retained':len(retained),'provider_seed_pool_not_used_as_central_set':True,'raw_hierarchy_fields_preserved':fields,'population_readback_sha256':c['population_readback_sha256'],'does_not_admit_hierarchy_linkage_science':True,'code_sha256':sha(__file__),'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()}}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
