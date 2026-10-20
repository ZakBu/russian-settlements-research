#!/usr/bin/env python3
"""Independently reconstruct all eligible alternatives for 20 fixed routed origins.
Streams compactparts; does not import model/reconstruction helpers or materialize
national triplets. Validates rawtop2/probabilities separately from protected cores.
"""
from pathlib import Path
import argparse,hashlib,json
import numpy as np,pandas as pd,pyarrow.parquet as pq
from require_model_snapshot import require_snapshot
H=Path(__file__).resolve().parent;ROOT=H.parent;T=ROOT/'transport'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--model',default='output_2021_restricted_baseline');ap.add_argument('--inputs');ap.add_argument('--code');a=ap.parse_args();M=ROOT/'model'/a.model;cfgpath=Path(a.inputs) if a.inputs else ROOT/'model'/('model_inputs_2021_restricted_inclusive.json' if 'inclusive' in a.model else 'model_inputs_2021_restricted.json');run=json.loads((M/'run_receipt.json').read_text())
 if not run['status'].startswith('COMPUTED'):raise SystemExit('WAIT_ACTUAL_MODEL_COMPUTED')
 require_snapshot(M,cfgpath,Path(a.code) if a.code else ROOT/'model/run_word_model.py',['candidate_centers.parquet','memberships.parquet'])
 cfg=json.loads(cfgpath.read_text());manifest_config=Path(cfg['travel_manifest']);manifest_config=manifest_config if manifest_config.is_absolute() else H.parents[2]/manifest_config;TD=manifest_config.parent;rp=TD/'routing_receipt.json';rr=json.loads(rp.read_text())
 if rr['status']!='COMPUTED':raise SystemExit('WAIT_ATOMIC_ROUTING_COMPUTED')
 mp=manifest_config;manifest=json.loads(mp.read_text());cfg=json.loads(cfgpath.read_text());sources=[mp,rp,cfgpath,M/'candidate_centers.parquet',M/'memberships.parquet',M/'run_receipt.json'];before={str(p):sha(p) for p in sources};assert sha(mp)==rr['output_manifest_sha256'];assert sha(cfgpath)==run['configuration_sha256'];centers=pd.read_parquet(M/'candidate_centers.parquet');members=pd.read_parquet(M/'memberships.parquet').set_index('id');maps=[]
 for key in ['origin_mapping','destination_mapping']:
  inf=manifest[key];p=TD/inf['path'];assert sha(p)==inf['sha256'];d=pd.read_parquet(p);d['id']=d.get('canonical_id',d.id);maps.append(d)
 orig,dest=maps;ordered=orig.sort_values('id');chosen=ordered.iloc[np.linspace(0,len(ordered)-1,20,dtype=int)];selected=chosen.origin_index.to_numpy();providers=centers[centers.intrinsic_empirical_rank.eq(centers.intrinsic_empirical_rank.min())] if cfg.get('initial_assignment_center_scope')=='lowest_empirical_order_only' else centers;mass=providers.set_index('id').own_positive_mass;dm=dest.id.map(mass).to_numpy(float);oc=orig.snap_km.to_numpy()*4;dc=dest.snap_km.to_numpy()*4;pieces=[];limit=cfg['model']['max_travel_minutes']+1e-4
 for part in manifest['parts']:
  for batch in pq.ParquetFile(TD/part['path']).iter_batches(batch_size=1000000,columns=['origin_index','destination_index','network_minutes']):
   oi=batch.column('origin_index').to_numpy();di=batch.column('destination_index').to_numpy();keep=np.isin(oi,selected)&np.isfinite(dm[di]);oi=oi[keep];di=di[keep]
   if not len(oi):continue
   network=batch.column('network_minutes').to_numpy()[keep];minutes=(network+(oc[oi]+dc[di]).astype('float32')).astype('float32');same=orig.iloc[oi].id.to_numpy()==dest.iloc[di].id.to_numpy();minutes[same]=0;valid=np.isfinite(minutes)&(minutes>=0)&(minutes<=limit)
   if valid.any():pieces.append(pd.DataFrame({'origin':orig.iloc[oi[valid]].id.to_numpy(),'destination':dest.iloc[di[valid]].id.to_numpy(),'minutes':minutes[valid],'mass':dm[di[valid]]}))
 edges=pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame(columns=['origin','destination','minutes','mass']);edges['gravity']=edges.mass.astype(float)*np.exp(-edges.minutes.astype(float)/cfg['model']['time_decay_minutes']);edges=edges.sort_values(['origin','gravity','destination'],ascending=[True,False,True]);totals=edges.groupby('origin').gravity.sum();edges['probability']=edges.gravity/(edges.origin.map(totals)+cfg['model']['outside_mass']);checks=[];rows=[]
 def check(name,ok):checks.append({'check':name,'pass':bool(ok)})
 for uid in chosen.id:
  actual=members.loc[uid];g=edges[edges.origin.eq(uid)];check(uid+'_raw_winner',pd.isna(actual.raw_model_center_id) if g.empty else actual.raw_model_center_id==g.iloc[0].destination)
  if len(g):
   top=g.iloc[0];check(uid+'_top_probability',np.isclose(actual.raw_top_probability,top.probability,atol=1e-7,rtol=1e-6));check(uid+'_top_gravity',np.isclose(actual.raw_top_gravity,top.gravity,atol=1e-7,rtol=1e-6));check(uid+'_top_network_minutes',np.isclose(actual.raw_top_travel_minutes,top.minutes,atol=1e-4));check(uid+'_conditional_probability_sum',np.isclose(g.probability.sum()+cfg['model']['outside_mass']/(g.gravity.sum()+cfg['model']['outside_mass']),1.))
  if len(g)>1:check(uid+'_second_winner_and_ratio',actual.second_center_id==g.iloc[1].destination and np.isclose(actual.second_to_first_gravity_ratio,g.iloc[1].gravity/g.iloc[0].gravity,atol=1e-7,rtol=1e-6))
  if not actual.protected_core:
   want=None if g.empty or g.iloc[0].probability<cfg['model']['minimum_choice_probability'] else g.iloc[0].destination;check(uid+'_threshold_assignment',pd.isna(actual.assigned_center_id) if want is None else actual.assigned_center_id==want)
  rows.append({'id':uid,'alternatives':len(g),'protected_core':bool(actual.protected_core)})
 check('all_selected_inputs_stable',before=={p:sha(Path(p)) for p in before});result={'status':'INDEPENDENT_HUFF_RECONSTRUCTION_VERIFIED' if all(c['pass'] for c in checks) else 'RETURN_TO_REPAIR_LOOP','checks':checks,'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'sampled_origins':rows,'sampled_edges':len(edges),'source_sha256':before,'scope':'20equally spaced canonicalIDs amongacceptedroutedorigins; all eligible loworderalternatives reconstructed from everypart. Tests model arithmetic/probability semantics, not observed destination choice.','scientific_final_allowed':False};(H/(a.model+'_huff_independent_sample.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');edges.to_csv(H/(a.model+'_huff_reconstructed_sample.csv.gz'),index=False);print(json.dumps({k:v for k,v in result.items() if k not in ['checks','source_sha256']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
