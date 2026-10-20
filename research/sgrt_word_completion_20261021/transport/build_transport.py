#!/usr/bin/env python3
"""Build an OSM car graph with measured geometry and scenario travel speeds, not observed traffic."""
from pathlib import Path
import argparse,time,json,hashlib,os,re,gc
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
import osmium
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix,save_npz,load_npz
from scipy.sparse.csgraph import connected_components,dijkstra
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2];RAW=Path('/workspace/scratch/sgrt_transport');PBF=RAW/'russia.osm.pbf'
SPEED={'motorway':100,'motorway_link':50,'trunk':90,'trunk_link':50,'primary':70,'primary_link':40,'secondary':60,'secondary_link':35,'tertiary':50,'tertiary_link':30,'unclassified':40,'residential':30,'living_street':15,'service':20,'track':15,'road':25}
AMENITIES={'school','college','university','kindergarten','hospital','clinic','doctors','pharmacy','dentist','bank','atm','marketplace','social_facility','townhall','post_office'}
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def xyz(lat,lon):
 a,b=np.radians(lat),np.radians(lon);return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def distances(lats,lons):
 a,b=np.radians(lats),np.radians(lons);v=np.sin(np.diff(a)/2)**2+np.cos(a[:-1])*np.cos(a[1:])*np.sin(np.diff(b)/2)**2
 return 6371.0088*2*np.arcsin(np.sqrt(np.clip(v,0,1)))
def spd(tags,h):
 base=SPEED[h];v=tags.get('maxspeed','');m=re.match(r'^\s*(\d+(?:\.\d+)?)',v)
 if m:base=min(float(m.group(1))*(1.60934 if 'mph' in v else 1),130)
 factor=.65 if tags.get('surface') in {'unpaved','ground','dirt','earth','mud','sand','grass'} else .8 if tags.get('surface') in {'gravel','fine_gravel','compacted','pebblestone'} else 1
 return max(5,base*factor)
def extract():
 t=time.time();ways=[];pois=[];schema=pa.schema([('way_id',pa.int64()),('refs',pa.list_(pa.int64())),('lat',pa.list_(pa.float64())),('lon',pa.list_(pa.float64())),('highway',pa.string()),('speed_kmh',pa.float64()),('oneway',pa.int8()),('tags',pa.string())]);writer=pq.ParquetWriter(RAW/'road_ways.parquet',schema,compression='zstd');nway=npoi=ninvalid=nrestricted=0
 proc=osmium.FileProcessor(str(PBF)).with_locations(f'sparse_file_array,{RAW}/node_locations.idx').with_filter(osmium.filter.KeyFilter('highway','route','amenity','healthcare','office'))
 for ob in proc:
  tags={x.k:x.v for x in ob.tags};isway=ob.is_way();isnode=ob.is_node()
  if (tags.get('amenity') in AMENITIES or 'healthcare' in tags or tags.get('office')=='government') and (isway or isnode):
   try:
    if isnode:lat,lon=ob.location.lat,ob.location.lon
    else:
     loc=[(n.lat,n.lon) for n in ob.nodes if n.location.valid()];lat=float(np.mean([a for a,b in loc]));lon=float(np.mean([b for a,b in loc]))
    if np.isfinite(lat+lon):pois.append({'osm_type':'way' if isway else 'node','osm_id':ob.id,'lat':lat,'lon':lon,'geometry_role':'vertex_mean_not_interior_point' if isway else 'source_node','name':tags.get('name'),'amenity':tags.get('amenity'),'healthcare':tags.get('healthcare'),'tags_json':json.dumps(tags,ensure_ascii=False)})
   except Exception:ninvalid+=1
  if isway and tags.get('highway') in SPEED:
   if tags.get('motorcar',tags.get('motor_vehicle',tags.get('vehicle',tags.get('access','')))) in {'no','private','agricultural','forestry','delivery','customers','permit','official','psv','bus','taxi','emergency'}:nrestricted+=1;continue
   if tags.get('construction') and tags.get('highway')=='construction':continue
   try:
    refs=[n.ref for n in ob.nodes];lat=[n.lat for n in ob.nodes];lon=[n.lon for n in ob.nodes]
    if len(refs)<2:continue
    ow=tags.get('oneway','');direction=-1 if ow=='-1' else 1 if ow in {'yes','true','1'} or tags.get('junction')=='roundabout' or tags.get('highway') in {'motorway','motorway_link'} and ow not in {'no','0','false'} else 0
    ways.append({'way_id':ob.id,'refs':refs,'lat':lat,'lon':lon,'highway':tags['highway'],'speed_kmh':spd(tags,tags['highway']),'oneway':direction,'tags':json.dumps(tags,ensure_ascii=False)})
    nway+=1
   except Exception:ninvalid+=1
  if len(ways)>=20000:writer.write_table(pa.Table.from_pylist(ways,schema=schema));ways=[];print('ways',nway,'pois',npoi+len(pois),'seconds',round(time.time()-t),flush=True)
  if len(pois)>=20000:
   pp=RAW/f'poi_{npoi:09d}.parquet';pd.DataFrame(pois).to_parquet(pp,index=False);npoi+=len(pois);pois=[]
 if ways:writer.write_table(pa.Table.from_pylist(ways,schema=schema))
 writer.close()
 if pois:pd.DataFrame(pois).to_parquet(RAW/f'poi_{npoi:09d}.parquet',index=False);npoi+=len(pois)
 dump(ROOT/'extraction_receipt.json',{'status':'EXTRACTED','road_ways':nway,'POI_rows':npoi,'invalid_geometry':ninvalid,'restricted_ways_excluded':nrestricted,'seconds':time.time()-t,'source':str(PBF),'road_way_parquet':str(RAW/'road_ways.parquet'),'node_index':str(RAW/'node_locations.idx'),'speed_assumptions':SPEED,'actual_traffic_observed':False,'turn_restrictions_applied':False,'ferry_routes_included':False,'note':'Motor-road graph; private/no/agricultural/forestry vehicle access excluded. Ferry/time-dependent restrictions and turn relations not yet applied; disconnected components retained.'})
 print('EXTRACTED',nway,npoi,flush=True)
def compress():
 start=time.time();ends=[];pf=pq.ParquetFile(RAW/'road_ways.parquet');total=sum(pf.metadata.row_group(i).column(1).num_values for i in range(pf.metadata.num_row_groups));print('allrefs_expected',total,flush=True)
 allrefs=np.memmap(RAW/'allroad_refs.bin',dtype='int64',mode='w+',shape=(total,));alllat=np.memmap(RAW/'allroad_lat.bin',dtype='float64',mode='w+',shape=(total,));alllon=np.memmap(RAW/'allroad_lon.bin',dtype='float64',mode='w+',shape=(total,));offset_total=0
 for b in pf.iter_batches(batch_size=20000,columns=['refs','lat','lon']):
  a=b.column(0);vals=a.values.to_numpy();n=len(vals);allrefs[offset_total:offset_total+n]=vals;alllat[offset_total:offset_total+n]=b.column(1).values.to_numpy();alllon[offset_total:offset_total+n]=b.column(2).values.to_numpy();offset=a.offsets.to_numpy();ends.append(np.r_[vals[offset[:-1]],vals[offset[1:]-1]]);offset_total+=n
 assert offset_total==total
 allrefs.flush();alllat.flush();alllon.flush();print('allrefs',total,flush=True)
 unique,first,count=np.unique(allrefs,return_index=True,return_counts=True);lat=alllat[first];lon=alllon[first];del allrefs,alllat,alllon;gc.collect()
 axis_path=REPO/'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet'
 axis=pd.read_parquet(axis_path if axis_path.exists() else REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',columns=['id','name','region','lat','lon']);axis=axis[axis.lat.notna()&axis.lon.notna()].copy()
 fed=pd.read_csv(REPO/'research/sgrt_national_integration_20261019/core/external_federal_features.csv',usecols=['id','name','region','lat','lon']);axis=pd.concat([axis,fed],ignore_index=True).drop_duplicates('id')
 tree=cKDTree(xyz(lat,lon));ch,near=tree.query(xyz(axis.lat.values,axis.lon.values));snapkm=2*6371.0088*np.arcsin(np.clip(ch/2,0,1));axis['road_osm_node']=unique[near];axis['road_snap_lat']=lat[near];axis['road_snap_lon']=lon[near];axis['snap_km']=snapkm;axis.to_parquet(RAW/'settlement_road_snap_raw.parquet',index=False)
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
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['extract','compress','graph','snap']);a=ap.parse_args();globals()[a.stage]()
