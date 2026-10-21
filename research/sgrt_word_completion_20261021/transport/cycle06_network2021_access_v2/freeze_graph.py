#!/usr/bin/env python3
from pathlib import Path
import json,time,hashlib,datetime
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.sparse import load_npz
from scipy.sparse.csgraph import connected_components
from graph_io import sha
H=Path(__file__).resolve().parent;T=Path('/tmp/sgrt_network2021_access_v2')
def parquet_parts(source,subdir,batch_size=400000):
 dest=H/subdir;dest.mkdir(exist_ok=True);parts=[]
 for i,b in enumerate(pq.ParquetFile(source).iter_batches(batch_size=batch_size)):
  p=dest/f'part_{i:03d}.parquet';assert not p.exists();pq.write_table(__import__('pyarrow').Table.from_batches([b]),p,compression='zstd');assert p.stat().st_size<95_000_000;parts.append({'path':str(p.relative_to(H)),'rows':len(b),'bytes':p.stat().st_size,'sha256':sha(p)})
 return parts

def main():
 start=time.monotonic();assert not (H/'graph_artifact_receipt.json').exists();points=pd.read_parquet(H/'routing_points.parquet');sn=pd.read_parquet(T/'settlement_road_snap.parquet');assert sn.id.is_unique;sn=points.merge(sn.drop(columns=['name','region','lat','lon']),on='id',how='left',validate='one_to_one');sn['snap_status']=sn.snap_status.fillna('missing_source_point_coordinate_no_snap');sn['accepted_snap']=sn.snap_km.le(10)&sn.road_node_index.notna();sn['network_source_timestamp_utc']='2021-01-01T21:42:03Z';sn['connector_scenario_kmh']=15.;sn.to_parquet(H/'settlement_road_snap.parquet',index=False)
 node_parts=parquet_parts(T/'road_nodes.parquet','road_nodes');edge_parts=parquet_parts(T/'road_edges.parquet','road_edges');parts=[];dest=H/'graph_npz_parts';dest.mkdir(exist_ok=True)
 with (T/'routing_graph.npz').open('rb') as stream:
  while True:
   data=stream.read(90_000_000)
   if not data:break
   p=dest/f'part_{len(parts):03d}.bin';assert not p.exists();p.write_bytes(data);parts.append({'path':str(p.relative_to(H)),'bytes':len(data),'sha256':sha(p)})
 graph=load_npz(T/'routing_graph.npz');assert np.isfinite(graph.data).all() and (graph.data>=0).all();nstrong,strong=connected_components(graph,directed=True,connection='strong');weak=pd.read_parquet(T/'road_nodes.parquet',columns=['weak_component']).weak_component.to_numpy();component=pd.DataFrame({'kind':['weak','strong'],'components':[int(weak.max()+1),int(nstrong)],'largest_component_nodes':[int(np.bincount(weak).max()),int(np.bincount(strong).max())]});component.to_csv(H/'component_summary.csv',index=False)
 for name in ['compression_receipt.json','graph_receipt.json','snap_receipt.json']:
  data=json.loads((T/name).read_text());data['road_source_snapshot']='2021-01-01T21:42:03Z';(H/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 source_files=[H/'source_filter_receipt.json',H/'road_extraction_receipt.json',H/'routing_points.parquet',H/'routing_points_receipt.json',H/'road_profile.py',H/'assemble_graph2021.py',H/'protocol.json'];receipt={'status':'HISTORICAL2021_DIRECTED_GRAPH_AND_ALL_AXIS_SNAPS_COMPUTED_PENDING_INDEPENDENT_GRAPH_AUDIT','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':{str(p.relative_to(H)):sha(p) for p in source_files},'graph_npz_sha256':sha(T/'routing_graph.npz'),'graph_npz_parts':parts,'node_parts':node_parts,'edge_parts':edge_parts,'nodes':graph.shape[0],'directed_arcs':graph.nnz,'weak_components':int(weak.max()+1),'strong_components':int(nstrong),'all_points':len(sn),'coordinate_available':int(sn.point_coordinates_available.sum()),'snap_status_counts':sn.snap_status.value_counts().to_dict(),'equal_distance_nearest_vertex_ties':int(sn.nearest_vertex_distance_tie.fillna(False).sum()),'snap_tie_policy':'lowest OSM node ID among listed equal-distance source candidates; not observed attachment','accepted_snaps':int(sn.accepted_snap.sum()),'accepted_coordinate_point_fraction':float(sn.accepted_snap.sum()/sn.point_coordinates_available.sum()),'all_potential_destinations_covered_by_points':True,'snap_sha256':sha(H/'settlement_road_snap.parquet'),'route_matrix_computed':False,'road_year':'2021','source_timestamp_utc':'2021-01-01T21:42:03Z','turn_restrictions_applied':False,'ferries_applied':False,'speed_or_connector_observed':False,'source_points_not_claimed_exact_historical_positions':True,'seconds':time.monotonic()-start}
 (H/'graph_artifact_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['node_parts','edge_parts','graph_npz_parts']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
