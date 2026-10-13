import sys,json,re,collections
from pathlib import Path
import pandas as pd,duckdb
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');E=O.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from frozen_working_state56 import load
from current_chain_state_20261007 import sha,normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
import current_chain_state_20261007 as state_module
base_sha=sha;hash_cache={}
def sha(path):
 path=Path(path);st=path.stat();key=(str(path),st.st_size,st.st_mtime_ns)
 if key not in hash_cache:hash_cache[key]=base_sha(path)
 return hash_cache[key]
state_module.sha=sha
s=load(56);before=s.metrics();protected=s.obs[['source_record_id','population','population_value_quality']].copy();src=E/'native_singleton_rural_mass_20261008/frozen_finite.py';import importlib.util
sp=importlib.util.spec_from_file_location('ff',src);ff=importlib.util.module_from_spec(sp);sp.loader.exec_module(ff);bf=ff.finite(s)
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet');C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');P=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet');DBF=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
base=E/'baseline_fullraw_point_code_conflict_scan_20261008/explicit_other_published_NP_point_binding_candidates.csv.gz';seven=E/'baseline_fullraw_point_code_conflict_scan_20261008/seven_full3_current_carrier_binding_conflicts.csv';other=pd.read_csv(base,keep_default_na=False);skip=set(pd.read_csv(seven,keep_default_na=False).source_record_id);other=other[~other.source_record_id.isin(skip)];new=pd.read_csv(O/'explicit_other_published_NP_point_binding_candidates.csv.gz',keep_default_na=False);f=pd.concat([new.assign(cohort='source53'),other.assign(cohort='baseline439')],ignore_index=True)
con=duckdb.connect(config={'threads':1});h=con.execute('select * from read_parquet(?)',[str(H)]).fetchdf();cl=con.execute('select * from read_parquet(?)',[str(C)]).fetchdf();raw=con.execute('select row_number() over() as rn,object_level,object_name,oktmo,mun_upper,mun_lower,population,okato_dadata,oktmo_dadata,fias_id_dadata,fias_level_dadata,latitude_dadata,longitude_dadata from read_parquet(?)',[str(RAW)]).fetchdf();con.close();raw=raw.set_index('rn');classifier=cl.set_index('historical_okato');pins={str(p):sha(p) for p in [RAW,H,C,P,DBF,base,seven,src,O/'scan.py',O/'recover.py',*s.inputs]};statecode=O/'frozen_working_state56.py';pins[str(statecode)]=sha(statecode)
ex=E/'direct_old_geokladr_point_reserve_20261007_spatial_review/suggested_raw_point_exclusion_keys.csv';excluded=set(pd.read_csv(ex,dtype=str).raw_own_code);pins[str(ex)]=sha(ex)
def name(v):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',normalize(v)).split())
def parish(v):
 v=normalize(v);v=re.sub(r'\b(?:сельское поселение|сельское|поселение|сельсовет|сельский совет|сельская администрация|муниципальное образование)\b',' ',v);v=name(v)
 # Printed grammatical gender agreement with settlement/council role, retained explicitly.
 if v.endswith('ское'):v=v[:-2]+'ий'
 return v
counties={z.historical_okato[:5]:county_key(z.name) for z in cl.itertuples() if z.is_settlement_raw=='f' and len(z.historical_okato)==8 and z.historical_okato.endswith('000') and 'район' in normalize(z.name)}
parent_names=collections.defaultdict(set)
for z in cl.itertuples():parent_names[z.historical_okato].add(parish(z.name))
parent_map={k:next(iter(v)) for k,v in parent_names.items() if len(v)==1}
valid=h[h.historical_name_exact.fillna(False)&h.historical_type_exact.fillna(False)&h.historical_code_structure_compatible.fillna(False)&~h.is_deleted.fillna(True)&h.is_settlement_raw.eq('t')&h.latitude_from_lat.between(41,82)&h.longitude_from_long.between(19,180)].copy();valid['n']=valid.name.map(name);valid['county']=valid.historical_okato_2009_raw.str[:5].map(counties).fillna('');valid['parish']=valid.historical_okato_2009_raw.str[:8].map(parent_map).fillna('');valid=valid.drop_duplicates(['historical_okato_2009_raw','record_number_1based','latitude_from_lat','longitude_from_long','name','status'])
idx=collections.defaultdict(list);coord=collections.defaultdict(set)
for z in valid.to_dict('records'):
 idx[(z['n'],z['historical_point_modern_region'])].append(z);coord[(z['latitude_from_lat'],z['longitude_from_long'],z['county'],z['historical_point_modern_region'])].add(z['historical_okato_2009_raw'])
W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');pins[str(W)]=sha(W)
c=duckdb.connect(config={'threads':1});c.register('risk',f[['source_record_id']].drop_duplicates());w=c.execute('select w.* from read_parquet(?) w join risk r using(source_record_id)',[str(W)]).fetchdf();c.close();wiki_idx=collections.defaultdict(list)
for q in w.to_dict('records'):
 literal_labels=json.loads(q['wikidata_tsv_ru_labels_json'])
 ownlabel=any(name(re.sub(r'\s*\([^)]*\)\s*$','',label))==name(q['source_name']) for label in literal_labels)
 if not q['wikidata_truthy_exact_p764_match'] or not ownlabel or q['entity_competition_across_tsv_or_truthy']:continue
 p31=json.loads(q['wikidata_truthy_p31_claims_json']);coords=json.loads(q['wikidata_truthy_p625_claims_json']);codes=json.loads(q['wikidata_truthy_exact_p764_claims_json'])
 if not any(k['value_qid'] in {'Q5084','Q532','Q192287','Q515','Q3957','Q486972','Q2023000'} for k in p31):continue
 xy={(k['latitude'],k['longitude']) for k in coords if k.get('wgs84_valid')}
 if len(xy)!=1 or not codes:continue
 point=coords[0];origin=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/point['source_file'];pins[str(origin)]=sha(origin)
 # Reopen each exact cited raw property row, rather than accepting candidate metadata as admission.
 import gzip
 needed={int(k['line_number']):(prop,k) for prop,arr in [('P625',coords),('P764',codes),('P31',p31)] for k in arr if k['source_file']==point['source_file']};found={}
 with gzip.open(origin,'rt') as stream:
  for ln,line in enumerate(stream,1):
   if ln in needed:found[ln]=json.loads(line)
   if ln>=max(needed):break
 assert all(found[ln].get('item','').rsplit('/',1)[-1]==q['wikidata_qid'] and found[ln].get('property','').rsplit('/',1)[-1]==prop for ln,(prop,k) in needed.items())
 assert all(str(found[int(k['line_number'])]['value'])==str(q['source_oktmo_exact_digits']) for k in codes if k['source_file']==point['source_file'])
 assert any(prop=='P764' for prop,k in needed.values()) and any(prop=='P31' for prop,k in needed.values())
 q['verified_own_point_origin']=str(origin);q['verified_own_point_origin_sha256']=pins[str(origin)];q['verified_own_point_locator']='qid='+q['wikidata_qid']+';P625line1based='+str(point['line_number']);q['verified_latitude'],q['verified_longitude']=next(iter(xy));wiki_idx[q['source_record_id']].append(q)
members=collections.defaultdict(list)
for sid in s.by_id.index:members[s.uf.find(sid)].append(sid)
reject=[];points=[];witness=[];holds=[];original=dict(s.point_rows)
for sid,g in f.groupby('source_record_id',sort=False):
 if sid not in original:holds.append({'source_record_id':sid,'reason':'current point already absent'});continue
 z=g.iloc[0].to_dict();row=s.by_id.loc[sid];pp=original[sid];own=raw.loc[int(sid.rsplit(':',1)[1])];dc=county_key(own.mun_upper);pc=parish(own.mun_lower);allgeo=idx.get((name(row.settlement_name),row.region_norm),[]);typed=[a for a in allgeo if normalize(a['status']) in {'деревня','село','поселок сельского типа','хутор','станица','город','поселок городского типа','станция','разъезд','слобода'} and normalize(a['status']).replace('поселок сельского типа','поселок')==normalize(row.settlement_type).replace('ё','е')];chosen=[a for a in typed if a['county']==dc and (a['parish']==pc or str(a['oktmo_2011_raw'])==str(own.oktmo)[:8])];safe=[]
 for a in chosen:
  key=(a['latitude_from_lat'],a['longitude_from_long'],a['county'],a['historical_point_modern_region']);cluster=coord[key]
  if a['historical_okato_2009_raw'] in excluded or len(cluster)!=1:continue
  safe.append(a)
 recovery=safe[0] if len(safe)==1 else None
 wiki=wiki_idx.get(sid,[]);ownwiki=wiki[0] if len(wiki)==1 else None
 comp=members[s.uf.find(sid)];affected=[]
 xy=(ownwiki['verified_latitude'],ownwiki['verified_longitude']) if ownwiki else (recovery['latitude_from_lat'],recovery['longitude_from_long']) if recovery else None
 if xy and any(distance_km(xy,(original[i]['latitude'],original[i]['longitude']))>5 for i in comp if i in original and i!=sid and str(original[i].get('coordinate_source_record_id',''))!=str(pp.get('coordinate_source_record_id',''))):ownwiki=None;recovery=None;xy=None
 for target in comp:
  if target not in original:continue
  old=original[target]
  if target!=sid and not (str(old.get('coordinate_source_record_id',''))==str(pp.get('coordinate_source_record_id','')) and (old['latitude'],old['longitude'])==(pp['latitude'],pp['longitude'])):continue
  ledger=old['point_ledger_path'];pins[ledger]=sha(Path(ledger));affected.append(target);reject.append({'target_source_record_id':target,'rejection_status':'reviewed_rejected_coordinate_claim_only','old_latitude':old['latitude'],'old_longitude':old['longitude'],'origin_ledger':ledger,'origin_ledger_sha256':pins[ledger],'case':sid,'reason':'Explicit provider code belongs to another actual published2021 own NP with shared FIAS/coordinates; active current provider claim or exact inherited clone held pending independent own physical point; identity/source observations unchanged','rejected_coordinate_source_record_id':old.get('coordinate_source_record_id',''),'rejected_provider_code':z['provider_own_code'],'native_own_code':z['native_own_code'],'actual_provider_point_origin_file':old.get('point_origin_file',''),'actual_provider_point_origin_sha256':old.get('point_origin_sha256',''),'actual_provider_point_origin_locator':old.get('point_origin_locator',''),'actual_provider_point_origin_kind':old.get('point_origin_kind','')})
  if ownwiki:
   q=ownwiki;points.append({'target_source_record_id':target,'latitude':q['verified_latitude'],'longitude':q['verified_longitude'],'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':q['wikidata_qid'],'point_origin_file':q['verified_own_point_origin'],'point_origin_sha256':q['verified_own_point_origin_sha256'],'point_origin_locator':q['verified_own_point_locator'],'point_origin_kind':'independent_truthy_own_native2021_P764_P31_P625_bound_point','coordinate_binding_rule':'Reopened raw cached own physical NP P31, exact complete own native2021 OKTMO P764, single own P625 coordinate; exact own label; all entity competitions retained and blocked; wrong provider ID rejected separately; correct coded own point replaces wrong raw provider point and exact historical clones','point_use_inference':'own_current_representative_point_reused_by_source_supported_continuity','historical_census_coordinate_asserted':False,'rejected_external_provider_ID_binding':pp.get('coordinate_source_record_id',''),'native2021_own_oktmo':z['native_own_code'],'case':sid})
  elif recovery:
   a=recovery;points.append({'target_source_record_id':target,'latitude':a['latitude_from_lat'],'longitude':a['longitude_from_long'],'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':a['historical_okato_2009_raw'],'point_origin_file':str(DBF),'point_origin_sha256':pins[str(DBF)],'point_origin_locator':f"record1based={int(a['record_number_1based'])};LAT/LONG;code={a['historical_okato_2011_raw']}",'point_origin_kind':'independent_raw_own_coded_GeoKLADR2011_locality_point','coordinate_binding_rule':'Exact own historical NP classifier name/type/code plus independently printed current county and own subordinate council lexical context or exact8digit municipal code; proper raw own NP Geo2011 record; distinct raw own-code coordinate in compatible county/region; excluded wrong raw point keys rejected; no provider ID reuse and no population identity gate','point_use_inference':'coded_historical_own_locality_representative_point_reused_by_source_supported_continuity','historical_census_coordinate_asserted':False,'rejected_external_provider_ID_binding':pp.get('coordinate_source_record_id',''),'native2021_own_oktmo':z['native_own_code'],'case':sid})
 witness.append({**z,'current_own_parish_normalized':pc,'current_own_county_normalized':dc,'all_regional_historical_name_geo_candidates':len(allgeo),'own_county_parish_geo_candidates':len(chosen),'safe_own_distinct_coded_geo_candidates':len(safe),'candidate_geo_witnesses_json':json.dumps(chosen,ensure_ascii=False,default=str),'accepted_own_geo_witness_json':json.dumps(recovery,ensure_ascii=False,default=str),'affected_current_and_exact_clone_source_IDs_json':json.dumps(affected),'accepted_own_Wikidata_witness_json':json.dumps(ownwiki,ensure_ascii=False,default=str),'point_recovered':bool(recovery or ownwiki),'identity_rejected':False})
for filename,data,cols in [('point_use_rejections.csv.gz',reject,['target_source_record_id','rejection_status','old_latitude','old_longitude','origin_ledger','origin_ledger_sha256']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('fullraw_own_code_point_recovery_witnesses.csv.gz',witness,None),('recovery_holds.csv.gz',holds,['source_record_id','reason'])]:
 (pd.DataFrame(data) if data else pd.DataFrame(columns=cols)).to_csv(O/filename,index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
s.reject_point_uses(O/'point_use_rejections.csv.gz');s.add_deltas(point_paths=[O/'accepted_point_use_delta.csv.gz']);af=ff.finite(s);pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);outputs=['point_use_rejections.csv.gz','accepted_point_use_delta.csv.gz','fullraw_own_code_point_recovery_witnesses.csv.gz','recovery_holds.csv.gz'];receipt={'baseline_stage':56,'status':'independent own-code correction/rejection batch State API replayed; raw identity/source values unchanged','source53_conflict_carriers':new.source_record_id.nunique(),'baseline439_conflict_carriers':other.source_record_id.nunique(),'delegated_seven_baseline_full3_ids':sorted(skip),'before_finite':bf,'after_finite':af,'net_finite_population_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']},'rejection_uses':len(reject),'accepted_replacement_point_uses':len(points),'recovered_current_carriers':sum(w['point_recovered'] for w in witness),'held_current_carriers':sum(not w['point_recovered'] for w in witness),'input_pins':pins,'output_pins':{n:sha(O/n) for n in outputs},'population_quality_values_unchanged':True,'no_identity_edge_rejected':True};(O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins','delegated_seven_baseline_full3_ids']},ensure_ascii=False))
