from pathlib import Path
import pandas as pd,json,re,gzip,hashlib,datetime,collections,duckdb,time,resource
O=Path(__file__).parent;PACK=O.parent;E=PACK.parent;B=E/'main_axis_residual_application66_20261008';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
LF=[E/'largest_available_year_lifecycle_round2_20261008/accepted_lifecycle_events.csv',E/'largest_lifecycle_residual_20261008/accepted_lifecycle_events.csv',B/'g17_accepted_lifecycle_event.csv'];OF=[E/'largest_available_year_lifecycle_round2_20261008/accepted_own_sourceyear_observations.csv',E/'largest_lifecycle_residual_20261008/accepted_own_sourceyear_observations.csv',B/'g17_accepted_own_sourceyear_observation.csv'];EX=E/'absorbed_large_direct_events_followup_20261008/literal_own_inclusion_source_excerpts.txt';events=set()
for p in OF:
 f=pd.read_csv(p,dtype=str,keep_default_na=False);events.update(f.source_record_id)
f=pd.read_csv(O/'accepted_regional_unique_source_evidence.csv.gz',dtype=str,keep_default_na=False);allcur=pd.read_csv(PACK/'county_all_positive_current/all_current_ownpoint_positive_residual_actual66.csv.gz',dtype=str,keep_default_na=False)
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
coverage={'scope':'limited explicit accepted lifecycle corpus plus source-bound cached inclusion hardcases and P571 claims in chosen currentpoint raw Wikidata files; not complete knownhistory or all cached article chronology','accepted_typed_lifecycle_source_UIDs':sorted(events),'all_current_residual_targets_checked':len(allcur),'scoped_known_inclusion_current_matches':knownmatches,'county_admissions_checked':len(f),'county_admission_known_lifecycle_exclusions':len(held),'point_origin_Wikidata_raw_files_scanned':len(files),'cached_P571_claims_in_chosen_point_sources':dict(p571),'cached_P571_after_historic_census_holds':birthholds,'provider_registration_dates_not_physical_NP_birth':True,'composer_all_typed_lifecycle_endpoint_SID_validation_required':True,'input_pins':{str(p):sha(p) for p in LF+OF+[EX]+[Path(fn) for fn in files]}};(O/'scoped_lifecycle_guard_coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
seed='physical_NP_status_bridge_20261008_fixed5_v1';f['sample_rank']=[hashlib.sha256((seed+'|'+a+'|'+b).encode()).hexdigest() for a,b in zip(f.current_source_record_id,f.historic_source_record_id)];sample=f.sort_values('sample_rank').head(5);sample.to_csv(O/'fixed5_source_review_sample.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'fixed5_selection_receipt.json').write_text(json.dumps({'seed':seed,'selection':'five SHA256(seed|currentUID|historicUID)-ranked accepted county/parish source witnesses','rows':len(sample)}))
# Conditional full3 finite known/ownpoint-complete UID projection on actual66, combined regional+county packets.
REG=PACK/'regional_unique_all_residual_rule';COUNTY=PACK/'county_scoped_admission';ef=pd.concat([pd.read_csv(REG/'accepted_identity_edge_delta.csv.gz',dtype=str,keep_default_na=False),pd.read_csv(COUNTY/'accepted_identity_edge_delta.csv.gz',dtype=str,keep_default_na=False),pd.read_csv(O/'accepted_identity_edge_delta.csv.gz',dtype=str,keep_default_na=False)],ignore_index=True);pe=pd.concat([pd.read_csv(REG/'accepted_point_use_delta.csv.gz',dtype=str,keep_default_na=False),pd.read_csv(COUNTY/'accepted_point_use_delta.csv.gz',dtype=str,keep_default_na=False),pd.read_csv(O/'accepted_point_use_delta.csv.gz',dtype=str,keep_default_na=False)],ignore_index=True);c=duckdb.connect();ends=set(ef.from_source_record_id)|set(ef.to_source_record_id);c.register('ee',pd.DataFrame({'source_record_id':list(ends)}));roots=c.execute('select distinct s.root from read_parquet(?) s join ee using(source_record_id)',[str(B/'applied_state_observations.parquet')]).fetchdf();c.register('rr',roots);d=c.execute('select s.source_record_id,s.root,s.census_year,s.population,p.has_own_point from read_parquet(?) s join rr using(root) join read_csv_auto(?) p using(source_record_id)',[str(B/'applied_state_observations.parquet'),str(B/'applied_component_snapshot.csv.gz')]).fetchdf();c.close();parents={x:x for x in roots.root};sr=d.set_index('source_record_id').root.to_dict()
def find(x):
 while parents[x]!=x:parents[x]=parents[parents[x]];x=parents[x]
 return x
for z in ef.to_dict('records'):parents[find(sr[z['from_source_record_id']])]=find(sr[z['to_source_record_id']])
newpts=set(pe.target_source_record_id);gg=collections.defaultdict(list)
for z in d.to_dict('records'):gg[find(z['root'])].append(z)
gain=collections.Counter();uids=collections.Counter();missing=[]
for rt,ms in gg.items():
 ys={int(z['census_year']) for z in ms};ok=ys=={2002,2010,2021} and all(pd.notnull(z['population']) for z in ms) and all(z['has_own_point'] or z['source_record_id'] in newpts for z in ms)
 if ok:
  for z in ms:gain[int(z['census_year'])]+=float(z['population']);uids[int(z['census_year'])]+=1
 else:missing.append({'root':rt,'years':sorted(ys),'unknown_population_rows':sum(pd.isnull(z['population']) for z in ms),'missing_points':sum(not z['has_own_point'] and z['source_record_id'] not in newpts for z in ms)})
reg=json.loads((COUNTY/'conditional_main_population_projection.json').read_text())['combined_conditional_full3_population_gain_by_year'];add={str(y):gain[y]-reg.get(str(y),0) for y in [2002,2010,2021]};projection={'status':'conditional_scoped_actual66_UF_projection_no_State_no_canonical_application','combined_regional_county_status_edges':len(ef),'combined_retro_point_targets':len(newpts),'combined_conditional_full3_population_gain_by_year':dict(gain),'combined_conditional_new_primary_UIDs_by_year':dict(uids),'incremental_status_bridge_conditional_population_gain_by_year':add,'remaining_partial_or_missing_use_groups':missing,'canonical_replay_required':True};(O/'conditional_main_population_projection.json').write_text(json.dumps(projection,indent=2))

r=json.loads((O/'regional_unique_admission_receipt.json').read_text());r.update(packet_scope='exact all-type region-unique physical railway NP observed census-type variation; no urban-rural municipal or administrative totals admitted',observed_legal_type_change_date='UNKNOWN',lifecycle_guard_exclusions=0,lifecycle_guard_coverage='LIMITED',canonical_replay_required=True,conditional_projection_file=str(O/'conditional_main_population_projection.json'))
for q in [REG/'frozen_asset_manifest.json',COUNTY/'frozen_asset_manifest.json']:
 r['input_pins'][str(q)]=sha(q)
(O/'final_status_bridge_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
files=[p for p in O.iterdir() if p.is_file() and p.name!='frozen_asset_manifest.json'];manifest={'packet':'physical_NP_observed_type_bridge','frozen_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'accepted_edges':len(f),'files':{str(p.resolve()):sha(p) for p in files},'total_bytes':sum(p.stat().st_size for p in files)};(O/'frozen_asset_manifest.json').write_text(json.dumps(manifest,indent=2));print('manifest',sha(O/'frozen_asset_manifest.json'));print('conditional combined',dict(gain),'statusincrement',add);print('guard exclusions',len(held),'birthclaims',dict(p571))
