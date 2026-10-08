from pathlib import Path
import pandas as pd,json,re,gzip,hashlib,datetime,collections,duckdb,time,resource
O=Path(__file__).parent/'final';PACK=O.parent.parent;E=PACK.parent;B=E/'main_axis_residual_application67_20261008';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
LF=[E/'largest_available_year_lifecycle_round2_20261008/accepted_lifecycle_events.csv',E/'largest_lifecycle_residual_20261008/accepted_lifecycle_events.csv',B/'g17_accepted_lifecycle_event.csv'];OF=[E/'largest_available_year_lifecycle_round2_20261008/accepted_own_sourceyear_observations.csv',E/'largest_lifecycle_residual_20261008/accepted_own_sourceyear_observations.csv',B/'g17_accepted_own_sourceyear_observation.csv'];EX=E/'absorbed_large_direct_events_followup_20261008/literal_own_inclusion_source_excerpts.txt';events=set()
for p in OF:
 f=pd.read_csv(p,dtype=str,keep_default_na=False);events.update(f.source_record_id)
f=pd.read_csv(O/'accepted_source_evidence.csv.gz',dtype=str,keep_default_na=False);allcur=pd.read_csv(PACK/'county_all_positive_current/all_current_ownpoint_positive_residual_actual66.csv.gz',dtype=str,keep_default_na=False)
# Explicit source-bound cached inclusion hardcases scoped by proper region and receiving municipality.
hardcases=[('Сокольники','тульская','Новомосковск'),('Росляково','мурманская','Мурманск'),('Гикало','чеченская','Грозный'),('Пурпе','ямало ненецкий','Губкинский'),('Неклюдово','нижегородская','Бор'),('Октябрьский','нижегородская','Бор')]
def simple(s):return ' '.join(re.sub(r'[^а-я0-9 ]',' ',str(s).lower().replace('ё','е')).split())
knownmatches=[]
for z in allcur.to_dict('records'):
 for name,reg,parent in hardcases:
  if simple(z['settlement_name'])==simple(name) and reg in simple(z['region_norm']) and simple(parent) in simple(z['district_raw']):knownmatches.append({'source_record_id':z['source_record_id'],'name':name,'region':z['region_norm'],'county':z['district_raw'],'known_relation':'included_in_receiving_parent','source_file':str(EX),'scoped_name_region_parent_context':True})
known=set(events)|{z['source_record_id'] for z in knownmatches};p571=collections.defaultdict(list);files=collections.defaultdict(set)
for z in f.to_dict('records'):
 p=json.loads(z['current_accepted_physical_point_json']);ref=p['coordinate_source_record_id'];fn=p['point_origin_file']
 if re.fullmatch(r'Q[0-9]+',ref) and 'wikidata' in fn:files[fn].add(ref)
for fn,qs in files.items():
 with gzip.open(fn,'rt') as fh:
  for ln,line in enumerate(fh,1):
   d=json.loads(line);qid=d.get('item','').rsplit('/',1)[-1];prop=d.get('property','').rsplit('/',1)[-1]
   if qid in qs and prop=='P571':p571[qid].append({'file':fn,'sha256':sha(fn),'line':ln,'literal_raw':d})
birthholds=[]
for z in f.to_dict('records'):
 p=json.loads(z['current_accepted_physical_point_json']);qid=p['coordinate_source_record_id'];oldyear=int(z['historic_year'])
 for cl in p571.get(qid,[]):
  val=str(cl['literal_raw'].get('value',''));m=re.search(r'([0-9]{4})-',val)
  if m and int(m.group(1))>oldyear:known.add(z['current_source_record_id']);birthholds.append({'current_source_record_id':z['current_source_record_id'],'historic_source_record_id':z['historic_source_record_id'],'hold':'cached_own_point_source_P571_after_historic_census_requires_lifecycle_scope_review','raw_birth_claim':cl})
held=f[f.current_source_record_id.isin(known)|f.historic_source_record_id.isin(known)];assert len(held)==0,'Positive known event guard requires removing heldedges/pointuses and recalculating conditional main before freeze'
coverage={'scope':'limited explicit accepted lifecycle corpus plus source-bound cached inclusion hardcases and P571 claims in chosen currentpoint raw Wikidata files; not complete knownhistory or all cached article chronology','accepted_typed_lifecycle_source_UIDs':sorted(events),'all_current_residual_targets_checked':len(allcur),'scoped_known_inclusion_current_matches':knownmatches,'next68_admissions_checked':len(f),'next68_admission_known_lifecycle_exclusions':len(held),'point_origin_Wikidata_raw_files_scanned':len(files),'cached_P571_claims_in_chosen_point_sources':dict(p571),'cached_P571_after_historic_census_holds':birthholds,'provider_registration_dates_not_physical_NP_birth':True,'composer_all_typed_lifecycle_endpoint_SID_validation_required':True,'input_pins':{str(p):sha(p) for p in LF+OF+[EX]+[Path(fn) for fn in files]}};(O/'scoped_lifecycle_guard_coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))

seed='next68_temporal_mass_20261008_fixed5_v1';f['sample_rank']=[hashlib.sha256((seed+'|'+a+'|'+b).encode()).hexdigest() for a,b in zip(f.current_source_record_id,f.historic_source_record_id)];sample=f.sort_values('sample_rank').head(4);alias=f[f.current_name.eq('Круглое Поле')];sample=pd.concat([sample,alias]).drop_duplicates(['current_source_record_id','historic_source_record_id']);sample.to_csv(O/'fixed_source_review_sample.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'sample_receipt.json').write_text(json.dumps({'seed':seed,'selection':'four sha-ranked edges plus fixed largest formername sourcebound bridge','rows':len(sample)}))
files=[p for p in O.parent.rglob('*') if p.is_file() and p.name!='frozen_asset_manifest.json'];manifest={'packet':'next68_temporal_mass','baseline':67,'frozen_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'accepted_edges':len(f),'source_input_guard_pins':coverage['input_pins'],'files':{str(p.resolve()):sha(p) for p in files},'total_bytes':sum(p.stat().st_size for p in files)};(O/'frozen_asset_manifest.json').write_text(json.dumps(manifest,indent=2));print('manifest',sha(O/'frozen_asset_manifest.json'),'edges',len(f),'bytes',manifest['total_bytes'])
