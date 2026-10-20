#!/usr/bin/env python3
"""Exact bounded directed shortest paths, all origins against frozen destination union."""
from pathlib import Path
import argparse,os,json,time,hashlib,subprocess,concurrent.futures
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
from scipy.sparse import load_npz
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2];RAW=Path('/workspace/scratch/sgrt_transport')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def export_graph():
 graph_sha=sha(ROOT/'routing_graph.npz');marker=RAW/'reverse_graph_export.json';prior=json.loads(marker.read_text()) if marker.exists() else {};refresh=prior.get('graph_sha256')!=graph_sha
 graph=load_npz(ROOT/'routing_graph.npz').transpose().tocsr()
 for name,values,dtype in [('rev_indptr.bin',graph.indptr,'uint64'),('rev_indices.bin',graph.indices,'uint32'),('rev_weights.bin',graph.data,'float32')]:
  path=RAW/name;size=len(values)*np.dtype(dtype).itemsize
  if refresh or not path.exists() or path.stat().st_size!=size:
   tmp=RAW/(name+'.tmp_'+str(os.getpid()));values.astype(dtype).tofile(tmp);tmp.replace(path)
 del graph
 tmp=RAW/('reverse_graph_export.json.tmp_'+str(os.getpid()));tmp.write_text(json.dumps({'graph_sha256':graph_sha}));tmp.replace(marker)

def run(candidates,supplement,workers=4,budget=None):
 t=time.time();export_graph();source_hash=sha(candidates)
 snap=pd.read_parquet(ROOT/'settlement_road_snap.parquet');target=snap[snap.snap_km<=10].reset_index(drop=True);cc=pd.read_parquet(candidates)
 if supplement and supplement.exists():cc=pd.concat([cc,pd.read_parquet(supplement)],ignore_index=True).drop_duplicates('id')
 services=REPO/'research/sgrt_word_completion_20261021/model/routing_destinations_additional_services2021.parquet'
 if services.exists():cc=pd.concat([cc,pd.read_parquet(services)],ignore_index=True).drop_duplicates('id')
 source=cc[['id']].merge(snap,on='id',how='inner',validate='one_to_one');source=source[source.snap_km<=10].reset_index(drop=True)
 base_source_count=len(source);aliases={'RU-FED-MOW':'ctx:RU-FED-MOW','RU-FED-SPB':'ctx:RU-FED-SPB'};extra=[];alias_proof=[]
 for raw_id,canonical_id in aliases.items():
  if canonical_id in set(cc.id) and canonical_id not in set(source.id):
   old=snap.loc[snap.id.eq(raw_id)].iloc[0].copy();declared=cc.loc[cc.id.eq(canonical_id)].iloc[0];assert abs(float(declared.lat)-old.lat)<1e-10 and abs(float(declared.lon)-old.lon)<1e-10;old['id']=canonical_id;extra.append(old);alias_proof.append({'raw_origin_id':raw_id,'canonical_id':canonical_id,'road_node_index':int(old.road_node_index),'coordinates_identical':True})
 if extra:source=pd.concat([source,pd.DataFrame(extra)],ignore_index=True)
 target['canonical_id']=target.id.replace(aliases);source['canonical_id']=source.id.replace(aliases)
 rejected=cc.loc[~cc.id.isin(source.id)].copy();rejected['snap_km']=rejected.id.map(snap.set_index('id').snap_km);rejected['route_status']=np.where(rejected.snap_km.isna(),'not_in_geolocated_snap_axis','snap_over10km');rejected.to_parquet(ROOT/'route_destination_rejections.parquet',index=False)
 budgetpath=REPO/'research/sgrt_word_completion_20261021/model/routing_destinations_budgets_frozen.parquet'
 frozen_hashes={str(path):sha(path) for path in [candidates,supplement,services,budgetpath,ROOT/'routing_graph.npz'] if path is not None and path.exists()}
 if budget is None:
  if not budgetpath.exists():raise RuntimeError('Waiting for agreed frozen role budgets from model engineer: '+str(budgetpath))
  rolebudgets=pd.read_parquet(budgetpath).set_index('id')['routing_budget_minutes'];mapped=source.id.map(rolebudgets);assert mapped.notna().all(),'Every destination needs an explicit frozen role budget';assert mapped.isin([180,360]).all();limits=mapped.to_numpy('float32')
 else:limits=np.full(len(source),budget,dtype='float32')
 source['routing_budget_minutes']=limits
 target.to_parquet(ROOT/'route_origin_index.parquet',index=False);source.to_parquet(ROOT/'route_destination_index.parquet',index=False)
 subprocess.run(['g++','-O3','-std=c++17',str(ROOT/'route_matrix.cpp'),'-o',str(RAW/'route_matrix')],check=True)
 shards=[]
 partitions=list(np.array_split(np.arange(base_source_count),workers))
 if len(source)>base_source_count:partitions.append(np.arange(base_source_count,len(source)))
 for i,indices in enumerate(partitions):
  d=RAW/f'route_shard_{i}';d.mkdir(exist_ok=True)
  for name in ['rev_indptr.bin','rev_indices.bin','rev_weights.bin']:
   p=d/name
   if not p.exists():p.symlink_to(RAW/name)
  target.road_node_index.to_numpy('uint32').tofile(d/'target_nodes.bin');target.snap_km.mul(4).to_numpy('float32').tofile(d/'target_connectors.bin')
  ss=source.iloc[indices];ss.road_node_index.to_numpy('uint32').tofile(d/'source_nodes.bin');ss.snap_km.mul(4).to_numpy('float32').tofile(d/'source_connectors.bin');limits[indices].tofile(d/'source_budgets.bin')
  fingerprint=hashlib.sha256((sha(ROOT/'routing_graph.npz')+''.join(sha(d/name) for name in ['target_nodes.bin','target_connectors.bin','source_nodes.bin','source_connectors.bin','source_budgets.bin'])).encode()).hexdigest();marker=d/'input_fingerprint.txt'
  if not marker.exists() or marker.read_text()!=fingerprint:
   (d/'route_checkpoint.txt').unlink(missing_ok=True);(d/'matrix_pairs.bin').unlink(missing_ok=True);marker.write_text(fingerprint)
  shards.append((d,int(indices[0]),len(indices)))
 def execute(shard):
  d,offset,count=shard
  with open(d/'progress.log','a') as log:subprocess.run([str(RAW/'route_matrix'),str(d)],check=True,stderr=log)
  return d,offset,count
 print(json.dumps({'stage':'START','destinations':len(source),'origins':len(target),'budget_counts':pd.Series(limits).value_counts().to_dict(),'workers':workers,'input':str(candidates),'supplement':str(supplement),'input_sha256':source_hash}),flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
  for done in pool.map(execute,shards):print('completed',str(done),flush=True)
 # Durable exact matrix: numeric indexes reference immutable ordered ID mappings.
 target['origin_index']=np.arange(len(target),dtype='uint32');source['destination_index']=np.arange(len(source),dtype='uint32')
 target.to_parquet(ROOT/'route_origin_index.parquet',index=False);source.to_parquet(ROOT/'route_destination_index.parquet',index=False)
 aliasreceipt={'status':'RESOLVED_EXACT_ENTITY_ALIASES','origin_global_indices_unchanged':True,'base_destinations':base_source_count,'appended_context_destinations':len(source)-base_source_count,'aliases':alias_proof,'identity_rule':'use canonical_id when present, otherwise id; same canonical ID implies self-zero','no_new_geographic_points':True};alias_tmp=ROOT/'federal_context_alias_receipt.json.tmp';alias_tmp.write_text(json.dumps(aliasreceipt,indent=2));alias_tmp.replace(ROOT/'federal_context_alias_receipt.json')
 schema=pa.schema([('origin_index',pa.uint32()),('destination_index',pa.uint32()),('network_minutes',pa.float32())]);n=0;parts=[];partdir=ROOT/'candidate_travel_times_parts';partdir.mkdir(exist_ok=True)
 for d,offset,count in shards:
  raw=np.memmap(d/'matrix_pairs.bin',dtype=[('origin','<u4'),('center','<u4'),('network_minutes','<f4')],mode='r')
  for a in range(0,len(raw),1000000):
   v=raw[a:a+1000000];table=pa.Table.from_arrays([pa.array(v['origin']),pa.array(v['center']+offset),pa.array(v['network_minutes'])],schema=schema);part=partdir/f'part_{len(parts):05d}.parquet';temp=part.with_suffix('.parquet.tmp');pq.write_table(table,temp,compression='zstd',use_dictionary=['origin_index','destination_index'],use_byte_stream_split=['network_minutes']);temp.replace(part);assert part.stat().st_size<50_000_000;parts.append({'path':str(part.relative_to(ROOT)),'rows':len(v),'bytes':part.stat().st_size,'sha256':sha(part)});n+=len(v)
  print('materialized',str(d),n,'pairs',flush=True)
 manifest={'format':'compact_parquet_parts_v1','rows':n,'parts':parts,'schema':str(schema),'origin_mapping':{'path':'route_origin_index.parquet','sha256':sha(ROOT/'route_origin_index.parquet'),'index_column':'origin_index'},'destination_mapping':{'path':'route_destination_index.parquet','sha256':sha(ROOT/'route_destination_index.parquet'),'index_column':'destination_index'},'value_rule':'canonical_id if present otherwise id; network_minutes from exact bounded directed shortest paths; connector=float32(4*origin_snap_km+4*destination_snap_km); travel=float32(network+connector); same canonical ID override all three to0; destination budget from mapping','reconstruct':'python reconstruct_travel_matrix.py','standalone_string_matrix_written':False,'entity_alias_receipt':{'path':'federal_context_alias_receipt.json','sha256':sha(ROOT/'federal_context_alias_receipt.json')}}
 manifest_tmp=ROOT/'candidate_travel_times_manifest.json.tmp';manifest_tmp.write_text(json.dumps(manifest,indent=2));manifest_tmp.replace(ROOT/'candidate_travel_times_manifest.json');output_hash=sha(ROOT/'candidate_travel_times_manifest.json');assert sha(candidates)==source_hash,'Frozen destination file changed during computation'
 assert all(sha(Path(path))==value for path,value in frozen_hashes.items()),'Frozen routing inputs changed during computation'
 receipt={'status':'COMPUTED_PENDING_QA','frozen_input_sha256':frozen_hashes,'graph_sha256':sha(ROOT/'routing_graph.npz'),'access_repair_receipt_sha256':sha(ROOT/'access_repair_receipt.json'),'yearround_profile_receipt_sha256':sha(ROOT/'yearround_profile_receipt.json'),'candidate_source_path':str(candidates),'candidate_sha256':source_hash,'supplement_sha256':sha(supplement) if supplement and supplement.exists() else None,'services2021_supplement_sha256':sha(services) if services.exists() else None,'input_candidates':len(cc),'accepted_destination_snaps':len(source),'accepted_origin_snaps':len(target),'pairs':n,'origin_snap_max_km':10,'speed_model':'OSM maxspeed/class defaults/surface; not observed traffic','connector_model':'15kmh direct connector outside mapped network; separate column','directed_graph':True,'routing_budget_minutes_max':float(limits.max()),'routing_budget_counts':pd.Series(limits).value_counts().to_dict(),'frozen_budget_manifest_sha256':sha(budgetpath) if budget is None else None,'routing_budget_explicit_override':budget,'workers':workers,'no_row_meaning':'outside stated routing budget,disconnected or unaccepted snap; never zero','turn_restriction_relations':False,'ferry_routes_in_main_graph':False,'access_priority':'motorcar > motor_vehicle > vehicle > access; repaired; see access_repair_receipt.json','destination_access_policy':'destination roads retained; through-traffic restriction not represented','graph_source':'Geofabrik Russia OSM 2026-10-19','this_coordinator_seconds':time.time()-t,'output_format':'compact_parquet_parts_v1','output_manifest_sha256':output_hash,'standalone_string_matrix_written':False,'entity_alias_receipt':{'path':'federal_context_alias_receipt.json','sha256':sha(ROOT/'federal_context_alias_receipt.json')}};receipt_tmp=ROOT/'routing_receipt.json.tmp';receipt_tmp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2));receipt_tmp.replace(ROOT/'routing_receipt.json');print(json.dumps(receipt,indent=2),flush=True);subprocess.run(['python',str(ROOT/'verify_matrix.py')],check=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,default=REPO/'research/sgrt_word_completion_20261021/model/routing_destinations_frozen.parquet');p.add_argument('--supplement',type=Path,default=REPO/'research/sgrt_word_completion_20261021/model/routing_destinations_additional_urban.parquet');p.add_argument('--workers',type=int,default=4);p.add_argument('--budget',type=int,default=None);a=p.parse_args();run(a.candidates,a.supplement,a.workers,a.budget)
