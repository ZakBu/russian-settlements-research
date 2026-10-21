"""Preregistered12 source-chosen destination slices; independent originalgraph SciPy Dijkstra."""
from pathlib import Path
import json,time,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
H=Path(__file__).resolve().parent;R=H.parents[1];S=R/'transport/cycle07_geography_recovery_extension';B=Path('/tmp/sgrt_network2021_access_v2');start=time.monotonic();TOL=.05;checks=[]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def ck(k,v,d=None):checks.append({'check':k,'passed':bool(v),'detail':d})
manifest=S/'candidate_travel_times_manifest.json';m=json.loads(manifest.read_text());inputs=[manifest,S/'route_origin_index.parquet',S/'route_destination_index.parquet',R/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet',B/'routing_graph.npz'];before={str(p):sha(p) for p in inputs};o=pd.read_parquet(inputs[1]);d=pd.read_parquet(inputs[2]);patch=pd.read_parquet(inputs[3]);new=d[d.destination_index.ge(17913)].copy();partial=new[new.canonical_id.isin(patch.id)].sort_values('canonical_id');vertex=new[~new.canonical_id.isin(patch.id)].sort_values('canonical_id');positions=[0,1,len(vertex)//2,len(vertex)-1];target=pd.concat([partial,vertex.iloc[positions]]);ck('source_selection8partial4vertex',len(partial)==8 and len(target)==12 and target.canonical_id.is_unique);prereg={'status':'PREREGISTERED_BEFORE_NUMERIC_COMPARISON','selection':'All8newsource477provider destinations; four other newvertexadmin destinations at sortedcanonicalID positions0/1/floor(N/2)/last. No result-based selection.','old_origin_prefix':155129,'old_destination_prefix':17913,'all_origins':len(o),'targets':target[['destination_index','canonical_id','name','attachment_policy']].where(pd.notna(target[['destination_index','canonical_id','name','attachment_policy']]),None).to_dict('records'),'source_inputs_sha256':before,'float64_originalgraph_tolerance_minutes':TOL,'boundary_policy':'Every actual/missing-key mismatch retained; admissible numerical-boundary ambiguity only if originalgraph total within0.05minute of180. Never patch pairs.','new_writer_selection':'Double path/partial offsets plus separatelyfloat32(4*snap_km) connectors; selfcanonicalID total0. Stored networkfloat32; consumer reconstruction inherited separately.'};(H/'preregistration.json').write_text(json.dumps(prereg,ensure_ascii=False,indent=2)+'\n')
def pointseeds(frame,col):
 result=[]
 for row in frame.itertuples():
  raw=getattr(row,col,None)
  if isinstance(raw,str) and raw:
   result.append([(int(v['node']),float(v['minutes'])) for v in json.loads(raw)])
  else:result.append([(int(row.road_node_index),0.)])
 return result
outseeds=pointseeds(o,'outgoing_seeds_json');flat=[(i,n,t) for i,seeds in enumerate(outseeds) for n,t in seeds];point=np.array([v[0] for v in flat],dtype=np.int64);node=np.array([v[1] for v in flat],dtype=np.int64);offset=np.array([v[2] for v in flat]);snap_o=(4*o.snap_km.to_numpy()).astype(np.float32).astype(np.float64);ck('unchanged_original_graph',before[str(B/'routing_graph.npz')]=='a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366');graph=load_npz(B/'routing_graph.npz').T.tocsr();ck('original_source_float64_weights',graph.data.dtype==np.dtype('float64'));selected=set(map(int,target.destination_index));parts=[x for x in m['parts'] if x['path'].startswith('additional_parts/')];rows=[]
for part in parts:
 p=S/part['path'];ck('part_source_pin_'+p.name,sha(p)==part['sha256']);tab=pq.read_table(p,filters=[('destination_index','in',sorted(selected))]);
 if len(tab):rows.append(tab.to_pandas())
a=pd.concat(rows,ignore_index=True);ck('selected_slices_unique',not a.duplicated(['origin_index','destination_index']).any());summaries=[];boundary=[];slicewitness=[]
for qi,q in enumerate(target.itertuples(index=False)):
 incoming=pointseeds(pd.DataFrame([q._asdict()]),'incoming_seeds_json')[0];dist=np.full(graph.shape[0],np.inf)
 for nn,initial in incoming:
  one=dijkstra(graph,indices=nn,directed=True,limit=180.);np.minimum(dist,one+initial,out=dist);del one
 net=np.full(len(o),np.inf);np.minimum.at(net,point,dist[node]+offset);direct_same=0
 # Direct same-original-compressed-interval movement can bypass both endpoints.
 if pd.notna(getattr(q,'way_id',np.nan)):
  match=o.way_id.eq(q.way_id)&o.left_osm_node.eq(q.left_osm_node)&o.right_osm_node.eq(q.right_osm_node)
  for j in np.flatnonzero(match.to_numpy()):
   origin=o.iloc[j];delta=float(q.left_partial_minutes-origin.left_partial_minutes)
   if (delta>=0 and origin.oneway>=0) or (delta<=0 and origin.oneway<=0):net[j]=min(net[j],abs(delta));direct_same+=1
 total=net+snap_o+float(np.float32(4*q.snap_km));selfmask=o.canonical_id.eq(q.canonical_id).to_numpy();net[selfmask]=0.;total[selfmask]=0.;expected=total<=180.;actual=a[a.destination_index.eq(q.destination_index)];seen=np.zeros(len(o),bool);seen[actual.origin_index.to_numpy(dtype=int)]=True;av=np.full(len(o),np.nan);av[actual.origin_index.to_numpy(dtype=int)]=actual.network_minutes.to_numpy();joint=seen&expected;err=np.abs(av[joint]-net[joint]);ck('all_observed_network_values_'+str(q.destination_index),np.all(np.isfinite(net[seen])) and (np.abs(av[seen]-net[seen])<TOL).all(),{'actual':int(seen.sum()),'max_error_minutes':float(np.max(np.abs(av[seen]-net[seen]))) if seen.any() else 0})
 mismatch=np.flatnonzero(seen!=expected);margins=np.abs(total[mismatch]-180.);ck('all_key_differences_only_declared_float_boundary_'+str(q.destination_index),np.isfinite(margins).all() and (margins<TOL).all(),{'key_differences':len(mismatch)})
 for j in mismatch:boundary.append({'origin_id':o.canonical_id.iloc[j],'destination_id':q.canonical_id,'original_float64_network_minutes':float(net[j]),'original_float64_total_minutes':float(total[j]),'actual_key_present':bool(seen[j]),'absolute_margin_to180_minutes':float(abs(total[j]-180.)),'pair_not_patched':True})
 summaries.append({'destination_index':int(q.destination_index),'destination_id':q.canonical_id,'name':q.name,'source_group':'recovered_partial_provider' if qi<8 else 'new_admin_vertex','n_all_scoped_origins':len(o),'n_actual_pairs':int(seen.sum()),'n_originalfloat64_expected_pairs':int(expected.sum()),'n_boundary_key_differences':len(mismatch),'maximum_network_minute_error':float(np.max(np.abs(av[seen]-net[seen]))) if seen.any() else 0,'n_direct_sameedge_evaluations':direct_same,'n_self_origins':int(selfmask.sum())});print('destination',qi+1,'of12','pairs',int(seen.sum()),'seconds',round(time.monotonic()-start),flush=True)
 # All actual values and every boundary case retained, not just chosen small errors.
 for j in np.flatnonzero(seen):slicewitness.append({'origin_index':int(j),'destination_index':int(q.destination_index),'network_minutes_actual':float(av[j]),'network_minutes_independent_float64':float(net[j]),'independent_total_minutes':float(total[j])})
 del dist
pd.DataFrame(summaries).to_csv(H/'all12_destination_numeric_summaries.csv',index=False);pd.DataFrame(boundary,columns=['origin_id','destination_id','original_float64_network_minutes','original_float64_total_minutes','actual_key_present','absolute_margin_to180_minutes','pair_not_patched']).to_csv(H/'all_numerical_boundary_cases.csv',index=False);pd.DataFrame(slicewitness).to_parquet(H/'all12_observed_pair_numeric_readback.parquet',index=False);ck('inputs_unchanged',all(sha(p)==s for p,s in before.items()));ok=all(x['passed'] for x in checks);rec={'status':'ACCEPTED_SCOPED_INDEPENDENT_12_DESTINATION_DIJKSTRA' if ok else 'REJECTED','all_checks_passed':ok,'n_checks':len(checks),'n_failed':sum(not x['passed'] for x in checks),'checks':checks,'targets':len(target),'all_origin_opportunities':len(o)*len(target),'actual_observed_pairs_independently_replayed':len(slicewitness),'numerical_boundary_key_differences':len(boundary),'maximum_network_minute_error':max(x['maximum_network_minute_error'] for x in summaries),'accepted_manifest_sha256':before[str(manifest)] if ok else None,'source_inputs_sha256':before,'code_sha256':sha(__file__),'seconds':time.monotonic()-start,'scope':'12 prechosen source-only destination slices across all origins, originalfloat64graph+independent SciPy. Fullmatrix key/interface/prefix review is guardian separate. Tolerance0.05minutes legacy; boundary uncertainty disclosed, no data patched. Geometry/sourceadmissions do not prove offroad crossing access or observed travel.'};(H/'audit.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:rec[k] for k in ['status','n_checks','n_failed','maximum_network_minute_error','numerical_boundary_key_differences','seconds']}),flush=True)
