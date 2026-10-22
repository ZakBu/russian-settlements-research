"""Bounded-memory exact directed request lookup; missing != disconnected."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def lookup_direct_pairs(requests,manifest_path):
 mp=Path(manifest_path);m=json.loads(mp.read_text());sources={str(mp):sha(mp)}
 maps=[]
 for key in ['origin_mapping','destination_mapping']:
  p=mp.parent/m[key]['path'];actual=sha(p)
  if actual!=m[key]['sha256']:raise ValueError('mapping SHA mismatch')
  sources[str(p)]=actual;d=pd.read_parquet(p)
  if not np.array_equal(d[m[key]['index_column']],np.arange(len(d))):raise ValueError('mapping not dense')
  maps.append(d)
 o,d=maps;oid=o.canonical_id.astype(str).to_numpy();did=d.canonical_id.astype(str).to_numpy()
 oi=requests.id.map(pd.Series(np.arange(len(o)),index=oid));di=requests.center_id.map(pd.Series(np.arange(len(d)),index=did))
 valid=oi.notna()&di.notna();key=np.full(len(requests),-1,dtype=np.int64);key[valid]=oi[valid].astype('int64')*len(d)+di[valid].astype('int64')
 wanted,back=np.unique(key[key>=0],return_inverse=True);values=np.full(len(wanted),np.nan,dtype='float32');found=np.zeros(len(wanted),bool)
 scanned=0
 for part in m['parts']:
  p=mp.parent/part['path'];actual=sha(p)
  if actual!=part['sha256']:raise ValueError(f'part SHA mismatch:{p}')
  sources[str(p)]=actual;t=pd.read_parquet(p);scanned+=len(t)
  a=t.origin_index.to_numpy(dtype='int64');b=t.destination_index.to_numpy(dtype='int64');k=a*len(d)+b
  pos=np.searchsorted(wanted,k);hit=pos<len(wanted);hit[hit]&=wanted[pos[hit]]==k[hit]
  a=a[hit];b=b[hit];pos=pos[hit]
  total=(t.network_minutes.to_numpy(dtype='float32')[hit]+(4*o.snap_km.to_numpy(float)[a]+4*d.snap_km.to_numpy(float)[b]).astype('float32')).astype('float32')
  total[oid[a]==did[b]]=0
  if found[pos].any():raise ValueError('duplicate requested matrix pair')
  values[pos]=total;found[pos]=True
 out=requests.copy();out['direct_minutes']=np.nan;out.loc[valid,'direct_minutes']=values[back]
 out['direct_route_status']=np.where(~valid,'origin_or_destination_not_in_accepted_mapping',np.where(out.direct_minutes.notna(),'observed_bounded_matrix_route','not_observed_within_destination_budget_unknown'))
 out.loc[out.id==out.center_id,'direct_minutes']=0
 out.loc[out.id==out.center_id,'direct_route_status']='same_canonical_id_zero'
 return out,dict(manifest_sha256=sha(mp),matrix_rows_scanned=scanned,requests=len(out),source_hashes=sources,direction='origin_NP_to_center',connector_minutes_per_km=4,missing_is_not_infinite=True)
