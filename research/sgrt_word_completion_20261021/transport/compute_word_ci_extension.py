#!/usr/bin/env python3
"""Append 360-minute WordCi scope without mutating any intrinsic-run matrix input."""
from pathlib import Path
import hashlib,json,subprocess,shutil,time
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq,pyarrow.dataset as ds
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
BASE=Path(__file__).resolve().parent; REPO=BASE.parents[2]; RAW=Path('/workspace/scratch/sgrt_transport');OUT=BASE/'word_ci_extension360';OUT.mkdir(exist_ok=True)
SHORT=BASE.parent/'model/word_ci_high_parent_budget_shortfalls.parquet'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def dump(name,d):
 p=OUT/name;tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def main():
 start=time.monotonic();watch=[BASE/'candidate_travel_times_manifest.json',BASE/'routing_receipt.json',BASE/'route_origin_index.parquet',BASE/'route_destination_index.parquet',BASE/'routing_graph.npz',SHORT];hashes={str(p):sha(p) for p in watch}
 assert hashes[str(SHORT)]=='6faac1ed7b3c73bee1f6173f4cd0f2218c421f472217a4da25d5e54144e5a869'
 old=json.loads((BASE/'candidate_travel_times_manifest.json').read_text());receipt=json.loads((BASE/'routing_receipt.json').read_text());assert receipt['status']=='COMPUTED'
 origins=pd.read_parquet(BASE/'route_origin_index.parquet');dest=pd.read_parquet(BASE/'route_destination_index.parquet');short=pd.read_parquet(SHORT);selected=dest[dest.canonical_id.isin(short.id)].copy().reset_index(drop=True);assert len(selected)==len(short)==26;assert selected.routing_budget_minutes.eq(180).all()
 upgraded=dest.copy();upgraded.loc[upgraded.canonical_id.isin(short.id),'routing_budget_minutes']=360
 # All mapping global indices and geographic rows remain byte-for-byte semantically unchanged.
 pd.testing.assert_frame_equal(dest.drop(columns='routing_budget_minutes'),upgraded.drop(columns='routing_budget_minutes'))
 for name in ['route_origin_index.parquet','route_destination_rejections.parquet','settlement_road_snap.parquet','federal_context_alias_receipt.json']:
  shutil.copyfile(BASE/name,OUT/name)
 upgraded.to_parquet(OUT/'route_destination_index.parquet',index=False);selected.to_parquet(OUT/'extended_destinations_before.parquet',index=False)
 job=RAW/'word_ci_extension360';job.mkdir(exist_ok=True)
 for n in ['rev_indptr.bin','rev_indices.bin','rev_weights.bin']:
  p=job/n
  if not p.exists():p.symlink_to(RAW/n)
 for name,values in [('target_nodes',origins.road_node_index.to_numpy('uint32')),('target_connectors',origins.snap_km.mul(4).to_numpy('float32')),('source_nodes',selected.road_node_index.to_numpy('uint32')),('source_connectors',selected.snap_km.mul(4).to_numpy('float32')),('source_budgets',np.full(26,360,'float32'))]:values.tofile(job/(name+'.bin'))
 fingerprint=hashlib.sha256(''.join(sha(job/n) for n in ['target_nodes.bin','target_connectors.bin','source_nodes.bin','source_connectors.bin','source_budgets.bin']).encode()).hexdigest();marker=job/'input_fingerprint.txt'
 if not marker.exists() or marker.read_text()!=fingerprint:
  (job/'route_checkpoint.txt').unlink(missing_ok=True);(job/'matrix_pairs.bin').unlink(missing_ok=True);marker.write_text(fingerprint)
 with open(job/'progress.log','a') as log:subprocess.run([str(RAW/'route_matrix'),str(job)],check=True,stderr=log)
 raw=np.fromfile(job/'matrix_pairs.bin',dtype=[('origin','<u4'),('center','<u4'),('network_minutes','<f4')]);globaldest=selected.destination_index.to_numpy('uint32')[raw['center']];print('COMPUTED26',len(raw),flush=True)
 # Read exact existing 180-minute pair keys rather than relying on float association at the boundary.
 paths=[str(BASE/p['path']) for p in old['parts']];data=ds.dataset(paths,format='parquet').to_table(columns=['origin_index','destination_index'],filter=ds.field('destination_index').isin(selected.destination_index.tolist()));existing=pd.DataFrame({'origin':data['origin_index'].to_numpy(),'destination':data['destination_index'].to_numpy()})
 oldkeys=existing.origin.to_numpy('uint64')*np.uint64(len(dest))+existing.destination.to_numpy('uint64');allkeys=raw['origin'].astype('uint64')*np.uint64(len(dest))+globaldest.astype('uint64');assert len(np.unique(oldkeys))==len(oldkeys);assert len(np.unique(allkeys))==len(allkeys);assert np.isin(oldkeys,allkeys).all(),'Extension360 must contain every prior180pair'
 keep=~np.isin(allkeys,oldkeys);add=raw[keep];adddest=globaldest[keep];assert not np.isin(allkeys[keep],oldkeys).any()
 # Independent full SciPy slices for all26 endpoints, including nation-wide accepted origins.
 graph=load_npz(BASE/'routing_graph.npz').transpose().tocsr();checks=[];orig_nodes=origins.road_node_index.to_numpy('int64');oc=origins.snap_km.to_numpy()*4
 for i,row in selected.iterrows():
  dist=dijkstra(graph,directed=True,indices=int(row.road_node_index),limit=360);values=dist[orig_nodes];total=values+oc+float(row.snap_km)*4;expected=np.flatnonzero(total<=360);got=raw[raw['center']==i];got_orig=got['origin'];missing=np.setdiff1d(expected,got_orig);extra=np.setdiff1d(got_orig,expected)
  if len(missing)+len(extra):assert np.all(np.abs(total[np.r_[missing,extra]]-360)<.001),'True boundary mismatch'
  error=float(np.max(np.abs(got['network_minutes']-values[got_orig]))) if len(got) else 0.;assert error<.005
  checks.append({'id':row.canonical_id,'pairs':len(got),'max_network_minutes_error':error,'boundary_rounding_pair_differences':len(missing)+len(extra)})
 del graph
 added=[]
 for off in range(0,len(add),1000000):
  p=OUT/f'additional_part_{len(added):03d}.parquet';tab=pa.table({'origin_index':pa.array(add['origin'][off:off+1000000],type=pa.uint32()),'destination_index':pa.array(adddest[off:off+1000000],type=pa.uint32()),'network_minutes':pa.array(add['network_minutes'][off:off+1000000],type=pa.float32())});pq.write_table(tab,p,compression='zstd',use_dictionary=['origin_index','destination_index'],use_byte_stream_split=['network_minutes']);assert p.stat().st_size<50_000_000;added.append({'path':p.name,'rows':len(tab),'bytes':p.stat().st_size,'sha256':sha(p)})
 parts=[dict(p,path='../'+p['path']) for p in old['parts']]+added
 manifest=dict(old,rows=old['rows']+len(add),parts=parts,origin_mapping={'path':'route_origin_index.parquet','sha256':sha(OUT/'route_origin_index.parquet'),'index_column':'origin_index'},destination_mapping={'path':'route_destination_index.parquet','sha256':sha(OUT/'route_destination_index.parquet'),'index_column':'destination_index'},base_manifest={'path':'../candidate_travel_times_manifest.json','sha256':hashes[str(BASE/'candidate_travel_times_manifest.json')]},extension_scope='all accepted national origins to26newWordCi higher-parent destinations,360min; only previously absent keys appended')
 dump('matrix_verification.json',{'status':'PASS','scipy_full_destination_slices':checks,'all26_destinations_checked':True,'base_pairs_for26':len(existing),'extended_all360_pairs':len(raw),'new_pairs':len(add),'duplicate_pair_keys_added':0,'base_globalindices_unchanged':True,'maximum_error_minutes':max(x['max_network_minutes_error'] for x in checks)})
 dump('candidate_travel_times_manifest.json',manifest)
 assert all(sha(Path(p))==v for p,v in hashes.items()),'Inputs mutated during extension'
 newreceipt=dict(receipt,status='COMPUTED',output_manifest_sha256=sha(OUT/'candidate_travel_times_manifest.json'),pairs=manifest['rows'],routing_budget_counts=upgraded.routing_budget_minutes.value_counts().to_dict(),base_immutable_inputs_sha256=hashes,extension_destinations=26,extension_added_pairs=len(add),extension_all_origins=True,extension_source_shortfalls_sha256=sha(SHORT),extension_source_shortfalls_path=str(SHORT.relative_to(REPO)),extension_qa_sha256=sha(OUT/'matrix_verification.json'),extension_seconds=round(time.monotonic()-start,3),this_namespace='word_ci_extension360')
 dump('routing_receipt.json',newreceipt);print(json.dumps({'status':'COMPUTED','new_pairs':len(add),'combined_pairs':manifest['rows'],'manifest_sha256':newreceipt['output_manifest_sha256'],'seconds':newreceipt['extension_seconds']}),flush=True)
if __name__=='__main__':main()
