from pathlib import Path
import json,gzip,re,collections,hashlib
import pandas as pd
R=Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=Path(__file__).parent;P=E/'cached_missing2010_dated_source_mass_20261008';f=pd.read_csv(P/'current44_disjoint_missing2010.csv.gz',dtype={'current_okato':str,'current_oktmo':str},keep_default_na=False);exclude=set();pins={str(P/'current44_disjoint_missing2010.csv.gz'):hashlib.sha256((P/'current44_disjoint_missing2010.csv.gz').read_bytes()).hexdigest()}
for p in [P/'accepted_identity_edge_delta.csv',P/'accepted_qualified_native_source_ID_credit_union.csv',E/'native2010_whole_region_name_type_mass_20261008/accepted_source_binding_witness.csv.gz',E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'working_full_chain_20261007/complete_publisher_partition_members.csv',E/'working_full_chain_20261007/complete_territorial_scope_constituents.csv',E/'working_full_chain_20261007/named_merger_lineage_constituents.csv',E/'working_full_chain_20261007/direct_inclusion_transformation_path_native_credit_union.csv']:
 if p.exists():
  z=pd.read_csv(p,dtype=str,keep_default_na=False);pins[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
  for c in z:
   if 'source_record_id' in c:exclude.update(z[c])
f=f[~f.current_source_record_id.isin(exclude)&~f.native2002_source_record_id.isin(exclude)].copy();wanted={q for v in f.own_QIDs_json for q in json.loads(v)};paths=set()
for d in [P,E/'temporal_missing2002_all_components_20261008',E/'own_uncached2002_secondary_scope_20261008']:
 for name in ['inventory_receipt.json','receipt.json','queue_receipt.json']:
  p=d/name
  if p.exists():
   r=json.load(open(p));paths.update(Path(v) for v in r.get('input_pins',{}) if v.endswith('.json')or v.endswith('.json.gz'))
for folder in ['/workspace/settlements-raw/data/raw/wikidata_entities_full','/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007','/workspace/settlements-work/additional_uncached_census_histories_20261008','/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007','/workspace/settlements-work/own_dated2002_secondary_scope_20261008','/workspace/settlements-work/own_uncached2002_secondary_scope_20261008']:
 paths.update(Path(folder).glob('*.json.gz'))
cached=set();labels={};labelpaths={};rawpins={}
for p in sorted(paths):
 if not p.exists():continue
 try:b=p.read_bytes();d=json.loads(gzip.decompress(b)if p.name.endswith('.gz')else b);es=d.get('entities',d.get('payload',{}).get('entities',{}))
 except:continue
 if not isinstance(es,dict):continue
 for q,e in es.items():
  if not isinstance(e,dict):continue
  label=e.get('labels',{}).get('ru',{}).get('value','')
  if label:labels[q]=label;labelpaths[q]=str(p)
  if q in wanted:cached.add(q);rawpins[str(p)]=hashlib.sha256(b).hexdigest()
weights={};qcomponents=collections.defaultdict(list)
for a in f.to_dict('records'):
 for q in json.loads(a['own_QIDs_json']):
  if q in cached or not re.fullmatch('Q[1-9][0-9]*',q):continue
  weights[q]=max(weights.get(q,0),a['population2002']+a['population2021']);qcomponents[q].append(a['current_source_record_id'])
ranked=sorted(weights,key=lambda q:(-weights[q],q));trial=ranked[:300];settrial=set(trial);f['uncached_QIDs_json']=f.own_QIDs_json.map(lambda v:json.dumps([q for q in json.loads(v)if q in settrial]));trialf=f[f.uncached_QIDs_json.ne('[]')].copy();trialf.to_csv(O/'uncached_current44_trial_queue.csv.gz',index=False,compression={'method':'gzip','mtime':0});f.to_csv(O/'remaining_uncached_cohort.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame([{'qid':q,'native_02_21_population_priority_weight':weights[q],'current_source_record_IDs_json':json.dumps(qcomponents[q]),'trial_requested':q in settrial}for q in ranked]).to_csv(O/'ranked_uncached_QIDs.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'request_QIDs.json').write_text(json.dumps(trial));(O/'cached_reference_labels.json').write_text(json.dumps(labels,ensure_ascii=False));(O/'cached_reference_label_paths.json').write_text(json.dumps(labelpaths));rec={'baseline_inventory_stage':44,'already_accepted_or_scoped_source_IDs_excluded':len(exclude),'remaining_components':len(f),'wanted_QIDs':len(wanted),'already_cached_QIDs':len(cached),'uncached_QIDs':len(ranked),'trial_QIDs':len(trial),'trial_components':len(trialf),'trial_existing_native2002_population':int(trialf.population2002.sum()),'trial_existing_native2021_population':int(trialf.population2021.sum()),'input_pins':pins|rawpins,'output_pins':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in O.glob('*.csv.gz')}};(O/'queue_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in rec.items()if k not in ['input_pins','output_pins']},ensure_ascii=False))
