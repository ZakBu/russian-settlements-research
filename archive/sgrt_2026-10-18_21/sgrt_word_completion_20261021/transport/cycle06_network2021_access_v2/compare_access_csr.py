"""Exhaustive actual CSR differences, bounded by full per-way edge-sequence comparison."""
from pathlib import Path
import json,time
import numpy as np,pandas as pd
from scipy.sparse import load_npz
from graph_io import sha
H=Path(__file__).resolve().parent;OLD=H.parent/'cycle06_network2021';T=Path('/tmp/sgrt_network2021_access_v2');OT=Path('/tmp/sgrt_network2021')
def weight(g,ids,u,v):
 a=int(np.searchsorted(ids,u));b=int(np.searchsorted(ids,v))
 if a==len(ids) or b==len(ids) or ids[a]!=u or ids[b]!=v:return np.nan
 start,end=g.indptr[a:a+2];ix=np.searchsorted(g.indices[start:end],b)
 return float(g.data[start+ix]) if ix<end-start and g.indices[start+ix]==b else np.nan
def main():
 start=time.monotonic();w=pd.read_parquet(H/'all_changed_compressed_edge_witnesses.parquet');pairs=set()
 for r in w.itertuples():
  if r.oneway>=0:pairs.add((r.u_osm,r.v_osm))
  if r.oneway<=0:pairs.add((r.v_osm,r.u_osm))
 oldr=json.loads((OLD/'graph_artifact_receipt.json').read_text());newr=json.loads((H/'graph_artifact_receipt.json').read_text());assert sha(OT/'routing_graph.npz')==oldr['graph_npz_sha256'];assert sha(T/'routing_graph.npz')==newr['graph_npz_sha256'];og=load_npz(OT/'routing_graph.npz');ng=load_npz(T/'routing_graph.npz');oi=pd.read_parquet(OLD/'road_nodes',columns=['osm_id']).osm_id.to_numpy('int64');ni=pd.read_parquet(H/'road_nodes',columns=['osm_id']).osm_id.to_numpy('int64');assert len(oi)==og.shape[0] and len(ni)==ng.shape[0]
 changes=[];unchanged=0
 for u,v in sorted(pairs):
  a=weight(og,oi,u,v);b=weight(ng,ni,u,v)
  if (np.isnan(a) and np.isnan(b)) or a==b:unchanged+=1
  else:changes.append(dict(u_osm=u,v_osm=v,old_minutes=a,v2_minutes=b,change='added_arc' if np.isnan(a) else 'removed_arc' if np.isnan(b) else 'weight_changed'))
 d=pd.DataFrame(changes);d.to_parquet(H/'all_changed_actual_csr_arc_witnesses.parquet',index=False);lost=np.setdiff1d(oi,ni,assume_unique=True);gained=np.setdiff1d(ni,oi,assume_unique=True);pd.DataFrame(dict(osm_id=np.r_[lost,gained],change=['removed_node']*len(lost)+['added_node']*len(gained))).to_parquet(H/'all_changed_actual_graph_vertex_witnesses.parquet',index=False)
 c=d.change.value_counts().to_dict();assert c.get('added_arc',0)-c.get('removed_arc',0)==ng.nnz-og.nnz;assert len(gained)-len(lost)==ng.shape[0]-og.shape[0]
 receipt=dict(status='ALL_ACTUAL_CSR_CHANGE_WITNESSES_COMPUTED',candidate_directed_pairs=len(pairs),candidate_unchanged_actual_minimum_arcs=unchanged,actual_arc_change_counts=c,actual_removed_vertices=len(lost),actual_added_vertices=len(gained),arc_count_delta_exactly_reconciled=True,vertex_count_delta_exactly_reconciled=True,completeness='Every unchanged per-way compressed sequence has identical full SHA256; therefore every possible changed directed arc is in union of ALL old/new changed compressed sequence arcs. Actual CSR minimum queried for each candidate, so unchanged parallel-arc minima are excluded.',seconds=time.monotonic()-start)
 (H/'all_actual_csr_graph_diff_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
