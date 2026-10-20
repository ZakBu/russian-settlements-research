#!/usr/bin/env python3
"""Independently reconstruct features and solve ridge by linear algebra."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
from sklearn.model_selection import GroupKFold
BASE=Path(__file__).resolve().parents[2];OLD=BASE.parent/'sgrt_national_integration_20261019';OUT=BASE/'reviews/statistics'
checks=[]
def ck(name,ok,**info):checks.append({'check':name,'pass':bool(ok),**info})
s=pd.read_parquet(BASE/'results/systems_all_levels.parquet');s=s[(s.level==1)&s.has_rural_periphery&s.center_axis_kind.eq('ordinary')].copy()
context=pd.read_csv(BASE/'results/municipal_dominant_context.csv');s=s.merge(context,on='center_index',validate='one_to_one')
m=pd.read_parquet(BASE/'results/memberships.parquet',columns=['id','center_index_l1','distance'])
d=pd.read_parquet(OLD/'core/feature_master.parquet',columns=['id','econ_native_2011_legal_entities','econ_native_2011_direct_consumer_function_diversity'])
x=m.merge(d,on='id',validate='one_to_one');x=x[x.center_index_l1>=0]
ag=x.groupby('center_index_l1').agg(n2011=('econ_native_2011_legal_entities','sum'),distance=('distance','mean'))
s=s.merge(ag,left_on='center_index',right_index=True,how='left')
s['x0']=np.log(1+s.center_population_2002)
s['x1']=np.log(1+s.rural_external_population_2002)
s['x2']=np.log(1+s.distance)
s['x3']=s.center_population_2002/s.system_population_2002.replace(0,np.nan)
s['x4']=np.log(1+s.agri_total_ha_2010_native_code/s.system_population_2002.replace(0,np.nan))
s['x5']=np.log(1+s.agri_production_nominal_thousand_rub_2010/s.system_population_2002.replace(0,np.nan))
s['x6']=np.log(1+1000*s.n2011/s.system_population_2002.replace(0,np.nan))
s['x7']=s.center_id.map(d.set_index('id').econ_native_2011_direct_consumer_function_diversity)
features=[f'x{i}' for i in range(8)];rederived=[];evals=[];splitchecks=[]
saved=pd.read_parquet(BASE/'results/regression_out_of_region_predictions.parquet')
summary=pd.read_csv(BASE/'results/regression_comparison.csv')
for first,last in [(2002,2021),(2010,2021)]:
 good=s.mutual80.eq(True)&s[f'rural_external_population_{first}'].gt(0)&s[f'rural_external_population_{last}'].gt(0)&s[features].notna().all(axis=1)&np.isfinite(s[features]).all(axis=1)
 a=s[good].copy();target=np.log(a[f'rural_external_population_{last}'].values/a[f'rural_external_population_{first}'].values)/(last-first)
 period=f'{first}-{last}';ck(period+'_same_complete304rows',len(a)==304,n=len(a),regions=int(a.region.nunique()))
 splits=list(GroupKFold(n_splits=5).split(a,groups=a.region))
 for fold,(train,test) in enumerate(splits):
  overlap=set(a.iloc[train].region)&set(a.iloc[test].region)
  splitchecks.append({'period':period,'fold':fold,'train_regions':len(set(a.iloc[train].region)),'test_regions':len(set(a.iloc[test].region)),'overlap':len(overlap)})
  ck(period+f'_fold{fold}_region_disjoint',not overlap)
 for label,ncols in [('M1',4),('M2',6),('M3',8)]:
  mat=a[features[:ncols]].to_numpy();pred=np.full(len(a),np.nan)
  for train,test in splits:
   mean=mat[train].mean(axis=0);scale=mat[train].std(axis=0);scale[scale==0]=1
   design=(mat[train]-mean)/scale;ymean=target[train].mean()
   # alpha=1; intercept is unpenalized, centered training y.
   coef=np.linalg.solve(design.T@design+np.eye(ncols),design.T@(target[train]-ymean))
   pred[test]=((mat[test]-mean)/scale)@coef+ymean
  expected=pd.DataFrame({'center_id':a.center_id.values,'prediction_rederived':pred,'target_rederived':target})
  original=saved[saved.period.eq(period)&saved.model.eq(label)]
  join=expected.merge(original,on='center_id',validate='one_to_one')
  ck(period+'_'+label+'_targets_exact',np.allclose(join.target_rederived,join.target,rtol=0,atol=1e-15))
  ck(period+'_'+label+'_linear_algebra_predictions',np.allclose(join.prediction_rederived,join.prediction,rtol=1e-10,atol=1e-12),max_error=float(abs(join.prediction_rederived-join.prediction).max()))
  rmse=float(np.sqrt(np.square(pred-target).mean()));mae=float(abs(pred-target).mean());reported=summary[summary.period.eq(period)&summary.model.eq(label)].iloc[0]
  ck(period+'_'+label+'_RMSE_MAE',np.isclose(rmse,reported.rmse_annual_log,rtol=1e-12,atol=1e-14) and np.isclose(mae,reported.mae_annual_log,rtol=1e-12,atol=1e-14))
  evals.append({'period':period,'model':label,'rows':len(a),'regions':int(a.region.nunique()),'rmse':rmse,'mae':mae})
  for uid,y,p in zip(a.center_id,target,pred):rederived.append({'period':period,'model':label,'center_id':uid,'target':float(y),'prediction':float(p)})
intervals=pd.read_csv(BASE/'results/regression_paired_error_intervals.csv')
ck('all_error_improvement_intervals_include_zero',intervals.region_bootstrap_p025.le(0).all() and intervals.region_bootstrap_p975.ge(0).all())
for row in intervals.itertuples():
 g=summary[summary.period.eq(row.period)].set_index('model');other=row.comparison.split('_')[0]
 exact=1-g.loc[other,'rmse_annual_log']/g.loc['M1','rmse_annual_log']
 ck(row.period+'_'+row.comparison+'_reported_point_reduction',np.isclose(exact,row.relative_rmse_reduction,rtol=1e-12,atol=1e-14))
status='PASS_DESCRIPTIVE_ONLY' if all(c['pass'] for c in checks) else 'REVISE'
report={'status':status,'checks':checks,'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'implementation_independence':'Features rebuilt from master+memberships+checked municipal context. Ridge solved as centered closed-form normal equations, no author import or sklearn Ridge/StandardScaler/Pipeline. GroupKFold shared only for deterministic split definition.','results':evals,'interpretation':'304 complete strict systems across48regions. M2/M3 reduce heldout RMSE point estimate; all paired region bootstrap intervals include zero. No robust incremental benefit established. Contemporary fixed geometry, source and boundary uncertainty prevent causal/predictive historical claims.','scope_limits':['Early municipal and organization variables remain moderncode-linked or retrospective-source variables','Region heldout is spatial separation, not blind pre-registered independent validation','Bootstrap conditional on fitted cross-validation predictions does not cover data-generation/model-fit/geometry uncertainty'],'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(OUT/'independent_regression_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
pd.DataFrame(rederived).to_parquet(OUT/'independent_regression_predictions.parquet',index=False)
pd.DataFrame(splitchecks).to_csv(OUT/'region_split_checks.csv',index=False)
with (OUT/'VERDICT.md').open('a') as f:f.write('\n## Регрессии\n\n'+status+f": {len(checks)} условий, {report['n_failed']} не пройдено. M1/M2/M3 пересчитаны по замкнутому решению ridge на тех же304строках48регионов. Все интервалы прибавки к M1 включают0: устойчивое улучшение не установлено.\n")
print(json.dumps({'status':status,'n_checks':len(checks),'n_failed':report['n_failed']},ensure_ascii=False))
