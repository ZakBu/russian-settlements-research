import pyarrow.parquet as pq,pandas as pd,numpy as np,json,hashlib,math
from pathlib import Path
from pyproj import Transformer
from sklearn.neighbors import BallTree
root=Path(__file__).resolve().parents[2];f=pd.read_csv(root/'research_staging/geo/features.csv.gz',usecols=['entity_uid','population_2010','latitude_2010','longitude_2010'])
x,y=Transformer.from_crs(4326,6933,always_xy=True).transform(f.longitude_2010.to_numpy(),f.latitude_2010.to_numpy());blocks=[f'{math.floor(a/200000)}:{math.floor(b/200000)}' for a,b in zip(x,y)];hold=np.array([int(hashlib.sha256(('settlement-context-v1|'+b).encode()).hexdigest(),16)%5==0 for b in blocks]);fold=np.array([int(hashlib.sha256(('settlement-context-fold-v1|'+b).encode()).hexdigest(),16)%5 for b in blocks]);risk=f.population_2010.to_numpy()>0;xy=np.radians(np.array([f.latitude_2010.to_numpy(),f.longitude_2010.to_numpy()]).T);blocks=np.array(blocks);reports=[];errors=[]
source=json.loads((root/'research_staging/e1/development/result.json').read_text())
for k in range(5):
 test=(~hold)&risk&(fold==k);train=(~hold)&risk&(fold!=k);idx=np.flatnonzero(train);dd=BallTree(xy[test],metric='haversine').query(xy[train],k=1)[0][:,0]*6371.0088;train[idx[dd<60]]=False;mini=float(dd[dd>=60].min());r={'fold':k,'train_before_buffer':len(idx),'train_after_buffer':int(train.sum()),'test_n':int(test.sum()),'train_blocks':len(set(blocks[train])),'test_blocks':len(set(blocks[test])),'nearest_train_test_km':mini,'overlap':int((train&test).sum())};reports.append(r)
 expected=source['cv_folds'][k]
 for key,val in r.items():
  if key=='overlap':assert val==0;continue
  if abs(val-expected[key])>1e-9:errors.append([k,key,val,expected[key]])
report={'status':'reviewed' if not errors else 'needs_revision','method':'Independent direct SHA/projection/mask code; sklearnBallTree distances already independently validated on200bruteforcequeries','rows':len(f),'risk':int(risk.sum()),'development_risk':int((risk&~hold).sum()),'holdout_risk':int((risk&hold).sum()),'holdout_labels_read':0,'folds':reports,'errors':errors}
(root/'research_staging/replication/split_buffer_comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
