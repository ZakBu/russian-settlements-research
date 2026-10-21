"""Full added-key validation and ALL new-origin/new-destination float64 SciPy route slices."""
from pathlib import Path
import json,time
import numpy as np,pandas as pd
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
from compute_admitted_routing_extension import sha,seeds,H,R,OLD,B,OLDMANIFESTSHA
TOL=.05

def main():
 start=time.monotonic();mp=H/'candidate_travel_times_manifest.json';m=json.loads(mp.read_text());base=json.loads((OLD/'candidate_travel_times_manifest.json').read_text());assert sha(OLD/'candidate_travel_times_manifest.json')==OLDMANIFESTSHA;o=pd.read_parquet(H/m['origin_mapping']['path']);d=pd.read_parquet(H/m['destination_mapping']['path']);bo=pd.read_parquet(OLD/base['origin_mapping']['path']);bd=pd.read_parquet(OLD/base['destination_mapping']['path']);assert o.canonical_id.is_unique and d.canonical_id.is_unique;assert np.array_equal(o.origin_index,np.arange(len(o))) and np.array_equal(d.destination_index,np.arange(len(d)));pd.testing.assert_frame_equal(o.iloc[:len(bo)][bo.columns].reset_index(drop=True),bo,check_dtype=True,check_exact=True);pd.testing.assert_frame_equal(d.iloc[:len(bd)][bd.columns].reset_index(drop=True),bd,check_dtype=True,check_exact=True)
 parts=m['parts'][len(base['parts']):];a=pd.concat([pd.read_parquet(H/p['path']) for p in parts],ignore_index=True);assert len(a)==m['rows']-base['rows'];assert not a.duplicated(['origin_index','destination_index']).any();assert ((a.origin_index>=len(bo))|(a.destination_index>=len(bd))).all();assert a.origin_index.lt(len(o)).all() and a.destination_index.lt(len(d)).all();assert np.isfinite(a.network_minutes).all() and a.network_minutes.ge(0).all();assert m['rows']==sum(p['rows'] for p in m['parts'])
 for p in m['parts']:assert sha(H/p['path'])==p['sha256']
 graph=load_npz(B/'routing_graph.npz');assert sha(B/'routing_graph.npz')=='a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366';rev=graph.T.tocsr();samples=[];boundaries=[];maxerr=0.;oldO=len(bo);oldD=len(bd);target_cache={}
 def query(q,targets,mode,actual):
  nonlocal maxerr
  direction='outgoing' if mode=='forward' else 'incoming';targetdir='incoming' if mode=='forward' else 'outgoing';ss=seeds(pd.DataFrame([q]),direction)[0];dist=np.full(graph.shape[0],np.inf)
  for seed in ss:
   v=dijkstra(graph if mode=='forward' else rev,directed=True,indices=int(seed['node']),limit=180.);np.minimum(dist,v+seed['minutes'],out=dist)
  if mode not in target_cache:
   ts=seeds(targets,targetdir);flat=[(i,v) for i,s in enumerate(ts) for v in s];point=np.array([i for i,v in flat],dtype='int64');nn=np.array([v['node'] for i,v in flat],dtype='int64');offset=np.array([v['minutes'] for i,v in flat]);target_cache[mode]=(point,nn,offset)
  point,nn,offset=target_cache[mode];net=np.full(len(targets),np.inf);np.minimum.at(net,point,dist[nn]+offset)
  if mode=='reverse' and pd.notna(q.get('way_id')):
   # A same-original-edge route may bypass both compressed endpoints.
   for j,t in targets.iloc[oldO:].iterrows():
    if q.id==t.id:net[j]=0.;continue
    if q.way_id!=t.way_id or q.left_osm_node!=t.left_osm_node or q.right_osm_node!=t.right_osm_node:continue
    delta=q.left_partial_minutes-t.left_partial_minutes
    if (delta>=0 and t.oneway>=0) or (delta<=0 and t.oneway<=0):net[j]=min(net[j],abs(delta))
  conn=targets.snap_km.mul(4).to_numpy('float32').astype('float64')+float(np.float32(4*q.snap_km));total=net+conn;expected=total<=180.;selfmask=targets.canonical_id.eq(q.canonical_id).to_numpy();net[selfmask]=0.;total[selfmask]=0.;expected[selfmask]=True;seen=np.zeros(len(targets),bool);av=np.full(len(targets),np.nan);key=actual.destination_index.to_numpy('int64') if mode=='forward' else actual.origin_index.to_numpy('int64');seen[key]=True;av[key]=actual.network_minutes.to_numpy();both=seen&expected;err=np.abs(av[both]-net[both]);maxerr=max(maxerr,float(err.max()) if len(err) else 0.);assert (err<TOL).all();miss=np.flatnonzero(seen!=expected)
  for j in miss:
   margin=abs(total[j]-180.)
   assert np.isfinite(margin) and margin<TOL,(mode,q.canonical_id,j,total[j],seen[j]);boundaries.append({'mode':mode,'query_id':q.canonical_id,'target_id':targets.canonical_id.iloc[j],'scipy_total':total[j],'actual_key_present':bool(seen[j]),'distance_to180_boundary_minutes':margin,'no_pair_patched':True})
  samples.append({'mode':mode,'query_id':q.canonical_id,'actual_pairs':int(seen.sum()),'scipy_expected_pairs':int(expected.sum()),'boundary_only_key_differences':len(miss),'max_network_minute_error':float(err.max()) if len(err) else 0.})
 fg=a[a.origin_index.ge(oldO)&a.destination_index.lt(oldD)].groupby('origin_index',sort=False).groups;rg=a[a.destination_index.ge(oldD)].groupby('destination_index',sort=False).groups
 for q in o.iloc[oldO:].itertuples(index=False):
  q=pd.Series(q._asdict());actual=a.loc[fg.get(q.origin_index,[])];query(q,d.iloc[:oldD].reset_index(drop=True),'forward',actual)
  if len(samples)%25==0:print('fullSciPySlices',len(samples),'elapsed',round(time.monotonic()-start),flush=True)
 for q in d.iloc[oldD:].itertuples(index=False):
  q=pd.Series(q._asdict());actual=a.loc[rg.get(q.destination_index,[])];query(q,o,'reverse',actual)
 pd.DataFrame(samples).to_parquet(H/'all_new_routing_full_SciPy_slices.parquet',index=False);pd.DataFrame(boundaries,columns=['mode','query_id','target_id','scipy_total','actual_key_present','distance_to180_boundary_minutes','no_pair_patched']).to_parquet(H/'new_routing_numerical_boundary_uncertainty.parquet',index=False);r={'status':'ALL_ADDED_KEYS_AND_ALL_NEW_QUERY_SLICES_PASS_PENDING_INDEPENDENT_ADMISSION','new_pairs':len(a),'combined_pairs':m['rows'],'full_float64_SciPy_query_slices':len(samples),'new_origin_slices':len(o)-oldO,'new_destination_slices':len(d)-oldD,'max_network_minutes_error':maxerr,'preregistered_legacy_tolerance_minutes':TOL,'boundary_only_key_differences':len(boundaries),'boundary_pairs_not_patched':True,'all_old_prefix_mapping_values_dtypes_and_part_bytes_exact':True,'old_graph_unchanged':True,'no_false_unbounded_completeness_claim_for_neworigins':True,'new_scope_minutes':180.,'seconds':time.monotonic()-start,'manifest_sha256':sha(mp)};(H/'routing_verification.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':main()
