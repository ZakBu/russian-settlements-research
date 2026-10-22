#!/usr/bin/env python3
"""Independent unit-vector distances, centered OLS and ranked Pearson rho."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1];B=R.parent;O=Path(__file__).resolve().parent/'wave2';O.mkdir(exist_ok=True)
def main():
 p=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet').set_index('id');m=pd.read_csv(R/'model/results/canonical_documented_external_memberships.csv');a=pd.read_csv(R/'gradients/gradient_points.csv');fits=pd.read_csv(R/'gradients/distance_gradients.csv');old=pd.read_csv(B/'anchor_research_20261019/model/documented_graph/service_edges_calculated.csv');bad=set(old[old.geometry_status.eq('coordinate_conflict_quarantined')].origin_uid.dropna());checks=[];rows=[]
 def ck(n,v):checks.append({'name':n,'pass':bool(v)})
 keys=['canonical_source_id','canonical_evidence_date','destination_uid','function_group','canonical_service_level']
 def xyz(lat,lon):
  la,lo=np.deg2rad([lat,lon]);return np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
 for key,g in m.groupby(keys,dropna=False):
  q=p.loc[key[2]];uv=xyz(q.lat,q.lon);dist=[];change=[]
  for uid in g.origin_uid:
   z=p.loc[uid];ar=a[a.origin_uid.eq(uid)]
   for k,v in zip(keys,key):ar=ar[ar[k].fillna('').eq('' if pd.isna(v) else v)]
   ck('one_point_'+str((key,uid)),len(ar)==1);ar=ar.iloc[0]
   if uid in bad:ck('quarantine_'+uid,pd.isna(ar.distance_km));continue
   vector=xyz(z.lat,z.lon);d=6371.0088*np.arctan2(np.linalg.norm(np.cross(uv,vector)),np.dot(uv,vector));c=np.log1p(z.population_2021)-np.log1p(z.population_2010)
   ck('distance_'+str((key,uid)),abs(d-ar.distance_km)<=1e-10);ck('change_'+str((key,uid)),abs(c-ar.log1p_change_2010_2021)<=1e-10);dist.append(d);change.append(c)
  ar=fits.copy()
  for k,v in zip(keys,key):ar=ar[ar[k].fillna('').eq('' if pd.isna(v) else v)]
  ar=ar.iloc[0];d=np.asarray(dist);c=np.asarray(change);n=len(d)
  if n>=5 and np.ptp(d)>1e-9:
   slope=float(np.dot(d-d.mean(),c-c.mean())/np.dot(d-d.mean(),d-d.mean()));ck('slope_'+str(key),abs(slope-ar.slope_log1p_change_per_km)<=1e-10)
   rankd=pd.Series(d).rank().to_numpy();rankc=pd.Series(c).rank().to_numpy();rho=float(np.corrcoef(rankd,rankc)[0,1]) if np.ptp(c)>0 else np.nan
   ck('rho_'+str(key),(np.isnan(rho) and pd.isna(ar.spearman)) or abs(rho-ar.spearman)<=1e-10);rows.append(dict(zip(keys,key),n=n,slope=slope,spearman=rho))
  else:ck('no_small_n_fit_'+str(key),pd.isna(ar.slope_log1p_change_per_km))
 ck('all_138_canonical_edges',len(a)==len(m)==138);ck('all_28_source_groups',len(fits)==28);ck('eleven_descriptive_groups',len(rows)==11);ck('zeros_not_dropped',a.population_2010.eq(0).sum()==p.loc[list(m.origin_uid),'population_2010'].eq(0).sum());ck('no_p_values',not fits.p_value_computed.any())
 pd.DataFrame(rows).to_csv(O/'independent_gradients.csv',index=False)
 audit={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','n_checks':len(checks),'checks':checks,'inputs':{str(f.relative_to(B)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [R/'model/results/canonical_documented_external_memberships.csv',R/'gradients/gradient_points.csv',R/'gradients/distance_gradients.csv']},'independent_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'interpretation':'Descriptive slopes over dated fixed source memberships. Overlapping and repeated groups are not independent statistical replicates. No historical function boundary or causal gradient inferred.'}
 (O/'GRADIENT_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(audit['status'],len(checks));assert all(x['pass'] for x in checks)
if __name__=='__main__':main()
