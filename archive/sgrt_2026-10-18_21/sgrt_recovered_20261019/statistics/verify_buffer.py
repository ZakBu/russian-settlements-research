from pathlib import Path
import json,numpy as np,pandas as pd
from scipy.spatial import cKDTree
from independent_core import haversine
O=Path(__file__).resolve().parent;a=pd.read_csv(O/'functional_spatial_OOF_predictions.csv.gz');a=a[a.block_km.eq(400)];b=pd.read_csv(O/'buffer50_spatial_OOF_predictions.csv.gz');r=json.loads((O/'buffer50_validation.json').read_text());f=pd.read_parquet(O/'buffer50_same_cohort.parquet');checks=[]
def ck(n,x,details=None):checks.append({'test':n,'passed':bool(x),'details':details});assert x,(n,details)
key=['center_id','outcome','model'];j=a.merge(b,on=key,validate='one_to_one',suffixes=('_main','_gap'));ck('same_all_test_ids_outcomes_models',len(j)==len(a)==len(b));ck('same_test_folds_blocks_and_outcomes',j.fold_main.eq(j.fold_gap).all() and j.block_id_main.eq(j.block_id_gap).all() and np.array_equal(j.y_main,j.y_gap));core=pd.read_parquet(O/'functional_same_cohort.parquet');ck('same_cohort_4262',f.center_id.is_unique and set(f.center_id)==set(core.center_id) and len(f)==4262)
for outcome in ['outcome_total','outcome_environment']:
 g=f.copy() if outcome=='outcome_total' else f[f.noncenter_members>0].copy();pred=b[b.outcome.eq(outcome)&b.model.eq('M1')].set_index('center_id');g['fold']=g.center_id.map(pred.fold);rows=[q for q in r['results'] if q.get('model')=='M1' and q['outcome']==outcome][0]
 for info in rows['folds']:
  fold=info['fold'];te=g[g.fold.eq(fold)];tr=g[~g.fold.eq(fold)];phi=np.radians(te.lat.to_numpy());lam=np.radians(te.lon.to_numpy());tc=np.c_[np.cos(phi)*np.cos(lam),np.cos(phi)*np.sin(lam),np.sin(phi)];phi=np.radians(tr.lat.to_numpy());lam=np.radians(tr.lon.to_numpy());ac=np.c_[np.cos(phi)*np.cos(lam),np.cos(phi)*np.sin(lam),np.sin(phi)];dist=cKDTree(tc).query(ac)[0];keep=tr[dist>2*np.sin(50/(2*6371.0088))];ck(f'train_counts_{outcome}_{fold}',len(keep)==info['train_n'] and len(tr)-len(keep)==info['excluded_train_within50km'] and len(te)==info['test_n']);mindistance=min(float(haversine(te.lat.to_numpy(),te.lon.to_numpy(),row.lat,row.lon).min()) for row in keep.itertuples());ck(f'independent_haversine_gap_{outcome}_{fold}',mindistance>=50-1e-7,{'minimum_train_test_distance_km':mindistance})
(O/'buffer50_audit.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'failed':0},indent=2));print(json.dumps({'passed':len(checks),'failed':0}))
