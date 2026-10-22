"""Stream bounded matrix into sparse directed member/provider route field.
Only <=180-minute ACTIVE-provider records are retained. No161m string matrix.
Disposable numeric cache can be rebuilt from immutable compact manifest.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy import sparse
from matrix_query import sha

def within_cap(minutes,cap):
 cap=float(cap)
 if not np.isfinite(cap) or cap<0:raise ValueError('invalid direct-time cap')
 values=np.asarray(minutes,dtype='float64')
 if np.any(~np.isfinite(values)) or np.any(values<0):raise ValueError('invalid observed direct time')
 return values<=cap+1e-4

class RouteField:
 def __init__(self,routes,origins,providers,mass):
  self.routes=routes.tocsr();self.routes.sort_indices()
  self.origins=origins;self.providers=providers
  self.origin_id_to_index={str(x):i for i,x in enumerate(origins.canonical_id)}
  self.provider_id_to_index={str(x):i for i,x in enumerate(providers.id)}
  self.mass=mass;self.tau=None;self.q=None;self.graph_cache={}
 def row(self,origin):
  i=self.origin_id_to_index.get(str(origin))
  if i is None:return np.empty(0,dtype='int32'),np.empty(0,dtype='float32')
  a,b=self.routes.indptr[i:i+2];return self.routes.indices[a:b],self.routes.data[a:b]
 def best_provider(self,origin,cap,tau):
  idx,t=self.row(origin);take=within_cap(t,cap)
  if not take.any():return None,None,None
  idx=idx[take];t=t[take];g=self.mass[idx]*np.exp(-t/tau)
  # provider table is ID-sorted, stable maximum tie takes first canonicalID.
  k=int(np.argmax(g));return int(idx[k]),float(t[k]),float(g[k])
 def feasible_providers(self,origin,cap):
  idx,t=self.row(origin);return frozenset(map(int,idx[within_cap(t,cap)]))
 def time(self,origin,provider_index):
  if str(origin)==str(self.providers.id.iloc[provider_index]):return 0.
  idx,t=self.row(origin);k=int(np.searchsorted(idx,provider_index))
  return float(t[k]) if k<len(idx) and idx[k]==provider_index else None
 def provider_graph(self,cap,tau=60.,symmetry='reciprocal'):
  cachekey=(float(cap),float(tau),symmetry)
  if cachekey in self.graph_cache:return self.graph_cache[cachekey]
  rows=[self.origin_id_to_index.get(str(x),-1) for x in self.providers.id]
  if min(rows)<0:raise ValueError('active provider lacks accepted origin mapping')
  r=self.routes[np.asarray(rows)].tocsr();g=r.copy();g.data=self.mass[g.indices]*np.exp(-g.data/tau)
  # Self is source-route0, but NOT an interaction/conditional destination.
  g.setdiag(0);g.eliminate_zeros();den=np.asarray(g.sum(axis=1)).ravel()
  q=sparse.diags(np.divide(1.,den,out=np.zeros_like(den),where=den>0))@g
  # Keep denominator SAME full180 field; edge admissibility cap differs.
  mask=r.copy();mask.data=within_cap(mask.data,cap).astype('float32');mask.setdiag(0);mask.eliminate_zeros()
  a=q.multiply(mask).tocsr()
  if symmetry=='reciprocal':w=a.multiply(a.T);w.data=np.sqrt(w.data)
  elif symmetry=='directed_max':w=a.maximum(a.T)
  else:raise ValueError('unknown symmetry rule')
  w.setdiag(0);w.eliminate_zeros();self.graph_cache[cachekey]=(w.tocsr(),q.tocsr(),den);return self.graph_cache[cachekey]

def build_route_field(base,cache_dir):
 base=Path(base);cache=Path(cache_dir);cache.mkdir(parents=True,exist_ok=True)
 here=Path(__file__).resolve().parent;protocol=json.loads((here/'PROTOCOL_v1.json').read_text())
 poolp=here/'source_provider_pool/active_provider_pool.parquet'
 providers=pd.read_parquet(poolp).sort_values('id').reset_index(drop=True)
 mp=base/protocol['matrix_manifest'];m=json.loads(mp.read_text())
 if sha(mp)!=protocol['matrix_sha256']:raise ValueError('matrix SHA mismatch')
 initial_pins={str(p):sha(p) for p in [Path(__file__),here/'PROTOCOL_v1.json',poolp,mp]}
 maps=[]
 for key in ['origin_mapping','destination_mapping']:
  p=mp.parent/m[key]['path']
  if sha(p)!=m[key]['sha256']:raise ValueError('mapping SHA mismatch')
  x=pd.read_parquet(p)
  if not np.array_equal(x[m[key]['index_column']],np.arange(len(x))):raise ValueError('mapping not dense')
  maps.append(x)
 origins,dest=maps;active=pd.Series(np.arange(len(providers)),index=providers.id)
 dest_to_provider=dest.canonical_id.map(active).fillna(-1).to_numpy('int64')
 if (dest.loc[dest_to_provider>=0,'routing_budget_minutes']<180).any():raise ValueError('heterogeneous shorter-than-denominator route budget')
 record=[];count=0;row_counts=np.zeros(len(origins),dtype="int64")
 for i,part in enumerate(m['parts']):
  p=mp.parent/part['path']
  if sha(p)!=part['sha256']:raise ValueError('part SHA mismatch')
  t=pd.read_parquet(p);a=t.origin_index.to_numpy('int64');oldb=t.destination_index.to_numpy('int64');b=dest_to_provider[oldb];take=b>=0
  a=a[take];oldb=oldb[take];b=b[take]
  minutes=(t.network_minutes.to_numpy('float32')[take]+(4*origins.snap_km.to_numpy(float)[a]+4*dest.snap_km.to_numpy(float)[oldb]).astype('float32')).astype('float32')
  minutes[origins.canonical_id.to_numpy()[a]==dest.canonical_id.to_numpy()[oldb]]=0
  if np.any(~np.isfinite(minutes)) or np.any(minutes<0):raise ValueError('invalid source directed time')
  use=within_cap(minutes,180)
  z=pd.DataFrame(dict(a=a[use].astype('int32'),b=b[use].astype('int32'),minutes=minutes[use]));cp=cache/f'bounded_{i:03}.parquet';z.to_parquet(cp,index=False);record.append(cp);count+=len(z);row_counts+=np.bincount(z.a.to_numpy(),minlength=len(origins))
 # Two-pass CSR assembly: retain one compact source chunk at a time.
 # No list of all bounded frames or COO duplicate of the whole route field.
 indptr=np.r_[0,np.cumsum(row_counts)].astype('int64')
 indices=np.empty(count,dtype='int32');values=np.empty(count,dtype='float32');cursor=indptr[:-1].copy()
 for part in record:
  z=pd.read_parquet(part);order=np.argsort(z.a.to_numpy(),kind='stable');aa=z.a.to_numpy()[order]
  if len(aa):
   starts=np.r_[0,np.flatnonzero(np.diff(aa))+1];sizes=np.diff(np.r_[starts,len(aa)])
   positions=cursor[aa]+np.arange(len(aa))-np.repeat(starts,sizes)
   indices[positions]=z.b.to_numpy()[order];values[positions]=z.minutes.to_numpy()[order]
   cursor+=np.bincount(aa,minlength=len(origins))
 if not np.array_equal(cursor,indptr[1:]):raise ValueError('CSR source counts mismatch')
 routes=sparse.csr_matrix((values,indices,indptr),shape=(len(origins),len(providers)),copy=False);routes.sort_indices()
 if routes.nnz!=count or not routes.has_canonical_format:raise ValueError('duplicate bounded matrix pairs')
 sparse.save_npz(cache/'routes_180.npz',routes,compressed=True)
 origins.to_parquet(cache/'origin_mapping.parquet',index=False);providers.to_parquet(cache/'provider_mapping.parquet',index=False)
 if any(sha(Path(p))!=h for p,h in initial_pins.items()):raise ValueError('source/cache builder bytes changed during source preparation')
 receipt=dict(origin_mapping_sha256=sha(cache/'origin_mapping.parquet'),provider_mapping_sha256=sha(cache/'provider_mapping.parquet'),source_pins=initial_pins,matrix_manifest_sha256=sha(mp),provider_pool_sha256=sha(poolp),source_rows=m['rows'],retained_bounded_rows=count,uniform_denominator_budget_minutes=180,cache_rebuildable=True,route_cache_sha256=sha(cache/'routes_180.npz'),code_sha256=sha(Path(__file__)))
 (cache/'cache_receipt.json').write_text(json.dumps(receipt,indent=2))
 for p in record:p.unlink()
 return RouteField(routes,origins,providers,providers.own_positive_mass.to_numpy(float)),receipt
