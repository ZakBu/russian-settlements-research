"""Literal cached P1082, checked current physical-NP binding, no census mutation."""
from pathlib import Path
from decimal import Decimal
import collections,csv,gzip,hashlib,json,math,re,time,unicodedata,datetime
import pyarrow as pa,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/extended_population_history_20261013');O.mkdir(exist_ok=True,parents=True)
R=Path('/workspace/russian-settlements-research');C=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');POINT=Path('/workspace/scratch/tochno-enrichment-20261013/applied/applied_core_point_snapshot.parquet')
RAWNP=Path('/workspace/scratch/tochno-enrichment-20261013/raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def norm(v):return ' '.join(unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е').split())
def namekey(v):return norm(re.sub(r'\s*\([^)]*\)\s*$','',str(v or '')))
def val(s):return s.get('datavalue',{}).get('value')
def actual(cs,p):return [s for s in cs.get(p,[]) if s.get('rank') in ('normal','preferred') and s.get('mainsnak',{}).get('snaktype')=='value']
def dist(a,b):
 lat1,lon1,lat2,lon2=map(math.radians,[*a,*b]);x=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2;return 6371*2*math.asin(min(1,math.sqrt(x)))
def entity_maps(d,path=''):
 if not isinstance(d,dict):return
 if isinstance(d.get('entities'),dict):yield d['entities'],path+'entities/'
 elif re.fullmatch(r'Q\d+',str(d.get('id',''))) and isinstance(d.get('claims'),dict):yield {d['id']:d},path
 else:
  for k in ('payload','data','response','body'):
   if k in d:yield from entity_maps(d[k],path+k+'/')
start=time.monotonic();pins={str(p):sha(p) for p in [C,POINT,RAWNP]}
cols=['source_record_id','census_year','root','settlement_name','settlement_type','region_norm','district_raw','population','is_additive_settlement_record','accepted_point_present','accepted_latitude','accepted_longitude','oktmo','finite_ordinary_full3_all_ownpoints']
base=pq.read_table(C,columns=cols).to_pylist();native={r['source_record_id']:r for r in base if r['census_year']==2021};raw=pq.read_table(RAWNP,columns=['object_level','object_name','region','oktmo']).to_pylist();rawnp={i+1:r for i,r in enumerate(raw) if r['object_level']=='Населенный пункт'}
codeall=collections.defaultdict(set)
for r in native.values():
 if re.fullmatch(r'\d{8,11}',str(r['oktmo'] or '')):codeall[r['oktmo']].add(r['source_record_id'])
roots=collections.defaultdict(list)
for r in native.values():roots[r['root']].append(r['source_record_id'])
targets={}
for sid,r in native.items():
 row=int(sid.rsplit(':',1)[1]);source=rawnp.get(row)
 if source and r['is_additive_settlement_record'] and r['accepted_point_present'] and len(roots[r['root']])==1 and all(math.isfinite(float(r[v])) for v in ['accepted_latitude','accepted_longitude']):targets[sid]=r
# Existing accepted direct point origins are QID bindings only when own-point kind says raw P625.
direct=collections.defaultdict(set);directproof={}
for p in pq.read_table(POINT,columns=['source_record_id','point_origin_locator','point_origin_kind','point_origin_file','point_origin_sha256','point_ledger_path']).to_pylist():
 sid=p['source_record_id'];m=re.search(r'entity=(Q\d+);claim=P625',p['point_origin_locator'] or '')
 if sid in targets and m and p['point_origin_kind']=='wikidata_truthy_p625_raw_claim':direct[m[1]].add(sid);directproof[(m[1],sid)]=p
paths=set(Path('/workspace/settlements-raw/data/raw/wikidata_entities_full').glob('*.json*'))
# Existing checked packet caches, not fresh downloads or unbounded internet collection.
for p in (R/'research_rebuild/evidence').rglob('*'):
 if p.is_file() and (p.name.endswith('.json') or p.name.endswith('.json.gz')) and any(k in str(p) for k in ['wikidata_entities','live_entities','live_wikidata','raw_wikidata','raw_entities','raw_qid_batches','full_entities','entity_fetch_and_replay','population_batch','own_dated2002_secondary_scope']):paths.add(p)
cache={};manifest={};parseheld=collections.Counter()
for p in sorted(paths):
 try:
  b=p.read_bytes();d=json.loads(gzip.decompress(b) if p.name.endswith('.gz') else b);maps=list(entity_maps(d));n=0
  for es,locator in maps:
   for q,e in es.items():
    if not isinstance(e,dict) or not e.get('claims'):continue
    n+=1;old=cache.get(q)
    if old is None or int(e.get('lastrevid',0))>int(old[0].get('lastrevid',0)):cache[q]=(e,p,hashlib.sha256(b).hexdigest(),locator)
  if n:manifest[str(p)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'entities':n}
 except (ValueError,OSError,AttributeError,TypeError):parseheld['unparseable_or_nonentity']+=1
# Only exact NP8..11 codes or documented single lost leading zero of NP10.
alias={};proof={}
for sid,r in targets.items():
 code=r['oktmo'];source=rawnp[int(sid.rsplit(':',1)[1])]
 if isinstance(code,str) and re.fullmatch(r'\d{10}',code) and len(codeall[code])==1 and '0'+code not in codeall:
  alias['0'+code]=code;proof[sid]={'rule':'source_native_NP10_decimal_single_lost_leading_zero_only','source_row1':int(sid.rsplit(':',1)[1]),'source_object_name':source['object_name'],'source_region':source['region'],'source_raw_code':source['oktmo'],'source_sha256':pins[str(RAWNP)]}
qcodes=collections.defaultdict(set)
for q,(e,*_) in cache.items():
 for st in actual(e['claims'],'P764'):
  v=val(st['mainsnak'])
  if isinstance(v,str):qcodes[v].add(q);qcodes[alias[v]].add(q) if v in alias else None
physical={'Q532','Q3957','Q515','Q7930989','Q2514025','Q486972','Q771444','Q2023000','Q5084','Q2983893','Q1849719','Q747074','Q24258416','Q27517483','Q27062006','Q15078955','Q20019082'}
bad={'Q43229','Q56061','Q15284','Q17354472','Q1048835','Q5393308','Q755707','Q1136601','Q15916867','Q4167410','Q55488','Q728937','Q3914'}
holds=collections.Counter();bindings={};rows=[];guidseen=set()
for q,(e,p,h,locator) in cache.items():
 cs=e['claims'];codes={v for st in actual(cs,'P764') if isinstance((v:=val(st['mainsnak'])),str)};sids=set()
 for code in codes:
  nc=code if code in codeall else alias.get(code)
  if nc and len(codeall[nc])==1 and len(qcodes[nc])==1:sids.update(codeall[nc]&targets.keys())
 route='unique_current_native_code_literal_name_physical_type_own_point'
 if len(sids)==1:sid=next(iter(sids))
 elif not sids and len(direct[q])==1:
  sid=next(iter(direct[q]));route='existing_accepted_direct_raw_P625_QID_native_binding'
  if any(c in codeall and codeall[c]!={sid} for c in codes):holds['direct_binding_competing_native_code']+=1;continue
 else:continue
 if any((nc:= (co if co in codeall else alias.get(co))) and codeall[nc]-{sid} for co in codes):holds['competing_current_native_identifier']+=1;continue
 r=targets[sid];p31={v.get('id') for st in actual(cs,'P31') if isinstance((v:=val(st['mainsnak'])),dict)};description=e.get('descriptions',{}).get('ru',{}).get('value','');desc=norm(description)
 names=[v.get('value','') for v in e.get('labels',{}).values()]+[v.get('value','') for a in e.get('aliases',{}).values() for v in a]
 if namekey(r['settlement_name']) not in {namekey(n) for n in names}:holds['literal_own_name_mismatch']+=1;continue
 if p31&bad or re.search(r'^(муниципаль|сельсовет|сельское поселение|городской округ|район\b)|организац|предприяти|железнодорожная станция',desc):holds['wrong_object_level_or_asset']+=1;continue
 if not p31&physical:holds['unreviewed_physical_class']+=1;continue
 typewords={'город':r'\bгород\b','деревня':r'\bдеревн','село':r'\bсело\b','хутор':r'\bхутор','аул':r'\bаул','станица':r'\bстаниц','поселок':r'\bпоселок|поселение городского типа'};stated={k for k,v in typewords.items() if re.search(v,desc)};nt=norm(r['settlement_type'])
 if nt in typewords and stated and nt not in stated:holds['explicit_type_contradiction']+=1;continue
 if nt=='город' and not p31&{'Q515','Q7930989','Q3957'}:holds['city_type_unproved']+=1;continue
 pts=[v for st in actual(cs,'P625') if isinstance((v:=val(st['mainsnak'])),dict) and v.get('globe')=='http://www.wikidata.org/entity/Q2']
 unique={(v.get('latitude'),v.get('longitude')) for v in pts}
 if len(unique)!=1:holds['missing_or_multiple_own_coordinates']+=1;continue
 pt=next(iter(unique));distance=dist(pt,(r['accepted_latitude'],r['accepted_longitude']))
 if distance>5:holds['current_point_conflict_over5km']+=1;continue
 rowid=int(sid.rsplit(':',1)[1]);src=rawnp[rowid]
 bindings[q]={'wikidata_qid':q,'anchor_source_record_id':sid,'root':r['root'],'native_name':r['settlement_name'],'native_type':r['settlement_type'],'native_region':r['region_norm'],'source_region_raw':src['region'],'source_object_name':src['object_name'],'source_object_level':'Населенный пункт','source_row_1based':rowid,'native_code_raw':r['oktmo'],'item_P764_codes_json':json.dumps(sorted(codes)),'binding_route':route,'single_zero_proof_json':json.dumps(proof.get(sid,{}),ensure_ascii=False),'direct_binding_proof_json':json.dumps(directproof.get((q,sid),{}),ensure_ascii=False),'own_P625_distance_km':distance,'P31_json':json.dumps(sorted(p31)),'physical_description_raw':description,'binding_source_path':str(p),'binding_source_sha256':h,'current_own_latitude':r['accepted_latitude'],'current_own_longitude':r['accepted_longitude'],'historical_coordinates_observed':False,'current_point_reference_only':True,'full3_not_required':True,'native_full3_current':r['finite_ordinary_full3_all_ownpoints']}
 for st in cs.get('P1082',[]):
  guid=st.get('id','')
  if not guid or guid in guidseen:holds['missing_or_duplicate_GUID']+=1;continue
  if st.get('rank') not in ('normal','preferred'):holds['deprecated_statement']+=1;continue
  quals=st.get('qualifiers',{})
  if any(quals.get(k) for k in ['P518','P642','P21']):holds['subset_or_unproved_scope']+=1;continue
  dates=quals.get('P585',[])
  if len(dates)!=1:holds['undated_or_multiple_dates']+=1;continue
  dt=val(dates[0]);amount=val(st.get('mainsnak',{}))
  if not isinstance(dt,dict) or not isinstance(amount,dict):holds['nonliteral_date_or_quantity']+=1;continue
  date=dt.get('time','');m=re.fullmatch(r'\+(\d{4,})-(\d\d)-(\d\d)T00:00:00Z',date);precision=dt.get('precision',0)
  if not m or precision<9 or dt.get('before',0) or dt.get('after',0):holds['ambiguous_date']+=1;continue
  y=int(m[1]);month,day=int(m[2]),int(m[3])
  if (precision==9 and (month or day)) or (precision==10 and (not 1<=month<=12 or day)) or (precision>=11 and (not 1<=month<=12 or not 1<=day<=31)):holds['date_precision_mismatch']+=1;continue
  if precision>=11 and dt.get('calendarmodel')=='http://www.wikidata.org/entity/Q1985727':
   try:datetime.date(y,month,day)
   except ValueError:holds['invalid_Gregorian_date']+=1;continue
  try:n=Decimal(amount['amount'])
  except Exception:holds['invalid_amount']+=1;continue
  if not n.is_finite() or n<0 or n!=n.to_integral_value() or amount.get('unit')!='1':holds['noninteger_negative_or_wrong_unit']+=1;continue
  refs=st.get('references',[]);p248=[];urls=[];titles=[]
  for rr in refs:
   ss=rr.get('snaks',{})
   p248.extend(v['id'] for sn in ss.get('P248',[]) if isinstance((v:=val(sn)),dict) and 'id' in v)
   urls.extend(v for sn in ss.get('P854',[]) if isinstance((v:=val(sn)),str))
   titles.extend(v.get('text','') for sn in ss.get('P1476',[]) if isinstance((v:=val(sn)),dict))
  guidseen.add(guid);rows.append({'source_uid':'WIKIDATA:'+guid,'statement_guid':guid,'wikidata_qid':q,'anchor_source_record_id':sid,'root':r['root'],'observed_year':y,'raw_date_literal':date,'date_precision':precision,'date_calendar':dt.get('calendarmodel',''),'population_value':int(n),'raw_amount':amount['amount'],'raw_unit':amount['unit'],'statement_rank':st['rank'],'source_tier':'wikidata_cached_literal_secondary','observation_status':'recovered_reconstructed_secondary_population_observation','primary_verification':'primary_unverified','boundary_comparability':'UNKNOWN','population_scope':'literal_whole_physical_NP_item_no_subset_qualifiers','source_object_level':'physical_settlement','same_year_as_native_census':y in (2002,2010,2021),'do_not_override_native_census':True,'historical_coordinates_observed':False,'current_point_reference_only':True,'prior_approved_GUID_membership':'UNKNOWN_prior_external_observation_files_unavailable','source_file':str(p),'source_sha256':h,'source_locator':locator+q+'/claims/P1082/'+guid,'item_lastrevid':e.get('lastrevid',0),'P248_ids_json':json.dumps(p248),'reference_urls_json':json.dumps(urls,ensure_ascii=False),'reference_titles_json':json.dumps(titles,ensure_ascii=False),'references_json':json.dumps(refs,ensure_ascii=False),'qualifiers_json':json.dumps(quals,ensure_ascii=False),'raw_statement_json':json.dumps(st,ensure_ascii=False),'binding_route':route,'current_own_latitude':r['accepted_latitude'],'current_own_longitude':r['accepted_longitude']})
# Competing values are retained. Yearly descriptive sums use one value per current NP only.
conflicts=collections.defaultdict(set)
for r in rows:conflicts[(r['root'],r['raw_date_literal'],r['date_precision'])].add(r['population_value'])
for r in rows:r['same_place_date_value_conflict']=len(conflicts[(r['root'],r['raw_date_literal'],r['date_precision'])])>1
pq.write_table(pa.Table.from_pylist(rows),O/'population_history_long.parquet',compression='zstd');used={r['wikidata_qid'] for r in rows};pq.write_table(pa.Table.from_pylist([bindings[q] for q in sorted(used)]),O/'current_physical_bindings.parquet',compression='zstd')
byyear=[]
for y in sorted({r['observed_year'] for r in rows}):
 yr=[r for r in rows if r['observed_year']==y];values=collections.defaultdict(set)
 for r in yr:values[r['root']].add(r['population_value'])
 one=[next(iter(v)) for v in values.values() if len(v)==1];byyear.append({'year':y,'observations':len(yr),'current_physical_NPs':len(values),'single_value_NPs':len(one),'conflicting_or_multidate_NPs':sum(len(v)>1 for v in values.values()),'descriptive_population_sum_single_value_NPs_only':sum(one)})
with (H/'by_year.csv').open('w') as f:w=csv.DictWriter(f,byyear[0].keys() if byyear else ['year']);w.writeheader();w.writerows(byyear)
(H/'raw_source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
receipt={'status':'actual_recovered_secondary_history_bound_to_current_physical_NPs','inputs':pins,'cached_snapshot_files':len(manifest),'latest_cached_entities':len(cache),'current_native_physical_targets':len(targets),'observations':len(rows),'own_NP_anchors':len({r['anchor_source_record_id'] for r in rows}),'current_roots':len({r['root'] for r in rows}),'bound_QIDs':len(used),'observed_year_count':len(byyear),'min_year':min((r['observed_year'] for r in rows),default=None),'max_year':max((r['observed_year'] for r in rows),default=None),'before2002_observations':sum(r['observed_year']<2002 for r in rows),'before2002_NPs':len({r['root'] for r in rows if r['observed_year']<2002}),'non_native_census_year_observations':sum(r['observed_year'] not in (2002,2010,2021) for r in rows),'previous_approved_count_reference_only':10963,'net_new_GUIDs_vs_previous':'UNKNOWN_external_prior_GUID_ledger_absent','full3_not_required':True,'bound_non_full3_NPs':sum(not bindings[q]['native_full3_current'] for q in used),'holds':dict(holds),'parse_holds':dict(parseheld),'all_statement_GUIDs_unique':len(guidseen)==len(rows),'primary_verification':'primary_unverified','historical_boundary_comparability':'UNKNOWN','historical_coordinates_observed':False,'native_census_or_graph_modified':False,'outputs':{p.name:{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in O.glob('*.parquet')},'elapsed_seconds':round(time.monotonic()-start,2)}
(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
