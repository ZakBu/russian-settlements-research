"""Stream accepted original ways; attach source NP points to actual spherical road segments.
No graph mutation, point relocation, inferred junction snapping, or source-identity adoption.
"""
from pathlib import Path
import json,time,hashlib,math
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.spatial import cKDTree
H=Path(__file__).resolve().parent;R=H.parents[1];TEMP=Path('/tmp/sgrt_network2021_access_v2');EARTH=6371.0088;CAP=10.;EPS=1.e-7

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as s:
  for b in iter(lambda:s.read(4194304),b''):h.update(b)
 return h.hexdigest()
def unit(lat,lon):
 a,b=np.radians(lat),np.radians(lon);return np.stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)],axis=-1)
def angle(a,b):return np.arctan2(np.linalg.norm(np.cross(a,b),axis=-1),np.sum(a*b,axis=-1))
def project(p,a,b):
 theta=float(angle(a,b))
 if theta<1.e-15:return float(angle(p,a))*EARTH,0.,a
 n=np.cross(a,b);n=n/np.linalg.norm(n);q=p-n*float(np.dot(p,n));qn=np.linalg.norm(q)
 if qn>1.e-15:
  q=q/qn
  # The nearer perpendicular projection has positive dot to p; its antipode cannot be closest.
  aq=float(angle(a,q));qb=float(angle(q,b))
  if aq+qb<=theta+2.e-12:return float(angle(p,q))*EARTH,min(1.,max(0.,aq/theta)),q
 da,db=float(angle(p,a)),float(angle(p,b));return (da*EARTH,0.,a) if da<=db else (db*EARTH,1.,b)
def directed_seeds(u,v,lc,rc,one):
 if lc<=1.e-10:return [{'node':u,'minutes':0.}],[{'node':u,'minutes':0.}],'left_retained_vertex'
 if rc<=1.e-10:return [{'node':v,'minutes':0.}],[{'node':v,'minutes':0.}],'right_retained_vertex'
 out=([{'node':v,'minutes':rc}] if one>=0 else [])+([{'node':u,'minutes':lc}] if one<=0 else [])
 inc=([{'node':u,'minutes':lc}] if one>=0 else [])+([{'node':v,'minutes':rc}] if one<=0 else [])
 return out,inc,'strict_compressed_edge_interior'
def retained_interval(refs,ids,seg):
 gp=np.searchsorted(ids,refs);ret=gp<len(ids);ret[ret]&=ids[gp[ret]]==refs[ret];kept=np.flatnonzero(ret);lefts=kept[kept<=seg];rights=kept[kept>=seg+1]
 if not len(lefts) or not len(rights):raise ValueError('Missing actual retained endpoint dependency: no invented graph index or fallback')
 return gp,int(lefts[-1]),int(rights[0])
def main():
 start=time.monotonic();candidate=R/'source_geography_recovery_cycle06/all479_finite_source_coordinate_candidates.parquet';ways=TEMP/'road_ways.parquet';nodeids=TEMP/'graph_node_ids.npy';graph=TEMP/'routing_graph.npz';old=R/'transport/cycle06_network2021_access_v2'
 protocol={'status':'PROSPECTIVE_SOURCE_GEOMETRY_ATTACHMENT_PROTOCOL_NOT_IDENTITY_ADOPTION','candidate_sha256':sha(candidate),'old_graph_sha256':sha(graph),'accepted_original_road_ways_sha256':sha(ways),'source_NP_point_selection':'independent finite dated identity source, never selected by road or travel outcome','metric':'unit-sphere minor-great-circle original segment projection; EarthR6371.0088km; original way cumulative segment lengths/speeds','complete_search':'ALL accepted original ways; midpoint sphericalcap triangle inequality10km+halfsegmentlength; no geometry-dependent subsample','maximum_connector_km':CAP,'connector_minutes_per_km':4.,'equal_distance_tolerance_km':EPS,'equal_distance_selection':'lexicographic(sourcewayID,originalsegmentindex); all equal-nearest sourcewitnesses retained, never fastest-route choice','directed_partials':'to both retained compressed endpoints only where sourceoneway permits; cumulative measured originalpolyline partialtime','point_source_adoption':'PENDING separate independent identity admission; over10 affects routing only','immutable_old_graph_and_snaps':True}
 pp=H/'attachment_preregistration.json'
 if pp.exists():assert json.loads(pp.read_text())==protocol
 else:pp.write_text(json.dumps(protocol,indent=2)+'\n')
 pts=pd.read_parquet(candidate);xyz=unit(pts.source_lat.to_numpy(),pts.source_lon.to_numpy());tree=cKDTree(xyz);ids=np.load(nodeids,mmap_mode='r');assert len(ids)==9533601 and (ids[1:]>ids[:-1]).all();best=np.full(len(pts),np.inf);chosen={};tie=collections_defaultdict_list();totalways=totalsegments=checkedpairs=0;replacements=0
 columns=['way_id','refs','lat','lon','speed_kmh','oneway','all_source_tags_sha256','osm_version','source_timestamp']
 for ib,bat in enumerate(pq.ParquetFile(ways).iter_batches(batch_size=15000,columns=columns)):
  lats=bat.column(2);lons=bat.column(3);offset=lats.offsets.to_numpy();la=lats.values.to_numpy();lo=lons.values.to_numpy();uv=unit(la,lo);positions=np.arange(max(0,len(la)-1));ends=offset[1:]-1;positions=positions[~np.isin(positions,ends)];a,b=uv[positions],uv[positions+1];theta=angle(a,b);mid=a+b;validmid=np.linalg.norm(mid,axis=1)>1.e-12;assert validmid.all(),'Antipodal source road segment requires separate review';mid=mid/np.linalg.norm(mid,axis=1)[:,None];radius=2*np.sin(np.minimum(np.pi,CAP/EARTH+theta/2)/2);near,_=tree.query(mid,k=1);selected=np.flatnonzero(near<=radius+1.e-13);totalsegments+=len(positions);totalways+=bat.num_rows
  for at in selected:
   vi=int(positions[at]);wi=int(np.searchsorted(offset,vi,side='right')-1);seg=vi-int(offset[wi]);wayid=int(bat.column(0)[wi].as_py())
   for point in tree.query_ball_point(mid[at],radius[at]+1.e-13):
    dist,fraction,q=project(xyz[point],a[at],b[at]);checkedpairs+=1
    if dist>CAP+EPS or dist>best[point]+EPS:continue
    key=(wayid,seg);witness={'id':pts.id.iloc[point],'way_id':wayid,'segment_index':seg,'connector_km':dist,'segment_fraction':fraction,'projection_lat':float(np.degrees(np.arctan2(q[2],np.linalg.norm(q[:2])))),'projection_lon':float(np.degrees(np.arctan2(q[1],q[0]))),'segment_u_osm':int(bat.column(1)[wi].as_py()[seg]),'segment_v_osm':int(bat.column(1)[wi].as_py()[seg+1])}
    best[point]=min(best[point],dist);tie[point]=[w for w in tie[point] if w['connector_km']<=best[point]+EPS]
    if True:
     refs=np.asarray(bat.column(1)[wi].as_py(),dtype='int64');rlat=np.asarray(bat.column(2)[wi].as_py());rlon=np.asarray(bat.column(3)[wi].as_py());gp,left,right=retained_interval(refs,ids,seg);cum=np.r_[0.,np.cumsum(angle(unit(rlat[:-1],rlon[:-1]),unit(rlat[1:],rlon[1:]))*EARTH)];along=float(cum[seg]+fraction*(cum[seg+1]-cum[seg]));speed=float(bat.column(4)[wi].as_py());one=int(bat.column(5)[wi].as_py());lc=float((along-cum[left])/speed*60);rc=float((cum[right]-along)/speed*60);u,v=int(gp[left]),int(gp[right]);out=([{'node':v,'minutes':rc}] if one>=0 else [])+([{'node':u,'minutes':lc}] if one<=0 else []);inc=([{'node':u,'minutes':lc}] if one>=0 else [])+([{'node':v,'minutes':rc}] if one<=0 else []);payload=dict(witness,left_osm_node=int(refs[left]),right_osm_node=int(refs[right]),left_graph_node=u,right_graph_node=v,left_way_position=left,right_way_position=right,left_partial_minutes=lc,right_partial_minutes=rc,compressed_edge_minutes=lc+rc,along_original_way_km=along,oneway=one,speed_kmh=speed,outgoing_seeds_json=json.dumps(out),incoming_seeds_json=json.dumps(inc),source_way_refs_json=json.dumps(refs.tolist()),source_way_lat_json=json.dumps(rlat.tolist()),source_way_lon_json=json.dumps(rlon.tolist()),source_way_tags_sha256=bat.column(6)[wi].as_py(),source_way_version=int(bat.column(7)[wi].as_py()),source_way_timestamp=bat.column(8)[wi].as_py());
     out,inc,endpoint=directed_seeds(u,v,lc,rc,one);payload['outgoing_seeds_json']=json.dumps(out);payload['incoming_seeds_json']=json.dumps(inc);payload['attachment_endpoint_case']=endpoint
     tie[point].append(payload);chosen[point]=min(tie[point],key=lambda w:(w['way_id'],w['segment_index']));replacements+=1
  if ib%50==0:print('batches',ib,'ways',totalways,'segments',totalsegments,'pointwithin10km',len(chosen),'elapsed',round(time.monotonic()-start),flush=True)
 rows=[];ties=[]
 for i,z in enumerate(pts.itertuples()):
  r={'id':z.id,'name':z.name,'source_NP_lat':z.source_lat,'source_NP_lon':z.source_lon,'source_NP_node':z.source_osm_node_id,'source_candidate_class':z.source_candidate_class,'coordinate_source_identity_adopted':False,'snap_status':'accepted_geometry_within10km_pending_source_admission' if i in chosen else 'no_accepted_road_geometry_within10km','snap_km':best[i] if np.isfinite(best[i]) else None}
  if i in chosen:
   r.update(chosen[i]);r['equal_nearest_source_geometry_witness_count']=len(tie[i]);ties.extend(tie[i])
  rows.append(r)
 pd.DataFrame(rows).to_parquet(H/'provisional_sourcepoint_partial_edge_attachments.parquet',index=False);pd.DataFrame(ties).to_parquet(H/'all_equal_nearest_original_segment_witnesses.parquet',index=False);assert protocol['old_graph_sha256']==sha(graph);rec={'status':'ACTUAL_ALL_SOURCE_GEOMETRY_ATTACHMENTS_PENDING_SOURCE_ADOPTION','source_points':len(pts),'actual_source_ways_scanned':totalways,'actual_original_segments_scanned':totalsegments,'actual_point_segment_distance_evaluations':checkedpairs,'within10km':len(chosen),'rejected_over10km':len(pts)-len(chosen),'equal_nearest_multiple_witness_NPs':sum(len(v)>1 for v in tie.values()),'source_coordinate_unchanged':True,'old_graph_sha256_unchanged':True,'old_graph_nodes_and_indices_unchanged':True,'seconds':time.monotonic()-start,'output_sha256':sha(H/'provisional_sourcepoint_partial_edge_attachments.parquet')};(H/'provisional_attachment_receipt.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec),flush=True)
def collections_defaultdict_list():
 from collections import defaultdict
 return defaultdict(list)
if __name__=='__main__':main()
