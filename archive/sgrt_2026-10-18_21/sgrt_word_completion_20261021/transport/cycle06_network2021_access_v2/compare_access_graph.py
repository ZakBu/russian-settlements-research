"""Full source-order per-way SHA comparison plus every changed compressed edge witness."""
from pathlib import Path
import json,hashlib,time,itertools
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq,pyarrow.compute as pc
H=Path(__file__).resolve().parent;OLD=H.parent/'cycle06_network2021';T=Path('/tmp/sgrt_network2021_access_v2');OT=Path('/tmp/sgrt_network2021')
C=['u_osm','v_osm','u_lat','u_lon','v_lat','v_lon','length_km','travel_minutes','oneway'];DT=np.dtype([(x,'<i8' if x in ['u_osm','v_osm'] else 'i1' if x=='oneway' else '<f8') for x in C])
def fingerprints(path):
 current=None;hasher=None;count=0;prior=-1
 for b in pq.ParquetFile(path).iter_batches(batch_size=200000):
  a={name:b.column(b.schema.get_field_index(name)).to_numpy(zero_copy_only=False) for name in C+['way_id','highway']};numeric=np.empty(len(b),dtype=DT)
  for name in C:numeric[name]=a[name]
  ids=a['way_id'];cuts=np.r_[0,np.flatnonzero(ids[1:]!=ids[:-1])+1,len(ids)]
  for start,end in zip(cuts[:-1],cuts[1:]):
   wid=int(ids[start])
   if wid!=current:
    if current is not None:yield current,count,hasher.hexdigest()
    assert wid>prior,'Source order must be strictly increasing across per-way groups';prior=wid;current=wid;hasher=hashlib.sha256();hasher.update(str(a['highway'][start]).encode()+b'\x00');count=0
   hasher.update(numeric[start:end].tobytes());count+=int(end-start)
 if current is not None:yield current,count,hasher.hexdigest()
def main():
 start=time.monotonic();left=iter(fingerprints(OT/'road_edges.parquet'));right=iter(fingerprints(T/'road_edges.parquet'));a=next(left,None);b=next(right,None);same=0;changed=[]
 while a is not None or b is not None:
  if b is None or (a is not None and a[0]<b[0]):changed.append(dict(way_id=a[0],change='removed_way',old_segments=a[1],new_segments=0,old_edge_sha256=a[2],new_edge_sha256=None));a=next(left,None)
  elif a is None or b[0]<a[0]:changed.append(dict(way_id=b[0],change='added_way',old_segments=0,new_segments=b[1],old_edge_sha256=None,new_edge_sha256=b[2]));b=next(right,None)
  else:
   if a[1:]==b[1:]:same+=1
   else:changed.append(dict(way_id=a[0],change='changed_compression_or_protection',old_segments=a[1],new_segments=b[1],old_edge_sha256=a[2],new_edge_sha256=b[2]))
   a=next(left,None);b=next(right,None)
 diff=pd.DataFrame(changed);assert not diff.change.eq('added_way').any();removed=pd.read_parquet(H/'removed_source_way_witnesses.parquet');assert set(diff.loc[diff.change.eq('removed_way'),'way_id'])==set(removed.way_id)
 diff.to_parquet(H/'all_changed_source_way_compression_fingerprints.parquet',index=False);ids=pa.array(diff.way_id.to_numpy(),type=pa.int64());w=[]
 for label,path in [('old',OT/'road_edges.parquet'),('access_v2',T/'road_edges.parquet')]:
  for batch in pq.ParquetFile(path).iter_batches(batch_size=200000):
   table=pa.Table.from_batches([batch]);take=table.filter(pc.is_in(table['way_id'],value_set=ids))
   if len(take):d=take.to_pandas();d['version']=label;w.append(d)
 pd.concat(w,ignore_index=True).to_parquet(H/'all_changed_compressed_edge_witnesses.parquet',index=False)
 oldsnap=pd.read_parquet(OLD/'settlement_road_snap.parquet').set_index('id');new=pd.read_parquet(H/'settlement_road_snap.parquet').set_index('id');assert oldsnap.index.equals(new.index)
 snapcols=['road_osm_node','snap_km','accepted_snap','weak_component','road_node_index'];joined=oldsnap[snapcols].add_prefix('old_').join(new[snapcols].add_prefix('v2_'));changed_snap=(joined.old_road_osm_node.fillna(-1)!=joined.v2_road_osm_node.fillna(-1))|(joined.old_snap_km.fillna(-1)!=joined.v2_snap_km.fillna(-1))|(joined.old_accepted_snap!=joined.v2_accepted_snap);joined[changed_snap].reset_index().to_parquet(H/'all_changed_point_snap_witnesses.parquet',index=False)
 oldr=json.loads((OLD/'graph_artifact_receipt.json').read_text());nr=json.loads((H/'graph_artifact_receipt.json').read_text());res=dict(status='FULL_SOURCE_WAY_COMPRESSION_AND_ALL_POINT_SNAP_DIFF_COMPLETE',all_old_accepted_source_ways=same+len(diff),identical_source_way_compressed_sequences=same,changed_source_way_counts=diff.change.value_counts().to_dict(),old_compressed_segments=int(pq.ParquetFile(OT/'road_edges.parquet').metadata.num_rows),v2_compressed_segments=int(pq.ParquetFile(T/'road_edges.parquet').metadata.num_rows),changed_compressed_edge_witnesses=sum(len(x) for x in w),changed_point_snaps=int(changed_snap.sum()),old_accepted_snaps=int(oldsnap.accepted_snap.sum()),v2_accepted_snaps=int(new.accepted_snap.sum()),newly_rejected_points=int((oldsnap.accepted_snap&~new.accepted_snap).sum()),newly_admitted_points=int((~oldsnap.accepted_snap&new.accepted_snap).sum()),old_graph_nodes=oldr['nodes'],v2_graph_nodes=nr['nodes'],old_directed_arcs=oldr['directed_arcs'],v2_directed_arcs=nr['directed_arcs'],old_weak_components=oldr['weak_components'],v2_weak_components=nr['weak_components'],scope='Full SHA256 of every per-way ordered compressed numeric edge sequence and highway literal; all changed sequences then retained in full. Index changes alone are not spatial changes.',seconds=time.monotonic()-start)
 (H/'old_vs_access_v2_graph_diff_receipt.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res),flush=True)
if __name__=='__main__':main()
