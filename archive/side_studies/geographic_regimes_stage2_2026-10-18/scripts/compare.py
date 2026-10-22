"""Stage II fixed baseline similarity; entire admissible graph before descriptive Y filters.
Usage: python compare.py --metrics PATH --output PATH
"""
import argparse,hashlib,json,platform
from pathlib import Path
import numpy as np,pandas as pd
from scipy.spatial import cKDTree

def run(metrics,output):
 out=Path(output);out.mkdir(parents=True,exist_ok=True);d=pd.read_csv(metrics)
 allpairs=[];scales={};unsupported=[]
 for kind in ['region','grid50','grid25','grid100','grid50shift25']:
  q=d[(d.kind==kind)&(d.n_positive2002>=20)].copy().sort_values('unit').reset_index(drop=True)
  q['log_nn2002']=np.log1p(q.nn2002_km_median)
  q['log_size_median2002']=np.log1p(q.size_median2002)
  q['log_size_p90_2002']=np.log1p(q.size_p90_2002)
  q['log_centre100k2002']=np.log1p(q.centre100k2002_km_median)
  features=['logpop2002','logn2002','top10_share2002','size_fraction_lt10','size_fraction_10_99','size_fraction_100_999','log_size_median2002','log_size_p90_2002','log_nn2002','log_centre100k2002']
  ok=np.isfinite(q[features].to_numpy(float)).all(axis=1)
  unsupported.extend([{'kind':kind,'unit':u,'reason':'baseline_nonfinite'} for u in q.loc[~ok,'unit']]);q=q.loc[ok].reset_index(drop=True)
  X=q[features].to_numpy(float);med=np.median(X,axis=0);iqr=np.quantile(X,.75,axis=0)-np.quantile(X,.25,axis=0);sd=np.std(X,axis=0);scale=np.where(iqr>0,iqr,sd);active=scale>0
  Z=(X[:,active]-med[active])/scale[active];fs=np.asarray(features)[active].tolist()
  scales[kind]={'n_eligible':len(q),'features':fs,'medians':med[active].tolist(),'scales':scale[active].tolist(),'rule':'median/IQR; SD fallback for zero IQR; constants dropped','calipers':{'max_abs':1.,'rms':.5}}
  pairs=cKDTree(Z).query_pairs(1.,p=np.inf,output_type='ndarray') if len(q)>1 else np.empty((0,2),int)
  counts=np.zeros(len(q),int)
  for i,j in pairs:
   diff=Z[i]-Z[j];rms=float(np.sqrt(np.mean(diff**2)))
   if rms>.5:continue
   counts[i]+=1;counts[j]+=1;a=q.iloc[i];b=q.iloc[j]
   r={'kind':kind,'a':a.unit,'b':b.unit,'rms_difference':rms,'max_abs_difference':float(abs(diff).max())}
   for f,v in zip(fs,diff):r['std_diff_'+f]=v
   for k in ['n_positive2002','population2002','population2021','relchange_2002_2021','top10_share2002','top10_delta_pp','survival_fraction','nn2002_km_median','nn2021_km_median','nn_change_km_median','nn_ratio_median','nn_baseline_zero_count','nn_newneighbor_fraction','centre100k2002_km_median','dominant_region','dominant_region_fraction']:
    if k in q:
     r['a_'+k]=a[k];r['b_'+k]=b[k]
   r['both_decline']=bool(a.relchange_2002_2021<0 and b.relchange_2002_2021<0)
   r['loss_difference_pp']=100*abs(a.relchange_2002_2021-b.relchange_2002_2021)
   r['similar_loss']=bool(r['both_decline'] and r['loss_difference_pp']<=5)
   r['concentration_gap_pp']=abs(a.top10_delta_pp-b.top10_delta_pp)
   r['survival_gap_pp']=100*abs(a.survival_fraction-b.survival_fraction)
   r['nn_ratio_gap']=abs(a.nn_ratio_median-b.nn_ratio_median)
   r['contrast_score']=r['concentration_gap_pp']/10+r['survival_gap_pp']/10+r['nn_ratio_gap']/.25
   allpairs.append(r)
  unsupported.extend([{'kind':kind,'unit':u,'reason':'no_baseline_analogue'} for u in q.loc[counts==0,'unit']])
  scales[kind]['n_admissible_pairs']=int(sum(counts)//2);scales[kind]['n_units_with_analogue']=int((counts>0).sum())
 pairs=pd.DataFrame(allpairs).sort_values(['kind','a','b']);pairs.to_csv(out/'comparison_registry.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 pd.DataFrame(unsupported).to_csv(out/'no_analogue_registry.csv',index=False)
 # Regional illustrations preferred; if <3 disjoint regional pairs, only cross-dominant-region local cells.
 selected=[];used=set()
 for rank,key,ascending in [('contrast_concentration','concentration_gap_pp',False),('contrast_neighborhood','nn_ratio_gap',False),('low_contrast','contrast_score',True)]:
  candidates=pairs[pairs.similar_loss].copy()
  candidates=candidates[candidates.apply(lambda r:(r.kind,str(r.a)) not in used and (r.kind,str(r.b)) not in used,axis=1)]
  regions=candidates[candidates.kind=='region']
  if len(regions):candidates=regions
  else:
   candidates=candidates[candidates.kind=='grid50']
   if 'a_dominant_region' in candidates:candidates=candidates[candidates.a_dominant_region!=candidates.b_dominant_region]
  if not len(candidates):continue
  r=candidates.sort_values([key,'rms_difference','a','b'],ascending=[ascending,True,True,True]).iloc[0].to_dict();r['selection']=rank;r['selection_status']='outcome-selected exploratory illustration';selected.append(r);used|={(r['kind'],str(r['a'])),(r['kind'],str(r['b']))}
 pd.DataFrame(selected).to_csv(out/'selected_illustrations.csv',index=False)
 summary=[]
 for kind,g in pairs.groupby('kind'):
  for subset,h in [('all_baseline_pairs',g),('similar_decline_pairs',g[g.similar_loss])]:
   rr={'kind':kind,'subset':subset,'n_pairs':len(h)}
   for f in ['concentration_gap_pp','survival_gap_pp','nn_ratio_gap','loss_difference_pp']:
    for qt in [.1,.5,.9]:rr[f+'_q'+str(int(100*qt))]=h[f].quantile(qt)
   summary.append(rr)
 pd.DataFrame(summary).to_csv(out/'pair_distributions.csv',index=False)
 meta={'input_metrics_sha256':hashlib.sha256(Path(metrics).read_bytes()).hexdigest(),'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'python':platform.python_version(),'scaling':scales,'n_pairs':len(pairs),'illustrations':len(selected),'limitations':['Admissible graph reuses units; pairs are dependent.','Outcome filtering is descriptive and potentially collider-conditioned.','Nearest centre is within ordinary panel; federal anchors remain separate context.','No p values or equivalence/causal claims.']}
 (out/'matching_receipt.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False));print(json.dumps(meta,ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--metrics',required=True);a.add_argument('--output',required=True);args=a.parse_args();run(args.metrics,args.output)
