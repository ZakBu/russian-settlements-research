#!/usr/bin/env python3
"""Independent center/external/union demography and descriptive thresholds."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1];B=R.parent;O=Path(__file__).resolve().parent/'wave2';O.mkdir(exist_ok=True)
def main():
 paths=[R/'model/results/centre_periphery_demography.csv',R/'model/results/demographic_direction_sensitivity.csv',R/'model/results/canonical_documented_external_memberships.csv'];a=pd.read_csv(paths[0]);d=pd.read_csv(paths[1]);m=pd.read_csv(paths[2]);p=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet').set_index('id');keys=['canonical_source_id','canonical_evidence_date','destination_uid','function_group','canonical_service_level'];checks=[]
 def ck(n,v):checks.append({'name':n,'pass':bool(v)})
 for r in a.itertuples(index=False):
  z=m.copy()
  for k in keys:z=z[z[k].fillna('').eq('' if pd.isna(getattr(r,k)) else getattr(r,k))]
  ext=set(z.origin_uid);ck('explicit_origins_'+str(tuple(getattr(r,k) for k in keys)),ext==set(r.external_origin_uids.split('|')))
  for y in [2002,2010,2021]:
   cp=p.loc[r.destination_uid,f'population_{y}'];ep=p.loc[list(ext),f'population_{y}'];s=ep.sum() if ep.notna().all() else np.nan
   for part,v in [('center',cp),('external',s),('total',cp+s)]:ck(f'population_{part}_{y}_{r.canonical_source_id}_{r.destination_uid}',np.isclose(v,getattr(r,f'{part}_population_{y}'),equal_nan=True))
 for r in d.itertuples(index=False):
  z=a.copy()
  for k in keys:z=z[z[k].fillna('').eq('' if pd.isna(getattr(r,k)) else getattr(r,k))]
  rr=z.iloc[0]
  for part in ['center','external','total']:
   v0=rr[f'{part}_population_{r.from_census}'];v1=rr[f'{part}_population_{r.to_census}']
   if not np.isfinite(v0) or not np.isfinite(v1):expected='missing_population'
   elif v0==0:expected='zero_both_censuses' if v1==0 else 'positive_after_zero_census_not_function_birth'
   else:
    delta=100*(v1-v0)/v0;expected='stable_within_threshold' if abs(delta)<=r.stability_threshold_percent else 'growth' if delta>0 else 'decline'
   ck(f'direction_{part}_{r.canonical_source_id}_{r.destination_uid}_{r.from_census}_{r.to_census}_{r.stability_threshold_percent}',expected==getattr(r,part+'_direction'))
 ck('28_fixed_boundaries',len(a)==28);ck('168_descriptive_profiles',len(d)==168);ck('no_functional_process_inferred',not d.functional_type_or_migration_process_identified.any());ck('no_historical_backcast',not a.historical_function_presence_backcast.any())
 audit={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','n_checks':len(checks),'checks':checks,'input_sha256':{str(f.relative_to(B)):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths},'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'interpretation':'Thresholds describe population directions only; repeated source sets are not independent observations; no migration or functional type established.'};(O/'CENTER_PERIPHERY_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(audit['status'],len(checks));assert all(x['pass'] for x in checks)
if __name__=='__main__':main()
