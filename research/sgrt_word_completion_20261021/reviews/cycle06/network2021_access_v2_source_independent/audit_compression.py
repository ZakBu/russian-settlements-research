#!/usr/bin/env python3
"""Full independent V2 compressed subpath replay after source subset admission."""
from pathlib import Path
import pyarrow.parquet as pq,pandas as pd,numpy as np,json,hashlib,datetime,collections
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[2];TMP=Path('/tmp/sgrt_network2021_access_v2');checks=[]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def ck(n,v,detail=None):checks.append({'check':n,'pass':bool(v),'detail':detail})
source=json.loads((HERE/'audit.json').read_text());ck('independent_source_subset71PASS',source['all_checks_passed']is True and source['n_checks']==71);paths=[TMP/'road_ways.parquet',TMP/'road_edges.parquet',TMP/'junction_ids.npy',TMP/'graph_node_ids.npy',TMP/'compression_receipt.json'];pins={str(p):sha(p)for p in paths};receipt=json.loads((TMP/'compression_receipt.json').read_text());junction=np.load(TMP/'junction_ids.npy',mmap_mode='r');graphids=np.load(TMP/'graph_node_ids.npy',mmap_mode='r');ck('all_retainedjunctions_equal_actual_graphnodeIDs',np.array_equal(junction,graphids));iterator=iter(pq.ParquetFile(TMP/'road_edges.parquet').iter_batches(batch_size=100000));buf=None;cursor=0;consumed=0

def take(n):
 global buf,cursor,consumed
 parts=[]
 while n:
  if buf is None or cursor==len(buf):buf=next(iterator).to_pandas();cursor=0
  k=min(n,len(buf)-cursor);parts.append(buf.iloc[cursor:cursor+k]);cursor+=k;n-=k;consumed+=k
 return pd.concat(parts,ignore_index=True)if len(parts)>1 else parts[0].reset_index(drop=True)
err=collections.Counter();mx=collections.defaultdict(float);nways=nedges=0
for b in pq.ParquetFile(TMP/'road_ways.parquet').iter_batches(batch_size=10000,columns=['way_id','refs','lat','lon','speed_kmh','oneway','highway']):
 refs=b.column(1);la=b.column(2);lo=b.column(3);o=refs.offsets.to_numpy();ids=refs.values.to_numpy();lat=la.values.to_numpy();lon=lo.values.to_numpy();nr=len(b);nways+=nr;err['invalid_offsets']+=int(not(np.array_equal(o,la.offsets.to_numpy())and np.array_equal(o,lo.offsets.to_numpy())));err['invalid_geometry']+=int((~np.isfinite(lat)).sum()+(~np.isfinite(lon)).sum()+(np.diff(o)<2).sum());p=np.radians(lat);q=np.radians(lon);v=np.sin(np.diff(p)/2)**2+np.cos(p[:-1])*np.cos(p[1:])*np.sin(np.diff(q)/2)**2;v=np.clip(v,0,1);length=np.r_[0,12742.0176*np.arctan2(np.sqrt(v),np.sqrt(1-v))];length[o[:-1]]=0;cumulative=np.cumsum(length);j=np.searchsorted(junction,ids);yes=j<len(junction);yes[yes]&=junction[j[yes]]==ids[yes];cuts=np.flatnonzero(yes);way=np.searchsorted(o[1:],cuts,side='right');same=way[:-1]==way[1:];a=cuts[:-1][same];z=cuts[1:][same];wi=way[:-1][same];got=take(len(a));nedges+=len(got);dist=cumulative[z]-cumulative[a];speed=b.column(4).to_numpy();time=dist/speed[wi]*60
 for col,expected in [('u_osm',ids[a]),('v_osm',ids[z]),('u_lat',lat[a]),('u_lon',lon[a]),('v_lat',lat[z]),('v_lon',lon[z]),('oneway',b.column(5).to_numpy()[wi]),('way_id',b.column(0).to_numpy()[wi]),('highway',np.array(b.column(6).to_pylist(),object)[wi])]:err[col]+=int(np.count_nonzero(got[col].to_numpy()!=expected))
 for col,expected in [('length_km',dist),('travel_minutes',time)]:
  difference=np.abs(got[col]-expected);mx[col]=max(mx[col],float(difference.max()));err[col]+=int((~np.isclose(got[col],expected,atol=1e-8,rtol=1e-8)).sum())
 source_lengths=cumulative[o[1:]-1]-cumulative[o[:-1]];sums=np.bincount(wi,weights=got.length_km,minlength=nr);diff=np.abs(source_lengths-sums);mx['per_way_length_km']=max(mx['per_way_length_km'],float(diff.max()));err['per_way_conservation']+=int((~np.isclose(source_lengths,sums,atol=1e-8,rtol=1e-8)).sum())
remaining=(0 if buf is None else len(buf)-cursor)+sum(len(b)for b in iterator);ck('all5591746ways_full_compressed_edgegeometry_identity_and_order',nways==5591746 and nedges==receipt['edges']and consumed==nedges and remaining==0 and all(v==0 for k,v in err.items()if k not in['length_km','travel_minutes','per_way_conservation']),{'ways':nways,'edges':nedges,'errors':dict(err)});ck('allV2edge_lengths_minutes_and_wayconservation',err['length_km']==err['travel_minutes']==err['per_way_conservation']==0,dict(mx))
for p,h in pins.items():ck('frozen_geometry_artifact_unchanged:'+p,sha(p)==h)
result={'status':'INDEPENDENT_ACCESS_V2_FULL_COMPRESSION_ACCEPTED'if all(c['pass']for c in checks)else'REJECT_ACCESS_V2_FULL_COMPRESSION','all_checks_passed':all(c['pass']for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass']for c in checks),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_subset_admission_sha256':sha(HERE/'audit.json'),'audit_code_sha256':sha(Path(__file__)),'ways':nways,'edges':nedges,'checks':checks,'actual_input_sha256':pins,'scope':'Every newly compressed V2 edge exact raw retained vertex subpath, scalar spherical length/minutes, waydirection/class/order and global perwaylength conservation. CSR/snaps/matrix separately reviewed by guardian.'};(HERE/'compression_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'status':result['status'],'n_checks':len(checks),'n_failed':result['n_failed'],'ways':nways,'edges':nedges,'failures':[c for c in checks if not c['pass']]},ensure_ascii=False,indent=2))
