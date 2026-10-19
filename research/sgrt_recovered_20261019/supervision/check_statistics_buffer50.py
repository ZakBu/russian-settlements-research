"""Supervisor replay of ridge OOF predictions and paired spatial bootstrap.
Does not import statistics author code. Conditions on its frozen feature cohort.
"""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
O=Path(__file__).resolve().parent;R=O.parent;S=R/'statistics';j=json.loads((S/'buffer50_validation.json').read_text());f=pd.read_parquet(S/'buffer50_same_cohort.parquet').set_index('center_id');p=pd.read_csv(S/'buffer50_spatial_OOF_predictions.csv.gz');checks=[]
def ck(n,v,**kw):
 checks.append(dict(test=n,passed=bool(v),**kw))
 if not v:raise AssertionError(checks[-1])
for x in json.loads((S/'buffer50_provenance.json').read_text()):ck('input_hash_'+x['path'],hashlib.sha256((R/x['path']).read_bytes()).hexdigest()==x['sha256'])
ck('OOF_keys_unique',not p.duplicated(['center_id','outcome','block_km','model']).any());ck('same_cohort_4262',len(f)==4262 and f.index.is_unique);ck('all_outcomes_finite',np.isfinite(p.y).all())
ordinary=pd.read_parquet(R/'model/centers.parquet');ids=set(ordinary[~ordinary.external_anchor].id);ck('cohort_only_real_ordinary_zones',set(f.index)<=ids)
# Verify three models use identical rows, target values, blocks and folds for every experiment.
for (outcome,size),g in p.groupby(['outcome','block_km']):
 counts=g.groupby('center_id').model.nunique();ck(f'same_rows_all3_{outcome}_{size}',counts.eq(3).all());ck(f'identical_y_block_fold_{outcome}_{size}',g.groupby('center_id')[['y','block_id','fold']].nunique().eq(1).all().all());ck(f'blocks_never_split_across_folds_{outcome}_{size}',g.groupby('block_id').fold.nunique().eq(1).all())
ck('zero_demographic_values_not_dropped',f.population_2010.ge(0).all() and f.outcome_total.notna().all())
# Refit every declared split with train-only imputation/scaling, using solve rather than pinv.
max_predict_error=0.;metric_errors=[]
for row in [r for r in j['results'] if 'model' in r]:
 g=p[p.outcome.eq(row['outcome'])&p.block_km.eq(row['block_km'])&p.model.eq(row['model'])].copy();z=f.loc[g.center_id];x=z[row['features']].to_numpy(float);y=g.y.to_numpy();pred=np.empty(len(g));fold=g.fold.to_numpy()
 for k in range(5):
  train=fold!=k;test=~train
  # Independently apply the spherical50km buffer using haversine matrices.
  phi=np.radians(z.lat.to_numpy());lam=np.radians(z.lon.to_numpy());p2=phi[test];l2=lam[test];keep=np.ones(len(z),bool)
  for start in range(0,len(z),500):
   stop=min(start+500,len(z));p1=phi[start:stop,None];l1=lam[start:stop,None];q=np.sin((p1-p2)/2)**2+np.cos(p1)*np.cos(p2)*np.sin((l1-l2)/2)**2;minimum=2*6371.0088*np.arcsin(np.sqrt(np.clip(q,0,1))).min(axis=1);keep[start:stop]=minimum>50
  train &= keep;expected=next(v for v in row['folds'] if v['fold']==k);ck(f'buffer_train_set_{row["outcome"]}_{row["model"]}_{k}',int(train.sum())==expected['train_n'],train_n=int(train.sum()))
  xx=x[train].copy();xt=x[test].copy();med=[]
  for col in range(x.shape[1]):
   known=xx[:,col][np.isfinite(xx[:,col])];m=float(np.median(known)) if len(known) else 0;xx[~np.isfinite(xx[:,col]),col]=m;xt[~np.isfinite(xt[:,col]),col]=m
  mean=xx.mean(axis=0);scale=xx.std(axis=0);scale[scale==0]=1;xx=np.column_stack([np.ones(train.sum()),(xx-mean)/scale]);xt=np.column_stack([np.ones(test.sum()),(xt-mean)/scale]);penalty=np.eye(xx.shape[1]);penalty[0,0]=0;coef=np.linalg.solve(xx.T@xx+penalty,xx.T@y[train]);pred[test]=xt@coef
 error=float(abs(pred-g.prediction.to_numpy()).max());max_predict_error=max(max_predict_error,error);ck(f'ridge_replay_{row["outcome"]}_{row["block_km"]}_{row["model"]}',error<1e-7,max_prediction_error=error)
 rmse=np.sqrt(np.mean((g.prediction.to_numpy()-y)**2));ck(f'RMSE_{row["outcome"]}_{row["block_km"]}_{row["model"]}',abs(rmse-row['RMSE_OOF'])<1e-12)
# Same declared random generator/order, recompute block resampling from saved OOF errors.
rng=np.random.default_rng(20261019);comparisons=[]
for outcome in ['outcome_total','outcome_environment']:
 for size in [400]:
  z=p[p.outcome.eq(outcome)&p.block_km.eq(size)];wide=z.pivot(index='center_id',columns='model',values='prediction');v=z.drop_duplicates('center_id').set_index('center_id').reindex(wide.index)
  for before,after in [('M1','M2'),('M2','M3'),('M1','M3')]:
   diff=(wide[after]-v.y)**2-(wide[before]-v.y)**2;loss=diff.to_frame('difference').join(v.block_id).groupby('block_id').difference.agg(['sum','size']);original=next(r for r in j['results'] if r.get('outcome')==outcome and r.get('block_km')==size and r.get('comparison')==after+' minus '+before);n=original['bootstrap_repetitions'];sample=rng.integers(0,len(loss),size=(n,len(loss)));boots=loss['sum'].to_numpy()[sample].sum(axis=1)/loss['size'].to_numpy()[sample].sum(axis=1);lo,hi=np.quantile(boots,[.025,.975]);point=float(loss['sum'].sum()/loss['size'].sum());err=max(abs(lo-original['CI025']),abs(hi-original['CI975']),abs(point-original['delta_MSE']));ck(f'paired_block_bootstrap_{outcome}_{size}_{after}-{before}',err<1e-10,max_error=float(err));comparisons.append(dict(outcome=outcome,block_km=size,comparison=after+' minus '+before,delta_MSE=point,CI025=float(lo),CI975=float(hi)))
summary=dict(status='PASS',passed=len(checks),failed=0,max_independent_ridge_prediction_error=max_predict_error,checks=checks,independently_recomputed_comparisons=comparisons,interpretation='Conditional retrospective associations only. Spherical50km gap independently reconstructed from haversine matrices; same test folds retained. Conditional retrospective association only.');tmp=O/'statistics_buffer50_checks.json.tmp';tmp.write_text(json.dumps(summary,ensure_ascii=False,indent=2));json.loads(tmp.read_text());tmp.replace(O/'statistics_buffer50_checks.json');print(json.dumps(summary,ensure_ascii=False,indent=2))
