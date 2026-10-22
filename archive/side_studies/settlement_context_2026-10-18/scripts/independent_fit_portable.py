#!/usr/bin/env python3
"""Independent implementation of locked E1 fit, no imported project modules.
Execute only after coordinator freeze. Reads labels solely for dev positive2010 UID.
"""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import csv,gzip,hashlib,json,math,sys
from pathlib import Path
import numpy as np,pandas as pd
from pyproj import Transformer
from sklearn.neighbors import BallTree
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--features',type=Path,required=True);ap.add_argument('--lock',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
lockpath=a.lock;lock=json.loads(lockpath.read_text())
assert lock['status']=='locked_for_remaining_retrospective_evaluation'
fpath=a.features;raw=a.repo/'publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
assert hashlib.sha256(fpath.read_bytes()).hexdigest()==lock['features_sha256'];assert hashlib.sha256(raw.read_bytes()).hexdigest()==lock['input_sha256']
f=pd.read_csv(fpath);p=f.population_2010.to_numpy(float);p0=f.population_2002.to_numpy(float)
xx,yy=Transformer.from_crs(4326,6933,always_xy=True).transform(f.longitude_2010.to_numpy(),f.latitude_2010.to_numpy())
blocks=np.array([str(math.floor(x/200000))+':'+str(math.floor(y/200000)) for x,y in zip(xx,yy)])
hold=np.array([int(hashlib.sha256(('settlement-context-v1|'+b).encode()).hexdigest(),16)%5==0 for b in blocks]);test=hold&(p>0);train=(~hold)&(p>0)
xy=np.radians(np.array([f.latitude_2010.to_numpy(),f.longitude_2010.to_numpy()]).T)
trids=np.flatnonzero(train);d=BallTree(xy[test],metric='haversine').query(xy[train],k=1)[0][:,0]*6371.0088;train[trids[d<60]]=False
wanted=set(f.loc[train,'entity_uid']);observed={}
with gzip.open(raw,'rt',newline='') as s:
 for r in csv.DictReader(s):
  if r['entity_uid'] in wanted:observed[r['entity_uid']]=float(r['population_2021'])
y=np.array([observed[u]==0 for u in f.loc[train,'entity_uid']],float)
x=pd.DataFrame({'log_population2010':np.log1p(p),'own_history':np.divide(2*(p-p0),p+p0,out=np.full(len(f),np.nan),where=p+p0>0),'own_history_missing':~np.isfinite(p0),'lat':f.latitude_2010,'lon':f.longitude_2010,'sin_lon':np.sin(np.radians(f.longitude_2010)),'cos_lon':np.cos(np.radians(f.longitude_2010))})
for r in [10,30,60,100]:
 x['log_mass'+str(r)]=np.log1p(f['r'+str(r)+'_mass2010']);x['log_count'+str(r)]=np.log1p(f['r'+str(r)+'_count_all']);x['empty'+str(r)]=f['r'+str(r)+'_empty']
for key in ['nearest_ge10000_km','nearest_ge100000_km','distance_RU-FED-MOW_km','distance_RU-FED-SPB_km']:x['log_'+key]=np.log1p(f[key])
base=list(x.columns);x['history']=f.r30_history_symmetric_change;x['zero_fraction']=f.r30_history_zero_fraction;x['log_pair_count']=np.log1p(f.r30_history_pair_count);x['coverage']=np.divide(f.r30_history_pair_count,f.r30_count_all,out=np.full(len(f),np.nan),where=f.r30_count_all>0);addon=['history','zero_fraction','log_pair_count','coverage']
x=x.replace([np.inf,-np.inf],np.nan);preds=pd.DataFrame({'entity_uid':f.loc[test,'entity_uid']})
params=dict(learning_rate=.08,max_iter=150,max_leaf_nodes=15,min_samples_leaf=100,l2_regularization=1,early_stopping=False,random_state=20261018,loss='log_loss')
for name,cols in [('baseline',base),('augmented',base+addon)]:
 with threadpool_limits(limits=2):
  m=HistGradientBoostingClassifier(**params);m.fit(x.loc[train,cols],y);preds[name]=m.predict_proba(x.loc[test,cols])[:,1]
out=a.output;out.mkdir(parents=True,exist_ok=True)
preds.to_csv(out/'e1_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
(out/'receipt.json').write_text(json.dumps({'status':'computed','method':'Separate source implementation; same locked sklearn learner/library, not independent algorithm/data','lock_sha256':hashlib.sha256(lockpath.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'train_n':int(train.sum()),'test_n':int(test.sum()),'baseline_columns':base,'additional_columns':addon,'holdout_labels_read':0,'prediction_sha256':hashlib.sha256((out/'e1_predictions.csv.gz').read_bytes()).hexdigest(),'params':params},indent=2)+'\n');print('Independent E1 fit done',int(train.sum()),int(test.sum()))
