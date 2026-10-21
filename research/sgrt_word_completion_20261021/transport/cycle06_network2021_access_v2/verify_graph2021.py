#!/usr/bin/env python3
"""Readback QA: independent full-way length conservation and sampled directed arc checks."""
from pathlib import Path
import json,time,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.sparse import load_npz
from graph_io import sha,load_graph,load_nodes
H=Path(__file__).resolve().parent;T=Path('/tmp/sgrt_network2021_access_v2')
def main():
 start=time.monotonic();receipt=json.loads((H/'graph_artifact_receipt.json').read_text());graph=load_graph();nodes=load_nodes();assert len(nodes)==graph.shape[0] and nodes.node_index.eq(np.arange(len(nodes))).all();assert nodes.osm_id.is_unique
 extraction=json.loads((H/'road_extraction_receipt.json').read_text());assert sha(T/'road_ways.parquet')==extraction['working_geometry_sha256']
 # Independent atan2 great-circle formula applied to every original consecutive road vertex.
 rows=[]
 for b in pq.ParquetFile(T/'road_ways.parquet').iter_batches(batch_size=20000,columns=['way_id','lat','lon']):
  offsets=b.column(1).offsets.to_numpy();lat=np.deg2rad(b.column(1).values.to_numpy());lon=np.deg2rad(b.column(2).values.to_numpy());q=np.sin(np.diff(lat)/2)**2+np.cos(lat[:-1])*np.cos(lat[1:])*np.sin(np.diff(lon)/2)**2;q=np.clip(q,0,1);length=12742.0176*np.arctan2(np.sqrt(q),np.sqrt(1-q));length[offsets[1:-1]-1]=0.;length=np.r_[length,0.];totals=np.add.reduceat(length,offsets[:-1]);rows.append(pd.DataFrame({'way_id':b.column(0).to_numpy(),'source_original_polyline_km':totals}))
 expected=pd.concat(rows,ignore_index=True);assert expected.way_id.is_unique
 edges=pd.read_parquet(H/'road_edges',columns=['way_id','length_km']);summed=edges.groupby('way_id',sort=False).length_km.sum().rename('compressed_polyline_km');check=expected.join(summed,on='way_id',how='left',validate='one_to_one');assert check.compressed_polyline_km.notna().all();error=(check.source_original_polyline_km-check.compressed_polyline_km).abs();assert error.max()<1e-7
 check['absolute_length_error_km']=error;check.nlargest(100,'absolute_length_error_km').to_csv(H/'maximum_way_length_conservation_errors.csv',index=False)
 del edges,expected,check
 # Read bounded sample independently from durable compressed edges. Parallel arc may be faster.
 sample=[];rng=np.random.default_rng(2026102107)
 for part in receipt['edge_parts']:
  f=H/part['path'];assert sha(f)==part['sha256'];df=pd.read_parquet(f);sample.append(df.iloc[rng.choice(len(df),min(40,len(df)),replace=False)])
 sample=pd.concat(sample,ignore_index=True);lookup=nodes.set_index('osm_id').node_index;sample['u']=sample.u_osm.map(lookup);sample['v']=sample.v_osm.map(lookup);assert sample[['u','v']].notna().all().all();checks=[]
 for row in sample.itertuples():
  for u,v in ([(int(row.u),int(row.v))] if row.oneway==1 else [(int(row.v),int(row.u))] if row.oneway==-1 else [(int(row.u),int(row.v)),(int(row.v),int(row.u))]):
   a,b=graph.indptr[u:u+2];where=np.searchsorted(graph.indices[a:b],v);assert where<b-a and graph.indices[a+where]==v;weight=float(graph.data[a+where]);assert weight>=0 and weight<=row.travel_minutes+1e-9;checks.append({'way_id':int(row.way_id),'oneway':int(row.oneway),'u':u,'v':v,'source_segment_time':float(row.travel_minutes),'graph_minimum_arc_time':weight})
 pd.DataFrame(checks).to_parquet(H/'sampled_directed_arc_checks.parquet',index=False)
 points=pd.read_parquet(H/'routing_points.parquet');snap=pd.read_parquet(H/'settlement_road_snap.parquet');assert len(points)==len(snap) and points.id.equals(snap.id);valid=snap.road_node_index.notna();mapped=nodes.set_index('node_index');assert snap.loc[valid,'road_osm_node'].astype('int64').to_numpy().tolist()==mapped.loc[snap.loc[valid,'road_node_index'].astype('int64'),'osm_id'].tolist();assert snap.loc[~snap.point_coordinates_available,'road_node_index'].isna().all()
 assert sha(T/'road_ways.parquet')==extraction['working_geometry_sha256']
 result={'status':'PASS_SOURCE_WAY_LENGTHS_DURABLE_GRAPH_DIRECTED_ARCS_AND_SNAPS','scope':'Author QA; independent raw predicate audit is separate. No observed trip validation.','accepted_source_ways_checked':len(error),'maximum_absolute_way_length_conservation_error_km':float(error.max()),'sampled_source_segments':len(sample),'sampled_directed_arc_assertions':len(checks),'all_point_rows_checked':len(snap),'all_coordinate_snap_vertex_bindings_checked':int(valid.sum()),'missing_coordinate_no_snap_checked':int((~snap.point_coordinates_available).sum()),'durable_graph_matches_temporary_graph_sha256':receipt['graph_npz_sha256']==sha(T/'routing_graph.npz'),'source_geometry_unchanged':True,'audit_code_sha256':sha(Path(__file__)),'seconds':time.monotonic()-start}
 (H/'graph_qa_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
