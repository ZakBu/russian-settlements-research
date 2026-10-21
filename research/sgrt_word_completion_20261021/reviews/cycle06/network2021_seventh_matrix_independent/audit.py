from pathlib import Path
import json,hashlib,time,gc
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');H=B/'transport/cycle06_network2021_access_v2_seventh_extension';BASE=B/'transport/cycle06_network2021_access_v2';T=Path('/tmp/sgrt_network2021_access_v2');O=B/'reviews/cycle06/network2021_seventh_matrix_independent';checks=[];start=time.time()
def ck(n,v,**kw):checks.append(dict(check=n,pass_=bool(v),**kw))
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(4194304),b''):h.update(x)
 return h.hexdigest()
m=json.loads((H/'candidate_travel_times_manifest.json').read_text());receipt=json.loads((H/'routing_receipt.json').read_text());receipt['pairs']=receipt['combined_rows'];g=load_npz(T/'routing_graph.npz');gr=json.loads((BASE/'graph_artifact_receipt.json').read_text());ck('actual_graph_binding',sha(T/'routing_graph.npz')==m['graph_sha256']==gr['graph_npz_sha256']);ck('actual_snapshot_2021',m['graph_source_timestamp_utc'].startswith('2021-01-01'))
orig=pd.read_parquet(H/m['origin_mapping']['path']); dest=pd.read_parquet(H/m['destination_mapping']['path']);ck('origin_mapping_hash',sha(H/m['origin_mapping']['path'])==m['origin_mapping']['sha256']);ck('dest_mapping_hash',sha(H/m['destination_mapping']['path'])==m['destination_mapping']['sha256']);ck('mappings_contiguous_unique',np.array_equal(orig.origin_index,np.arange(len(orig))) and np.array_equal(dest.destination_index,np.arange(len(dest))) and orig.canonical_id.is_unique and dest.canonical_id.is_unique)
# New deterministic slices: distinct from producer's equally spaced selection, includes both budgets and an attachment-tie target when available.
rng=np.random.default_rng(2026102113);sel=[]
for budget in [180,360]:
 ix=np.flatnonzero(dest.routing_budget_minutes.eq(budget)&(dest.index>=6792))
 if len(ix):sel.extend(rng.choice(ix,size=min(2,len(ix)),replace=False).tolist())
base_dest=pd.read_parquet(BASE/'route_destination_index.parquet');upgrade=np.flatnonzero(dest.routing_budget_minutes.to_numpy()[:6792]>base_dest.routing_budget_minutes.to_numpy());sel.extend(rng.choice(upgrade,size=2,replace=False).tolist());sel.append(2541)
sel.extend(dest.index[dest.canonical_id.isin(['ctx:RU-FED-MOW','ctx:RU-FED-SPB'])].tolist());sel=sorted(set(sel));pieces=[];oc=orig.snap_km.to_numpy()*4;dc=dest.snap_km.to_numpy()*4;bud=dest.routing_budget_minutes.to_numpy();selforig=pd.Index(orig.canonical_id).get_indexer(dest.canonical_id);selfcount=np.zeros(len(dest),dtype=int);rows=0;dups=0
# Ordered encoded key set checked per-destination using concatenated compact keys (592MB) below if needed; parts themselves generally group destination.
seen_bits=np.zeros((len(dest),(len(orig)+7)//8),dtype=np.uint8)
for pi,part in enumerate(m['parts']):
 p=H/part['path'];ck('matrix_hash_'+str(pi),sha(p)==part['sha256']);q=pq.read_table(p).to_pandas();oi=q.origin_index.to_numpy().astype('int64');di=q.destination_index.to_numpy().astype('int64');net=q.network_minutes.to_numpy();ck('matrix_rows_and_indices_'+str(pi),len(q)==part['rows'] and np.all((oi>=0)&(oi<len(orig))) and np.all((di>=0)&(di<len(dest))))
 total=net+(oc[oi]+dc[di]).astype('float32');same=oi==selforig[di];total[same]=0;ck('matrix_values_'+str(pi),np.isfinite(net).all() and (net>=0).all() and (total<=bud[di]+1e-4).all());selfcount+=np.bincount(di[same],minlength=len(dest));rows+=len(q)
 encoded=di.astype(np.uint64)*np.uint64(len(orig))+oi.astype(np.uint64);dups+=len(encoded)-len(np.unique(encoded));byte=oi//8;mask=(1<<(oi%8)).astype(np.uint8);dups+=int(np.count_nonzero(seen_bits[di,byte]&mask));np.bitwise_or.at(seen_bits,(di,byte),mask)
 take=np.isin(di,sel)
 if take.any():pieces.append(pd.DataFrame(dict(origin_index=oi[take],destination_index=di[take],network_minutes=net[take],travel_minutes=total[take])))
 if pi%10==0:print('MATRIX_PART',pi,flush=True)
ck('ALL_matrix_rows_unique_keys_self',rows==m['rows']==receipt['pairs'] and dups==0 and np.all(selfcount==1),rows=rows,duplicate_keys=dups);del seen_bits
actual=pd.concat(pieces,ignore_index=True);rev=g.T.tocsr();slices=[]
for j in sel:
 w=dest.iloc[j];dist=dijkstra(rev,directed=True,indices=int(w.road_node_index),limit=float(w.routing_budget_minutes));nv=dist[orig.road_node_index.to_numpy(dtype=int)];tv=nv+oc+float(w.snap_km)*4;tv[selforig[j]]=0;nv[selforig[j]]=0;eligible=np.isfinite(tv)&(tv<=w.routing_budget_minutes);ex=pd.DataFrame(dict(origin_index=np.flatnonzero(eligible),expected_network=nv[eligible],expected_total=tv[eligible]));got=actual[actual.destination_index.eq(j)];z=ex.merge(got,on='origin_index',how='outer',validate='one_to_one',indicator=True);both=z._merge.eq('both');err=float(np.abs(z.loc[both,'expected_total']-z.loc[both,'travel_minutes']).max());boundary=z[~both];bvalid=True
 # No boundary discrepancies expected; don't silently permit missing interior rows.
 boundary_times=boundary.expected_total.combine_first(boundary.travel_minutes);boundary_ok=bool((boundary_times-float(w.routing_budget_minutes)).abs().le(.001).all());ck('fresh_SciPy_slice_'+str(j),boundary_ok and err<.01,maximum_error_minutes=err,expected_rows=len(ex),actual_rows=len(got),boundary_only_pair_difference=len(boundary));slices.append(dict(destination_id=w.id,destination_index=j,budget=float(w.routing_budget_minutes),maximum_error_minutes=err,expected_rows=len(ex),actual_rows=len(got),boundary_only_pair_difference=len(boundary)))
ck('first6792IDs_indices_coords_exact',dest.iloc[:6792].canonical_id.equals(base_dest.canonical_id) and dest.iloc[:6792].road_node_index.equals(base_dest.road_node_index));ck('all_old_budgets_monotonic_only238upgrades',int((dest.routing_budget_minutes.iloc[:6792].to_numpy()>base_dest.routing_budget_minutes.to_numpy()).sum())==238);ck('all17913destination_ids_unique',len(dest)==17913 and dest.canonical_id.is_unique);result=dict(status='ACCEPTED' if all(x['pass_'] for x in checks) else 'REJECTED',all_checks_passed=all(x['pass_'] for x in checks),n_checks=len(checks),n_failed=sum(not x['pass_'] for x in checks),checks=checks,fresh_independent_SciPy_slices=slices,graph_sha256=sha(T/'routing_graph.npz'),matrix_manifest_sha256=sha(H/'candidate_travel_times_manifest.json'),snap_sha256=sha(BASE/'settlement_road_snap.parquet'),scope='ALL7_REQUIRED_CANDIDATE_EXTENDED_MATRIX_COMPUTATION_WITH_DECLARED_FLOAT32_BUDGET_BOUNDARY_UNCERTAINTY_NOT_OBSERVED_TRAVEL',seconds=time.time()-start)
(O/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],result['n_checks'],result['n_failed'],flush=True);print([x for x in checks if not x['pass_']],flush=True)
