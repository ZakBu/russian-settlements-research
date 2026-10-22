#!/usr/bin/env python3
"""2021 graph assembly derived from pinned compression/minimum-parallel-arc algorithm."""
from pathlib import Path
import argparse,time,json,hashlib,gc
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix,save_npz,load_npz
from scipy.sparse.csgraph import connected_components,dijkstra
from road_profile import xyz,distances
H=Path(__file__).resolve().parent;REPO=H.parents[3];ROOT=RAW=Path('/tmp/sgrt_network2021')
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def compress():
 start=time.time();ends=[];pf=pq.ParquetFile(RAW/'road_ways.parquet');total=sum(pf.metadata.row_group(i).column(1).num_values for i in range(pf.metadata.num_row_groups));print('allrefs_expected',total,flush=True)
 allrefs=np.memmap(RAW/'allroad_refs.bin',dtype='int64',mode='w+',shape=(total,));alllat=np.memmap(RAW/'allroad_lat.bin',dtype='float64',mode='w+',shape=(total,));alllon=np.memmap(RAW/'allroad_lon.bin',dtype='float64',mode='w+',shape=(total,));offset_total=0
 for b in pf.iter_batches(batch_size=20000,columns=['refs','lat','lon']):
  a=b.column(0);vals=a.values.to_numpy();n=len(vals);allrefs[offset_total:offset_total+n]=vals;alllat[offset_total:offset_total+n]=b.column(1).values.to_numpy();alllon[offset_total:offset_total+n]=b.column(2).values.to_numpy();offset=a.offsets.to_numpy();ends.append(np.r_[vals[offset[:-1]],vals[offset[1:]-1]]);offset_total+=n
 assert offset_total==total
 allrefs.flush();alllat.flush();alllon.flush();print('allrefs',total,flush=True)
 unique,first,count=np.unique(allrefs,return_index=True,return_counts=True);lat=alllat[first];lon=alllon[first];del allrefs,alllat,alllon;gc.collect()
 axis_path=H/'routing_points.parquet'
 axis=pd.read_parquet(axis_path,columns=['id','name','region','lat','lon']);axis=axis[np.isfinite(axis[['lat','lon']]).all(axis=1)].copy()
 vertex_xyz=xyz(lat,lon);tree=cKDTree(vertex_xyz);query_xyz=xyz(axis.lat.values,axis.lon.values);pairdist,pairnear=tree.query(query_xyz,k=2);ch=pairdist[:,0].copy();near=pairnear[:,0].copy();tie=pairdist[:,1]<=ch+1e-14;alternatives={}
 for qi in np.flatnonzero(tie):
  cand=np.array(tree.query_ball_point(query_xyz[qi],ch[qi]+1e-14),dtype='int64');dist=np.linalg.norm(vertex_xyz[cand]-query_xyz[qi],axis=1);cand=cand[dist<=dist.min()+1e-14];near[qi]=cand[np.argmin(unique[cand])];ch[qi]=float(np.linalg.norm(vertex_xyz[near[qi]]-query_xyz[qi]));alternatives[int(qi)]=json.dumps(sorted(unique[cand].tolist()))
 axis['nearest_vertex_distance_tie']=tie;axis['nearest_vertex_tie_osm_ids_json']=[alternatives.get(i,'[]') for i in range(len(axis))];axis['tie_policy']='lowest_OSM_node_ID_among_equal_distance_candidates_not_observed_attachment';del vertex_xyz,query_xyz,pairdist,pairnear
 snapkm=2*6371.0088*np.arcsin(np.clip(ch/2,0,1));axis['road_osm_node']=unique[near];axis['road_snap_lat']=lat[near];axis['road_snap_lon']=lon[near];axis['snap_km']=snapkm;axis.to_parquet(RAW/'settlement_road_snap_raw.parquet',index=False)
 junction=np.union1d(np.union1d(unique[count>1],np.concatenate(ends)),unique[near]);del unique,count,first,ends,tree,lat,lon;gc.collect()
 np.save(RAW/'junction_ids.npy',junction);print('junctions',len(junction),'snapped',len(axis),flush=True)
 schema=pa.schema([('u_osm',pa.int64()),('v_osm',pa.int64()),('u_lat',pa.float64()),('u_lon',pa.float64()),('v_lat',pa.float64()),('v_lon',pa.float64()),('length_km',pa.float64()),('travel_minutes',pa.float64()),('oneway',pa.int8()),('highway',pa.string()),('way_id',pa.int64())]);writer=pq.ParquetWriter(ROOT/'road_edges.parquet',schema,compression='zstd');rows=[];nedge=0
 for b in pq.ParquetFile(RAW/'road_ways.parquet').iter_batches(batch_size=10000):
  for w in b.to_pylist():
   ids=np.array(w['refs'],np.int64);lat=np.array(w['lat']);lon=np.array(w['lon']);j=np.searchsorted(junction,ids);valid=(j<len(junction));valid[valid]&=junction[j[valid]]==ids[valid];cuts=np.flatnonzero(valid);lengths=np.r_[0,np.cumsum(distances(lat,lon))]
   for a,z in zip(cuts[:-1],cuts[1:]):
    if a==z:continue
    length=float(lengths[z]-lengths[a]);rows.append(dict(u_osm=int(ids[a]),v_osm=int(ids[z]),u_lat=float(lat[a]),u_lon=float(lon[a]),v_lat=float(lat[z]),v_lon=float(lon[z]),length_km=length,travel_minutes=length/w['speed_kmh']*60,oneway=w['oneway'],highway=w['highway'],way_id=w['way_id']));nedge+=1
   if len(rows)>=50000:writer.write_table(pa.Table.from_pylist(rows,schema=schema));rows=[]
  print('compressededges',nedge,'seconds',round(time.time()-start),flush=True)
 if rows:writer.write_table(pa.Table.from_pylist(rows,schema=schema))
 writer.close();dump(ROOT/'compression_receipt.json',{'status':'COMPRESSED','junction_nodes':len(junction),'edges':nedge,'seconds':time.time()-start,'method':'Retain all road-way endpoints and nodes referenced by multiple accepted ways; sum measured path lengths along removed degree2 interior geometry. Retains same-way turn geometry but does not model turn relations.'})

def graph():
 start=time.time();e=pd.read_parquet(ROOT/'road_edges.parquet');ids=np.unique(np.r_[e.u_osm.values,e.v_osm.values]);u=np.searchsorted(ids,e.u_osm.values);v=np.searchsorted(ids,e.v_osm.values)
 rows=np.r_[u[e.oneway>=0],v[e.oneway<=0]];cols=np.r_[v[e.oneway>=0],u[e.oneway<=0]];weights=np.r_[e.travel_minutes.values[e.oneway>=0],e.travel_minutes.values[e.oneway<=0]]
 # Parallel OSM arcs must take minimum, never scipy's additive duplicate reduction.
 order=np.lexsort((weights,cols,rows));r,c,w=rows[order],cols[order],weights[order];take=np.r_[True,(r[1:]!=r[:-1])|(c[1:]!=c[:-1])];matrix=coo_matrix((w[take],(r[take],c[take])),shape=(len(ids),len(ids))).tocsr();save_npz(ROOT/'routing_graph.npz',matrix)
 del rows,cols,weights,order,r,c,w,take,u,v;gc.collect()
 coords=pd.concat([e[['u_osm','u_lat','u_lon']].rename(columns={'u_osm':'osm_id','u_lat':'lat','u_lon':'lon'}),e[['v_osm','v_lat','v_lon']].rename(columns={'v_osm':'osm_id','v_lat':'lat','v_lon':'lon'})]).drop_duplicates('osm_id').set_index('osm_id').reindex(ids).reset_index();coords['node_index']=np.arange(len(ids));ncomponent,labels=connected_components(matrix,directed=True,connection='weak');coords['weak_component']=labels;coords.to_parquet(ROOT/'road_nodes.parquet',index=False)
 np.save(RAW/'graph_node_ids.npy',ids);dump(ROOT/'graph_receipt.json',{'status':'GRAPH_BUILT','yearround_profile_receipt_sha256':hashlib.sha256((ROOT/'yearround_profile_receipt.json').read_bytes()).hexdigest() if (ROOT/'yearround_profile_receipt.json').exists() else None,'nodes':len(ids),'directed_arcs':matrix.nnz,'weak_components':int(ncomponent),'largest_weak_component_nodes':int(np.bincount(labels).max()),'seconds':time.time()-start,'parallel_arcs':'minimum_time','speed_model':'scenario inferred class/default or explicit maxspeed, surface penalty','traffic_or_timetable_observed':False,'turn_restrictions':False,'ferries':False})
 print('GRAPH',len(ids),matrix.nnz,ncomponent,flush=True)

def snap():
 d=pd.read_parquet(RAW/'settlement_road_snap_raw.parquet');nodes=pd.read_parquet(ROOT/'road_nodes.parquet');lookup=nodes.set_index('osm_id');d['road_node_index']=d.road_osm_node.map(lookup.node_index);d['weak_component']=d.road_osm_node.map(lookup.weak_component);assert d.road_node_index.notna().all();dist=d.snap_km.values;d['snap_status']=np.where(dist<=2,'within2km',np.where(dist<=5,'2to5km',np.where(dist<=10,'5to10km','over10km_unaccepted')));d.to_parquet(ROOT/'settlement_road_snap.parquet',index=False);dump(ROOT/'snap_receipt.json',{'rows':len(d),'snap_status_counts':d.snap_status.value_counts().to_dict(),'distance_quantiles_km':dict(zip(['p50','p90','p95','p99','max'],np.quantile(dist,[.5,.9,.95,.99,1]).tolist())),'node_role':'nearest among all accepted road geometry vertices; protected as graph junction before degree2compression','offnetwork_connector_minutes':'assumed15kmh car connector; network and connector components stored separately','candidate_accepted_distance_km':10})
 print(d.snap_status.value_counts(),flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['compress','graph','snap']);a=ap.parse_args();globals()[a.stage]()
