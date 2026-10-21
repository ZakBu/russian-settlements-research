"""Independent numerical replay; no producer imports; expanded-region bootstrap."""
from pathlib import Path
import json,hashlib,datetime
import numpy as np,pandas as pd
from scipy.stats import t
H=Path(__file__).resolve().parent;B=H.parents[1];O=B/'analysis/cycle07_newsource030045090_baseline_v1';checks=[];rows=[];br=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ck(k,v):
 checks.append({'check':k,'pass':bool(v)})
 if not v:print('FAIL',k,flush=True)
def close(a,b):return np.allclose(np.asarray(a,float),np.asarray(b,float),atol=1e-7,rtol=1e-8,equal_nan=True)
def design(x):
 mu=x.mean(0);sd=x.std(0);sd=np.where(sd>1e-12,sd,1);return np.column_stack((np.ones(len(x)),(x-mu)/sd)),mu,sd
pre=json.loads((O/'preregistration.json').read_text());receipt=json.loads((O/'run_receipt.json').read_text());P=json.loads((B/'analysis/cycle07_tools/PROTOCOL_v2.json').read_text());source=Path(pre['source_receipt']);F=pd.read_parquet(source.parent/'all_caps_analysis_features.parquet');watch={O/k:v for k,v in receipt['outputs_sha256'].items()};watch.update({Path(k):v for k,v in pre['all_source_inputs_sha256'].items()});watch[source]=pre['source_receipt_sha256'];watch.update({source.parent/k:v for k,v in pre['source_outputs_sha256'].items()})
for p,h in watch.items():ck('initial_sha:'+str(p),sha(p)==h)
M=pd.read_csv(O/'model_metrics.csv');C=pd.read_csv(O/'coefficient_intervals.csv');R=pd.read_parquet(O/'unit_predictions.parquet');G=pd.read_csv(O/'sample_gates.csv');S=pd.read_parquet(O/'common_sample_membership.parquet');T=pd.read_csv(O/'grouped_cv_folds.csv');BB=pd.read_csv(O/'region_bootstrap_intervals.csv')
for spec in pre['scenarios']:
 name=spec['name'];outcome=spec['outcome'];terms=spec['terms'];required=list(dict.fromkeys(c for v in terms.values()for c in v))
 for cap,d in F.groupby('candidate_cap'):
  mask=np.isfinite(d[required+[outcome,'lat','lon']].to_numpy(float)).all(1)&d.region.notna()&d.system_population_complete_2010.eq(True)
  if spec['pure_primary']:mask &= d.analysis_system2010_primary_source_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  if spec['supported_primary']:mask &= d.analysis_system2010_primary_supported_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  e=d.loc[mask].sort_values('unit_id');n=len(e);ng=e.region.nunique();gate=G[G.scenario.eq(name)&G.candidate_cap.eq(cap)].iloc[0];passed=n>=max(P['minimum_sample'],P['minimum_sample_per_union_predictor']*(len(required)+1))and ng>=P['minimum_regions'];ck(f'gate:{name}:{cap}',gate.common_sample==n and gate.regions==ng and (gate.status=='COMPUTED')==passed)
  ss=S[S.scenario.eq(name)&S.candidate_cap.eq(cap)].set_index('unit_id');ck(f'membership:{name}:{cap}',np.array_equal(d.unit_id.map(ss.in_common_sample),mask));mm=M[M.scenario.eq(name)&M.candidate_cap.eq(cap)];ck(f'model_count:{name}:{cap}',len(mm)==(len(terms)if passed else 0))
  if not passed:continue
  y=e[outcome].to_numpy(float);groups=e.region.astype(str).to_numpy();regions,codes,counts=np.unique(groups,return_inverse=True,return_counts=True);load=np.zeros(P['cv_folds'],int);assigned=np.zeros(ng,int)
  for j in np.argsort(counts)[::-1]:f=np.argmin(load);assigned[j]=f;load[f]+=counts[j]
  folds=assigned[codes];seed=P['seed']+int(hashlib.sha256(f'{name}|{outcome}|{int(cap)}'.encode()).hexdigest()[:8],16);draws=np.random.default_rng(seed).multinomial(ng,np.full(ng,1/ng),size=P['cluster_bootstrap_replicates'])
  for model,cols in terms.items():
   keep=[];constant=[];collinear=[];D=np.ones((n,1))
   for col in cols:
    z=e[col].to_numpy(float)
    if z.std()<=1e-12:constant.append(col);continue
    trial=np.column_stack((D,(z-z.mean())/z.std()))
    if np.linalg.matrix_rank(trial)>D.shape[1]:keep.append(col);D=trial
    else:collinear.append(col)
   x=e[keep].to_numpy(float);D,mu,sd=design(x);beta=np.linalg.lstsq(D,y,rcond=None)[0];res=y-D@beta;bread=np.linalg.inv(D.T@D);scores=np.array([D[groups==g].T@res[groups==g]for g in regions]);cov=bread@scores.T@scores@bread*(ng/(ng-1))*((n-1)/(n-D.shape[1]));se=np.sqrt(np.maximum(np.diag(cov),0));ci=t.ppf(.975,ng-1)*se;hat=np.sum((D@bread)*D,1);sigma=res@res/(n-D.shape[1]);cooks=res**2/(D.shape[1]*sigma)*hat/(1-hat)**2;pred=np.empty(n);null=np.empty(n);bad=0
   tt=T[T.scenario.eq(name)&T.candidate_cap.eq(cap)&T.model.eq(model)].set_index('fold')
   for fold in range(P['cv_folds']):
    tr=folds!=fold;te=~tr;dx,m,s=design(x[tr]);vx=np.column_stack((np.ones(te.sum()),(x[te]-m)/s));pred[te]=vx@np.linalg.lstsq(dx,y[tr],rcond=None)[0];null[te]=y[tr].mean();rank=np.linalg.matrix_rank(dx);bad+=rank<dx.shape[1];rr=tt.loc[fold];ck(f'fold:{name}:{model}:{fold}',rr.n_train==tr.sum()and rr.n_test==te.sum()and rr.train_regions==len(np.unique(groups[tr]))and rr.test_regions==len(np.unique(groups[te]))and rr.train_design_rank==rank and close(rr.rmse,np.sqrt(np.mean((y[te]-pred[te])**2)))and close(rr.mae,np.mean(abs(y[te]-pred[te]))))
   cp=C[C.scenario.eq(name)&C.candidate_cap.eq(cap)&C.model.eq(model)].set_index('term').loc[['intercept']+keep];pr=R[R.scenario.eq(name)&R.candidate_cap.eq(cap)&R.model.eq(model)].set_index('unit_id').loc[e.unit_id];row=mm[mm.model.eq(model)].iloc[0];ck(f'OLS_CR1:{name}:{model}',close(beta,cp.beta)and close(se,cp.se_cluster_region)and close(beta-ci,cp.ci95_lower)and close(beta+ci,cp.ci95_upper)and close(mu,cp.predictor_mean.iloc[1:])and close(sd,cp.predictor_sd.iloc[1:]));ck(f'all_predictions:{name}:{model}',close(D@beta,pr.fitted)and close(res,pr.residual)and close(pred,pr.group_oof_prediction)and close(y-pred,pr.group_oof_residual)and close(hat,pr.leverage)and close(cooks,pr.cooks_distance)and np.array_equal(folds,pr.cv_fold))
   r2=1-res@res/np.sum((y-y.mean())**2);vals={'r2':r2,'adjusted_r2':1-(1-r2)*(n-1)/(n-D.shape[1]),'condition_number':np.linalg.cond(D),'group_oof_rmse':np.sqrt(np.mean((y-pred)**2)),'group_oof_mae':np.mean(abs(y-pred)),'group_oof_r2_train_mean_baseline':1-np.sum((y-pred)**2)/np.sum((y-null)**2),'max_cooks_distance':max(cooks)};ck(f'metrics:{name}:{model}',all(close(v,row[k])for k,v in vals.items())and row.n==n and row.regions==ng and row.parameters==D.shape[1]and row.cv_training_rank_deficient_folds==bad)
   samples=[]
   for draw in draws:
    ix=np.repeat(np.arange(n),draw[codes]);dd=D[ix]
    if np.linalg.matrix_rank(dd)==dd.shape[1]:samples.append(np.linalg.lstsq(dd,y[ix],rcond=None)[0])
   bb=np.quantile(samples,[.025,.975],axis=0);reported=BB[BB.scenario.eq(name)&BB.candidate_cap.eq(cap)&BB.model.eq(model)].set_index('term').loc[['intercept']+keep];ck(f'499_expanded_regions:{name}:{model}',np.all(reported.full_rank_replicates.eq(len(samples)))and close(bb[0],reported.ci95_lower)and close(bb[1],reported.ci95_upper)and np.all(reported.paired_region_draw_seed.eq(seed)))
   for j,term in enumerate(['intercept']+keep):br.append({'scenario':name,'cap':int(cap),'model':model,'term':term,'full_rank_draws':len(samples),'low':bb[0,j],'high':bb[1,j]})
   rows.append({'scenario':name,'cap':int(cap),'model':model,'n':n,'regions':ng,**vals});print('REPLAYED',name,model,flush=True)
ck('all60fits444intervals',len(rows)==60 and len(br)==444)
for p,h in watch.items():ck('final_sha:'+str(p),sha(p)==h)
pd.DataFrame(rows).to_csv(H/'all20_independent_metrics.csv',index=False);pd.DataFrame(br).to_csv(H/'all148_independent_bootstrap_intervals.csv',index=False);result={'status':'ACCEPTED_INDEPENDENT_ACTUAL_NUMERICAL_REPLAY'if all(c['pass']for c in checks)else'REJECT_NUMERICAL_REPLAY','all_checks_passed':all(c['pass']for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass']for c in checks),'accepted_analysis_receipt_sha256':sha(O/'run_receipt.json'),'audit_code_sha256':sha(Path(__file__)),'scope':'All60 fits OLS/regionCR1/groupCV point predictions/folds and444 intervals independently expanded region499draws. Source aggregates separately accepted191, spatial separately reviewed. No causal or cross-family cohort claim.','checks':checks};(H/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(result['status'],len(checks),result['n_failed'])
