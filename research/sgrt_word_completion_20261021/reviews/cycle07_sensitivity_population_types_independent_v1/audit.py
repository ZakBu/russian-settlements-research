"""Independent actual population reductions. No imports from producer modules."""
import json,hashlib,sys,gc,time
from pathlib import Path
import numpy as np,pandas as pd
B=Path(__file__).resolve().parents[2]; O=Path(__file__).parent
SRC=B/'typology/cycle07_complete/population_only_sensitivity_source477_v1/population_only_nodes.parquet'
PRIMARY={'direct_published_census_value','reviewed_primary_reported_value','reviewed_primary_source_value_or_null','direct_official_city_value','fresh_primary_r5_source','reviewed_primary_source_child_partition','reviewed_primary_control_derived_zero'}
SEC='secondary_confidentiality_protected_value_exact_scope_unverified'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def audit(e,n):
 p=Path(e['normalized_output_path']);c=json.loads((B/e['contract_path']).read_text());u=pd.read_parquet(p/'normalized_units.parquet').set_index('unit_id',drop=False);m=pd.read_parquet(p/'memberships_scoped.parquet',columns=['unit_id','id']); checks=[];bad=[]
 def ck(k,v):
  checks.append(k)
  if not bool(v):bad.append(k)
 def eq(k,v):
  a=u[k]; b=pd.Series(v,index=u.index) if not isinstance(v,pd.Series) else v.reindex(u.index)
  if pd.api.types.is_numeric_dtype(a.dtype) and pd.api.types.is_numeric_dtype(b.dtype):ok=np.isclose(a.to_numpy(dtype=float,na_value=np.nan),b.to_numpy(dtype=float,na_value=np.nan),rtol=1e-12,atol=1e-9,equal_nan=True)
  else:ok=(a.eq(b)|(a.isna()&b.isna())).fillna(False).to_numpy()
  ck(k,ok.all())
  if not ok.all():bad.append({'column':k,'first_ids':u.index[~ok].tolist()[:3],'actual':a[~ok].head(3).astype(str).tolist(),'expected':b[~ok].head(3).astype(str).tolist()})
 ck('units_hash',sha(p/'normalized_units.parquet')==e['normalized_units_sha256']);ck('nodes_hash',sha(p/'effective_population_source_view.parquet')==e['effective_nodes_sha256']);ck('source37d9',sha(SRC)==c['base_nodes_sha256']);ck('contract',sha(B/e['contract_path'])==e['contract_sha256'])
 raw=pd.read_parquet(c['raw_units_path']);raw=raw[raw.partition_role.eq('supported_end_forest')].set_index('unit_id');ck('all_exact_raw_ids',u.index.is_unique and set(u.index)==set(raw.index)); ck('membership_unique',not m.duplicated(['unit_id','id']).any() and set(m.unit_id)==set(u.index));ck('exclusive_full_atoms',m.id.is_unique and len(m)==173858)
 for col in ['core_id','unit_role','n_members','core_fixed_own_mass','lat','lon','original_provider_seed_ids']:eq(col,raw[col])
 atomic=u.raw_kind.isin(['provider_core_seed','atomic_residual']);core=n.reindex(u.core_id).copy();core.index=u.index
 eq('kind',u.raw_kind.replace({'provider_core_seed':'atomic_settlement','atomic_residual':'atomic_settlement'}));eq('central_object_ids_json',u.core_id.map(lambda x:json.dumps([x])));eq('central_object_definition',pd.Series(np.where(atomic,'own_atomic','one_focal_core'),index=u.index));ck('no_false_context',not c['context_projection'] and not c['context_numeric_projection'] and c['context_projection_status']=='NOT_PROJECTED_FOR_LIGHTWEIGHT_SENSITIVITY_NOT_FALSE')
 j=m.join(n.drop(columns='id'),on='id');j['isfocal']=j.id.eq(j.unit_id.map(u.core_id));j['add']=j._population_axis_row;j['ext']=j['add']&~j.isfocal;j['rural']=j.ext&j.accepted_statistical_rural_role2021.fillna(False);j['unknown']=j.ext&j.accepted_statistical_rural_role2021.isna();j['ctx']=j.id.isin(['ctx:RU-FED-MOW','ctx:RU-FED-SPB'])
 def count(mask):return j.loc[mask].groupby('unit_id',sort=False).size().reindex(u.index,fill_value=0)
 ac=count(j['add']);rc=count(j.rural);uc=count(j.unknown)
 for k,v in [('n_population_axis_settlements',ac),('n_external_settlements',count(j.ext)),('n_rural_external_settlements',rc),('n_unknown_role_external_settlements',uc),('rural_role_complete',uc.eq(0))]:eq(k,v)
 eq('n_members',count(pd.Series(True,index=j.index)))
 def stats(mask,y,prior=False):
  d=j.loc[mask]; pv='population_2010_prior' if prior else f'population_{y}';qv='population_value_quality_2010_prior' if prior else f'population_value_quality_{y}';v=pd.to_numeric(d[pv],errors='coerce');valid=v.notna()&np.isfinite(v)&v.ge(0);g=d.unit_id
  size=g.groupby(g,sort=False).size().reindex(u.index,fill_value=0); missing=(~valid).groupby(g,sort=False).sum().reindex(u.index,fill_value=0);tot=v.where(valid).groupby(g,sort=False).sum(min_count=1).reindex(u.index)
  q=d[qv].fillna('quality_unavailable'); secondary=v.where(valid&q.eq(SEC),0).groupby(g,sort=False).sum().reindex(u.index,fill_value=0)/tot.where(tot.gt(0));primary=v.where(valid&q.isin(PRIMARY),0).groupby(g,sort=False).sum().reindex(u.index,fill_value=0)/tot.where(tot.gt(0)); nonprimary=(~q.isin(PRIMARY)).groupby(g,sort=False).sum().reindex(u.index,fill_value=0)
  return dict(sum=tot,complete=size.gt(0)&missing.eq(0),missing=missing,zero=(valid&v.eq(0)).groupby(g,sort=False).sum().reindex(u.index,fill_value=0),primary_complete=size.gt(0)&missing.eq(0)&nonprimary.eq(0),secondary=secondary,primary=primary,q=q,g=g)
 for y in [2002,2010,2021]:
  s=stats(j['add'],y);r=stats(j.rural,y);co=stats(j.isfocal,y);ctxmask=j.ctx&j[f'population_{y}'].isna();ctx=count(ctxmask);cf=count(ctxmask&j.isfocal)
  for k,v in [('all',ctx),('focal',cf),('nonfocal',ctx-cf)]:eq(f'unknown_nonadditive_metropolitan_{k}_population_slots_{y}',v)
  full=s['complete']&core._population_axis_row&ctx.eq(0)
  eq(f'system_population_known_sum_{y}',s['sum']);eq(f'system_known_additive_member_population_sum_{y}',s['sum']);eq(f'system_population_complete_{y}',full);eq(f'n_missing_population_{y}',s['missing']);eq(f'n_observed_zero_{y}',s['zero'])
  eq(f'center_population_{y}',co['sum'].where(co['complete']));eq(f'center_population_complete_{y}',co['complete']);eq(f'own_population_{y}',co['sum'].where(atomic&co['complete']));eq(f'own_population_complete_{y}',atomic&co['complete']);eq(f'rural_external_population_known_sum_{y}',r['sum'].where(rc.gt(0),0));eq(f'rural_population_complete_{y}',(r['complete']|rc.eq(0))&uc.eq(0))
  eq(f'population_secondary_protected_scope_unverified_known_population_share_{y}',s['secondary']);eq(f'system_population_exact_primary_supported_{y}',s['primary_complete']&core._population_axis_row&ctx.eq(0));eq(f'classification_population_exact_primary_supported_{y}',co['primary_complete'].where(atomic,s['primary_complete']&core._population_axis_row&ctx.eq(0)));eq(f'classification_secondary_population_share_{y}',co['secondary'].where(atomic,s['secondary']))
  for col,z in [(f'population_quality_counts_json_{y}',s),(f'center_population_quality_counts_json_{y}',co)]:
   counts=pd.crosstab(z['g'],z['q']);actual=u[col].map(json.loads);ck(col,all(actual.loc[k]=={q:int(v) for q,v in row.items() if v} for k,row in counts.iterrows()) and all(actual.loc[k]=={} for k in u.index.difference(counts.index)))
 basis=j['add']| (j.isfocal&j.unit_id.map(atomic));s=stats(basis,2010);pr=stats(basis,2010,True)
 for col,sv in [('prior_secondary2010_population_share',pr['secondary']),('current_secondary2010_population_share',s['secondary']),('primary2010_population_share',s['primary']),('protected_secondary2010_population_share',s['secondary']),('population2010_known_denominator',s['sum']),('2010_missing_population_count',s['missing'])]:eq(col,sv)
 for col,flag in [('n_members_primary2010_newly_recovered','primary2010_overlay_applied'),('n_members_primary2010_numeric_changed','primary2010_numeric_changed'),('n_members_primary2010_quality_changed','primary2010_quality_changed')]:eq(col,count(basis&j[flag]))
 rv=j.population_2010.where(basis&j.primary2010_overlay_applied,0).groupby(j.unit_id,sort=False).sum().reindex(u.index,fill_value=0);eq('primary2010_newly_recovered_population_share',rv/s['sum'].where(s['sum'].gt(0)))
 eq('unknown_nonadditive_central_population_slots2010',((~core._population_axis_row)&core.population_2010.isna()).astype(int))
 for col,mask in [('central_object_set_sha256',j.isfocal),('rural_external_members_set_sha256',j.rural),('additive_whole_members_set_sha256',j['add'])]:
  sets=j.loc[mask].groupby('unit_id',sort=False).id.agg(list);h=sets.map(lambda ids:hashlib.sha256(json.dumps(sorted(ids),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()).reindex(u.index,fill_value=hashlib.sha256(b'[]').hexdigest());eq(col,h)
 ck('source_unchanged',sha(p/'normalized_units.parquet')==e['normalized_units_sha256'] and sha(SRC)==c['base_nodes_sha256'])
 out={'status':'ACCEPTED_INDEPENDENT_LIGHT_POPULATION_AND_CENTRAL_SETS' if not bad else 'REJECTED','all_checks_passed':not bad,'n_failed':len(bad),'n_checks':len(checks),'checks':checks,'failures':bad,'units_sha256':e['normalized_units_sha256'],'accepted_units_sha256':e['normalized_units_sha256'],'nodes_sha256':e['effective_nodes_sha256'],'rural_excludes_exact_central_set':True,'whole_members_counted_once':True,'source_population_sha256':sha(SRC),'actual_normalized_units_path':str(p/'normalized_units.parquet'),'n_units':len(u),'n_atoms':len(m),'scope':'All actual source memberships, all three years, exact focal/rural/additive sets, ANY unknown metropolitan member, quality and353 prior/current; no hierarchy-method revalidation; types require separate actual audit','code_sha256':sha(__file__)}
 dst=O/f"{e['scenario']}_cap{e['cap_minutes']:03d}_population_audit.json";dst.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(dst.name,out['status'],len(checks),len(bad),flush=True)
 if bad:print(json.dumps(bad[:6],ensure_ascii=False),flush=True)
 return out
if __name__=='__main__':
 n=pd.read_parquet(SRC).set_index('id',drop=False);prog=json.loads((B/'typology/cycle07_complete/sensitivity_light_execution_v1/progress.json').read_text());results=[]
 for e in prog['entries']:
  dst=O/f"{e['scenario']}_cap{e['cap_minutes']:03d}_population_audit.json"
  if dst.exists():continue
  results.append(audit(e,n));gc.collect()
 print('new',len(results),'fail',sum(not r['all_checks_passed'] for r in results),flush=True)
