from pathlib import Path
import json,hashlib,time,gc
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.sparse import load_npz
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');H=B/'transport/cycle06_network2021_access_v2';T=Path('/tmp/sgrt_network2021_access_v2');O=B/'reviews/cycle06/network2021_access_v2_graph_independent';start=time.time();checks=[]
def ck(n,v,**kw):checks.append(dict(check=n,pass_=bool(v),**kw))
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(4194304),b''):h.update(x)
 return h.hexdigest()
r=json.loads((H/'graph_artifact_receipt.json').read_text())
for k in ['graph_npz_parts','node_parts','edge_parts']:
 for p in r[k]:ck('durable_'+p['path'],sha(H/p['path'])==p['sha256'])
g=load_npz(T/'routing_graph.npz');n=pd.read_parquet(T/'road_nodes.parquet');ck('actual_graph_source_sha',sha(T/'routing_graph.npz')==r['graph_npz_sha256']);ck('CSR_dimensions_sorted_canonical',g.shape==(len(n),len(n)) and g.nnz==r['directed_arcs'] and g.has_canonical_format);ck('all_CSRweights_finite_nonnegative',np.isfinite(g.data).all() and (g.data>=0).all());ids=n.osm_id.to_numpy();ck('full_OSMnode_index',np.array_equal(n.node_index,np.arange(len(n))) and n.osm_id.is_monotonic_increasing and n.osm_id.is_unique)
# Streaming exact parallel-arc minimum reduction into existing CSR slots. No Python edge-key sets or nationwide edge-sort duplicate.
keys=np.repeat(np.arange(len(n),dtype=np.uint64),np.diff(g.indptr))*np.uint64(len(n))+g.indices.astype(np.uint64);minimum=np.full(g.nnz,np.inf);edgecount=0
for j,batch in enumerate(pq.ParquetFile(T/'road_edges.parquet').iter_batches(batch_size=200000)):
 e=batch.to_pandas();u=np.searchsorted(ids,e.u_osm.to_numpy());v=np.searchsorted(ids,e.v_osm.to_numpy());ck('source_edge_endpoint_ids_'+str(j),np.array_equal(ids[u],e.u_osm) and np.array_equal(ids[v],e.v_osm));edgecount+=len(e)
 for mask,a,b in [(e.oneway.to_numpy()>=0,u,v),(e.oneway.to_numpy()<=0,v,u)]:
  ek=a[mask].astype(np.uint64)*np.uint64(len(n))+b[mask].astype(np.uint64);pos=np.searchsorted(keys,ek);valid=pos<len(keys);valid[valid]&=keys[pos[valid]]==ek[valid];ck('every_directed_source_arc_in_CSR_'+str(j)+'_'+str(len(ek)),valid.all());np.minimum.at(minimum,pos,e.travel_minutes.to_numpy()[mask])
ck('ALL_CSR_arcs_exact_minimum_no_missing_extra',np.isfinite(minimum).all() and np.allclose(minimum,g.data,rtol=0,atol=1e-12),arcs=g.nnz,compressed_source_edges=edgecount);del keys,minimum;gc.collect()
s=pd.read_parquet(H/'settlement_road_snap.parquet');a=s[s.accepted_snap].copy();ix=a.road_node_index.to_numpy(dtype=int);ck('all173864_snaprows',len(s)==173864 and s.id.is_unique);ck('all155129_accepted_node_bindings',len(a)==155129 and np.array_equal(ids[ix],a.road_osm_node.astype('int64')) and np.allclose(n.lat.to_numpy()[ix],a.road_snap_lat,atol=0,rtol=0) and np.allclose(n.lon.to_numpy()[ix],a.road_snap_lon,atol=0,rtol=0));ck('all_accepted_10km_policy',np.array_equal(s.accepted_snap,(s.snap_km<=10).fillna(False)))
lat1=np.radians(a.lat.to_numpy());lat2=np.radians(a.road_snap_lat.to_numpy());dlon=np.radians(a.road_snap_lon.to_numpy()-a.lon.to_numpy());h=np.sin((lat2-lat1)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2;km=2*6371.0088*np.arctan2(np.sqrt(h),np.sqrt(np.maximum(0,1-h)));ck('all_accepted_connector_geometry',np.allclose(km,a.snap_km,atol=1e-8,rtol=0));ck('exact_snap_SHA',sha(H/'settlement_road_snap.parquet')==r['snap_sha256'])
old=pd.read_parquet(B/'transport/cycle06_network2021/settlement_road_snap.parquet').set_index('id');z=s.set_index('id').reindex(old.index);ck('unchanged_all_point_ids_coordinates',z[['lat','lon']].equals(old[['lat','lon']]));ck('accepted_ID_set_identical',np.array_equal(z.accepted_snap,old.accepted_snap));changed=~(z.road_osm_node.eq(old.road_osm_node)|(z.road_osm_node.isna()&old.road_osm_node.isna()));ck('exactly_two_source_snap_changes',changed.sum()==2,ids=z.index[changed].tolist());z.loc[changed,['name','road_osm_node','snap_km']].join(old[['road_osm_node','snap_km']].add_prefix('prior_')).to_parquet(O/'actual_changed_snaps_independent.parquet')
for w in s[s.nearest_vertex_distance_tie.eq(True)].itertuples():ck('tie_declared_lowest_selected_'+w.id,int(w.road_osm_node)==min(json.loads(w.nearest_vertex_tie_osm_ids_json)) and ids[int(w.road_node_index)]==int(w.road_osm_node))
source=B/'reviews/cycle06/network2021_access_v2_source_independent/audit.json';compress=B/'reviews/cycle06/network2021_access_v2_source_independent/compression_audit.json'
for p in [source,compress]:d=json.loads(p.read_text());ck('source_and_compression_acceptance_'+p.name,d.get('n_failed',0)==0 and d.get('all_checks_passed',True) and 'ACCEPT' in d['status'])
d=dict(status='ACCEPTED' if all(c['pass_'] for c in checks) else 'REJECTED',all_checks_passed=all(c['pass_'] for c in checks),n_checks=len(checks),n_failed=sum(not c['pass_'] for c in checks),checks=checks,code_sha256=sha(Path(__file__)),graph_sha256=sha(T/'routing_graph.npz'),graph_artifact_receipt_sha256=sha(H/'graph_artifact_receipt.json'),snap_sha256=sha(H/'settlement_road_snap.parquet'),source_admission_sha256=sha(source),compression_admission_sha256=sha(compress),scope='NEW_ACCESS_V2_ALL_DIRECTED_CSR_ARCS_AND_BOUND_POINT_SNAPS_NOT_MATRIX_OR_OBSERVED_TRAVEL',matrix_independent_admission_pending=True,seconds=time.time()-start);(O/'audit.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(d['status'],len(checks),d['n_failed']);print([c for c in checks if not c['pass_']])
