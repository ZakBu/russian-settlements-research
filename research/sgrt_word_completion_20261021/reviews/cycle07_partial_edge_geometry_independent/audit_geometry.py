"""Independent exhaustive segment minima + bearings/haversine partial-edge cost replay."""
from pathlib import Path
import json,hashlib,time
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.spatial import cKDTree
from scipy.sparse import load_npz
H=Path(__file__).resolve().parent;R=H.parents[1];G=R/'transport/cycle07_geography_recovery_extension';TMP=Path('/tmp/sgrt_network2021_access_v2');ER=6371.0088;EPS=1e-7;checks=[]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def ck(k,ok,detail=None):checks.append({'check':k,'passed':bool(ok),'detail':detail})
def xyz(la,lo):
 la,lo=np.radians(la),np.radians(lo);return np.c_[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]
def hav(a,b,c,d):
 a,b,c,d=map(np.radians,[a,b,c,d]);x=np.sin((c-a)/2)**2+np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2;return 2*np.arctan2(np.sqrt(np.clip(x,0,1)),np.sqrt(np.clip(1-x,0,1)))
def bearing(a,b,c,d):
 a,c,dl=np.radians(a),np.radians(c),np.radians(d-b);return np.arctan2(np.sin(dl)*np.cos(c),np.cos(a)*np.sin(c)-np.sin(a)*np.cos(c)*np.cos(dl))
def project(pl,po,al,ao,bl,bo):
 arc=hav(al,ao,bl,bo);ap=hav(al,ao,pl,po);bp=hav(bl,bo,pl,po);ba=bearing(al,ao,bl,bo);pa=bearing(al,ao,pl,po);along=np.arctan2(np.sin(ap)*np.cos(pa-ba),np.cos(ap));inside=(arc>1e-15)&(along>=0)&(along<=arc);cross=np.abs(np.arcsin(np.clip(np.sin(ap)*np.sin(pa-ba),-1,1)));near_a=ap<=bp;frac=np.where(inside,along/np.maximum(arc,1e-300),np.where(near_a,0.,1.));dist=np.where(inside,cross,np.minimum(ap,bp))*ER;return dist,frac
start=time.monotonic();manifest=json.loads((G/'geometry_stage_manifest.json').read_text());print('manifestkeys',manifest.keys(),flush=True)
# Manifeststructure is pinned separately; explicitly watch everyactual geometryfile used.
files=[G/'attachment_preregistration.json',G/'prepare_partial_edge_attachments.py',G/'sourcepoint_partial_edge_attachments.parquet',G/'all_equal_nearest_original_segment_witnesses_readback.parquet',G/'equal_nearest_attachment_equivalence.parquet',TMP/'road_ways.parquet',TMP/'routing_graph.npz',TMP/'graph_node_ids.npy',R/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet'];before={str(p):sha(p) for p in files};ck('accepted_graph_pin',before[str(TMP/'routing_graph.npz')]=='a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366');ck('accepted_all_original_roadways_pin',before[str(TMP/'road_ways.parquet')]=='502ef1576dd44eea465dc7016714d1288a5e7c8f4c0f4da781aa492eb732c4a1')
pts=pd.read_parquet(G/'sourcepoint_partial_edge_attachments.parquet');witness=pd.read_parquet(G/'all_equal_nearest_original_segment_witnesses_readback.parquet');approved=pd.read_parquet(R/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet');ck('479diagnostics_477approved',len(pts)==479 and len(approved)==477 and approved.id.is_unique and set(approved.id)<=set(pts.id));actual=pts.set_index('id').loc[approved.id];ck('approved_point_coordinates_exact_and_unmoved',np.array_equal(actual.source_NP_lat.to_numpy(),approved.new_lat.to_numpy()) and np.array_equal(actual.source_NP_lon.to_numpy(),approved.new_lon.to_numpy()));pidx={v:i for i,v in enumerate(pts.id)};pl,po=pts.source_NP_lat.to_numpy(),pts.source_NP_lon.to_numpy();tree=cKDTree(xyz(pl,po));best=np.full(len(pts),np.inf);ties=[[] for _ in range(len(pts))];original={};wanted=set(witness.way_id);ways=segments=evals=0
for bi,b in enumerate(pq.ParquetFile(TMP/'road_ways.parquet').iter_batches(batch_size=20000,columns=['way_id','lat','lon','refs','speed_kmh','oneway','tags','osm_version','source_timestamp','all_source_tags_sha256'])):
 off=b.column(1).offsets.to_numpy();assert off[0]==0;la=b.column(1).values.to_numpy();lo=b.column(2).values.to_numpy();ids=b.column(0).to_numpy();pos=np.arange(len(la)-1);pos=pos[~np.isin(pos,off[1:]-1)];al,ao,bl,bo=la[pos],lo[pos],la[pos+1],lo[pos+1];arc=hav(al,ao,bl,bo);middle=xyz(al,ao)+xyz(bl,bo);middle/=np.linalg.norm(middle,axis=1)[:,None];rad=2*np.sin(np.minimum(np.pi,(10+EPS)/ER+arc/2)/2);dd,_=tree.query(middle,k=1);selected=np.flatnonzero(dd<=rad+1e-12);near=tree.query_ball_point(middle[selected],rad[selected]+1e-12);counts=np.array([len(a) for a in near]);si=np.repeat(selected,counts);pi=np.fromiter((i for l in near for i in l),dtype='int64',count=int(counts.sum()));evals+=len(pi)
 if len(pi):
  dist,fr=project(pl[pi],po[pi],al[si],ao[si],bl[si],bo[si]);local=np.full(len(pts),np.inf);np.minimum.at(local,pi,dist);best=np.minimum(best,local)
  for i in range(len(pts)):ties[i]=[v for v in ties[i] if v[2]<=best[i]+EPS]
  keep=(dist<=best[pi]+EPS)&(dist<=10+EPS);originpos=pos[si[keep]];wi=np.searchsorted(off,originpos,side='right')-1;seg=originpos-off[wi]
  for i,w,s,d,f in zip(pi[keep],ids[wi],seg,dist[keep],fr[keep]):ties[i].append((int(w),int(s),float(d),float(f)))
 for j,wayid in enumerate(ids):
  if wayid in wanted:original[int(wayid)]={name:b.column(k)[j].as_py() for k,name in enumerate(['way_id','lat','lon','refs','speed_kmh','oneway','tags','osm_version','source_timestamp','all_source_tags_sha256'])}
 ways+=len(b);segments+=len(pos)
 if bi%40==0:print('scannedways',ways,'segments',segments,'evals',evals,'seconds',round(time.monotonic()-start),flush=True)
ck('exhaustive_all_sourceways_segments',ways==5591746 and segments==53662112,{'ways':ways,'segments':segments,'evals':evals});ck('all479_have_original_segment_within10km',np.all(best<=10+EPS));ck('all474sourceways_readback',len(original)==len(wanted)==474)
globalrows=[]
for row in pts.itertuples():
 i=pidx[row.id];ours={(v[0],v[1]) for v in ties[i]};theirs=set(zip(witness[witness.id==row.id].way_id,witness[witness.id==row.id].segment_index));chosen=min(ours);ck('global_tied_segment_set_'+row.id,ours==theirs,{'ours':len(ours),'theirs':len(theirs)});ck('lex_not_fastest_primary_segment_'+row.id,chosen==(row.way_id,row.segment_index));ck('minimum_distance_'+row.id,abs(best[i]-row.minimum_geometry_distance_km)<=EPS);globalrows.append({'id':row.id,'approved':row.id in set(approved.id),'nearest_km_independent':best[i],'all_equal_nearest_segments':json.dumps(sorted(ours))})
pd.DataFrame(globalrows).to_parquet(H/'all479_independent_global_segment_minima.parquet',index=False)
nodeids=np.load(TMP/'graph_node_ids.npy',mmap_mode='r');graph=load_npz(TMP/'routing_graph.npz');ck('graph_indices_and_size9533601',len(nodeids)==9533601 and np.all(nodeids[1:]>nodeids[:-1]) and graph.shape==(len(nodeids),len(nodeids)));partialrows=[]
for ix,row in witness.iterrows():
 src=original[int(row.way_id)];refs=np.asarray(src['refs']);lat=np.asarray(src['lat']);lon=np.asarray(src['lon']);seg=int(row.segment_index);i=pidx[row.id];dist,frac=project(pl[i],po[i],lat[seg],lon[seg],lat[seg+1],lon[seg+1]);dist=float(dist);frac=float(frac);cum=np.r_[0.,np.cumsum(hav(lat[:-1],lon[:-1],lat[1:],lon[1:])*ER)];j=np.searchsorted(nodeids,refs);ret=(j<len(nodeids));ret[ret]&=nodeids[j[ret]]==refs[ret];positions=np.flatnonzero(ret);left=positions[positions<=seg][-1];right=positions[positions>=seg+1][0];along=cum[seg]+frac*(cum[seg+1]-cum[seg]);lc=(along-cum[left])*60/src['speed_kmh'];rc=(cum[right]-along)*60/src['speed_kmh'];u,v=int(j[left]),int(j[right]);tag=src['tags'];tag_obj=json.loads(tag);canon=json.dumps(tag_obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
 ck('original_source_identity_'+str(ix),json.loads(row.source_way_refs_json)==src['refs'] and json.loads(row.source_way_lat_json)==src['lat'] and json.loads(row.source_way_lon_json)==src['lon'] and row.source_way_tags_json==tag and row.source_way_tags_sha256==src['all_source_tags_sha256'] and row.source_way_version==src['osm_version'] and row.source_way_timestamp==src['source_timestamp']);ck('original_segment_endpoints_'+str(ix),row.segment_u_osm==refs[seg] and row.segment_v_osm==refs[seg+1]);ck('actual_retained_compressed_endpoints_'+str(ix),(row.left_way_position,row.right_way_position,row.left_graph_node,row.right_graph_node,row.left_osm_node,row.right_osm_node)==(left,right,u,v,refs[left],refs[right]));ck('bearing_projection_'+str(ix),abs(dist-row.connector_km)<=EPS and abs(frac-row.segment_fraction)*float((cum[seg+1]-cum[seg])*60/src['speed_kmh'])<=1e-7);ck('original_polyline_costs_'+str(ix),abs(lc-row.left_partial_minutes)<=1e-7 and abs(rc-row.right_partial_minutes)<=1e-7 and abs(lc+rc-row.compressed_edge_minutes)<1e-7 and row.oneway==src['oneway'] and row.speed_kmh==src['speed_kmh'])
 # Endpointpolicy replay uses original stored fraction only afterindependent metric/cost agreement,
 # preserving declared1e-10min source rounding policy; numeric alternative offsets retained separately.
 cl,cr=float(row.left_partial_minutes),float(row.right_partial_minutes);one=src['oneway']
 if cl<=1e-10:out=inc=[{'node':u,'minutes':0.}]
 elif cr<=1e-10:out=inc=[{'node':v,'minutes':0.}]
 else:out=([{'node':v,'minutes':cr}] if one>=0 else [])+([{'node':u,'minutes':cl}] if one<=0 else []);inc=([{'node':u,'minutes':cl}] if one>=0 else [])+([{'node':v,'minutes':cr}] if one<=0 else [])
 ck('directed_partial_seed_permissions_'+str(ix),json.loads(row.outgoing_seeds_json)==out and json.loads(row.incoming_seeds_json)==inc)
 full=cum[right]-cum[left];cost=full*60/src['speed_kmh']
 for aa,bb,allowed in [(u,v,one>=0),(v,u,one<=0)]:
  if allowed and aa!=bb:ck('compressed_graph_source_arc_'+str(ix)+f'_{aa}_{bb}',graph[aa,bb]>0 and float(graph[aa,bb])<=cost+1e-5)
 partialrows.append({'id':row.id,'way_id':row.way_id,'segment_index':seg,'approved':row.id in set(approved.id),'distance_km_independent':dist,'fraction_independent':frac,'left_minutes_independent':lc,'right_minutes_independent':rc,'max_cost_disagreement_minutes':max(abs(lc-cl),abs(rc-cr))})
pd.DataFrame(partialrows).to_parquet(H/'all527_independent_partial_cost_readback.parquet',index=False)
ck('45allsource_tied_NPs',sum(len(v)>1 for v in ties)==45);ck('connector4_and_newpolicy_explicit',pts.connector_assumed_minutes_per_km.eq(4).all() and pts.new_point_segment_projection_differs_from_old_geometry_vertex_policy.eq(True).all() and pts.offroad_access_not_observed.eq(True).all());ck('all_inputs_graph_geometry_code_unchanged',{str(p):sha(p) for p in files}==before)
rec={'status':'ACCEPTED_SCOPED_477_PARTIAL_EDGE_GEOMETRY_COST' if all(x['passed'] for x in checks) else 'REJECTED','all_checks_passed':all(x['passed'] for x in checks),'checks':checks,'n_checks':len(checks),'n_failed':sum(not x['passed'] for x in checks),'accepted_attachment_sha256':sha(G/'sourcepoint_partial_edge_attachments.parquet') if all(x['passed'] for x in checks) else None,'admitted_ID_filter_sha256':sha(R/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet'),'diagnostic479_notall_admitted':True,'approved_source_NP_points':477,'source_geometry_search':{'ways':ways,'segments':segments,'point_segment_evals':evals},'original_graph_sha256':before[str(TMP/'routing_graph.npz')],'own_code_sha256':sha(__file__),'inputs':before,'seconds':time.monotonic()-start,'limitations':'Segmentattachmentnewpolicy, oldvertexsnapsimmutable. Offroadaccess/crossbarrierpermissions notobserved; lexnearestties disclosed, notfastestroute. Proofdoesnotadopt2heldsourceNPidentities orobservedflows.'};(H/'audit.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:rec[k] for k in ['status','n_checks','n_failed','seconds']},ensure_ascii=False),flush=True);print(json.dumps([x for x in checks if not x['passed']][:15],ensure_ascii=False))
