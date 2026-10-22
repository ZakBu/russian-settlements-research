"""Independent claim checks from raw and published metrics/point results.
Does not read c2_sensitivity.py or reuse main functions.
"""
import pandas as pd,numpy as np,json,hashlib,math
from pathlib import Path
out=Path('stage2_work/replication');m=pd.read_csv('stage2_work/geo/outputs/territory_metrics.csv');pts=pd.read_csv('stage2_work/geo/outputs/point_distances.csv.gz');pairs=pd.read_csv('stage2_work/comparison/comparison_registry.csv.gz')
c2=[]
for kind in ['grid50','grid25','grid100','grid50shift25','region']:
 eligible=m[(m.kind==kind)&(m.n_positive2002>=20)&(m.relchange_2002_2021<0)].copy();eligible['unit']=eligible.unit.astype(str);eligible=eligible.set_index('unit')
 for v,col in [('primary','nn2021_km'),('original2021coordinates','nn2021_original_coords_km'),('baselinepositiveonly','nn2021_survivor_neighbors_km')]:
  deltas=pts[col]-pts.nn2002_km;grouped=pd.DataFrame({'unit':pts[kind].astype(str),'delta':deltas}).groupby('unit').delta.quantile(.9)
  join=eligible[['top10_delta_pp']].join(grouped)
  assert join.delta.notna().all()
  for tol in [0,1e-9]:
   num=int(((join.top10_delta_pp>0)&(join.delta>tol)).sum());c2.append(dict(kind=kind,variant=v,tolerance_km=tol,n=len(join),cooccurrence_n=num,fraction=num/len(join)))
pd.DataFrame(c2).to_csv(out/'claim2_independent_summary.csv',index=False)
# C1: reconstruct fixed baseline grouping and original matched registry filter.
r=pd.read_csv('repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz',usecols=['entity_uid','effective_region_norm_2002','population_2002','population_2021'])
deltas={};excl={}
for reg,d in r.groupby('effective_region_norm_2002'):
 d=d.sort_values(['population_2002','entity_uid'],ascending=[False,True]);k=math.ceil(len(d)/10);tot0=d.population_2002.sum();tot1=d.population_2021.sum();t0=d.iloc[:k].population_2002.sum();t1=d.iloc[:k].population_2021.sum();deltas[reg]=100*(t1/tot1-t0/tot0)
 big=d.iloc[0];excl[reg]=100*((t1-big.population_2021)/(tot1-big.population_2021)-(t0-big.population_2002)/(tot0-big.population_2002)) if tot0>big.population_2002 and tot1>big.population_2021 else np.nan
p=pairs[pairs.kind=='region'].copy();filter_=(p.a_relchange_2002_2021<0)&(p.b_relchange_2002_2021<0)&((p.a_relchange_2002_2021-p.b_relchange_2002_2021).abs()<=.05);p=p[filter_]
c1=[]
for variant,lookup in [('primary',deltas),('exclude_baseline_largest_fixedmembership',excl)]:
 gaps=np.array([abs(lookup[a]-lookup[b]) for a,b in zip(p.a,p.b)]);c1.append(dict(variant=variant,n_pairs=len(gaps),unique_units=len(set(p.a)|set(p.b)),median_gap_pp=float(np.median(gaps)),p90_gap_pp=float(np.quantile(gaps,.9))))
pd.DataFrame(c1).to_csv(out/'claim1_independent_summary.csv',index=False)
errors=[]
def check(name,a,b,tol=1e-5):
 if abs(a-b)>tol:errors.append(dict(check=name,independent=float(a),reference=float(b)))
base=next(x for x in c2 if x['kind']=='grid50' and x['variant']=='primary' and x['tolerance_km']==0)
check('C2N',base['n'],1189,0);check('C2numerator',base['cooccurrence_n'],364,0)
for variant,n in [('original2021coordinates',572),('baselinepositiveonly',367)]:check('C2'+variant,next(x['cooccurrence_n'] for x in c2 if x['kind']=='grid50' and x['variant']==variant and x['tolerance_km']==0),n,0)
for val,name in [(c1[0]['n_pairs'],'pairs'),(c1[0]['unique_units'],'units')]:check(name,val,104 if name=='pairs' else 46,0)
for result,med,p90 in [(c1[0],1.292665,3.035296),(c1[1],1.406697,3.727499)]:check(result['variant']+'median',result['median_gap_pp'],med);check(result['variant']+'p90',result['p90_gap_pp'],p90)
receipt=dict(status='passed' if not errors else 'failed',errors=errors,c1=c1,c2=c2,independent_implementation=True,main_claim_code_not_read=True,limitations='C2 uses published point distances verified separately on60origins; no independent fullnational geometry rerun; C1 recomputes shares from raw populations.')
json.dump(receipt,open(out/'claims_receipt.json','w'),indent=2);print(json.dumps(receipt,indent=2))
