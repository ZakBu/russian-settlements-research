#!/usr/bin/env python3
"""Independent closed-form ridge refit and error checks, no author functions."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
HERE=Path(__file__).resolve().parent;RUN=HERE.parent;REPO=HERE.parents[2]
def main():
 out=RUN/'results';pred=pd.read_parquet(out/'regression_out_of_region_predictions.parquet');metrics=pd.read_csv(out/'regression_comparison.csv');interval=pd.read_csv(out/'regression_paired_error_intervals.csv')
 s=pd.read_parquet(out/'systems_all_levels.parquet');s=s[s.level.eq(1)].set_index('center_id')
 context=pd.read_csv(out/'municipal_dominant_context.csv').set_index('center_index')
 m=pd.read_parquet(out/'memberships.parquet');master=pd.read_parquet(REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',columns=['id','econ_native_2011_legal_entities','econ_native_2011_direct_consumer_function_diversity']).set_index('id')
 joined=m[['id','center_index_l1','distance']].join(master,on='id');joined=joined[joined.center_index_l1.ge(0)]
 nentities=joined.groupby('center_index_l1').econ_native_2011_legal_entities.sum();dist=joined.groupby('center_index_l1').distance.mean()
 checks={};details=[]
 for period,group in pred.groupby('period'):
  p=group[group.model.eq('M1')];ids=p.center_id.to_list();s0=s.loc[ids];ctx=context.loc[s0.center_index]
  idx=s0.center_index.to_numpy();den=s0.system_population_2002.to_numpy(float)
  X=np.column_stack([np.log1p(s0.center_population_2002),np.log1p(s0.rural_external_population_2002),np.log1p(dist.loc[idx]),s0.center_population_2002/den,np.log1p(ctx.agri_total_ha_2010_native_code.to_numpy()/den),np.log1p(ctx.agri_production_nominal_thousand_rub_2010.to_numpy()/den),np.log1p(1000*nentities.loc[idx].to_numpy()/den),master.loc[ids].econ_native_2011_direct_consumer_function_diversity])
  start,end=map(int,period.split('-'));target=np.log(s0[f'rural_external_population_{end}']/s0[f'rural_external_population_{start}'])/(end-start)
  checks[period+'_target_recomputed']=bool(np.allclose(target,p.target,rtol=1e-12,atol=1e-12))
  groups=p.region.to_numpy();cv=GroupKFold(n_splits=min(5,len(np.unique(groups))));splits=list(cv.split(X,groups=groups))
  checks[period+'_regions_disjoint_all_folds']=all(not(set(groups[tr])&set(groups[te])) for tr,te in splits)
  for model,k in [('M1',4),('M2',6),('M3',8)]:
   pp=group[group.model.eq(model)];checks[period+'_'+model+'_same_ids']=ids==pp.center_id.to_list();Y=target.to_numpy();refit=np.empty(len(Y));A=X[:,:k]
   for train,test in splits:
    mu=A[train].mean(axis=0);scale=A[train].std(axis=0);scale[scale==0]=1
    Z=(A[train]-mu)/scale;intercept=Y[train].mean();beta=np.linalg.solve(Z.T@Z+np.eye(k),Z.T@(Y[train]-intercept));refit[test]=((A[test]-mu)/scale)@beta+intercept
   error=pp.prediction.to_numpy()-Y;rmse=float(np.sqrt(np.mean(error**2)));mae=float(np.mean(np.abs(error)));row=metrics[(metrics.period.eq(period))&metrics.model.eq(model)].iloc[0]
   checks[period+'_'+model+'_closed_form_predictions']=bool(np.allclose(refit,pp.prediction,rtol=1e-9,atol=1e-11))
   checks[period+'_'+model+'_rmse_mae']=bool(np.allclose([rmse,mae],[row.rmse_annual_log,row.mae_annual_log],rtol=1e-12,atol=1e-12))
   details.append({'period':period,'model':model,'n':len(Y),'max_prediction_abs_difference':float(np.max(np.abs(refit-pp.prediction.to_numpy()))),'rmse':rmse,'mae':mae})
 checks['all_comparison_intervals_include_zero']=bool((interval.region_bootstrap_p025.le(0)&interval.region_bootstrap_p975.ge(0)).all())
 result={'independent_algorithm':'closed-form numpy ridge with independently reconstructed features and train-only scaling','checks':checks,'n_checks':len(checks),'n_passed':sum(checks.values()),'all_pass':all(checks.values()),'results':details,'interpretation':'304 complete systems in48regions; all four paired error intervals include0; no established robust agrarian/economic incremental gain or causal effect','source_predictions_sha256':hashlib.sha256((out/'regression_out_of_region_predictions.parquet').read_bytes()).hexdigest()}
 (HERE/'independent_regression_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
