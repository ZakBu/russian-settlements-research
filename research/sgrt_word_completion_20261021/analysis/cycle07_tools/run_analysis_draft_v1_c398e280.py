"""New transport-scenario analysis. Imports numerical primitives only.
Source preparation and prospective review must precede actual estimation.
"""
from pathlib import Path
import argparse,hashlib,json,importlib.util,datetime
import numpy as np,pandas as pd
from sklearn.model_selection import GroupKFold
from new_adapter import sha,path,HERE
HELPER=path('analysis/cycle06_tools/run_regressions_cycle06.py')
assert sha(HELPER)=='3f79c110e5c705b396954aaf0e5837ba04b6b88d350637f76af989ba0a5dbb4b'
spec=importlib.util.spec_from_file_location('reviewed_numeric_primitives',HELPER);numeric=importlib.util.module_from_spec(spec);spec.loader.exec_module(numeric)
standardize,fit_ols,spatial_weights,moran=[getattr(numeric,k)for k in ['standardize','fit_ols','spatial_weights','moran']]
def clean(x):
 if isinstance(x,dict):return{k:clean(v)for k,v in x.items()}
 if isinstance(x,(list,tuple)):return[clean(v)for v in x]
 if isinstance(x,np.generic):return clean(x.item())
 if isinstance(x,float)and not np.isfinite(x):return None
 return x
def dump(p,v):p.write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,allow_nan=False))
def scenarios(protocol):
 variants=[('primary','outcome_system_change_pct',False,False,False),('rural_population_sensitivity','outcome_rural_change_pct',False,False,False),('positive_logratio_sensitivity','outcome_system_log_change_100',False,False,False),('historical_grain2010_sensitivity','outcome_system_change_pct',False,False,True),('pure_primary_sensitivity','outcome_system_change_pct',True,False,False),('supported_primary_sensitivity','outcome_system_change_pct',False,True,False)]
 for family,models in protocol['families'].items():
  for name,outcome,pure,supported,historical in variants:
   terms={m:[v.replace('log_agro_grain_yield2021','log_agro_grain_yield2010')if historical else v for v in cols]for m,cols in models.items()}
   yield family+'__'+name,outcome,terms,pure,supported

def estimate(frame,scenario,outcome,terms,protocol,pure=False,supported=False):
 outputs={k:[]for k in ['metrics','coefficients','predictions','spatial','samples','folds','gates','bootstrap']};required=list(dict.fromkeys(v for cols in terms.values()for v in cols))
 for cap,d in frame.groupby('candidate_cap',sort=True):
  finite=d[required+[outcome,'lat','lon']].apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan).notna().all(axis=1)&d.region.notna()
  if pure:finite&=d.analysis_system2010_primary_source_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  if supported:finite&=d.analysis_system2010_primary_supported_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  sample=d.loc[finite].sort_values('unit_id');n=len(sample);regions=sample.region.nunique();key={'scenario':scenario,'outcome':outcome,'candidate_cap':int(cap),'comparison_family':scenario.split('__')[0]};minimum=max(protocol['minimum_sample'],protocol['minimum_sample_per_union_predictor']*(len(required)+1));gate={**key,'all_units':len(d),'outcome_observed':int(d[outcome].notna().sum()),'common_sample':n,'regions':int(regions),'minimum_common_sample':minimum,'union_predictor_count':len(required),'status':'COMPUTED'if n>=minimum and regions>=protocol['minimum_regions']else'INSUFFICIENT_COMMON_SAMPLE_OR_REGIONS'};outputs['gates'].append(gate)
  outputs['samples'].extend({**key,'unit_id':r.unit_id,'in_common_sample':bool(ok)}for r,ok in zip(d.itertuples(),finite))
  if gate['status']!='COMPUTED':continue
  group=sample.region.astype(str).to_numpy();y=sample[outcome].to_numpy(float);folds=list(GroupKFold(n_splits=protocol['cv_folds']).split(sample,y,group));foldids=np.full(n,-1)
  for fold,(_,test)in enumerate(folds):foldids[test]=fold
  weights,spmeta=spatial_weights(sample.lat.to_numpy(),sample.lon.to_numpy(),protocol['moran_neighbors']);unique=sorted(np.unique(group));codes=pd.Categorical(group,categories=unique).codes;seed=protocol['seed']+int(hashlib.sha256(f'{scenario}|{outcome}|{int(cap)}'.encode()).hexdigest()[:8],16);draws=np.random.default_rng(seed).multinomial(len(unique),np.full(len(unique),1/len(unique)),size=protocol['cluster_bootstrap_replicates'])
  for model,cols in terms.items():
   mk={**key,'model':model};kept=[];constant=[];collinear=[];current=np.ones((n,1));rank=1
   for column in cols:
    value=sample[column].to_numpy(float);sd=value.std()
    if sd<=1e-12:constant.append(column);continue
    trial=np.column_stack([current,(value-value.mean())/sd]);newrank=np.linalg.matrix_rank(trial)
    if newrank>rank:kept.append(column);current=trial;rank=newrank
    else:collinear.append(column)
   x=sample[kept].to_numpy(float);fit=fit_ols(x,y,group);assert fit['rank']==fit['p'];pred=np.full(n,np.nan);null=np.full(n,np.nan);badfolds=0
   for fold,(train,test)in enumerate(folds):
    assert set(group[train]).isdisjoint(group[test]);tx,mean,sd=standardize(x[train]);vx,_,_=standardize(x[test],mean,sd);beta=np.linalg.lstsq(tx,y[train],rcond=None)[0];pred[test]=vx@beta;null[test]=y[train].mean();frank=int(np.linalg.matrix_rank(tx));badfolds+=frank<tx.shape[1];outputs['folds'].append({**mk,'fold':fold,'n_train':len(train),'n_test':len(test),'train_regions':len(np.unique(group[train])),'test_regions':len(np.unique(group[test])),'train_design_rank':frank,'train_design_parameters':tx.shape[1],'rmse':float(np.sqrt(np.mean((y[test]-pred[test])**2))),'mae':float(np.mean(abs(y[test]-pred[test])))})
   assert np.isfinite(pred).all();nullss=np.sum((y-null)**2)
   outputs['metrics'].append({**mk,'n':n,'regions':int(regions),'parameters':fit['p'],'rank':fit['rank'],'condition_number':fit['condition_number'],'r2':fit['r2'],'adjusted_r2':fit['adj_r2'],'group_oof_rmse':float(np.sqrt(np.mean((y-pred)**2))),'group_oof_mae':float(np.mean(abs(y-pred))),'group_oof_r2_train_mean_baseline':float(1-np.sum((y-pred)**2)/nullss)if nullss>0 else None,'dropped_constant_terms':'|'.join(constant),'dropped_collinear_terms':'|'.join(collinear),'cv_training_rank_deficient_folds':int(badfolds),'max_cooks_distance':float(fit['cooks'].max()),'interpretation':'descriptive association; caps alternative transport scenarios, not tiers'})
   for j,term in enumerate(['intercept']+kept):outputs['coefficients'].append({**mk,'term':term,'beta':float(fit['beta'][j]),'se_cluster_region':float(fit['se'][j]),'ci95_lower':float(fit['ci_lower'][j]),'ci95_upper':float(fit['ci_upper'][j]),'predictor_mean':None if j==0 else float(fit['mean'][j-1]),'predictor_sd':None if j==0 else float(fit['sd'][j-1]),'ci_dof':int(regions-1),'scale':'outcome units per predictor SD; conditional source values'})
   outputs['spatial'].append({**mk,**moran(fit['residual'],weights,protocol['moran_permutations'],protocol['seed']),**{'group_oof_'+k:v for k,v in moran(y-pred,weights,protocol['moran_permutations'],protocol['seed']).items()},**spmeta})
   for i,r in enumerate(sample.itertuples()):outputs['predictions'].append({**mk,'unit_id':r.unit_id,'center_id':r.center_id,'name':r.name,'region':r.region,'lat':r.lat,'lon':r.lon,'source_valued_outcome':float(y[i]),'fitted':float(fit['fitted'][i]),'residual':float(fit['residual'][i]),'group_oof_prediction':float(pred[i]),'group_oof_residual':float(y[i]-pred[i]),'cv_fold':int(foldids[i]),'leverage':float(fit['hat'][i]),'cooks_distance':float(fit['cooks'][i])})
   design,_,_=standardize(x);bs=[]
   for draw in draws:
    w=np.sqrt(draw[codes]);wx=design*w[:,None]
    if np.linalg.matrix_rank(wx)==wx.shape[1]:bs.append(np.linalg.lstsq(wx,y*w,rcond=None)[0])
   accepted=len(bs)>=protocol['minimum_successful_bootstrap_fraction']*len(draws);bounds=np.quantile(bs,[.025,.975],axis=0)if accepted else None
   for j,term in enumerate(['intercept']+kept):outputs['bootstrap'].append({**mk,'term':term,'status':'COMPUTED'if accepted else'INSUFFICIENT_FULL_RANK_CLUSTER_DRAWS','requested_replicates':len(draws),'full_rank_replicates':len(bs),'cluster_regions':len(unique),'ci95_lower':float(bounds[0,j])if accepted else None,'ci95_upper':float(bounds[1,j])if accepted else None,'paired_region_draw_seed':seed,'paired_region_draws_shared_within_family':True,'upstream_hierarchy_uncertainty_propagated':False})
 return outputs

def registration(source_receipt,proofs=()):
 sp=path(source_receipt);source=json.loads(sp.read_text());protocol=path('analysis/cycle07_tools/PROTOCOL_v1.json');return{'status':'PROSPECTIVE_NEW_TRANSPORT_SCENARIO_ANALYSIS_NO_METRICS','source_receipt':str(sp),'source_receipt_sha256':sha(sp),'supplemental_source_proofs_sha256':{str(path(p)):sha(path(p))for p in proofs},'source_family':source['source_family'],'analysis_code_sha256':sha(Path(__file__)),'numeric_helper_sha256':sha(HELPER),'protocol_sha256':sha(protocol),'scenarios':[{'name':n,'outcome':o,'terms':t,'pure_primary':p,'supported_primary':s}for n,o,t,p,s in scenarios(json.loads(protocol.read_text()))],'source_outputs_sha256':source['outputs_sha256'],'all_source_inputs_sha256':source['source_inputs_sha256'],'cross_family_score_comparison_is_added_inventory_effect':False,'all_caps_are_separate_scenarios_not_independent_replicates':True,'whole_complete_excludes_any_unknown_focal_or_nonfocal_metropolitan_member':True}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source-receipt',required=True);ap.add_argument('--output',required=True);ap.add_argument('--stage',choices=['preregister','full'],default='preregister');ap.add_argument('--review');ap.add_argument('--source-proof',action='append',default=[]);a=ap.parse_args();out=path(a.output);reg=registration(a.source_receipt,a.source_proof)
 if a.stage=='preregister':
  assert not out.exists();out.mkdir(parents=True);dump(out/'preregistration.json',reg);print(json.dumps({'status':'PREREGISTERED_NO_METRICS','sha256':sha(out/'preregistration.json')}));return
 assert json.loads((out/'preregistration.json').read_text())==reg;review=path(a.review);ad=json.loads(review.read_text());assert ad['all_checks_passed']is True and ad['preregistration_sha256']==sha(out/'preregistration.json')and ad['analysis_code_sha256']==sha(Path(__file__));assert not(out/'started_guard.json').exists();dump(out/'started_guard.json',{'status':'STARTED_AFTER_INDEPENDENT_ADMISSION','review_sha256':sha(review)})
 source=path(a.source_receipt).parent;watch={Path(p):h for p,h in reg['all_source_inputs_sha256'].items()};watch[path(a.source_receipt)]=reg['source_receipt_sha256'];watch.update({source/p:h for p,h in reg['source_outputs_sha256'].items()});watch.update({Path(p):h for p,h in reg['supplemental_source_proofs_sha256'].items()});watch.update({Path(__file__):sha(Path(__file__)),HELPER:sha(HELPER),review:sha(review)})
 for p,h in watch.items():assert sha(p)==h,('Changed source',p)
 frame=pd.read_parquet(source/'all_caps_analysis_features.parquet');assert not frame.duplicated(['candidate_cap','unit_id']).any();protocol=json.loads(path('analysis/cycle07_tools/PROTOCOL_v1.json').read_text());outputs={k:[]for k in ['metrics','coefficients','predictions','spatial','samples','folds','gates','bootstrap']}
 for n,o,t,p,s in scenarios(protocol):
  print('Running',n,flush=True)
  for k,v in estimate(frame,n,o,t,protocol,p,s).items():outputs[k].extend(v)
 names={'metrics':'model_metrics.csv','coefficients':'coefficient_intervals.csv','predictions':'unit_predictions.parquet','spatial':'spatial_residual_diagnostics.csv','samples':'common_sample_membership.parquet','folds':'grouped_cv_folds.csv','gates':'sample_gates.csv','bootstrap':'region_bootstrap_intervals.csv'}
 for k,v in outputs.items():
  d=pd.DataFrame(v);f=out/names[k];d.to_parquet(f,index=False)if f.suffix=='.parquet'else d.to_csv(f,index=False)
 for p,h in watch.items():assert sha(p)==h,('Source changed during estimation',p)
 dump(out/'run_receipt.json',{'status':'ACTUAL_ANALYSIS_COMPUTED_PENDING_INDEPENDENT_NUMERICAL_REVIEW','source_family':reg['source_family'],'source_receipt_sha256':reg['source_receipt_sha256'],'preregistration_sha256':sha(out/'preregistration.json'),'review_sha256':sha(review),'source_inputs_unchanged':True,'n_fits':len(outputs['metrics']),'n_gates':len(outputs['gates']),'n_bootstrap_intervals':len(outputs['bootstrap']),'outputs_sha256':{p.name:sha(p)for p in out.iterdir()if p.is_file()}})
if __name__=='__main__':main()
