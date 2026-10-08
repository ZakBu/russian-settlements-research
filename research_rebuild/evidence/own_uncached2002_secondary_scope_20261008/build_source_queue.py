from pathlib import Path
import sys,json,gzip,re
import pandas as pd
R=Path('/workspace/russian-settlements-research'); E=R/'research_rebuild/evidence';O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
s=load(38);old=E/'temporal_missing2002_all_components_20261008';f=pd.read_csv(old/'disjoint_cached_claim_inventory.csv.gz',dtype={'current_native_okato':str,'current_native_oktmo':str},keep_default_na=False)
credits=set();qcredited=set();pins={str(p):sha(p) for p in s.inputs}
for p in [E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'temporal_missing2002_all_components_20261008/accepted_selected_source_id_credit_union.csv',E/'temporal_missing2002_all_components_20261008/physical_grain_two_hold_followup/accepted_selected_source_id_credit_union.csv',E/'own_dated2002_secondary_scope_20261008/accepted_qualified_native_source_ID_credit_union.csv']:
 if p.exists():
  z=pd.read_csv(p,dtype=str,keep_default_na=False);credits.update(z.source_record_id);pins[str(p)]=sha(p)
future=E/'native_alias_remaining_mass_20261008/all_cached_native2002_context_followup/accepted_identity_edge_delta.csv'
if future.exists():
 z=pd.read_csv(future,dtype=str,keep_default_na=False);pins[str(future)]=sha(future)
 for col in z:
  if 'source_record_id' in col or col in ['left_id','right_id']:credits.update(z[col])
keep=[]
for a in f.to_dict('records'):
 sid=a['current_source_record_id']; nid=a['native2010_source_record_id'];root=s.uf.find(sid)
 if set(s.years[root])!={2010,2021} or sid in credits or nid in credits:continue
 keep.append(a)
f=pd.DataFrame(keep);wanted={q for x in f.own_native_code_QID_candidates_json for q in json.loads(x)}
paths={Path(p) for p in json.load(open(old/'receipt.json'))['input_pins'] if p.endswith('.json.gz') or p.endswith('.json')}
paths.update(Path('/workspace/settlements-work/own_dated2002_secondary_scope_20261008').glob('batch_*.json.gz'))
paths.update(Path('/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007').glob('*.json.gz'))
entities={};labels={};rawpins={}
for p in sorted(paths):
 if not p.exists():continue
 try:b=p.read_bytes();d=json.loads(gzip.decompress(b) if p.name.endswith('.gz') else b)
 except:continue
 es=d.get('entities',d.get('payload',{}).get('entities',{})) if isinstance(d,dict) else {}
 if not isinstance(es,dict):continue
 for q,z in es.items():
  if not isinstance(z,dict):continue
  if z.get('labels',{}).get('ru'):labels[q]=z['labels']['ru']['value']
  if q in wanted:
   if q not in entities or len(z.get('claims',{}).get('P1082',[]))>len(entities[q][0].get('claims',{}).get('P1082',[])):entities[q]=(z,str(p));rawpins[str(p)]=sha(p)
uncached=sorted(q for q in wanted-entities.keys() if re.fullmatch('Q[1-9][0-9]*',q));assert len(uncached)<=540
qset=set(uncached);f['uncached_QIDs_json']=f.own_native_code_QID_candidates_json.map(lambda v:json.dumps([q for q in json.loads(v) if q in qset]));queue=f[f.uncached_QIDs_json.ne('[]')].copy();queue.to_csv(O/'uncached_current38_queue.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'request_QIDs.json').write_text(json.dumps(uncached));(O/'cached_entity_paths.json').write_text(json.dumps({q:p for q,(z,p) in entities.items()}));(O/'cached_reference_labels.json').write_text(json.dumps(labels,ensure_ascii=False));f.to_csv(O/'current38_disjoint_queue.csv.gz',index=False,compression={'method':'gzip','mtime':0});rec={'baseline_stage':38,'active_disjoint_components':len(f),'wanted_QIDs':len(wanted),'already_cached_QIDs':len(entities),'uncached_QIDs':len(uncached),'uncached_components':len(queue),'uncached_native_population2010':int(queue.population2010.sum()),'uncached_native_population2021':int(queue.population2021.sum()),'uncached_max_weight':int(queue.maximum_observed_population_weight.sum()),'input_pins':pins|rawpins,'queue_hash':sha(O/'uncached_current38_queue.csv.gz')};(O/'queue_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in rec.items() if k!='input_pins'},ensure_ascii=False))
