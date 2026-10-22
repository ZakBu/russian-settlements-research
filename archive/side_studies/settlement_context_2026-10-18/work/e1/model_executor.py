"""Fixed development-only spatial CV. Never stores or numerically parses holdout outcomes.
Raw CSV is streamed; non-development UID outcome strings are discarded immediately.
Coordinator may import helpers for a separate locked final runner; this CLI has no holdout mode.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import argparse,csv,gzip,hashlib,json,platform,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier,HistGradientBoostingRegressor
from sklearn.metrics import average_precision_score,log_loss
from sklearn.neighbors import BallTree
from threadpoolctl import threadpool_limits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'statistics'))
from statistical_utils import split_blocks,buffered_train_mask,paired_block_bootstrap
SEED=20261018
PARAMS=dict(learning_rate=.08,max_iter=150,max_leaf_nodes=15,min_samples_leaf=100,l2_regularization=1,early_stopping=False,random_state=SEED)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def features(f):
 p=f.population_2010.to_numpy(float);p0=f.population_2002.to_numpy(float);den=p+p0
 x=pd.DataFrame(index=f.index)
 x['log_population2010']=np.log1p(p);x['own_history']=np.divide(2*(p-p0),den,out=np.full(len(f),np.nan),where=den>0);x['own_history_missing']=~np.isfinite(p0)
 x['lat']=f.latitude_2010;x['lon']=f.longitude_2010;x['sin_lon']=np.sin(np.deg2rad(x.lon));x['cos_lon']=np.cos(np.deg2rad(x.lon))
 for r in (10,30,60,100):
  x[f'log_mass{r}']=np.log1p(f[f'r{r}_mass2010']);x[f'log_count{r}']=np.log1p(f[f'r{r}_count_all']);x[f'empty{r}']=f[f'r{r}_empty']
 for name in ['nearest_ge10000_km','nearest_ge100000_km','distance_RU-FED-MOW_km','distance_RU-FED-SPB_km']:x['log_'+name]=np.log1p(f[name])
 baseline=list(x.columns)
 x['e1_history30']=f.r30_history_symmetric_change;x['e1_zero_fraction30']=f.r30_history_zero_fraction
 x['e1_log_pair_count30']=np.log1p(f.r30_history_pair_count);x['e1_coverage30']=np.divide(f.r30_history_pair_count,f.r30_count_all,out=np.full(len(f),np.nan),where=f.r30_count_all>0)
 return x,tuple(baseline),tuple(c for c in x if c.startswith('e1_'))
def read_dev_outcomes(path,wanted):
 values={}
 with gzip.open(path,'rt',newline='',encoding='utf-8') as h:
  for row in csv.DictReader(h):
   uid=row['entity_uid']
   if uid in wanted:values[uid]=row['population_2021']
 return pd.to_numeric(pd.Series(values),errors='coerce')
def losses(y,p,task):return (y-p)**2 if task=='zero' else abs(y-p)
def build_model(task,params=None):return (HistGradientBoostingClassifier if task=='zero' else HistGradientBoostingRegressor)(**(params or PARAMS),loss='log_loss' if task=='zero' else 'absolute_error')
def predict(m,x,task):return m.predict_proba(x)[:,1] if task=='zero' else m.predict(x)
def score(y,p,task):
 out={('brier' if task=='zero' else 'mae'):float(losses(y,p,task).mean())}
 if task=='zero':out.update(log_loss=float(log_loss(y,np.clip(p,1e-6,1-1e-6),labels=[0,1])),average_precision=float(average_precision_score(y,p)) if len(set(y))>1 else None)
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--features',default='research_staging/geo/features.csv.gz');ap.add_argument('--raw',default='repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz');ap.add_argument('--output',default='research_staging/e1/development');ap.add_argument('--direction',choices=['E1','E2','E3'],default='E1');ap.add_argument('--task',choices=['zero','change'],default='zero');ap.add_argument('--variant',choices=['history','rawmass','permuted'],default='history');ap.add_argument('--radius',type=int,choices=[10,30,60],default=30);ap.add_argument('--nn-baseline',action='store_true');ap.add_argument('--morphology',default='research_staging/e3/block_morphology2010.csv');ap.add_argument('--smoke',action='store_true');a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);start=time.time()
 f=pd.read_csv(a.features);assert f.entity_uid.is_unique
 block,hold,fold=split_blocks(f.longitude_2010,f.latitude_2010);x,base,addon=features(f)
 if a.direction=='E1':
  addon=('e1_history','e1_zero_fraction','e1_log_pair_count','e1_coverage')
  r=a.radius;x[addon[0]]=f[f'r{r}_history_symmetric_change'];x[addon[1]]=f[f'r{r}_history_zero_fraction'];x[addon[2]]=np.log1p(f[f'r{r}_history_pair_count']);x[addon[3]]=np.divide(f[f'r{r}_history_pair_count'],f[f'r{r}_count_all'],out=np.full(len(f),np.nan),where=f[f'r{r}_count_all']>0)
  if a.variant=='rawmass':
   addon=('e1_log_mass2002','e1_log_mass2010');x[addon[0]]=np.log1p(f[f'r{r}_history_mass2002']);x[addon[1]]=np.log1p(f[f'r{r}_history_mass2010'])
 if a.direction=='E2':
  addon=['e2_maxshare30','e2_logeffective_n30','e2_loglarger_distance','e2_larger_ratio','e2_degenerate30','e2_no_larger']
  x[addon[0]]=f.r30_maxshare;x[addon[1]]=np.log1p(f.r30_effective_n);x[addon[2]]=np.log1p(f.nearest_larger_km);x[addon[3]]=np.log1p(f.nearest_larger_size_ratio);x[addon[4]]=(f.r30_count_positive<=1)|(f.r30_mass2010<=0);x[addon[5]]=~np.isfinite(f.nearest_larger_km)
 if a.nn_baseline:
  x['nn_control_shape']=f.nn5_normalized;x['nn_control_logdistance']=np.log1p(f.nn1_km);base=tuple(base)+('nn_control_shape','nn_control_logdistance')
 if a.direction=='E3':
  mm=pd.read_csv(a.morphology).set_index('block_id');assert mm.index.is_unique
  addon=('morph_median_nn5_2010','morph_isolated10_2010','morph_lcc10_2010','morph_insufficient');mapped=mm.reindex(block).reset_index(drop=True)
  for c in addon:x[c]=mapped[c].to_numpy()
 assert all('2021' not in c for c in x.columns)
 mask_table=pd.DataFrame({'entity_uid':f.entity_uid,'block_id':block,'holdout':hold,'fold':fold});mask_table.to_csv(out/'split_manifest.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 (out/'pre_outcome_lock.json').write_text(json.dumps({'input_sha256':sha(a.raw),'features_sha256':sha(a.features),'split_sha256':sha(out/'split_manifest.csv.gz'),'code_sha256':sha(__file__),'baseline_columns':list(base),'additional_columns':list(addon),'created_unix':time.time(),'status':'development_reconnaissance_lock'},indent=2))
 dev=~hold;raw_y=read_dev_outcomes(a.raw,set(f.loc[dev,'entity_uid']));p21=f.entity_uid.map(raw_y).to_numpy(float)
 # Holdout target remains NaN by construction. Eligibility must be evaluated only on dev.
 assert np.isnan(p21[hold]).all()
 eligible=dev&(f.population_2010.to_numpy()>0)&np.isfinite(p21)&(p21>=0)
 ids=np.flatnonzero(eligible);p=f.population_2010.to_numpy(float);y=np.full(len(f),np.nan)
 y[ids]=(p21[ids]==0).astype(float) if a.task=='zero' else 2*(p21[ids]-p[ids])/(p21[ids]+p[ids])
 pred=pd.DataFrame({'entity_uid':f.loc[eligible,'entity_uid'],'block_id':block[eligible],'fold':fold[eligible],'observed':y[eligible],'baseline':np.nan,'augmented':np.nan})
 runs=[];folds=range(1) if a.smoke else range(5)
 for k in folds:
  test=eligible&(fold==k);train0=eligible&(fold!=k);train=buffered_train_mask(f.latitude_2010,f.longitude_2010,train0,test,60)
  if a.smoke:
   # Runtime diagnostic only; systematic subset cannot be treated as estimate.
   ix=np.flatnonzero(train);train[ix[10000:]]=False
  nearest=BallTree(np.deg2rad(f.loc[test,['latitude_2010','longitude_2010']]),metric='haversine').query(np.deg2rad(f.loc[train,['latitude_2010','longitude_2010']]),k=1)[0][:,0]*6371.0088
  assert nearest.min()>=59.999
  run={'fold':k,'train_before_buffer':int(train0.sum()),'train_after_buffer':int(train.sum()),'test_n':int(test.sum()),'train_blocks':len(set(block[train])),'test_blocks':len(set(block[test])),'nearest_train_test_km':float(nearest.min())}
  for label,cols in [('baseline',base),('augmented',tuple(base)+tuple(addon))]:
   t=time.time();xx=x
   if label=='augmented' and a.variant=='permuted':
    xx=x.copy();rng=np.random.default_rng(SEED+1+k)
    for mask in [train,test]:
     for bb in np.unique(block[mask]):
      ix=np.flatnonzero(mask&(block==bb));xx.loc[ix,list(addon)]=x.loc[rng.permutation(ix),list(addon)].to_numpy()
   with threadpool_limits(limits=2):m=build_model(a.task);m.fit(xx.loc[train,list(cols)],y[train]);pr=predict(m,xx.loc[test,list(cols)],a.task)
   pred.loc[pred.fold==k,label]=pr;run[label]=score(y[test],pr,a.task);run[label]['seconds']=time.time()-t
  runs.append(run);print(json.dumps(run),flush=True)
 pred=pred.dropna(subset=['baseline','augmented']);pred['baseline_loss']=losses(pred.observed,pred.baseline,a.task);pred['augmented_loss']=losses(pred.observed,pred.augmented,a.task);pred.to_parquet(out/'predictions.parquet',index=False)
 summary={'status':'smoke' if a.smoke else 'development_only','direction':a.direction,'variant':a.variant,'radius':a.radius,'task':a.task,'rows_master':len(f),'development_n':int(dev.sum()),'eligible_development_n':int(eligible.sum()),'development_zero2010_n':int((dev&(p==0)).sum()),'holdout_outcomes_parsed':0,'baseline_columns':base,'additional_columns':addon,'params':PARAMS,'seed':SEED,'input_sha256':sha(a.raw),'features_sha256':sha(a.features),'code_sha256':sha(__file__),'split_sha256':sha(out/'split_manifest.csv.gz'),'cv_folds':runs,'paired_interval':paired_block_bootstrap(pred.block_id,pred.baseline_loss,pred.augmented_loss),'baseline':score(pred.observed,pred.baseline,a.task),'augmented':score(pred.observed,pred.augmented,a.task),'seconds':time.time()-start,'python':platform.python_version(),'packages':{mod:__import__(mod).__version__ for mod in ['numpy','pandas','sklearn','pyproj','pyarrow']},'limitations':['Development spatial CV is reconnaissance, not final holdout evidence.','Conditional-on-fit bootstrap ignores retraining and residual dependence beyond blocks.','Stage71 ordinary-neighborhood context excludes federal territorial mass; capital distances included.','No causal interpretation; geometric proximity is not transport.']}
 (out/'result.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));print(json.dumps({k:summary[k] for k in ['status','direction','task','baseline','augmented','paired_interval','seconds']}),flush=True)
if __name__=='__main__':main()
