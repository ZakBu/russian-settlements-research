"""Read every selected/tied actual source way; alternate spherical-bearing geometry formulas."""
from pathlib import Path
import json,math,hashlib,time
import pandas as pd,numpy as np,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;R=H.parents[1];T=Path('/tmp/sgrt_network2021_access_v2');EARTH=6371.0088

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hav(a,b):
 a,b=np.radians(a),np.radians(b);da=b[...,0]-a[...,0];dl=b[...,1]-a[...,1];return 2*np.arcsin(np.sqrt(np.clip(np.sin(da/2)**2+np.cos(a[...,0])*np.cos(b[...,0])*np.sin(dl/2)**2,0,1)))
def bearing(a,b):
 a,b=np.radians(a),np.radians(b);dl=b[...,1]-a[...,1];return np.arctan2(np.sin(dl)*np.cos(b[...,0]),np.cos(a[...,0])*np.sin(b[...,0])-np.sin(a[...,0])*np.cos(b[...,0])*np.cos(dl))
def alternate(p,a,b):
 d12=float(hav(a,b));d13=float(hav(a,p));d23=float(hav(b,p))
 if d12<1.e-15:return d13*EARTH,0.
 db=float(bearing(a,p)-bearing(a,b));along=math.atan2(math.sin(d13)*math.cos(db),math.cos(d13))
 if 0<=along<=d12:return abs(math.asin(np.clip(math.sin(d13)*math.sin(db),-1,1)))*EARTH,along/d12
 return (d13*EARTH,0.) if d13<=d23 else (d23*EARTH,1.)
def main():
 start=time.monotonic();p=H/'provisional_sourcepoint_partial_edge_attachments.parquet';q=H/'all_equal_nearest_original_segment_witnesses.parquet';d=pd.read_parquet(p);ties=pd.read_parquet(q);pts=d.set_index('id');wanted=set(ties.way_id);lookup={};cols=['way_id','refs','lat','lon','speed_kmh','oneway','tags','osm_version','source_timestamp','all_source_tags_sha256']
 for b in pq.ParquetFile(T/'road_ways.parquet').iter_batches(batch_size=50000,columns=cols):
  for i in np.flatnonzero(np.isin(b.column(0).to_numpy(),list(wanted))):
   v={c:b.column(j)[int(i)].as_py() for j,c in enumerate(cols)};lookup[v['way_id']]=v
 assert set(lookup)==wanted;ids=np.load(T/'graph_node_ids.npy',mmap_mode='r');maxdistance=maxfraction=maxpartial=0.;full=[]
 for z in ties.itertuples():
  w=lookup[z.way_id];ref=np.asarray(w['refs']);coords=np.c_[w['lat'],w['lon']];assert json.loads(z.source_way_refs_json)==w['refs'] and json.loads(z.source_way_lat_json)==w['lat'] and json.loads(z.source_way_lon_json)==w['lon'];assert w['all_source_tags_sha256']==z.source_way_tags_sha256 and w['osm_version']==z.source_way_version and w['source_timestamp']==z.source_way_timestamp and w['oneway']==z.oneway and w['speed_kmh']==z.speed_kmh;row=pts.loc[z.id];point=np.array([row.source_NP_lat,row.source_NP_lon]);seg=int(z.segment_index);dist,fraction=alternate(point,coords[seg],coords[seg+1]);maxdistance=max(maxdistance,abs(dist-z.connector_km));maxfraction=max(maxfraction,abs(fraction-z.segment_fraction));assert abs(dist-z.connector_km)<1.e-7 and abs(fraction-z.segment_fraction)<1.e-5
  cum=np.r_[0.,np.cumsum(hav(coords[:-1],coords[1:]))*EARTH];along=cum[seg]+z.segment_fraction*(cum[seg+1]-cum[seg]);lc=(along-cum[int(z.left_way_position)])/w['speed_kmh']*60;rc=(cum[int(z.right_way_position)]-along)/w['speed_kmh']*60;maxpartial=max(maxpartial,abs(lc-z.left_partial_minutes),abs(rc-z.right_partial_minutes));assert max(abs(lc-z.left_partial_minutes),abs(rc-z.right_partial_minutes))<1.e-7;assert int(ids[int(z.left_graph_node)])==int(z.left_osm_node) and int(ids[int(z.right_graph_node)])==int(z.right_osm_node);assert ref[int(z.left_way_position)]==z.left_osm_node and ref[int(z.right_way_position)]==z.right_osm_node
  # Direction and exact endpoint cases are checked from primary source attributes.
  out=json.loads(z.outgoing_seeds_json);inc=json.loads(z.incoming_seeds_json);u,v=int(z.left_graph_node),int(z.right_graph_node)
  if z.attachment_endpoint_case=='left_retained_vertex':assert lc<1.e-8 and out==inc==[{'node':u,'minutes':0.}]
  elif z.attachment_endpoint_case=='right_retained_vertex':assert rc<1.e-8 and out==inc==[{'node':v,'minutes':0.}]
  else:
   assert {k['node'] for k in out}==({v} if w['oneway']==1 else {u} if w['oneway']==-1 else {u,v});assert {k['node'] for k in inc}==({u} if w['oneway']==1 else {v} if w['oneway']==-1 else {u,v})
  item=z._asdict();item.pop('Index');item['source_way_tags_json']=w['tags'];t=json.loads(w['tags']);item['source_bridge_literal']=t.get('bridge');item['source_tunnel_literal']=t.get('tunnel');item['source_layer_literal']=t.get('layer');item['source_access_literal']=t.get('access');item['source_motorcar_literal']=t.get('motorcar');item['source_motor_vehicle_literal']=t.get('motor_vehicle');item['alternate_formula_connector_km']=dist;full.append(item)
 full=pd.DataFrame(full);full.to_parquet(H/'all_equal_nearest_original_segment_witnesses_readback.parquet',index=False)
 chosen=full.sort_values(['id','way_id','segment_index']).drop_duplicates('id').set_index('id');out=d.copy()
 for i,z in out.iterrows():
  if z.id not in chosen.index:continue
  v=chosen.loc[z.id];assert int(v.way_id)==int(z.way_id) and int(v.segment_index)==int(z.segment_index);out.at[i,'minimum_geometry_distance_km']=z.snap_km;out.at[i,'snap_km']=z.connector_km
  for col in ['source_way_tags_json','source_bridge_literal','source_tunnel_literal','source_layer_literal','source_access_literal','source_motorcar_literal','source_motor_vehicle_literal']:out.at[i,col]=v[col]
 out['connector_assumed_minutes_per_km']=4.;out['new_point_segment_projection_differs_from_old_geometry_vertex_policy']=True;out['offroad_access_not_observed']=True;out['equal_nearest_geometry_uncertainty']=out.equal_nearest_source_geometry_witness_count.fillna(0).gt(1);out.to_parquet(H/'sourcepoint_partial_edge_attachments.parquet',index=False);r={'status':'ALL_SELECTED_AND_TIED_SOURCE_GEOMETRY_READBACK_PASS_PENDING_INDEPENDENT_AGENT_REVIEW','sourcepoint_rows':len(out),'actual_tied_source_segment_assertions':len(ties),'actual_source_ways_fully_readback':len(lookup),'max_alternate_connector_distance_disagreement_km':maxdistance,'max_alternate_segment_fraction_disagreement':maxfraction,'max_haversine_partial_minutes_disagreement':maxpartial,'corrected_snap_distance_is_chosen_segment_connector_not_minimum_alternative':True,'all_source_coordinates_unchanged':True,'global_graph_or_old_snaps_changed':False,'source_identity_adoption_pending':True,'seconds':time.monotonic()-start,'source_final_attachment_sha256':sha(H/'sourcepoint_partial_edge_attachments.parquet')};(H/'all_selected_geometry_readback_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':main()
