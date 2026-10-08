"""Cached literal secondary observations bound to strict current native full3.

No census ledger mutation; no inferred year/count/boundary. Re-run into a new
output directory. Memory-only scratch, compressed external observations.
"""
import collections, csv, gzip, hashlib, json, math, re, sys, time
from decimal import Decimal
from pathlib import Path
import duckdb

REPO=Path('/workspace/russian-settlements-research')
sys.path.insert(0,str(REPO/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize, distance_km
OUT=Path('/workspace/settlements-work/annual_cached_own_native_history_20261008/v4_2')
OUT.mkdir(exist_ok=True)
META=Path(__file__).parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def val(s):return s.get('datavalue',{}).get('value')
def actual(claims,prop):return [x for x in claims.get(prop,[]) if x.get('rank') in ('normal','preferred')]
def namekey(x):return normalize(re.sub(r'\s*\([^)]*\)\s*$','',x))
def main():
 start=time.monotonic();s=load(37)
 current=s.obs[s.obs.census_year.eq(2021)].copy()
 codeall=collections.defaultdict(set)
 for r in current.itertuples():
  code=str(r.oktmo).removesuffix('.0')
  if re.fullmatch(r'\d{8,11}',code):codeall[code].add(r.source_record_id)
 targets={};native_counts=collections.Counter()
 for r in current.itertuples():
  sid=r.source_record_id
  if not r.is_additive_settlement_record or r.region_norm in ('москва','санкт петербург','севастополь','крым'):continue
  if s.years[s.uf.find(sid)]!={2002,2010,2021} or sid not in s.point_rows or sid in s.conflicting_point_targets:continue
  native_counts['current_complete_identity_own_current_point']+=1
  code=str(r.oktmo).removesuffix('.0')
  if len(codeall[code])!=1:continue
  targets[code]=r
 # Full3 means all three native observations have finite counts and own points.
 members=collections.defaultdict(list)
 for r in s.obs.itertuples():members[s.uf.find(r.source_record_id)].append(r)
 for code,r in list(targets.items()):
  rows=members[s.uf.find(r.source_record_id)]
  if len(rows)!=3 or any(x.source_record_id not in s.point_rows or x.source_record_id in s.conflicting_point_targets or not math.isfinite(float(x.population)) for x in rows):del targets[code]
 native_counts['strict_full3_unique_exact8to11_current_code_targets']=len(targets)
 # Inventory existing parsed tables before raw scans. Legacy-only rows cannot
 # establish raw P585 precision or whole-item scope, so are not admitted here.
 c=duckdb.connect(config={'threads':1,'memory_limit':'256MB'})
 parsed=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/wikidata_secondary_full_history.parquet')
 inventory=c.execute('select source_tier,count(*),count(distinct wikidata_id),count(*) filter(where raw_statement_json is not null) from read_parquet(?) group by 1',[str(parsed)]).fetchall()
 paths=set()
 roots=[Path('/workspace/settlements-raw/data/raw/wikidata_entities_full'),Path('/workspace/settlements-work'),REPO/'research_rebuild/evidence']
 for root in roots:
  for p in root.rglob('*'):
   if p.is_file() and not p.name.startswith('._') and (p.name.endswith('.json') or p.name.endswith('.json.gz')) and any(x in str(p) for x in ['raw_entity_batches','entity_fetch_and_replay','wikidata_entities_full','raw_cache','full_entities','full_entity_batches','raw_qid_batches','raw_wikidata','raw_entities','wikidata_entities','live_wikidata','live_entities','wikidata_secondary_full3_expansion_20261007/population_batch','additional_uncached_census_histories_20261008/batch','own_dated2002_secondary_scope_20261008/batch']):paths.add(p)
 # Reuse exact raw file paths already indexed by full-entity parsed history.
 for (p,) in c.execute('select distinct entity_batch_file from read_parquet(?) where entity_batch_file is not null',[str(parsed)]).fetchall():
  p=Path(p)
  if p.exists():paths.add(p)
 cache={};manifest={};errors=[]
 for p in sorted(paths):
  try:
   data=json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith('.gz') else p.read_bytes())
   entities=data.get('entities',{})
   if not isinstance(entities,dict):continue
   if not entities:continue
   h=sha(p);manifest[str(p)]={'sha256':h,'bytes':p.stat().st_size,'entity_count':len(entities)}
   for q,e in entities.items():
    if not isinstance(e,dict) or not e.get('claims'):continue
    # Pick latest actual cached revision; retain provenance of that snapshot.
    old=cache.get(q)
    if old is None or int(e.get('lastrevid',0))>int(old[0].get('lastrevid',0)):cache[q]=(e,p,h)
  except (ValueError,OSError,AttributeError) as ex:errors.append({'path':str(p),'error':type(ex).__name__})
 # Documented decimal publisher leading-zero preservation: ONLY raw current
 # physical NP10 and raw item11 starting0; never8-to11 or arbitrary padding.
 native_source=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
 source_hash=sha(native_source);proofs=collections.defaultdict(list)
 for rawcode,level,printed,provider in c.execute("select oktmo,object_level,object_name,oktmo_dadata from read_parquet(?) where length(oktmo)=10 and object_level='Населенный пункт'",[str(native_source)]).fetchall():
  if rawcode not in targets:continue
  rawname=re.sub(r'^(?:г\.|пгт|рп|п\.|с\.|д\.|х\.|аул|станица)\s+','',str(printed),flags=re.I)
  rawname=re.sub(r'\s+(?:кп|рп|пгт)$','',rawname,flags=re.I) if targets[rawcode].settlement_type=='пгт' else rawname
  if namekey(rawname)==namekey(targets[rawcode].settlement_name):proofs[rawcode].append({'raw_native_code':rawcode,'native_object_level':level,'raw_native_printed_name':printed,'source_path':str(native_source),'source_sha256':source_hash,'source_locator':'object_level=Населенный пункт;oktmo='+rawcode+';object_name='+str(printed),'decimal_provider_code_literal':provider,'comparison_rule':'documented_native_physical_NP_numeric_publisher_lost_single_leading0_only10_to11; stage33_rule_preserved; raw_codes_unchanged'})
 zero_alias={('0'+code):code for code,proof in proofs.items() if len(proof)==1 and ('0'+code) not in codeall}
 # P764 must identify one QID among all cached entities, not merely targets.
 qcode=collections.defaultdict(set)
 for q,(e,p,h) in cache.items():
  for st in actual(e['claims'],'P764'):
   v=val(st.get('mainsnak',{}))
   if isinstance(v,str):qcode[v].add(q);qcode[zero_alias[v]].add(q) if v in zero_alias else None
 holds=collections.Counter();bindings={};rows=[]
 physical={'Q532','Q3957','Q515','Q7930989','Q2514025','Q486972','Q771444','Q2023000','Q5084','Q2983893','Q1849719','Q747074','Q15284'}
 bad={'Q43229','Q56061','Q15284','Q17354472','Q1048835','Q5393308','Q755707','Q1136601','Q15916867','Q4167410'}
 # Existing final v3 GUIDs remain frozen; this is an additive supplement.
 with gzip.open('/workspace/settlements-work/annual_cached_own_native_history_20261008/v3/observations.csv.gz','rt') as f:prior={r['statement_guid'] for r in csv.DictReader(f)}
 direct=collections.defaultdict(set);direct_proofs={}
 for code,r in targets.items():
  own=s.point_rows[r.source_record_id]
  text=own.get('point_origin_locator','')
  m=re.search(r'entity=(Q[0-9]+);claim=P625',text)
  if m and own.get('point_origin_kind')=='wikidata_truthy_p625_raw_claim' and own.get('coordinate_source_record_id')==r.source_record_id:
   path=Path(own.get('point_origin_file',''));lm=re.search(r'line=(\d+)',text)
   if path.exists() and lm and sha(path)==own.get('point_origin_sha256'):
    with gzip.open(path,'rt') as f:
     line=next((line for i,line in enumerate(f,1) if i==int(lm[1])),None)
    if line:
     raw=json.loads(line)
     if raw.get('item','').endswith('/'+m[1]) and raw.get('property','').endswith('/P625'):
      direct[m[1]].add(code);direct_proofs[m[1]]=dict(path=str(path),sha256=sha(path),locator=text)
 urban=[]
 for code,r in targets.items():
  if r.settlement_type not in ('город','пгт'):continue
  exact=[q for q in qcode[code]]
  bound=[q for q,cc in direct.items() if code in cc]
  urban.append({'current_source_record_id':r.source_record_id,'name':r.settlement_name,'type':r.settlement_type,'native_code_raw':code,'width':len(code),'native2021_population':int(r.population),'exact_P764_cached_QIDs':json.dumps(exact),'direct_accepted_own_P625_cached_QIDs':json.dumps(bound),'direct_QID_full_entity_cache_available':any(q in cache for q in bound)})
 with (META/'urban_cached_inventory.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(urban[0]));w.writeheader();w.writerows(urban)
 for q,(e,p,h) in cache.items():
  cs=e['claims'];codes={val(x.get('mainsnak',{})) for x in actual(cs,'P764')}
  matches=list({x if x in targets else zero_alias.get(x) for x in codes if x in targets or x in zero_alias})
  binding_route='exact_current_native_code'
  if len(matches)==1:
   code=matches[0]
   if len(qcode[code])!=1:holds['competing_cached_QID_current_code']+=1;continue
  elif len(matches)==0 and len(direct.get(q,set()))==1:
   code=next(iter(direct[q]));binding_route='independently_accepted_direct_own_raw_Wikidata_P625_QID'
   if any(c in codeall and codeall[c]!={targets[code].source_record_id} for c in codes):holds['direct_QID_code_matches_other_current_NP']+=1;continue
  else:continue
  if binding_route=='exact_current_native_code' and code not in codes:binding_route='documented_native_decimal_single_leadingzero_preservation'
  r=targets[code]
  names=[x.get('value','') for x in e.get('labels',{}).values()]+[x.get('value','') for lang in e.get('aliases',{}).values() for x in lang]
  if namekey(r.settlement_name) not in {namekey(x) for x in names}:holds['own_name_mismatch']+=1;continue
  desc=e.get('descriptions',{}).get('ru',{}).get('value','').lower()
  p31={v.get('id') for x in actual(cs,'P31') if isinstance((v:=val(x.get('mainsnak',{}))),dict)}
  if p31&bad or re.search(r'^(муниципаль|сельсовет|сельское поселение|городской округ|район\b)|организац|предприяти|железнодорожная станция',desc):holds['wrong_or_ambiguous_object_level']+=1;continue
  if not p31&physical and not re.search(r'деревн|село\b|пос[её]лок|город\b|аул\b|хутор\b|станиц',desc):holds['physical_settlement_type_not_supported']+=1;continue
  # An explicitly stated native subtype may not contradict the item subtype.
  native_type=normalize(r.settlement_type)
  subtype_words={'город':r'\bгород\b','село':r'\bсело\b','деревня':r'\bдеревн','хутор':r'\bхутор','аул':r'\bаул','станица':r'\bстаниц','поселок':r'\bпос[её]лок|\bпоселение городского типа'}
  stated={k for k,pat in subtype_words.items() if re.search(pat,desc)}
  if native_type in subtype_words and stated and native_type not in stated:
   holds['explicit_native_item_type_contradiction']+=1;continue
  if native_type=='город' and 'город' not in stated and not p31&{'Q515','Q7930989','Q3957'}:
   holds['native_city_type_not_supported']+=1;continue
  if native_type in ('деревня','село','хутор','аул','станица') and p31&{'Q515','Q7930989','Q3957'} and not stated:
   holds['native_rural_urban_P31_contradiction']+=1;continue
  # Current exact native populated-place binding survives former urban status;
  # this is no historical scope/identity admission. Event status stays raw-cache provenance.
  pts=[v for x in actual(cs,'P625') if isinstance((v:=val(x.get('mainsnak',{}))),dict) and v.get('globe')=='http://www.wikidata.org/entity/Q2']
  if not pts or len({(x['latitude'],x['longitude']) for x in pts})!=1:holds['missing_or_multiple_own_P625']+=1;continue
  pt=pts[0];own=s.point_rows[r.source_record_id];dist=distance_km((pt['latitude'],pt['longitude']),(own['latitude'],own['longitude']))
  if dist>5:holds['own_P625_disagrees_over5km']+=1;continue
  bindings[q]={'current_source_record_id':r.source_record_id,'current_native_oktmo':code,'current_name':r.settlement_name,'current_type':r.settlement_type,'current_region':r.region_norm,'current_latitude':own['latitude'],'current_longitude':own['longitude'],'own_P625_distance_km':dist,'p31_json':json.dumps(sorted(p31)),'physical_description':desc,'current_point_ledger':own.get('point_ledger_path',''),'current_point_origin_file':own.get('point_origin_file',''),'current_point_origin_sha256':own.get('point_origin_sha256',''),'current_point_origin_locator':own.get('point_origin_locator',''),'own_P625_latitude':pt['latitude'],'own_P625_longitude':pt['longitude'],'binding_source_path':str(p),'binding_source_sha256':h,'item_P764_codes_json':json.dumps(sorted(codes)),'native_decimal_leadingzero_sourceproof_json':json.dumps(proofs.get(code,[]) if binding_route=='documented_native_decimal_single_leadingzero_preservation' else [],ensure_ascii=False),'binding_route':binding_route,'independent_direct_point_proof_json':json.dumps(direct_proofs.get(q,{})),'binding_rule':'exact_native8to11digit_P764_unique_ALL_current_NPs_and_cached_QIDs_OR_independent_accepted_direct_own_raw_P625_QID_then_literal_own_name_physical_type_own_P625_within5km_only_documented_native_decimal10to11_singleleading0_NO8to11_padding'}
  for st in actual(cs,'P1082'):
   if st.get('id') in prior:continue
   quals=st.get('qualifiers',{})
   if quals.get('P518'):holds['P518_subset_statement']+=1;continue
   dates=quals.get('P585',[])
   if len(dates)!=1:holds['missing_or_multiple_P585']+=1;continue
   dt=val(dates[0]);amount=val(st.get('mainsnak',{}))
   if not isinstance(dt,dict) or not isinstance(amount,dict):continue
   literal=dt.get('time','');m=re.fullmatch(r'\+(\d{4,})-(\d\d)-(\d\d)T.*',literal);precision=dt.get('precision',0)
   if not m or precision<9 or dt.get('before',0) or dt.get('after',0):holds['ambiguous_literal_date']+=1;continue
   year=int(m[1])
   if year in (2002,2010,2021):continue
   if (precision==9 and (m[2],m[3])!=('00','00')) or (precision==10 and (m[2]=='00' or m[3]!='00')) or (precision>=11 and ('00' in (m[2],m[3]))):holds['precision_literal_mismatch']+=1;continue
   try:n=Decimal(amount['amount'])
   except Exception:continue
   if not n.is_finite() or n<0 or n!=n.to_integral_value() or amount.get('unit')!='1':holds['invalid_literal_quantity']+=1;continue
   ref=st.get('references',[]);p248=[];urls=[];titles=[]
   for rr in ref:
    ss=rr.get('snaks',{})
    p248 += [v['id'] for x in ss.get('P248',[]) if isinstance((v:=val(x)),dict) and 'id' in v]
    urls += [v for x in ss.get('P854',[]) if isinstance((v:=val(x)),str)]
    titles += [v.get('text','') for x in ss.get('P1476',[]) if isinstance((v:=val(x)),dict)]
   methods=[v.get('id') for x in quals.get('P459',[]) if isinstance((v:=val(x)),dict)]
   rows.append({'source_uid':'WIKIDATA:'+st.get('id',''),'wikidata_qid':q,'statement_guid':st.get('id',''),'observed_year':year,'raw_date_literal':literal,'date_precision':precision,'date_calendar':dt.get('calendarmodel',''),'population_value':int(n),'raw_amount':amount['amount'],'rank':st['rank'],'raw_file_path':str(p),'raw_file_sha256':h,'raw_locator':'entities/'+q+'/claims/P1082/'+st.get('id',''),'P248_ids_json':json.dumps(p248),'reference_urls_json':json.dumps(urls,ensure_ascii=False),'reference_titles_json':json.dumps(titles,ensure_ascii=False),'method_ids_json':json.dumps(methods),'population_scope':'literal_whole_item_no_P518','observation_class':'dated_secondary_population_observation','primary_verification':'primary_unverified','boundary_comparability':'UNKNOWN','coordinate_status':'current_own_point_only_retrospective_continuity_inference_not_historical_measurement','own_code_provider_quality':'current_own_item_binding_not_primary_source_verification'})
 # Preserve conflicting same literal item/date values separately; no averaging.
 amounts=collections.defaultdict(set)
 for r in rows:amounts[(r['wikidata_qid'],r['raw_date_literal'],r['date_precision'])].add(r['population_value'])
 for r in rows:r['same_item_date_conflict']=len(amounts[(r['wikidata_qid'],r['raw_date_literal'],r['date_precision'])])>1
 def writegz(path,data):
  if path.exists():raise FileExistsError(path)
  with gzip.open(path,'wt',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(data[0]) if data else ['empty']);w.writeheader();w.writerows(data)
 writegz(OUT/'observations.csv.gz',rows)
 used={r['wikidata_qid'] for r in rows};writegz(OUT/'current_bindings.csv.gz',[{'wikidata_qid':q,**bindings[q]} for q in sorted(used)])
 if sum(p.stat().st_size for p in OUT.glob('*.gz'))>2*1024*1024:raise ValueError('compressed output budget exceeded')
 byyear=[]
 for year in sorted({r['observed_year'] for r in rows}):
  yr=[r for r in rows if r['observed_year']==year];entityvalues=collections.defaultdict(set)
  for r in yr:entityvalues[r['wikidata_qid']].add(r['population_value'])
  unambig=[next(iter(v)) for v in entityvalues.values() if len(v)==1]
  byyear.append({'year':year,'observations':len(yr),'unique_current_entities':len(entityvalues),'single_value_entities':len(unambig),'conflicting_or_multiple_date_value_entities':sum(len(v)>1 for v in entityvalues.values()),'descriptive_sum_single_value_entities_only':sum(unambig)})
 with (META/'by_year.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(byyear[0]) if byyear else ['year']);w.writeheader();w.writerows(byyear)
 receipt={'status':'positive_working_secondary_collection_native_census_counts_unchanged','working_stage':37,'native_target_counts':dict(native_counts),'observations':len(rows),'unique_current_native_full3_entities':len(used),'before2002_entities':len({r['wikidata_qid'] for r in rows if r['observed_year']<2002}),'before2002_observations':sum(r['observed_year']<2002 for r in rows),'observed_years':[x['year'] for x in byyear],'cached_entities_scanned':len(cache),'raw_files_used_in_scan':len(manifest),'holds':dict(holds),'prior_v3_GUIDs_excluded':len(prior),'urban_cached_targets':len(urban),'urban_exact_P764_cached':sum(x['exact_P764_cached_QIDs']!='[]' for x in urban),'urban_direct_own_P625_QID_full_cache_available':sum(x['direct_QID_full_entity_cache_available'] for x in urban),'federal_city_cached_QIDs':sorted({'Q649','Q656'}&set(cache)),'parsed_inventory':inventory,'errors':errors,'elapsed_seconds':time.monotonic()-start,'limitations':['Source-bounded cached inventory; no national/all-source historical coverage claim.','Descriptive yearly sums count only unique entities with one literal amount across that year; conflicts excluded.','No invented years or zeros. Literal source zeros are preserved only when explicitly present.','Current native own-code/name/type/point binding does not establish historical identity, coordinate measurement or comparable boundaries.','Generic dated population observations are not labeled census; references and methods remain unverified literal evidence.','No changes to chosen native 2002/2010/2021 census values or current loader.'],'outputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.glob('*.gz')}}
 (META/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 (META/'raw_source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 (META/'native_state_input_manifest.json').write_text(json.dumps({str(p):sha(p) for p in s.inputs},indent=2)+'\n')
 print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
