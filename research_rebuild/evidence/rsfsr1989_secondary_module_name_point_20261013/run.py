from pathlib import Path
import gzip,json,collections,pyarrow.parquet as pq,pyarrow as pa,hashlib,time
MAIN=Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_secondary_name_point_20261013')
# Reuse documented normalization, geodesic and normal-TLS paced fetch helpers, not the main extraction.
exec((MAIN/'run.py').read_text().split('start=time.monotonic()')[0])
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/rsfsr1989_secondary_module_name_point_20261013');B=Path('/workspace/scratch/rsfsr1989_secondary_name_point_20261013');M=Path('/workspace/settlements-raw/data/raw/wikipedia_statistical/module_qid_population.jsonl.gz');ME=Path('/workspace/settlements-raw/data/raw/wikipedia_statistical/module_qid_entities.jsonl.gz');start=time.monotonic();requests=[];attempts=collections.Counter();api_limited=False;inputs={str(p):sha(p) for p in [M,ME,C,L,B/'secondary_population_1989_long.parquet',B/'current_own_NP_bindings.parquet']}
inputs[str(H/'module_point_near_preflight.json')]=sha(H/'module_point_near_preflight.json')
normal_fetch=fetch
def fetch(ids,props,filename):
 cachefile=O/'api_cache'/filename
 if filename.startswith('module_entity_batch_') and cachefile.exists():
  b=cachefile.read_bytes();requests.append({'cache_file':str(cachefile),'sha256':hashlib.sha256(b).hexdigest(),'prior_HTTP200_reused':True});return json.loads(b).get('entities',{})
 return normal_fetch(ids,props,filename)
pre=json.loads((H/'module_point_near_preflight.json').read_text());qnear={r['qid']:r for r in pre};qs=sorted(qnear);full={}
for i in range(0,len(qs),50):full.update(fetch(qs[i:i+50],'claims|labels',f'module_entity_batch_{i//50:03d}.json'))
classes={}
for p in MAIN.glob('class_batch_*.json'):classes.update(json.loads(p.read_text()).get('entities',{}))
allclasses={s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for e in full.values() for s in e.get('claims',{}).get('P31',[])};allclasses.discard(None);missing=sorted(allclasses-classes.keys())
for i in range(0,len(missing),50):classes.update(fetch(missing[i:i+50],'claims|labels|descriptions',f'module_class_batch_{i//50:03d}.json'))
rule=json.loads((MAIN/'receipt.json').read_text());physical=set(rule['physical_classes_rule']);municipal=set(rule['blocked_municipal_classes'])
for q,e in classes.items():
 label=' '.join(v.get('value','') for v in e.get('labels',{}).values()).casefold()
 if re.search(r'municipal|municipality|urban okrug|сельское поселение в россии|городское поселение в россии|городской округ|муниципаль',label):municipal.add(q)
for repeat in range(3):
 for q,e in classes.items():
  if q not in municipal and any(s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') in physical for s in e.get('claims',{}).get('P279',[])):physical.add(q)
physical-=municipal
base=pq.read_table(B/'secondary_population_1989_long.parquet').to_pylist();oldbindings=pq.read_table(B/'current_own_NP_bindings.parquet').to_pylist();oldanchors={r['anchor_source_record_id'] for r in oldbindings};oldq={r['wikidata_qid'] for r in oldbindings};oldguids={r['statement_uri_raw'].casefold() for r in base};current={r['source_record_id']:r for r in pq.read_table(C,columns=['source_record_id','census_year','root','settlement_name','settlement_type','region_norm','oktmo','okato','accepted_point_present','accepted_latitude','accepted_longitude']).to_pylist() if r['census_year']==2021};levels={r['source_record_id']:r for r in pq.read_table(L,columns=['source_record_id','native_source_object_level','tochno_latest__region']).to_pylist()};byname=collections.defaultdict(list)
for sid,r in current.items():
 if sid not in levels or levels[sid]['native_source_object_level']!='Населенный пункт' or r['region_norm'] in ['крым','севастополь'] or not r['accepted_point_present']:continue
 if all(isinstance(r[k],(int,float)) and math.isfinite(r[k]) for k in ['accepted_latitude','accepted_longitude']):byname[name(r['settlement_name'])].append(r)
audit=[];bindings={};holds=collections.Counter()
for q in qs:
 e=full.get(q,{});p31={s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for s in e.get('claims',{}).get('P31',[])};p31.discard(None);pts={(v['latitude'],v['longitude']) for s in e.get('claims',{}).get('P625',[]) if s.get('rank')!='deprecated' and (v:=s.get('mainsnak',{}).get('datavalue',{}).get('value',{})) and 'latitude' in v};why=[]
 if not p31&physical:why.append('physical_P31_not_proven')
 if p31&municipal:why.append('municipal_or_mixed_P31')
 if any(v not in classes and v not in physical and v not in municipal for v in p31):why.append('extra_P31_class_unverified')
 if len(pts)!=1:why.append('full_P625_not_unique')
 labels={name(v.get('value')) for v in e.get('labels',{}).values()}
 if any(re.search(r'сельсовет|муниципаль|район|сельское поселение|городской округ',label) for label in labels):why.append('aggregate_label')
 hits={}
 if len(pts)==1:
  pt=next(iter(pts));hits={r['source_record_id']:(r,distance(pt,(r['accepted_latitude'],r['accepted_longitude']))) for label in labels for r in byname.get(label,[]) if distance(pt,(r['accepted_latitude'],r['accepted_longitude']))<=5}
 if len(hits)!=1:why.append('full_literal_name_own_point_not_unique')
 if len(hits)==1:
  sid,(r,km)=next(iter(hits.items()))
  if sid in oldanchors or q in oldq:why.append('already_selected_subject')
  modulepoint=point(qnear[q]['module_coord'])
  if not modulepoint or distance(modulepoint,(r['accepted_latitude'],r['accepted_longitude']))>5:why.append('module_cached_point_disagreement')
 audit.append({'qid':q,'P31':sorted(p31),'P31_labels':{v:classes.get(v,{}).get('labels',{}) for v in p31},'hold_reasons':why})
 if why:
  holds.update(why);continue
 bindings[q]={'wikidata_qid':q,'anchor_source_record_id':sid,'root':r['root'],'current_name':r['settlement_name'],'current_type':r['settlement_type'],'current_region':r['region_norm'],'source_region_raw':levels[sid]['tochno_latest__region'],'native_code_raw':r['oktmo'],'native_OKATO11_raw':r['okato'],'binding_code_literals_json':'[]','binding_code_axes_json':'[]','own_point_distance_km':km,'identity_rule':'module_cached_P625_plus_full_API_unique_literal_name_P625_accepted_own_current_NP_point_within5km_and_physical_only_P31','subject_scope':'physical_NP_current_item_attachment_historical_boundary_UNKNOWN','source_entity_rows_json':'[]','current_point_reference_only':True,'source_name_point_context_json':json.dumps({'module_point_raw':qnear[q]['module_coord'],'full_API_labels':sorted(labels),'full_API_point':pt,'code_not_required':True},ensure_ascii=False)}
comp=collections.Counter(r['anchor_source_record_id'] for r in bindings.values())
for q in list(bindings):
 if comp[bindings[q]['anchor_source_record_id']]>1:holds['competing_QIDs_current_subject']+=1;del bindings[q]
added=[];claim_audit=[];seen=set()
with gzip.open(M,'rt') as f:
 for ordinal,line in enumerate(f):
  p=json.loads(line);q=p['item'].split('/')[-1];b=bindings.get(q)
  if not b or not str(p.get('date','')).startswith('1989-'):continue
  uri='<'+p['statement']+'>';key=uri.casefold()
  if key in seen or key in oldguids:continue
  seen.add(key);guid=p['statement'].split('/')[-1].replace('-','$',1);claims=[s for s in full[q].get('claims',{}).get('P1082',[]) if s.get('id','').casefold()==guid.casefold()];why=[]
  if len(claims)!=1:why.append('GUID_not_unique_full_match')
  else:
   s=claims[0];v=s.get('mainsnak',{}).get('datavalue',{}).get('value',{});qual=s.get('qualifiers',{});dates=[x.get('datavalue',{}).get('value',{}) for x in qual.get('P585',[])];n=Decimal(str(p['population']))
   if n!=Decimal(v.get('amount','NaN')) or n<0 or n!=n.to_integral_value():why.append('changed_or_invalid_quantity')
   if v.get('unit')!='1':why.append('unit_not_1')
   if set(qual)&{'P518','P642','P1534','P3005','P1011'}:why.append('explicit_subset')
   if not dates or any(not str(d.get('time','')).startswith('+1989-') or d.get('precision',0)<9 for d in dates):why.append('1989_literal_date_not_verified')
   if s.get('rank') not in ['normal','preferred']:why.append('rank_not_allowed')
  claim_audit.append({'qid':q,'statement_uri_raw':uri,'hold_reasons':why,'full_statement':claims[0] if len(claims)==1 else None})
  if why:holds.update(why);continue
  added.append({**b,'observed_year':1989,'source_date_raw':p['date'],'date_precision':'UNKNOWN_flat_module_not_preserved','population_value':int(n),'raw_population_literal':str(p['population']),'population_basis':'UNKNOWN','source_rank_raw':p['rank'],'statement_uri_raw':uri,'source_tier':'wikidata_cached_module_flat_dated_secondary','primary_verification':'primary_unverified','boundary_comparability':'UNKNOWN','whole_item_qualifiers_verification':'full_current_GUID_checked_no_explicit_subset_boundary_UNKNOWN','quantity_unit_verification':'full_current_GUID_unit_1','source_population_file':str(M),'source_population_sha256':inputs[str(M)],'source_population_row_0based':ordinal,'source_entity_file':str(ME),'source_entity_sha256':inputs[str(ME)],'do_not_override_primary':True,'historical_coordinates_observed':False,'source_census_method_verification':'UNKNOWN_generic_dated_P1082_not_automatically_census','full_API_statement_json':json.dumps(s,ensure_ascii=False),'full_API_P31_claims_json':json.dumps(full[q].get('claims',{}).get('P31',[]),ensure_ascii=False),'full_API_P625_claims_json':json.dumps(full[q].get('claims',{}).get('P625',[]),ensure_ascii=False),'full_API_P585_values_json':json.dumps(dates),'full_API_P459_method_ids_json':json.dumps([v.get('datavalue',{}).get('value',{}).get('id') for v in qual.get('P459',[])]),'full_API_P1013_basis_ids_json':json.dumps([v.get('datavalue',{}).get('value',{}).get('id') for v in qual.get('P1013',[])])})
qsadded={r['wikidata_qid'] for r in added};newbindings=[b for q,b in bindings.items() if q in qsadded];combined=base+added;allbindings=oldbindings+newbindings;vals=collections.defaultdict(set)
for r in combined:vals[r['anchor_source_record_id']].add(r['population_value'])
for r in combined:r['same_NP_year_value_conflict']=len(vals[r['anchor_source_record_id']])>1
for records in [combined,allbindings]:
 keys=set().union(*(r.keys() for r in records))
 for r in records:
  for k in keys:r.setdefault(k,None)
pq.write_table(pa.Table.from_pylist(combined),O/'secondary_population_1989_long.parquet',compression='zstd');pq.write_table(pa.Table.from_pylist(allbindings),O/'current_own_NP_bindings.parquet',compression='zstd');pq.write_table(pa.Table.from_pylist(added) if added else pq.read_table(B/'secondary_population_1989_long.parquet').slice(0,0),O/'additional_module_population_1989_long.parquet',compression='zstd');(H/'P31_point_subject_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(H/'P1082_claim_audit.json').write_text(json.dumps(claim_audit,ensure_ascii=False,indent=2)+'\n');receipt={'inputs':inputs,'module_unselected_frame':251,'module_point_near_candidates':len(qs),'API_requests':requests,'additional_GUIDs':len(added),'additional_subjects':len(newbindings),'additional_population_literal':sum(r['population_value'] for r in added),'full_subjects':len(vals),'full_GUID_rows':len(combined),'full_population_sum_min':sum(min(v) for v in vals.values()),'full_population_sum_max':sum(max(v) for v in vals.values()),'holds':dict(holds),'physical_types':sorted(physical),'municipal_types_blocked':sorted(municipal),'not_primary_census_or_national_total':True,'outputs':{p.name:{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in O.glob('*.parquet')},'elapsed_seconds':round(time.monotonic()-start,1)};(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='API_requests'},ensure_ascii=False))
