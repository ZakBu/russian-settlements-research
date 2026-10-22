#!/usr/bin/env python3
"""Actual compact2021 travel matrix for the preregistered all-six source-eligibility union."""
from pathlib import Path
import argparse,concurrent.futures,datetime,hashlib,json,os,subprocess,sys,time
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
from graph_io import sha,load_graph
H=Path(__file__).resolve().parent;T=Path('/tmp/sgrt_network2021')
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--required-destinations',type=Path,default=H/'all_six_required_potential_destinations.parquet');ap.add_argument('--workers',type=int,default=4);ap.add_argument('--resume',action='store_true');a=ap.parse_args();start=time.monotonic();required=a.required_destinations.resolve();assert 1<=a.workers<=4
 assert not (H/'candidate_travel_times_manifest.json').exists(),'Do not overwrite completed matrix'
 inputs=[required,H/'graph_artifact_receipt.json',H/'settlement_road_snap.parquet',H/'road_profile.py',H/'source_filter_receipt.json',H/'road_extraction_receipt.json',H/'route_matrix.cpp',Path(__file__)];pins={str(p):sha(p) for p in inputs};pr=H/'matrix_protocol.json'
 if pr.exists():assert a.resume and json.loads(pr.read_text())['source_sha256']==pins,'Protocol inputs changed; use a new namespace'
 else:dump(pr,{'status':'PREREGISTERED_BEFORE_MATRIX_COMPUTATION','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':pins,'required_scope':'Exact all-six accepted V4 own-mass/dated-eligibility provider+candidate+large-city union, supplied by parent; no2026-admission restriction','budgets':'360min for any possible candidate/large-city anchor;180min for function-only providers; exact required input table','origins':'All accepted<=10km2021snap rows of full current frame including2 explicitctx IDs; coordinateNA/over10 excluded with complete source snap table','time':'Exact bounded directed Dijkstra float32 edge scenario, explicit15kmh connectors; selfsameID0; absentrow never0','graph_review':'Actual computation may proceed parallel to independent graph review; adoption still requires independent acceptance','code':'Pinned unchanged existing C++worker copied with source provenance','workers':a.workers})
 points=pd.read_parquet(H/'settlement_road_snap.parquet');cc=pd.read_parquet(required);assert cc.id.is_unique and cc.routing_budget_minutes.isin([180,360]).all();target=points[points.accepted_snap.fillna(False)].copy().reset_index(drop=True);assert target.id.is_unique;target['canonical_id']=target.id;target['origin_index']=np.arange(len(target),dtype='uint32')
 cc=cc.merge(points[['id','snap_km','accepted_snap']],on='id',how='left',validate='one_to_one');rejected=cc.loc[~cc.accepted_snap.fillna(False)].copy();rejected['route_status']=np.where(rejected.snap_km.isna(),'no_accepted_coordinate_snap_in2021source','snap_over10km2021');rejected.to_parquet(H/'route_destination_rejections.parquet',index=False)
 source=cc.loc[cc.accepted_snap.fillna(False),['id','routing_budget_minutes','eligible_in_any_scenario','large_city_context_anchor']].merge(points.drop(columns=['accepted_snap']),on='id',validate='one_to_one').reset_index(drop=True);source['canonical_id']=source.id;source['destination_index']=np.arange(len(source),dtype='uint32');assert source.id.isin(target.id).all();target.to_parquet(H/'route_origin_index.parquet',index=False);source.to_parquet(H/'route_destination_index.parquet',index=False)
 graph=load_graph().transpose().tocsr();graphsha=json.loads((H/'graph_artifact_receipt.json').read_text())['graph_npz_sha256'];binaries={}
 for name,values,dtype in [('rev_indptr.bin',graph.indptr,'uint64'),('rev_indices.bin',graph.indices,'uint32'),('rev_weights.bin',graph.data,'float32')]:
  p=T/name;values.astype(dtype).tofile(p);binaries[name]=sha(p)
 del graph
 subprocess.run(['g++','-O3','-std=c++17',str(H/'route_matrix.cpp'),'-o',str(T/'route_matrix2021')],check=True)
 shards=[]
 for i,ix in enumerate(np.array_split(np.arange(len(source)),a.workers)):
  if not len(ix):continue
  d=T/f'matrix_shard_{i}';d.mkdir(exist_ok=True)
  for name in binaries:
   link=d/name
   if not link.exists():link.symlink_to(T/name)
  target.road_node_index.to_numpy('uint32').tofile(d/'target_nodes.bin');target.snap_km.mul(4).to_numpy('float32').tofile(d/'target_connectors.bin');ss=source.iloc[ix];ss.road_node_index.to_numpy('uint32').tofile(d/'source_nodes.bin');ss.snap_km.mul(4).to_numpy('float32').tofile(d/'source_connectors.bin');ss.routing_budget_minutes.to_numpy('float32').tofile(d/'source_budgets.bin')
  fingerprint=hashlib.sha256((graphsha+json.dumps(binaries,sort_keys=True)+''.join(sha(d/name) for name in ['target_nodes.bin','target_connectors.bin','source_nodes.bin','source_connectors.bin','source_budgets.bin'])).encode()).hexdigest();mark=d/'input_fingerprint.txt'
  if mark.exists():assert a.resume and mark.read_text()==fingerprint,'Never reuse a checkpoint with changed bytes'
  else:assert not (d/'matrix_pairs.bin').exists();mark.write_text(fingerprint)
  shards.append((d,int(ix[0]),len(ix)))
 dump(H/'matrix_execution_started.json',{'status':'ACTUALLY_ROUTING_2021','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'required_targets':len(cc),'accepted_targets':len(source),'rejected_targets':len(rejected),'origins':len(target),'budget_counts':{str(k):int(v) for k,v in source.routing_budget_minutes.value_counts().items()},'graph_sha256':graphsha,'binary_sha256':binaries,'source_sha256':pins})
 print('routing',len(source),'destinations',len(target),'origins',flush=True)
 def run(shard):
  d,offset,count=shard
  with (d/'progress.log').open('a') as log:subprocess.run([str(T/'route_matrix2021'),str(d)],stderr=log,check=True)
  return shard
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
  for shard in pool.map(run,shards):print('completed',str(shard),flush=True)
 schema=pa.schema([('origin_index',pa.uint32()),('destination_index',pa.uint32()),('network_minutes',pa.float32())]);parts=[];total=0;folder=H/'candidate_travel_times_parts';folder.mkdir(exist_ok=True)
 for d,offset,count in shards:
  raw=np.memmap(d/'matrix_pairs.bin',dtype=[('origin','<u4'),('center','<u4'),('network_minutes','<f4')],mode='r')
  for startrow in range(0,len(raw),1000000):
   v=raw[startrow:startrow+1000000];p=folder/f'part_{len(parts):05d}.parquet';assert not p.exists();table=pa.Table.from_arrays([pa.array(v['origin']),pa.array(v['center']+offset),pa.array(v['network_minutes'])],schema=schema);pq.write_table(table,p,compression='zstd',use_dictionary=['origin_index','destination_index'],use_byte_stream_split=['network_minutes']);assert p.stat().st_size<50_000_000;parts.append({'path':str(p.relative_to(H)),'rows':len(v),'bytes':p.stat().st_size,'sha256':sha(p)});total+=len(v)
  print('materialized',str(d),total,flush=True)
 alias={'status':'CANONICAL_CONTEXT_IDS_ALREADY_EXPLICIT','base_destinations':len(source),'appended_context_destinations':0,'aliases':[],'identity_rule':'canonical_id equals id; ctx federal context IDs are already explicit in origins and destinations; no additive population aliasing'};dump(H/'federal_context_alias_receipt.json',alias)
 manifest={'format':'compact_parquet_parts_v1','rows':total,'parts':parts,'schema':str(schema),'origin_mapping':{'path':'route_origin_index.parquet','sha256':sha(H/'route_origin_index.parquet'),'index_column':'origin_index'},'destination_mapping':{'path':'route_destination_index.parquet','sha256':sha(H/'route_destination_index.parquet'),'index_column':'destination_index'},'value_rule':'Directed origin to destination network_minutes; connector=float32(4*origin_snap_km+4*destination_snap_km); total=float32(network+connector); same canonical ID forces network/connector/total0; per-destination bounded budget','reconstruct':'python reconstruct_travel_matrix.py','standalone_string_matrix_written':False,'entity_alias_receipt':{'path':'federal_context_alias_receipt.json','sha256':sha(H/'federal_context_alias_receipt.json')},'graph_source_timestamp_utc':'2021-01-01T21:42:03Z','graph_sha256':graphsha};dump(H/'candidate_travel_times_manifest.json',manifest)
 assert all(sha(Path(p))==v for p,v in pins.items()),'Routing input changed during computation'
 receipt={'status':'COMPUTED_PENDING_QA','graph_sha256':graphsha,'graph_artifact_receipt_sha256':sha(H/'graph_artifact_receipt.json'),'source_snapshot_utc':'2021-01-01T21:42:03Z','graph_source':'Geofabrik Russia dated2021source exactSHA1b7c5e...','source_sha256':pins,'frozen_input_sha256':pins,'source_bytes_unchanged':True,'candidate_source_path':str(required),'input_candidates':len(cc),'accepted_destination_snaps':len(source),'rejected_destination_snaps':len(rejected),'accepted_origin_snaps':len(target),'pairs':total,'origin_snap_max_km':10,'routing_budget_minutes_max':float(source.routing_budget_minutes.max()),'routing_budget_counts':{str(k):int(v) for k,v in source.routing_budget_minutes.value_counts().items()},'output_format':'compact_parquet_parts_v1','output_manifest_sha256':sha(H/'candidate_travel_times_manifest.json'),'workers':a.workers,'directed_graph':True,'turn_restriction_relations':False,'ferry_routes_in_main_graph':False,'actual_traffic_observed':False,'no_row_meaning':'Outside declared budget, disconnected, or unaccepted snap; never zero','connector_model':'Explicit15kmh straight off-network scenario, not a mapped road','this_coordinator_seconds':time.monotonic()-start};dump(H/'routing_receipt.json',receipt)
 subprocess.run([sys.executable,str(H/'verify_matrix2021.py')],check=True)
if __name__=='__main__':main()
