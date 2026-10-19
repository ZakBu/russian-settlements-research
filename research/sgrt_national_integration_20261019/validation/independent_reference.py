#!/usr/bin/env python3
"""Independent medians/CDF ranks and confidence scenarios on positive evidence."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;N=H.parent;O=H/'independent_sources/reference';O.mkdir(parents=True,exist_ok=True)
RAW=['retail','food_service','education','healthcare','social_care','repair','personal','veterinary','pharmacy','banking','postal_service','marketplace_pickup'];FUNCTIONS=['trade_access']+RAW[1:-1]
POI={'school':'education','preschool':'education','other_education':'education','hospital':'healthcare','healthcare':'healthcare','veterinary':'veterinary','pharmacy':'pharmacy','bank':'banking','atm':'banking','post_office':'postal_service','postal_collection_point':'postal_service','market':'trade_access','retail_store':'trade_access','food_service':'food_service'}
EDGES={'coarse':[0,100,500,1000,3000,10000,50000,100000,np.inf],'fine':[0,50,100,250,500,1000,2500,5000,10000,25000,50000,100000,np.inf]}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def collapse(a):return np.column_stack([a[:,0]|a[:,-1],a[:,1:-1]])
def reference(frame,k,edges,minn):
 n=len(frame);valid=(k>0)&frame.population_2021.gt(0).to_numpy();bins=np.searchsorted(edges,frame.population_2021.to_numpy(),side='right')-1;reg=frame.region.to_numpy();regional={};national={};N=np.full(n,np.nan);med=N.copy();rank=N.copy();delta=N.copy();scope=np.where(valid,'insufficient_positive_reference','not_in_positive_evidence_reference').astype(object)
 for i in np.flatnonzero(valid):regional.setdefault((reg[i],bins[i]),[]).append(i);national.setdefault(bins[i],[]).append(i)
 stats={}
 for key,ix in list(regional.items())+list(national.items()):
  values=k[ix];freq=np.bincount(values,minlength=12);stats[key]=(len(ix),float(np.median(values)),(np.cumsum(freq)-.5*freq)/len(ix))
 for key,ix in regional.items():
  selected=key if stats[key][0]>=minn else key[1] if stats[key[1]][0]>=minn else None
  if selected is None:continue
  count,median,cdf=stats[selected];N[ix]=count;med[ix]=median;rank[ix]=cdf[k[ix]];delta[ix]=k[ix]-median;scope[ix]='same_region_size_bin_positive_evidence' if isinstance(selected,tuple) else 'RF_same_size_bin_positive_evidence_fallback'
 return {'referenceN':N,'reference_median':med,'reference_midrank':rank,'observed_diversity_minus_reference_median':delta,'reference_scope':scope}
def main():
 paths=[N/'screening/support_point_profiles.parquet',N/'critic/national_functional_reference.parquet',N/'critic/reference_sensitivity.csv',N/'places/places_objects_and_crosswalk.parquet',N/'critic/confidence_reference_by_point.parquet',N/'critic/confidence_sensitivity.csv',N/'services/wb_name_relaxed_features.parquet'];before={str(p):sha(p) for p in paths};cols=['id','region','population_2021','wb_strict_focus_published_locations']+[f'{key}_unmerged_function_{f}_witness' for key in ['legal_native','legal_conditional','physical_baseline','physical_conditional'] for f in RAW];s=pd.read_parquet(paths[0],columns=cols);ref=pd.read_parquet(paths[1]).set_index('id').reindex(s.id);wr=pd.read_parquet(paths[6],columns=['id','wb_name_relaxed_inclusive_focus_locations']).set_index('id').reindex(s.id);checks=[]
 def ck(n,v):checks.append({'name':n,'pass':bool(v)})
 def same(a,b):return np.allclose(a,b,rtol=0,atol=1e-12,equal_nan=True)
 def mask(key):return s[[f'{key}_unmerged_function_{f}_witness' for f in RAW]].to_numpy(bool)
 ln,lc,pn,pc=[mask(key) for key in ['legal_native','legal_conditional','physical_baseline','physical_conditional']];wb=np.zeros_like(ln);wb[:,-1]=s.wb_strict_focus_published_locations.gt(0);wbc=wb.copy();wbc[:,-1]=wr.wb_name_relaxed_inclusive_focus_locations.gt(0);raw={'legal_native':ln,'physical_baseline':pn,'physical_plus_wb_strict':pn|wb,'baseline':ln|pn|wb,'conditional_without_wb_relaxation':lc|pc|wb,'conditional_with_wb_relaxation':lc|pc|wbc};bundles={key:collapse(a) for key,a in raw.items()};sensitivity=pd.read_csv(paths[2]);summary=[]
 for key,a in bundles.items():
  k=a.sum(axis=1);ck(key+'_counts',np.array_equal(k,ref[key+'_listed_function_diversity']));primary=reference(s,k,EDGES['coarse'],30)
  for c,v in primary.items():ck(key+'_'+c,np.array_equal(v,ref[key+'_'+c]) if c=='reference_scope' else same(v,ref[key+'_'+c]))
  for label,minimum in [('coarse',30),('coarse',60),('fine',30),('fine',60)]:
   r=reference(s,k,EDGES[label],minimum);delta=r['observed_diversity_minus_reference_median'];row=sensitivity[(sensitivity.bundle==key)&(sensitivity.binning==label)&(sensitivity.minimum_referenceN==minimum)].iloc[0];common=np.isfinite(delta)&np.isfinite(primary['observed_diversity_minus_reference_median']);expected={'positive_listed_points':int((k>0).sum()),'reference_available':int(np.isfinite(delta).sum()),'regional_reference':int((r['reference_scope']=='same_region_size_bin_positive_evidence').sum()),'RF_fallback':int((r['reference_scope']=='RF_same_size_bin_positive_evidence_fallback').sum()),'above_reference_median':int((delta>0).sum()),'below_reference_median':int((delta<0).sum()),'common_with_primary':int(common.sum())};ck(f'{key}_{label}_{minimum}_all_summary_counts',all(row[c]==v for c,v in expected.items()));summary.append({'bundle':key,'binning':label,'minN':minimum,**expected})
 pp=pd.read_parquet(paths[3],columns=['baseline_uid','function_group','source_operating_status','source_confidence']);eligible=pp.baseline_uid.notna()&pp.function_group.isin(POI)&~pp.source_operating_status.isin(['permanently_closed','temporarily_closed']);index=pd.Index(s.id);cf=pd.read_parquet(paths[4]).set_index('id').reindex(s.id);cs=pd.read_csv(paths[5]);fidx={f:i for i,f in enumerate(FUNCTIONS)}
 for tag,threshold in [('primary_positive_or_unknown',None),('ge0p5',.5),('ge0p8',.8),('ge0p95',.95)]:
  score=pp.source_confidence;take=eligible&((score.gt(0)|score.isna()) if threshold is None else score.ge(threshold));selected=pp[take];mat=np.zeros_like(bundles['baseline']);rr=index.get_indexer(selected.baseline_uid);cc=selected.function_group.map(POI).map(fidx).to_numpy(int);mat[rr,cc]=True
  for key,a in [('physical_baseline',mat),('baseline',collapse(ln)|mat|collapse(wb))]:
   k=a.sum(axis=1);r=reference(s,k,EDGES['coarse'],30);delta=r['observed_diversity_minus_reference_median'];original=reference(s,bundles[key].sum(axis=1),EDGES['coarse'],30);fixed=np.where((k>0)&np.isfinite(original['reference_median']),k-original['reference_median'],np.nan);row=cs[(cs.threshold==tag)&(cs.bundle==key)].iloc[0];expected={'retained_baseline_linked_requested_POI_records':len(selected),'positive_listed_UID':int((k>0).sum()),'multiple_groups_UID':int((k>=2).sum()),'reference_available':int(np.isfinite(delta).sum()),'above_recomputed_reference_median':int((delta>0).sum()),'below_recomputed_reference_median':int((delta<0).sum()),'above_fixed_primary_reference_median':int((fixed>0).sum()),'fixed_primary_reference_available_positive_UID':int(np.isfinite(fixed).sum()),'same_exact_function_set_as_primary_UID':int((a==bundles[key]).all(axis=1).sum()),'primary_positive_lost':int((bundles[key].any(axis=1)&~a.any(axis=1)).sum())};ck(tag+'_'+key+'_confidence_summary',all(row[c]==v for c,v in expected.items()))
   if key=='baseline':
    for suffix,v in [('listed_function_diversity',k),('reference_median',r['reference_median']),('referenceN',r['referenceN']),('observed_diversity_minus_reference_median',delta),('observed_diversity_minus_fixed_primary_median',fixed)]:ck(tag+'_'+suffix,same(v,cf[tag+'_'+suffix]))
 ck('all_inputs_stable',all(sha(Path(p))==v for p,v in before.items()));pd.DataFrame(summary).to_csv(O/'independent_reference_sensitivity.csv',index=False);result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'input_SHA256':before,'code_SHA256':sha(Path(__file__)),'scope':'Positive-evidence population/region reference, self-included medians and empirical mid-CDF, all confidence filtered/fixed-reference point fields. No proof of physical function surplus, external centrality, causal support effect or policy ranking.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks',flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()
