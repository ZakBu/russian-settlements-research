from pathlib import Path
import sys,json,re,collections,gzip,struct
import pandas as pd,duckdb
O=Path(__file__).parent;E=O.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
ROSTER=E/'main_axis_residual_registry_20261008/current2021_missing_ownpoints.csv.gz'
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet');C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');G=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');SCREEN=Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet');EX=E/'direct_old_geokladr_point_reserve_20261007_spatial_review/suggested_raw_point_exclusion_keys.csv'
f=pd.read_csv(ROSTER,keep_default_na=False,dtype={'oktmo':str,'okato':str});c=duckdb.connect(config={'threads':1});c.register('targets',f[['source_record_id']]);h=c.execute('select * from read_parquet(?)',[str(H)]).fetchdf();cl=c.execute('select * from read_parquet(?)',[str(C)]).fetchdf();w=c.execute('select w.* from read_parquet(?) w join targets using(source_record_id)',[str(W)]).fetchdf();raw=c.execute('select row_number() over() rn,object_level,object_name,oktmo,mun_upper,mun_lower from read_parquet(?)',[str(RAW)]).fetchdf().set_index('rn');screen=c.execute('select w.* from read_parquet(?) w join targets using(source_record_id)',[str(SCREEN)]).fetchdf().set_index('source_record_id');allwiki=c.execute('select wikidata_qid,wikidata_truthy_p625_claims_json from read_parquet(?)',[str(W)]).fetchall();allgeo=c.execute('select historical_okato,latitude_from_lat,longitude_from_long from read_parquet(?)',[str(Path("/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet"))]).fetchall();c.close();pins={str(p):sha(p) for p in [ROSTER,RAW,H,C,G,W,SCREEN,EX,O/'build.py']}
def name(v):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',normalize(v)).split())
def parish(v):
 v=name(re.sub(r'\b(?:сельское поселение|сельское|поселение|сельсовет|сельский совет|сельская администрация|муниципальное образование)\b',' ',normalize(v)))
 return v[:-2]+'ий' if v.endswith('ское') else v
def typ(v):return normalize(v).replace('поселок сельского типа','поселок').replace('пгт','поселок городского типа')
counties={z.historical_okato[:5]:county_key(z.name) for z in cl.itertuples() if z.is_settlement_raw=='f' and len(z.historical_okato)==8 and z.historical_okato.endswith('000') and 'район' in normalize(z.name)}
parents=collections.defaultdict(set)
for z in cl.itertuples():parents[z.historical_okato].add(parish(z.name))
parentmap={k:next(iter(v)) for k,v in parents.items() if len(v)==1};excluded=set(pd.read_csv(EX,dtype=str).raw_own_code)
wikicoord=collections.defaultdict(set)
for q,arr in allwiki:
 for v in json.loads(arr):
  if v.get('wgs84_valid'):wikicoord[(v['latitude'],v['longitude'])].add(q)
valid=h[h.historical_name_exact.fillna(False)&h.historical_type_exact.fillna(False)&h.historical_code_structure_compatible.fillna(False)&~h.is_deleted.fillna(True)&h.is_settlement_raw.eq('t')&h.latitude_from_lat.between(41,82)&h.longitude_from_long.between(19,180)].copy();idx=collections.defaultdict(list);cluster=collections.defaultdict(set)
for z in valid.to_dict('records'):
 z['county']=counties.get(z['historical_okato_2009_raw'][:5],'');z['parish']=parentmap.get(z['historical_okato_2009_raw'][:8],'');idx[(name(z['name']),typ(z['status']),z['historical_point_modern_region'])].append(z);cluster[(z['latitude_from_lat'],z['longitude_from_long'])].add(z['historical_okato_2009_raw'])
for code,lat,lon in allgeo:
 if lat is not None and lon is not None:cluster[(lat,lon)].add(code)
# Reopen original physical DBF bytes for every admitted record.
with G.open('rb') as g:head=g.read(32);hl,rl=struct.unpack('<HH',head[8:12])
def verifygeo(z):
 with G.open('rb') as g:g.seek(hl+(int(z['record_number_1based'])-1)*rl);b=g.read(rl)
 assert b[:1]!=b'*';assert abs(float(b[363:379].strip())-z['longitude_from_long'])<1e-8;assert abs(float(b[379:395].strip())-z['latitude_from_lat'])<1e-8
 assert b[1:12].decode('ascii')==z['historical_okato_2011_raw'];assert str(int(b[355:363].decode('ascii').strip()))==str(int(z['oktmo_2011_raw'])) if b[355:363].strip() else not z['oktmo_2011_raw']
 return b[13:173].decode('cp866').strip()
# Cached truthy property statements checked against their original JSONL row, never provider pointers.
wik=collections.defaultdict(list);requests=collections.defaultdict(dict)
for z in w.to_dict('records'):
 if not z['wikidata_truthy_exact_p764_match'] or z['entity_competition_across_tsv_or_truthy'] or z['source_observation_competition_for_exact_oktmo']:continue
 if not any(name(re.sub(r'\s*\([^)]*\)\s*$','',v))==name(z['source_name']) for v in json.loads(z['wikidata_tsv_ru_labels_json'])):continue
 p31=json.loads(z['wikidata_truthy_p31_claims_json']);coords=json.loads(z['wikidata_truthy_p625_claims_json']);codes=json.loads(z['wikidata_truthy_exact_p764_claims_json']);xy={(v['latitude'],v['longitude']) for v in coords if v.get('wgs84_valid')}
 if len(xy)!=1 or not any(v['value_qid'] in {'Q5084','Q532','Q192287','Q515','Q3957','Q486972','Q2023000'} for v in p31):continue
 z['verified_xy']=next(iter(xy));z['props']={'P31':p31,'P625':coords,'P764':codes}
 for prop,arr in z['props'].items():
  for v in arr:requests[v['source_file']][int(v['line_number'])]=(z['wikidata_qid'],prop,z)
 wik[z['source_record_id']].append(z)
TSV=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');pins[str(TSV)]=sha(TSV);pins['/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet']=sha(Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet'));labelproof=collections.defaultdict(list)
with TSV.open() as stream:
 for ln,line in enumerate(stream,1):
  v=line.rstrip().split('\t')
  if len(v)<5:continue
  qi=re.search(r'Q\d+',v[0]);code=re.search(r'\d+',v[1])
  if not qi or not code:continue
  label=v[4].removesuffix('@ru')
  try:label=json.loads(label)
  except ValueError:continue
  labelproof[(qi[0],str(int(code[0])))].append((label,ln))
for sid,arr in list(wik.items()):
 wik[sid]=[z for z in arr if any(name(re.sub(r'\s*\([^)]*\)\s*$','',label))==name(z['source_name']) for label,ln in labelproof[(z['wikidata_qid'],str(int(z['source_oktmo_exact_digits'])))])]
found={}
for fn,req in requests.items():
 p=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/fn;pins[str(p)]=sha(p)
 with gzip.open(p,'rt') as g:
  for n,line in enumerate(g,1):
   if n in req:
    q,prop,z=req[n];a=json.loads(line);assert a['item'].rsplit('/',1)[-1]==q and a['property'].rsplit('/',1)[-1]==prop
    if prop=='P764':assert str(a['value'])==str(z['source_oktmo_exact_digits'])
    if prop=='P625':
     lon,lat=map(float,re.match(r'POINT\(([^ ]+) ([^)]+)\)',a['value']).groups());assert (lat,lon)==z['verified_xy']
    if prop=='P31':assert a['value'].rsplit('/',1)[-1] in {v['value_qid'] for v in z['props']['P31']}
    found[(fn,n)]=a
   if n>=max(req):break
 assert all((fn,n) in found for n in req)
points=[];evidence=[];holds=[]
for z in f.to_dict('records'):
 sid=z['source_record_id'];a=raw.loc[int(sid.rsplit(':',1)[1])];dc=county_key(a.mun_upper);pc=parish(a.mun_lower);choices=idx.get((name(z['settlement_name']),typ(z['settlement_type']),z['region_norm']),[])
 own=[g for g in choices if g['county'] and dc and g['county']==dc and ((g['parish'] and pc and g['parish']==pc) or str(g['oktmo_2011_raw'])==str(a.oktmo)[:8])];safe=[g for g in own if g['historical_okato_2009_raw'] not in excluded and len(cluster[(g['latitude_from_lat'],g['longitude_from_long'])])==1]
 qs=wik.get(sid,[]);q=qs[0] if len(qs)==1 and len(wikicoord[qs[0]['verified_xy']])==1 else None;g=safe[0] if len(safe)==1 else None
 if q and g and distance_km(q['verified_xy'],(g['latitude_from_lat'],g['longitude_from_long']))>5:q=None;g=None;reason='independent_ownpoint_over5km_conflict'
 else:reason='no_unique_source_positive_owncoded_point'
 if q:
  assert str(int(a.oktmo))==str(int(q['source_oktmo_exact_digits']))
  xy=q['verified_xy'];p625=q['props']['P625'][0];p=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/p625['source_file'];origin=str(p);osh=pins[origin];loc=f"qid={q['wikidata_qid']};P625line1based={p625['line_number']}";cid=q['wikidata_qid'];kind='raw_truthy_own_native2021_P764_P31_P625';rule='Reopened cached raw single own P625, physical NP P31 and full native2021 exact P764; exact own label; no competing entity or selected source observation';witness=json.dumps({k:q[k] for k in ['wikidata_qid','source_oktmo_exact_digits','wikidata_tsv_ru_labels_json','props']},ensure_ascii=False)
 elif g:
  verifygeo(g);xy=(g['latitude_from_lat'],g['longitude_from_long']);origin=str(G);osh=pins[origin];loc=f"record1based={g['record_number_1based']};byteoffset0based={g['record_byte_offset_0based']};code={g['historical_okato_2011_raw']};LAT/LONG";cid=g['historical_okato_2009_raw'];kind='raw_GeoKLADR2011_owncoded_named_locality';rule='Raw own classifier NP code/name/type and same raw Geo2011 code/name/type; explicit current county agrees, plus own subordinate council lexical context or exact8digit municipal code; unique raw point/code globally; reviewed wrongraw codes excluded';witness=json.dumps(g,ensure_ascii=False,default=str)
 else:holds.append({**z,'reason':reason,'regional_own_name_type_candidates':len(choices),'county_parish_candidates':len(own),'safe_geo_candidates':len(safe),'wiki_own_candidates':len(qs)});continue
 screenrow=screen.loc[sid].to_dict() if sid in screen.index else {};audit={k:screenrow.get(k) for k in ['raw_oktmo_dadata','raw_okato_dadata','provider_fias_level','provider_name_exact_selected_name','provider_type_exact_selected_type','provider_general_fias_duplicate_count','provider_coordinate_duplicate_count','raw_latitude_dadata','raw_longitude_dadata']}
 points.append({'target_source_record_id':sid,'latitude':xy[0],'longitude':xy[1],'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':cid,'point_origin_file':origin,'point_origin_sha256':osh,'point_origin_locator':loc,'point_origin_kind':kind,'coordinate_binding_rule':rule,'point_use_inference':'own_locality_representative_point_source_positive_current_context','historical_census_coordinate_asserted':False,'external_provider_ID_binding_asserted':False,'native2021_own_oktmo':str(a.oktmo)})
 evidence.append({**z,'current_own_county':dc,'current_own_parish':pc,'regional_own_name_type_candidates':len(choices),'county_parish_candidates':len(own),'safe_geo_candidates':len(safe),'point_source_witness_json':witness,'external_current_provider_audit_json':json.dumps(audit,ensure_ascii=False,default=str),'coordinate_binding_and_provider_ID_separate':True,'coordinate_origin_file':origin,'coordinate_origin_sha256':osh,'coordinate_origin_locator':loc})
chosen_counts=collections.Counter((p['point_origin_kind'],p['latitude'],p['longitude']) for p in points);blocked={p['target_source_record_id'] for p in points if chosen_counts[(p['point_origin_kind'],p['latitude'],p['longitude'])]>1}
for z in evidence:
 if z['source_record_id'] in blocked:holds.append({**z,'reason':'same_physical_point_resolves_multiple_current_targets'})
points=[p for p in points if p['target_source_record_id'] not in blocked];evidence=[z for z in evidence if z['source_record_id'] not in blocked]
for n,d in [('accepted_point_use_delta',points),('accepted_source_bound_ownpoint_evidence',evidence),('prioritized_unresolved',sorted(holds,key=lambda z:float(z['population']) if str(z['population']) else -1,reverse=True))]:pd.DataFrame(d).to_csv(O/(n+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
r={'baseline_stage':61,'input_missing_current_ownpoints':len(f),'accepted_current_ownpoints':len(points),'accepted_known_population2021':int(pd.DataFrame(evidence).population.replace('',0).astype(float).sum()) if evidence else 0,'point_origin_counts':dict(collections.Counter(p['point_origin_kind'] for p in points)),'unresolved_rows':len(holds),'source_observations_counts_and_identity_unchanged':True,'actual_main_axis_gain':'root Stage61 replay required; candidate counts do not establish finite/main-axis gain','input_pins':pins,'output_pins':{str(p):sha(p) for p in O.glob('*.csv.gz')}};(O/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
