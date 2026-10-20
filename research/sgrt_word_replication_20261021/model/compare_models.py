#!/usr/bin/env python3
"""Same-row region-held-out descriptive M1/M2/M3; never feeds catchment masses."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT.parent/'sgrt_national_integration_20261019'
def run():
 out=ROOT/'results';s=pd.read_parquet(out/'systems_all_levels.parquet');s=s[(s.level==1)&s.has_rural_periphery&s.center_axis_kind.eq('ordinary')].copy()
 ctx=pd.read_csv(out/'municipal_dominant_context.csv');s=s.merge(ctx,on='center_index',validate='one_to_one')
 mem=pd.read_parquet(out/'memberships.parquet',columns=['id','center_index_l1','distance','population_2002'])
 cols=['id','econ_native_2011_legal_entities','econ_native_2011_direct_consumer_function_diversity']
 d=pd.read_parquet(OLD/'core/feature_master.parquet',columns=cols)
 q=mem.merge(d,on='id',validate='one_to_one');q=q[q.center_index_l1>=0]
 e=q.groupby('center_index_l1').agg(registered2011_entities=('econ_native_2011_legal_entities','sum'),mean_distance_km=('distance','mean'))
 s=s.merge(e,left_on='center_index',right_index=True,how='left')
 center2011=d.set_index('id').econ_native_2011_direct_consumer_function_diversity
 s['center_2011_registered_diversity']=s.center_id.map(center2011)
 s['log_center2002']=np.log1p(s.center_population_2002)
 s['log_rural2002']=np.log1p(s.rural_external_population_2002)
 s['log_distance']=np.log1p(s.mean_distance_km)
 s['initial_center_share']=s.center_population_2002/s.system_population_2002.replace(0,np.nan)
 s['log_municipal_ha2010_per2002resident']=np.log1p(s.agri_total_ha_2010_native_code/s.system_population_2002.replace(0,np.nan))
 s['log_municipal_production2010_per2002resident']=np.log1p(s.agri_production_nominal_thousand_rub_2010/s.system_population_2002.replace(0,np.nan))
 s['log_registered2011_per1000resident2002']=np.log1p(1000*s.registered2011_entities/s.system_population_2002.replace(0,np.nan))
 blocks={'M1':['log_center2002','log_rural2002','log_distance','initial_center_share'],'M2':['log_municipal_ha2010_per2002resident','log_municipal_production2010_per2002resident'],'M3':['log_registered2011_per1000resident2002','center_2011_registered_diversity']}
 features=blocks['M1']+blocks['M2']+blocks['M3'];models={'M1':blocks['M1'],'M2':blocks['M1']+blocks['M2'],'M3':features}
 results=[];predictions=[];coefs=[];exclusions=[]
 for initial,final in [(2002,2021),(2010,2021)]:
  valid=(s[f'rural_external_population_{initial}']>0)&(s[f'rural_external_population_{final}']>0)&s[features].notna().all(axis=1)&np.isfinite(s[features]).all(axis=1)&s.mutual80.eq(True)
  a=s[valid].copy();a['target']=np.log(a[f'rural_external_population_{final}']/a[f'rural_external_population_{initial}'])/(final-initial)
  exclusions.append(dict(period=f'{initial}-{final}',all_rural_systems=len(s),same_complete_strict_rows=len(a),regions=a.region.nunique(),excluded=int((~valid).sum()),strict_mutual80=int(s.mutual80.eq(True).sum())))
  if len(a)<30 or a.region.nunique()<5:continue
  splitter=GroupKFold(n_splits=min(5,a.region.nunique()));splits=list(splitter.split(a,groups=a.region))
  for model,cols in models.items():
   pred=np.full(len(a),np.nan)
   for fold,(train,test) in enumerate(splits):
    pipe=make_pipeline(StandardScaler(),Ridge(alpha=1.0));pipe.fit(a.iloc[train][cols],a.iloc[train].target);pred[test]=pipe.predict(a.iloc[test][cols])
   err=pred-a.target.to_numpy();rmse=float(np.sqrt(np.mean(err**2)));mae=float(np.abs(err).mean())
   results.append(dict(period=f'{initial}-{final}',model=model,n=len(a),regions=a.region.nunique(),rmse_annual_log=rmse,mae_annual_log=mae,validation='5fold_region_held_out_same_rows',interpretation='descriptive_association_on_contemporary_fixed_catchments_not_causal_or_independent_historical_backtest'))
   for uid,region,y,p in zip(a.center_id,a.region,a.target,pred):predictions.append(dict(period=f'{initial}-{final}',model=model,center_id=uid,region=region,target=y,prediction=p))
   pipe=make_pipeline(StandardScaler(),Ridge(alpha=1));pipe.fit(a[cols],a.target)
   for f,c in zip(cols,pipe[-1].coef_):coefs.append(dict(period=f'{initial}-{final}',model=model,feature=f,standardized_ridge_coefficient=float(c),coefficient_not_causal=True))
 pd.DataFrame(results).to_csv(out/'regression_comparison.csv',index=False);pd.DataFrame(predictions).to_parquet(out/'regression_out_of_region_predictions.parquet',index=False);pd.DataFrame(coefs).to_csv(out/'regression_coefficients.csv',index=False);pd.DataFrame(exclusions).to_csv(out/'regression_exclusions.csv',index=False)
 # Paired region bootstrap on held-out errors: precision of comparison, not census uncertainty.
 p=pd.DataFrame(predictions);intervals=[];rng=np.random.default_rng(20261021)
 if len(p):
  for period,g in p.groupby('period'):
   w=g.pivot(index=['center_id','region','target'],columns='model',values='prediction').reset_index();regions=w.region.unique()
   sums={}
   for model in models:sums[model]=w.assign(e=np.square(w[model]-w.target)).groupby('region').e.agg(['sum','count']).reindex(regions)
   for other in ['M2','M3']:
    draws=[]
    for b in range(1000):
     sample=rng.integers(0,len(regions),len(regions));baseline=sums['M1'].iloc[sample];comp=sums[other].iloc[sample]
     draws.append(1-np.sqrt(comp['sum'].sum()/comp['count'].sum())/np.sqrt(baseline['sum'].sum()/baseline['count'].sum()))
    intervals.append(dict(period=period,comparison=other+'_vs_M1',relative_rmse_reduction=float(1-np.sqrt(sums[other]['sum'].sum()/sums[other]['count'].sum())/np.sqrt(sums['M1']['sum'].sum()/sums['M1']['count'].sum())),region_bootstrap_p025=float(np.quantile(draws,.025)),region_bootstrap_p975=float(np.quantile(draws,.975)),bootstrap_replicates=1000,interval_scope='paired_sampling_variability_of_heldout_error_not_source_or_boundary_uncertainty'))
 pd.DataFrame(intervals).to_csv(out/'regression_paired_error_intervals.csv',index=False)
 (out/'regression_receipt.json').write_text(json.dumps({'status':'COMPUTED','blocks':blocks,'same_rows_across_models':True,'population2021_predictor':False,'functional_mass_calibrated_by_this_regression':False,'geography':'modern_fixed_systems_not_historical_reconstruction','municipality':'2021dictionary_link_not_proven_boundary_equivalence2010','2011_RFSD':'registered_legal_witnesses_in_pinned_retrospective_release_not_complete_physical_2011_services','results':results,'row_exclusions':exclusions},ensure_ascii=False,indent=2))
 print(pd.DataFrame(results).to_string(index=False));print(pd.DataFrame(intervals).to_string(index=False))
if __name__=='__main__':run()
