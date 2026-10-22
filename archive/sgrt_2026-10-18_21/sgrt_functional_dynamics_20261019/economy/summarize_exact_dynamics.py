#!/usr/bin/env python3
"""Stratified and spatial robustness for identical exact-code linkage rules."""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
import pyarrow.parquet as pq
from build_dynamics import statust,spatial,sha,dump
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--panel',type=Path,required=True);a=ap.parse_args()
 p=pq.read_table(a.panel,columns=['id','population_2010','population_2021','lat','lon']).to_pandas()
 base=pq.read_table(a.out/'point_function_dynamics.parquet').to_pandas().query('quality_mode=="coded_baseline"')[['id','population_bin','demographic_2010_2021']]
 c=pq.read_table(a.out/'point_cohort_sensitivity.parquet').to_pandas().merge(p,on='id',validate='many_to_one').merge(base,on='id',validate='many_to_one')
 rows=[];frames=[]
 for name,z in c.groupby('cohort',sort=True):
  z=z.copy();z['quality_mode']=name
  for k,label in [(1,'any_direct_service'),(2,'diversification_ge2'),(3,'diversification_ge3')]:
   z[label+'_transition']=statust(z.direct_diversity_2016>=k,z.direct_diversity_2021>=k)
   for strat in [None,'population_bin','demographic_2010_2021']:
    zz=[('all',z)] if strat is None else z.groupby(strat,dropna=False,observed=True)
    for level,v in zz:
     t=v[label+'_transition'];r={'cohort':name,'feature':label,'stratifier':strat or 'all','stratum':level,'n':len(v)}
     for state in ['unobserved_both','witness_lost','witness_gained','witness_retained']:r[state]=int(t.eq(state).sum())
     r['observed_2016']=r['witness_lost']+r['witness_retained'];r['observed_2021']=r['witness_gained']+r['witness_retained'];r['net_change']=r['witness_gained']-r['witness_lost'];rows.append(r)
  frames.append(z)
 pd.DataFrame(rows).to_csv(a.out/'cohort_stratified_summary.csv',index=False)
 sub=a.out/'exact_cohort_spatial';sub.mkdir(exist_ok=True);checks=[]
 spatial(pd.concat(frames,ignore_index=True),sub,checks)
 dump(sub/'checks.json',checks);assert all(q['pass'] for q in checks)
 dump(sub/'MANIFEST.json',{x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sub.iterdir() if x.is_file() and x.name!='MANIFEST.json'})
 print(json.dumps({'checks':len(checks),'pass':True,'stratified_rows':len(rows)}))
if __name__=='__main__':main()
