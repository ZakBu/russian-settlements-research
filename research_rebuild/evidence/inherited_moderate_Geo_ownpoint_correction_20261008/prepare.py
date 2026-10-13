import json,gzip,re,sys,collections
from pathlib import Path
import pandas as pd,duckdb
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');E=O.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
F=pd.read_csv(O/'candidate_moderate_histories.csv.gz',keep_default_na=False);obs=pd.read_parquet(O/'frozen_moderate_observations.parquet').set_index('source_record_id');active=json.load(gzip.open(O/'frozen_active_point_uses.json.gz','rt'))
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet');C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');DBF=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
pins={str(p):sha(p) for p in [RAW,W,H,C,DBF,O/'prepare.py',O/'frozen_working_state58.py',O/'candidate_moderate_histories.csv.gz',O/'frozen_moderate_observations.parquet',O/'frozen_active_point_uses.json.gz']}
# Exclude all component members if any member is a recovered or newly admitted carrier.
excluded=set()
for pp in [E/'native_mass_raw_roster_point_corrections_20261008/fullraw_own_code_point_recovery_witnesses.csv.gz',E/'combined_ownpoint_correction_application_20261008/accepted_point_use_delta.csv.gz',E/'remaining_native_spatial_literal_mass_20261008/accepted_point_use_delta.csv.gz']:
 pins[str(pp)]=sha(pp);a=pd.read_csv(pp,keep_default_na=False)
 if 'point_recovered' in a:a=a[a.point_recovered.astype(str).str.lower().eq('true')]
 for col in ['source_record_id','target_source_record_id']:
  if col in a:excluded.update(a[col])
 for col in ['affected_current_and_exact_clone_source_IDs_json']:
  if col in a:
   for v in a[col]:excluded.update(json.loads(v))
# All raw regional rivals; no selected-only filtering.
def nm(v):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',normalize(re.sub(r'\s*\([^)]*\)\s*$','',str(v)))).split())
def bare(v):return nm(re.sub(r'^(?:город|село|деревня|пос[её]лок(?: городского типа| сельского типа)?|хутор|станица|аул|станция|разъезд|слобода|рабочий поселок)\s+','',normalize(v)))
def parish(v):
 v=nm(re.sub(r'\b(?:сельское поселение|сельсовет|сельская администрация|муниципальное образование)\b',' ',normalize(v)))
 if v.endswith('ское'):v=v[:-2]+'ий'
 return v
c=duckdb.connect(config={'threads':1});raw=c.execute('select row_number() over() rn,object_level,object_name,oktmo,region,mun_upper,mun_lower,settlement_type_full_dadata,settlement_dadata,settlement_fias_id_dadata,fias_id_dadata,fias_level_dadata,okato_dadata,oktmo_dadata,latitude_dadata,longitude_dadata from read_parquet(?)',[str(RAW)]).fetchdf();h=c.execute('select * from read_parquet(?)',[str(H)]).fetchdf();cl=c.execute('select * from read_parquet(?)',[str(C)]).fetchdf();c.register('targets',F[['source_record_id_2021']].rename(columns={'source_record_id_2021':'source_record_id'}));w=c.execute('select w.* from read_parquet(?) w join targets t using(source_record_id)',[str(W)]).fetchdf();c.close()
raw['n']=raw.object_name.map(bare);raw['county']=raw.mun_upper.map(county_key);raw=raw.set_index('rn');counties={z.historical_okato[:5]:county_key(z.name) for z in cl.itertuples() if z.is_settlement_raw=='f' and len(z.historical_okato)==8 and z.historical_okato.endswith('000') and 'район' in normalize(z.name)}
cl['n']=cl.name.map(bare);cl['county']=cl.historical_okato.str[:5].map(counties).fillna('');clnp=cl[cl.is_settlement_raw.eq('t')];geo={str(z['historical_okato_2009_raw']):z for z in h.to_dict('records') if z.get('historical_name_exact') and z.get('historical_type_exact') and z.get('historical_code_structure_compatible') and not z.get('is_deleted')}
rawidx=collections.defaultdict(list)
for z in raw[raw.object_level.eq('Населенный пункт')].to_dict('index').values():rawidx[(z['n'],z['county'],str(z['region']))].append(z)
wiki=collections.defaultdict(list)
for q in w.to_dict('records'):
 if not q['wikidata_truthy_exact_p764_match'] or q['entity_competition_across_tsv_or_truthy']:continue
 if not any(bare(t)==bare(q['source_name']) for t in json.loads(q['wikidata_tsv_ru_labels_json'])):continue
 p31=json.loads(q['wikidata_truthy_p31_claims_json']);coord=json.loads(q['wikidata_truthy_p625_claims_json']);codes=json.loads(q['wikidata_truthy_exact_p764_claims_json'])
 if not any(v['value_qid'] in {'Q5084','Q532','Q192287','Q515','Q3957','Q486972','Q2023000'} for v in p31):continue
 xy={(v['latitude'],v['longitude']) for v in coord if v.get('wgs84_valid')}
 if len(xy)!=1 or not codes:continue
 q.update(verified_xy=next(iter(xy)),p31=p31,coord=coord,codes=codes);wiki[q['source_record_id']].append(q)
# Exact raw Wikidata property rows reopened in one pass per cached file.
need=collections.defaultdict(dict)
for arr in wiki.values():
 for q in arr:
  for prop,a in [('P31',q['p31']),('P625',q['coord']),('P764',q['codes'])]:
   for v in a:need[v['source_file']][int(v['line_number'])]=(q['wikidata_qid'],prop,v)
verified={}
for fn,lines in need.items():
 p=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/fn;pins[str(p)]=sha(p)
 with gzip.open(p,'rt') as stream:
  for ln,line in enumerate(stream,1):
   if ln in lines:
    v=json.loads(line);qid,prop,wit=lines[ln];verified[(fn,ln)]=v.get('item','').rsplit('/',1)[-1]==qid and v.get('property','').rsplit('/',1)[-1]==prop and (prop!='P764' or str(v['value'])==str(wit['value_exact_digits']))
   if ln>=max(lines):break
holds=[];reject=[];points=[];witness=[];rivals=[]
for z in F.to_dict('records'):
 ids=[z['source_record_id_'+str(y)] for y in [2002,2010,2021]];sid=ids[2];own=raw.loc[int(sid.rsplit(':',1)[1])];cur=active[sid];row=obs.loc[sid];names={bare(obs.loc[i].settlement_name) for i in ids};reason='';q=None;anchor=None;route=''
 if set(ids)&excluded:reason='Excluded entire newly recovered/admitted component'
 rr=rawidx[(own.n,own.county,str(own.region))];rivals.append({'component_root':z['component_root'],'kind':'all_primary2021_raw_county_namesakes','witnesses_json':json.dumps(rr,ensure_ascii=False,default=str)})
 if not reason and len({str(a['oktmo']) for a in rr})!=1:reason='Actual raw2021 same-county own-name rivals'
 qs=[a for a in wiki[sid] if str(a['source_oktmo_exact_digits'])==str(own.oktmo) and bare(a['source_name'])==bare(row.settlement_name) and all(verified.get((v['source_file'],int(v['line_number'])),False) for arr in [a['p31'],a['coord'],a['codes']] for v in arr) and distance_km(a['verified_xy'],(cur['latitude'],cur['longitude']))<=5]
 if not reason and len(qs)==1:
  q=qs[0];anchor=q['verified_xy'];route='raw_own_Wikidata_P764_P31_P625';coord=q['coord'][0];origin=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/coord['source_file'];locator=f"qid={q['wikidata_qid']};P625_line1based={coord['line_number']}";code=q['wikidata_qid']
 elif not reason:
  exact=str(own.oktmo)==str(own.oktmo_dadata) and len(str(own.oktmo))==11;typed=own.fias_level_dadata in ['6','4'] and bool(own.fias_id_dadata) and bare(own.settlement_dadata)==bare(row.settlement_name) and nm(own.settlement_type_full_dadata)==nm(row.settlement_type);xy=(own.latitude_dadata,own.longitude_dadata)
  if exact and typed and pd.notna(xy[0]) and pd.notna(xy[1]) and distance_km(xy,(cur['latitude'],cur['longitude']))<=5:
   competitors=raw[raw.object_level.eq('Населенный пункт')&raw.fias_id_dadata.eq(own.fias_id_dadata)&~raw.oktmo.eq(own.oktmo)]
   if len(competitors):reason='Raw FIAS ID also binds other native own code'
   else:anchor=xy;route='actual_raw2021_exact_own_OKTMO_typed_FIAS_NP';origin=RAW;locator=f'parquet_row_1based={own.name};latitude_dadata,longitude_dadata';code=sid
  else:reason='Current own coded typed physical point not independently confirmed'
 targets=[]
 if not reason:
  for oldid in ids[:2]:
   p=active[oldid];d=distance_km(anchor,(p['latitude'],p['longitude']));isgeo='geo' in str(p.get('point_origin_kind','')).lower() and 'geonames' not in str(p.get('point_origin_kind','')).lower()
   if d<=5:continue
   if not isgeo:reason='Conflicting old point is not a Geo2011 claim';break
   m=re.search(r'(\d{11})',str(p.get('coordinate_source_record_id','')));a=geo.get(m.group(1)) if m else None
   if not a or bare(a['name']) not in names:reason='Old Geo own raw code/name/type binding unresolved';break
   county=counties.get(a['historical_okato_2009_raw'][:5],'');oldrow=obs.loc[oldid];historic=county_key(oldrow.district_raw);compatible=county==own.county or county==historic or str(a['historical_okato_2009_raw'])==str(own.okato_dadata)
   allr=clnp[clnp.n.eq(bare(a['name']))&clnp.county.eq(county)];rivals.append({'component_root':z['component_root'],'target_source_record_id':oldid,'kind':'all_raw_classifier_county_namesakes','witnesses_json':allr.to_json(orient='records',force_ascii=False)})
   if not compatible or not county and str(a['historical_okato_2009_raw'])!=str(own.okato_dadata):reason='Independent old source county/current own context incompatible';break
   if allr.historical_okato.nunique()!=1 and str(a['historical_okato_2009_raw'])!=str(own.okato_dadata):reason='Actual historical same-county namesakes without exact own code tie-break';break
   targets.append((oldid,p,a,d))
 if not reason and not targets:reason='No eligible old Geo use outside own current representative radius'
 if reason:holds.append({'component_root':z['component_root'],'native2021_source_record_id':sid,'native2021_name':row.settlement_name,'population_2021':row.population,'reason':reason});continue
 for oldid,p,a,d in targets:
  ledger=Path(p['point_ledger_path']);pins[str(ledger)]=sha(ledger);reject.append({'target_source_record_id':oldid,'rejection_status':'reviewed_superseded_representative_point_only','old_latitude':p['latitude'],'old_longitude':p['longitude'],'origin_ledger':str(ledger),'origin_ledger_sha256':pins[str(ledger)],'reason':'Superseded Geo2011 representative coordinate by independently coded own current representative point on already accepted stable three-year identity; not a historical census measurement','case':sid,'old_coordinate_claim_retained_as_alternative':True})
  points.append({'target_source_record_id':oldid,'latitude':anchor[0],'longitude':anchor[1],'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':code,'point_origin_file':str(origin),'point_origin_sha256':pins[str(origin)],'point_origin_locator':locator,'point_origin_kind':'independent_current_own_coded_representative_point_retrospective_'+route,'coordinate_binding_rule':'Already accepted three-year own-place continuity; exact raw current NP code/type/name and retained all source county rivals; historic coded own leaf/code/context; independently verified current coded representative point replaces Geo2011 representative coordinate','point_use_inference':'own_current_representative_point_reused_by_accepted_place_continuity','historical_census_coordinate_asserted':False,'historical_boundary_comparability':'UNKNOWN','case':sid})
  witness.append({'target_source_record_id':oldid,'current_native_source_record_id':sid,'current_native_name':row.settlement_name,'route':route,'old_distance_to_independent_current_km':d,'all_current_county_rivals':len(rr),'old_raw_classifier_code':a['historical_okato_2009_raw'],'old_raw_classifier_county':counties.get(a['historical_okato_2009_raw'][:5],''),'native_old_printed_county':obs.loc[oldid].district_raw,'old_historic_geo_code_equals_current_raw_own_okato':str(a['historical_okato_2009_raw'])==str(own.okato_dadata),'old_geo_classifier_county_equals_current_source_county':counties.get(a['historical_okato_2009_raw'][:5],'')==own.county,'old_geo_classifier_county_equals_historic_source_county':counties.get(a['historical_okato_2009_raw'][:5],'')==county_key(obs.loc[oldid].district_raw),'old_active_coordinate_equals_raw_Geo_record':(p['latitude'],p['longitude'])==(a['latitude_from_lat'],a['longitude_from_long']),'current_raw_county':own.mun_upper,'current_raw_own_oktmo':own.oktmo,'current_raw_provider_oktmo':own.oktmo_dadata,'own_current_entity':q['wikidata_qid'] if q else '', 'own_current_wiki_claims_json':json.dumps({p:q[p] for p in ['p31','coord','codes']} if q else {},ensure_ascii=False),'accepted_identity_preserved':True,'known_relocation_event_found':False,'Geo2011_is_historic_census_measurement':False})
for fn,a,cols in [('point_use_rejections.csv.gz',reject,['target_source_record_id','rejection_status','old_latitude','old_longitude','origin_ledger','origin_ledger_sha256']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('own_current_point_source_witnesses.csv.gz',witness,None),('all_raw_source_roster_rivals.csv.gz',rivals,None),('holds.csv.gz',holds,None)]:pd.DataFrame(a,columns=cols).to_csv(O/fn,index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
r={'baseline_stage':58,'status':'Source-positive representative-point supersession ready for independent replay','histories_reviewed':len(F),'corrected_histories':len({p['case'] for p in points}),'point_rejections':len(reject),'accepted_replacement_uses':len(points),'routes':dict(collections.Counter(a['route'] for a in witness)),'hold_reasons':dict(collections.Counter(a['reason'] for a in holds)),'population_2021_corrected_histories':int(F[F.source_record_id_2021.isin({p['case'] for p in points})].population_2021.sum()),'input_pins':pins,'output_pins':{fn:sha(O/fn) for fn in ['point_use_rejections.csv.gz','accepted_point_use_delta.csv.gz','own_current_point_source_witnesses.csv.gz','all_raw_source_roster_rivals.csv.gz','holds.csv.gz']},'identity_edges_changed':False,'raw_source_counts_types_codes_preserved':True,'historical_boundary_comparability':'UNKNOWN'};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
