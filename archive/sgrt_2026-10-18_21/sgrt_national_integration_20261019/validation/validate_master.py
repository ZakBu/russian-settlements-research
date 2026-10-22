#!/usr/bin/env python3
"""Mass audit after integration. No author model imports or fitted thresholds.

Missing master/bindings is an explicit pending state, never a successful audit.
Field mappings must be supplied by the source-owner lineage contract. Numeric
completeness and accepted evidence coverage are deliberately separate outputs.
"""
from pathlib import Path
import argparse,hashlib,json
import numpy as np,pandas as pd,pyarrow.parquet as pq

HERE=Path(__file__).resolve().parent;NAT=HERE.parent;BASE=NAT.parent;SEED=20261019
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(2**20),b''):h.update(x)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def score(uid,tag):return int.from_bytes(hashlib.sha256(f'{SEED}|{tag}|{uid}'.encode()).digest(),'big')
def filters(d,specs):
 keep=pd.Series(True,index=d.index)
 for f in specs:
  s=d[f['column']];op=f['op'];v=f.get('value')
  if op=='eq':k=s.eq(v)
  elif op=='in':k=s.isin(v)
  elif op=='notna':k=s.notna()
  elif op=='gt':k=s.gt(v)
  elif op=='ge':k=s.ge(v)
  elif op=='ne':k=s.ne(v)
  else:raise ValueError('Unsupported explicit filter '+op)
  keep&=k.fillna(False)
 return d[keep]
def read_source(path,columns,specs):
 columns=sorted(set(columns)|{f['column'] for f in specs})
 if path.suffix=='.parquet':d=pd.read_parquet(path,columns=columns)
 else:d=pd.read_csv(path,usecols=columns,low_memory=False)
 return filters(d,specs)
def unequal(a,b):
 if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):return ~np.isclose(a.to_numpy(dtype=float,na_value=np.nan),b.to_numpy(dtype=float,na_value=np.nan),rtol=1e-12,atol=1e-10,equal_nan=True)
 return ~(a.fillna('__MISSING__').astype(str).to_numpy()==b.fillna('__MISSING__').astype(str).to_numpy())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--master',type=Path,default=NAT/'core/feature_master.parquet');ap.add_argument('--bindings',type=Path,default=HERE/'validation_bindings.json');ap.add_argument('--axis',type=Path,default=BASE/'anchor_research_20261019/data/point_axis.parquet');ap.add_argument('--out',type=Path,default=HERE/'results');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 schemas={}
 available=[a.axis,a.master,NAT/'economy/economy_features.parquet',NAT/'agriculture/point_municipal_agriculture.parquet',NAT/'services/wb_settlement_features.parquet',BASE/'functional_dynamics_20261019/marketplaces/wb_delivery_locations_ru_20261019.parquet']
 for p in available:
  if p.exists():
   f=pq.ParquetFile(p);schemas[str(p)]={'rows':f.metadata.num_rows,'fields':{x.name:str(x.type) for x in f.schema_arrow},'sha256':sha(p)}
 dump(a.out/'source_schemas.json',schemas)
 if not a.master.exists():
  dump(a.out/'AUDIT.json',{'status':'WAITING_FOR_ACTUAL_MASTER','master':str(a.master),'precommitted_design_sha256':sha(HERE/'DESIGN.json'),'available_schemas':len(schemas),'integration_validation_executed':False});print('WAITING_FOR_ACTUAL_MASTER');return
 bound=a.bindings.exists();contract=json.loads(a.bindings.read_text()) if bound else json.loads((HERE/'validation_bindings.template.json').read_text())
 protected={str(a.axis):sha(a.axis),str(a.master):sha(a.master)};axis=pd.read_parquet(a.axis);m=pd.read_parquet(a.master);mid=contract.get('master_id','id');aid=contract.get('axis_id','id');checks=[];conflicts=[];balances=[];sources={}
 def ck(name,value,detail=None):checks.append({'name':name,'pass':bool(value),'detail':detail})
 def issue(kind,severity,uid=None,column=None,detail=None):conflicts.append({'kind':kind,'severity':severity,'id':uid,'column':column,'detail':detail})
 ck('axis_142570_unique',len(axis)==142570 and axis[aid].notna().all() and axis[aid].is_unique)
 ck('master_key_present',mid in m)
 if mid not in m:raise ValueError('Master key absent: '+mid)
 ck('master_142570_rows',len(m)==142570);ck('master_key_nonmissing',m[mid].notna().all());ck('master_key_unique',m[mid].is_unique)
 for uid in m.loc[m[mid].duplicated(keep=False),mid].drop_duplicates():issue('duplicate_master_key','ERROR',uid)
 for uid in sorted(set(axis[aid])-set(m[mid].dropna())):issue('missing_axis_key','ERROR',uid)
 for uid in sorted(set(m[mid].dropna())-set(axis[aid])):issue('foreign_axis_key','ERROR',uid)
 ck('exact_axis_key_set',set(axis[aid])==set(m[mid]))
 if not m[mid].is_unique:
  pd.DataFrame(conflicts).to_csv(a.out/'conflict_queue.csv',index=False);dump(a.out/'AUDIT.json',{'status':'FAIL_MASTER_PRIMARY_KEY','checks':checks});return
 reference=axis.set_index(aid).reindex(m[mid]);reference.index=m.index
 mapping=contract.get('axis_column_mapping',{});override={(x['id'],x['column']):x for x in contract.get('axis_overrides',[])}
 for c in contract.get('axis_columns',[]):
  target=mapping.get(c,c)
  if c not in reference:continue
  if target not in m:ck('axis_column_present_'+target,False);issue('missing_axis_column','ERROR',column=target);continue
  bad=~(m[target].eq(reference[c]).fillna(False)|(m[target].isna()&reference[c].isna())).to_numpy(dtype=bool);approved=0
  for pos in np.flatnonzero(bad):
   uid=m.iloc[pos][mid];ov=override.get((uid,c))
   if ov and ov.get('approved_by_independent_validator') and ov.get('source_url'):
    approved+=1;issue('explicit_independently_approved_axis_override','REVIEW',uid,target,ov['source_url'])
   else:issue('altered_frozen_axis_value','ERROR',uid,target,f'axis={reference.iloc[pos][c]!s}; master={m.iloc[pos][target]!s}')
  ck('axis_values_'+target,int(bad.sum())==approved,{'differences':int(bad.sum()),'approved_overrides':approved})
 for name in contract.get('nonnegative_columns',[]):
  bad=m[name].notna()&m[name].lt(0);ck('nonnegative_'+name,not bad.any())
  for uid in m.loc[bad,mid]:issue('negative_count','ERROR',uid,name)
 for name,value in contract.get('constant_bindings',{}).items():ck('declared_metadata_'+name,m[name].eq(value).all())
 ck('all_master_columns_bound',not contract.get('unbound_master_columns',[]),contract.get('unbound_master_columns',[]))
 ck('all_final_layer_columns_in_master',not contract.get('missing_layer_columns',[]),contract.get('missing_layer_columns',[]))
 for binding in contract.get('source_bindings',[]):
  path=Path(binding['path']);path=path if path.is_absolute() else BASE/path;name=binding['name'];sources[name]={'path':str(path),'sha256':sha(path)};sk=binding['source_keys'];mk=binding['master_keys'];cols=binding['columns'];s=read_source(path,sk+list(cols.values()),binding.get('filters',[]));dups=s.duplicated(sk,keep=False);ck('source_unique_'+name,not dups.any())
  for _,row in s.loc[dups,sk].drop_duplicates().iterrows():issue('nonunique_source_join_key','ERROR',column=name,detail=row.to_json(force_ascii=False))
  if dups.any():continue
  left=m[mk].rename(columns=dict(zip(mk,sk)));joined=left.merge(s,on=sk,how='left',validate='many_to_one',sort=False,indicator=True);ck('source_join_preserves_rows_'+name,len(joined)==len(m))
  for target,src in cols.items():
   expected=joined[src]
   if binding.get('missing_policy')=='zero_for_unmatched_count':expected=expected.mask(joined._merge.eq('left_only'),0)
   bad=unequal(m[target],expected);ck('all_values_'+name+'_'+target,not bad.any(),{'mismatched':int(bad.sum())})
   for uid in m.loc[bad,mid]:issue('source_value_mismatch','ERROR',uid,target,name)
   additive=not binding.get('replicated_municipal_context_not_additive',False) and sk==['id'] and mk==[mid]
   balances.append({'source':name,'master_column':target,'source_column':src,'source_rows_after_filters':len(s),'master_rows':len(m),'master_rows_joined':int(joined._merge.eq('both').sum()),'native_source_sum':float(pd.to_numeric(s[src],errors='coerce').sum(min_count=1)) if pd.api.types.is_numeric_dtype(s[src]) else None,'master_sum':float(m[target].sum(min_count=1)) if pd.api.types.is_numeric_dtype(m[target]) else None,'settlement_additive_comparison_permitted':additive,'municipal_replication_not_production':binding.get('replicated_municipal_context_not_additive',False)})
 for ob in contract.get('object_bindings',[]):
  path=Path(ob['path']);path=path if path.is_absolute() else BASE/path;s=read_source(path,[ob['object_key'],ob['source_settlement_key']],ob.get('accepted_filters',[]));good=s[ob['source_settlement_key']].notna();accepted=s[good];counts=accepted.groupby(ob['source_settlement_key'])[ob['object_key']].nunique();expected=m[mid].map(counts).fillna(0);bad=unequal(m[ob['master_count_column']],expected);ck('object_counts_'+ob['name'],not bad.any());ck('object_identity_unique_'+ob['name'],not accepted[ob['object_key']].duplicated().any())
  for uid in m.loc[bad,mid]:issue('object_aggregation_mismatch','ERROR',uid,ob['master_count_column'],ob['name'])
  balances.append({'source':ob['name'],'master_column':ob['master_count_column'],'source_rows_after_filters':len(s),'accepted_source_rows':len(accepted),'accepted_distinct_objects':int(accepted[ob['object_key']].nunique()),'master_sum':float(m[ob['master_count_column']].sum()),'foreign_link_objects':int((~accepted[ob['source_settlement_key']].isin(axis[aid])).sum()),'unresolved_after_filters':int((~good).sum())})
  sources[ob['name']]={'path':str(path),'sha256':sha(path)}
 # Coverage is computed from reference geography, never from source row totals.
 size=pd.cut(reference.population_2021,[-1,0,99,499,999,4999,19999,99999,np.inf],labels=['0','1-99','100-499','500-999','1000-4999','5000-19999','20000-99999','100000+']).astype('string').fillna('unknown');region=reference.region.fillna('unknown');features=contract.get('coverage_features') or [c for c in m if c not in axis and pd.api.types.is_numeric_dtype(m[c])]
 for grouping,groupcols in [('region',{'region':region}),('size',{'size':size}),('region_size',{'region':region,'size':size})]:
  rows=[];frame=pd.DataFrame(groupcols)
  for key,idx in frame.groupby(list(groupcols),dropna=False,observed=True).groups.items():
   label=dict(zip(groupcols,key if isinstance(key,tuple) else (key,)))
   for c in features:
    v=m.loc[idx,c];num=pd.to_numeric(v,errors='coerce');rows.append({**label,'feature':c,'coverage_kind':'numeric_completeness_not_evidence_coverage','rows':len(v),'nonmissing':int(v.notna().sum()),'missing':int(v.isna().sum()),'positive':int(num.gt(0).sum()),'zero':int(num.eq(0).sum()),'negative':int(num.lt(0).sum())})
   for cb in contract.get('coverage_status_bindings',[]):
    for status,specs in cb['states'].items():rows.append({**label,'feature':cb['name'],'coverage_kind':'declared_'+status,'rows':len(idx),'selected_rows':len(filters(m.loc[idx],specs))})
  pd.DataFrame(rows).to_csv(a.out/f'coverage_by_{grouping}.csv',index=False)
 # Predeclared review risks are flags, not automatic data deletion or SGRT labels.
 for flag in contract.get('risk_flags',[]):
  for uid in filters(m,flag['filters'])[mid]:issue(flag['kind'],flag['severity'],uid,detail='Source quality flag; not a demonstrated invalid settlement or SGRT')
 for c in features:
  if not any(x in c.lower() for x in ['count','entities','objects','pvz']):continue
  v=pd.to_numeric(m[c],errors='coerce');positive=v[v.gt(0)]
  if len(positive)>=100:
   threshold=float(positive.quantile(.999));risk=v.gt(threshold)
   for uid in m.loc[risk,mid]:issue('extreme_source_count','REVIEW',uid,c,f'positive_999_quantile={threshold}')
  risk=reference.population_2021.eq(0)&v.gt(0)
  for uid in m.loc[risk,mid]:issue('zero_census_with_noncontemporaneous_witness','REVIEW_NOT_ERROR',uid,c,'Census and source dates differ or only years are known; not proof of an invalid function')
 conflicts_frame=pd.DataFrame(conflicts,columns=['kind','severity','id','column','detail']);conflicts_frame.to_csv(a.out/'conflict_queue.csv',index=False);pd.DataFrame(balances).to_csv(a.out/'source_balance.csv',index=False)
 sample=pd.DataFrame({'id':m[mid],'region':region,'population_2021':reference.population_2021,'size':size});sample['selection_hash']=[score(uid,f'region_size|{reg}|{sz}') for uid,reg,sz in zip(sample.id,sample.region,sample['size'])];selected=sample.sort_values('selection_hash').groupby(['region','size'],observed=True,dropna=False).head(1).copy();selected['selection_reason']='region_size_stratum'
 riskids=set(conflicts_frame.id.dropna());risk=sample[sample.id.isin(riskids)&~sample.id.isin(selected.id)].copy();risk['selection_hash']=[score(uid,'risk') for uid in risk.id];risk=risk.sort_values('selection_hash').head(75);risk['selection_reason']='predeclared_risk_queue';selected=pd.concat([selected,risk],ignore_index=True);selected['evaluation_split']=['holdout_no_calibration' if score(uid,'external_split')%3==0 else 'exploratory_audit' for uid in selected.id];selected['external_review_status']='not_yet_reviewed';selected.to_csv(a.out/'external_audit_sample.csv',index=False)
 protected.update({v['path']:v['sha256'] for v in sources.values()});ck('all_inputs_stable_during_audit',all(sha(Path(p))==digest for p,digest in protected.items()))
 status='PASS_INTEGRATION_MAPPING' if checks and all(x['pass'] for x in checks) and bound and (contract.get('source_bindings') or contract.get('object_bindings')) else 'PENDING_BINDINGS' if not bound else 'FAIL_OR_UNVERIFIED_BINDINGS'
 result={'status':status,'checks':checks,'checks_count':len(checks),'all_executed_checks_pass':all(x['pass'] for x in checks),'axis_sha256':sha(a.axis),'master_sha256':sha(a.master),'binding_sha256':sha(a.bindings) if bound else None,'sources':sources,'coverage_features':len(features),'semantic_coverage_bindings':len(contract.get('coverage_status_bindings',[])),'conflict_rows':len(conflicts),'conflicting_UIDs':int(conflicts_frame.id.nunique()),'planned_external_sample_rows':len(selected),'planned_external_sample_regions':selected.region.nunique(),'external_cases_actually_reviewed':0,'raw_source_checks_pending':contract.get('raw_checks',[]),'meaning':'Integration fidelity only. Checks are not SGRT accuracy; unreviewed external sample is not validation evidence.'};dump(a.out/'AUDIT.json',result);print(status,len(checks),'checks',len(conflicts),'queue rows')
if __name__=='__main__':main()
