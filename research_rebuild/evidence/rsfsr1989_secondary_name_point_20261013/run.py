from pathlib import Path
from decimal import Decimal
import duckdb,pyarrow.parquet as pq,pyarrow as pa,json,collections,hashlib,math,re,unicodedata,urllib.request,urllib.parse,time
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/rsfsr1989_secondary_name_point_20261013');B=Path('/workspace/scratch/rsfsr1989_secondary_okato_extension_20261013');C=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');L=Path('/workspace/scratch/tochno-np-attach-20261013/native_np_latest_all_attributes.parquet');P=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_population.tsv');E=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return ' '.join(unicodedata.normalize('NFKC',str(x or '')).casefold().replace('ё','е').split())
def name(x):return norm(re.sub(r'\s*\([^)]*\)\s*$','',x))
def rdf(x):
 x=re.sub(r'@\w+(-\w+)?$','',x or '')
 try:return json.loads(x) if x.startswith('"') else x
 except ValueError:return x.strip('"')
def qid(x):
 m=re.search(r'/(Q\d+)>?$',x or '');return m[1] if m else ''
def point(x):
 m=re.fullmatch(r'POINT\(([-+0-9.]+) ([-+0-9.]+)\)',str(x or ''));return (float(m[2]),float(m[1])) if m else None
def distance(a,b):
 la,lo,lb,lp=map(math.radians,[*a,*b]);v=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2;return 12742*math.asin(min(1,math.sqrt(v)))
def fetch(ids,props,filename):
 global api_limited
 cached=(O/'api_cache'/filename) if filename.startswith('entity_batch_') else H/filename
 cached.parent.mkdir(exist_ok=True,parents=True)
 if cached.exists():
  data=cached.read_bytes();requests.append({'cache_file':filename,'sha256':hashlib.sha256(data).hexdigest(),'previous_HTTP200_response_reused':True});return json.loads(data).get('entities',{})
 if api_limited:return {}
 time.sleep(4)
 attempts[filename]+=1
 url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(ids),'props':props,'languages':'ru|en','format':'json'});rec={'url':url,'TLS':'normal_default_verification'}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0 (own NP scope audit)'}),timeout=30) as r:data=r.read();rec['http_status']=r.status
  cached.write_bytes(data);rec['sha256']=hashlib.sha256(data).hexdigest();requests.append(rec);return json.loads(data).get('entities',{})
 except Exception as e:
  rec['failure']=str(e)
  if getattr(e,'code',None)==429:
   rec['retry_after']=e.headers.get('Retry-After');requests.append(rec)
   if attempts[filename]<3:
    time.sleep(min(30,int(rec['retry_after'] or '15')));return fetch(ids,props,filename)
   api_limited=True;return {}
  requests.append(rec);return {}
start=time.monotonic();inputs={str(p):sha(p) for p in [C,L,P,E,B/'secondary_population_1989_long.parquet',B/'current_own_NP_bindings.parquet']};base=pq.read_table(B/'secondary_population_1989_long.parquet').to_pylist();bindings=pq.read_table(B/'current_own_NP_bindings.parquet').to_pylist();oldq={r['wikidata_qid'] for r in bindings};oldanchors={r['anchor_source_record_id'] for r in bindings};current={r['source_record_id']:r for r in pq.read_table(C,columns=['source_record_id','census_year','root','settlement_name','settlement_type','region_norm','oktmo','okato','accepted_point_present','accepted_latitude','accepted_longitude']).to_pylist() if r['census_year']==2021};levels={r['source_record_id']:r for r in pq.read_table(L,columns=['source_record_id','native_source_object_level','tochno_latest__region']).to_pylist()};byname=collections.defaultdict(list)
for sid,r in current.items():
 if sid not in levels or levels[sid]['native_source_object_level']!='Населенный пункт' or r['region_norm'] in ['крым','севастополь'] or not r['accepted_point_present']:continue
 if not all(isinstance(r[k],(int,float)) and math.isfinite(r[k]) for k in ['accepted_latitude','accepted_longitude']):continue
 byname[name(r['settlement_name'])].append(r)
c=duckdb.connect(config={'threads':2,'memory_limit':'1GB'});c.execute("create temp table pop as select * from (select row_number() over()-1 row0,* from read_csv(?,delim='\t',quote='',header=true,all_varchar=true)) where \"?date\" like '1989-%'",[str(P)]);ps=c.execute('select * from pop').fetchall();pcols=[x[0] for x in c.description];pop=[dict(zip(pcols,r)) for r in ps];c.execute("select * from (select row_number() over()-1 row0,* from read_csv(?,delim='\t',quote='',header=true,all_varchar=true)) where \"?item\" in (select distinct \"?item\" from pop)",[str(E)]);es=c.fetchall();ecols=[x[0] for x in c.description];entities=collections.defaultdict(list)
for e in es:
 r=dict(zip(ecols,e));q=qid(r['?item'])
 if q not in oldq:entities[q].append(r)
candidates={};holds=collections.Counter()
for q,er in entities.items():
 labels={name(rdf(e['?label'])) for e in er};pts={p for e in er if (p:=point(e['?coord']))}
 if len(pts)!=1:holds['no_unique_source_point']+=1;continue
 if any(re.search(r'сельсовет|муниципаль|район|сельское поселение|городской округ|\(станция\)|\(разъезд\)',norm(rdf(e['?label']))) for e in er):holds['aggregate_asset_label']+=1;continue
 p=next(iter(pts));hits={r['source_record_id']:(r,distance(p,(r['accepted_latitude'],r['accepted_longitude']))) for label in labels for r in byname.get(label,[]) if distance(p,(r['accepted_latitude'],r['accepted_longitude']))<=5}
 if len(hits)!=1:holds['name_point_not_unique_current_NP']+=1;continue
 sid,(r,km)=next(iter(hits.items()))
 if sid in oldanchors:holds['already_selected_current_subject']+=1;continue
 candidates[q]={'wikidata_qid':q,'anchor_source_record_id':sid,'root':r['root'],'current_name':r['settlement_name'],'current_type':r['settlement_type'],'current_region':r['region_norm'],'source_region_raw':levels[sid]['tochno_latest__region'],'native_code_raw':r['oktmo'],'native_OKATO11_raw':r['okato'],'binding_code_literals_json':'[]','binding_code_axes_json':'[]','own_point_distance_km':km,'identity_rule':'unique_literal_name_and_unique_P625_within5km_accepted_own_current_NP_point_plus_full_P31_physical_only_no_municipal_mixed','subject_scope':'physical_NP_current_item_attachment_historical_boundary_UNKNOWN','source_entity_rows_json':json.dumps(sorted({e['row0'] for e in er})),'current_point_reference_only':True,'source_name_point_context_json':json.dumps({'labels':sorted(labels),'point':p,'admin_labels':sorted({rdf(e['?adminLabel']) for e in er}),'admin_QIDs':sorted({qid(e['?admin']) for e in er}),'code_is_not_identity_requirement':True},ensure_ascii=False)}
# Competing source items for one current NP cannot both establish unique subject identity.
comp=collections.Counter(b['anchor_source_record_id'] for b in candidates.values())
for q in list(candidates):
 if comp[candidates[q]['anchor_source_record_id']]>1:holds['competing_QIDs_for_current_subject']+=1;del candidates[q]
(H/'name_point_candidates.json').write_text(json.dumps(list(candidates.values()),ensure_ascii=False,indent=2)+'\n');print(json.dumps({'passing_name_point_unique_candidates':len(candidates),'holds':dict(holds)}),flush=True)
requests=[];attempts=collections.Counter();api_limited=False;full={};qs=sorted(candidates)
for i in range(0,len(qs),50):full.update(fetch(qs[i:i+50],'claims|labels',f'entity_batch_{i//50:03d}.json'))
classes=set()
for e in full.values():
 classes.update(s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for s in e.get('claims',{}).get('P31',[]))
classes.discard(None);cls={};classids=sorted(classes)
for i in range(0,len(classids),50):cls.update(fetch(classids[i:i+50],'claims|labels|descriptions',f'class_batch_{i//50:03d}.json'))
# Explicit physical categories; municipality categories always block, even when physical type coexists.
physical={'Q5084','Q2514025','Q2023000','Q771444','Q15078955','Q10354598','Q486972','Q515','Q532','Q3957','Q2989453','Q1549591','Q5119','Q7930989','Q4220917'};municipal={'Q2661988','Q634099','Q13626398','Q15284','Q33146843'}
for q,e in cls.items():
 label=' '.join(v.get('value','') for v in e.get('labels',{}).values()).casefold()
 if re.search(r'municipal|municipality|urban okrug|сельское поселение в россии|городское поселение в россии|городской округ|муниципаль',label):municipal.add(q)
 if any(s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') in physical for s in e.get('claims',{}).get('P279',[])):physical.add(q)
physical-=municipal
audit=[];allowed={}
for q,b in candidates.items():
 e=full.get(q,{});p31={s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for s in e.get('claims',{}).get('P31',[])};p31.discard(None);why=[]
 if not p31&physical:why.append('physical_P31_not_proven')
 if any(v not in cls and v not in physical and v not in municipal for v in p31):why.append('extra_P31_class_unverified')
 if p31&municipal:why.append('municipal_or_mixed_P31')
 if not e:why.append('API_unavailable')
 fullpts={(v['latitude'],v['longitude']) for st in e.get('claims',{}).get('P625',[]) if st.get('rank')!='deprecated' and (v:=st.get('mainsnak',{}).get('datavalue',{}).get('value',{})) and 'latitude' in v}
 if len(fullpts)!=1:why.append('full_P625_not_unique')
 elif distance(next(iter(fullpts)),(current[b['anchor_source_record_id']]['accepted_latitude'],current[b['anchor_source_record_id']]['accepted_longitude']))>5:why.append('full_P625_own_point_disagreement')
 audit.append({'qid':q,'P31':sorted(p31),'P31_labels':{v:cls.get(v,{}).get('labels',{}) for v in p31},'reasons':why})
 if why:holds['P31_type_or_full_P625_rejected_or_unknown']+=1;continue
 allowed[q]=b
added=[];seen=set();claim_audit=[]
for r in pop:
 q=qid(r['?item']);b=allowed.get(q)
 if not b:continue
 key=r['?statement'].casefold()
 if key in seen:continue
 seen.add(key);guid=r['?statement'].split('/')[-1].rstrip('>').replace('-','$',1);claims=[s for s in full[q].get('claims',{}).get('P1082',[]) if s.get('id','').casefold()==guid.casefold()];why=[]
 if len(claims)!=1:why.append('GUID_not_unique_full_match')
 else:
  s=claims[0];v=s.get('mainsnak',{}).get('datavalue',{}).get('value',{});qual=s.get('qualifiers',{});dates=[x.get('datavalue',{}).get('value',{}) for x in qual.get('P585',[])];subsets=set(qual)&{'P518','P642','P1534','P3005','P1011'}
  if subsets:why.append('subset_qualifier')
  if v.get('unit')!='1':why.append('unit_not_1')
  if not dates or any(not str(d.get('time','')).startswith('+1989-') or d.get('precision',0)<9 for d in dates):why.append('1989_literal_date_not_verified')
  try:
   n=Decimal(r['?population']);actual=Decimal(v.get('amount','NaN'))
   if n!=actual or not n.is_finite() or n<0 or n!=n.to_integral_value():why.append('invalid_or_changed_quantity')
  except Exception:why.append('unparseable_quantity')
  if s.get('rank') not in ['normal','preferred']:why.append('deprecated_or_unknown_full_rank')
 claim_audit.append({'qid':q,'statement_uri':r['?statement'],'hold_reasons':why,'full_statement':claims[0] if len(claims)==1 else None})
 if why:holds['full_P1082_scope_or_quantity_rejected']+=1;continue
 added.append({**b,'observed_year':1989,'source_date_raw':r['?date'],'date_precision':'UNKNOWN_flat_cache_not_preserved','population_value':int(n),'raw_population_literal':r['?population'],'population_basis':'UNKNOWN','source_rank_raw':r['?rank'],'statement_uri_raw':r['?statement'],'source_tier':'wikidata_cached_flat_dated_secondary','primary_verification':'primary_unverified','boundary_comparability':'UNKNOWN','whole_item_qualifiers_verification':'sampled_full_current_GUID_checked_no_explicit_subset_historical_boundary_UNKNOWN','quantity_unit_verification':'full_current_GUID_unit_1','source_population_file':str(P),'source_population_sha256':inputs[str(P)],'source_population_row_0based':r['row0'],'source_entity_file':str(E),'source_entity_sha256':inputs[str(E)],'do_not_override_primary':True,'historical_coordinates_observed':False,'source_census_method_verification':'UNKNOWN_generic_dated_P1082_not_automatically_census','full_API_P31_ids_json':json.dumps(sorted({s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for s in full[q].get('claims',{}).get('P31',[]) if s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id')}))})
acceptedq={r['wikidata_qid'] for r in added};newbindings=[b for q,b in allowed.items() if q in acceptedq];allrows=base+added;allbindings=bindings+newbindings;vals=collections.defaultdict(set)
for r in allrows:vals[r['anchor_source_record_id']].add(r['population_value'])
for r in allrows:r['same_NP_year_value_conflict']=len(vals[r['anchor_source_record_id']])>1
for records in [allrows,allbindings]:
 fields=set().union(*(r.keys() for r in records))
 for r in records:
  for field in fields:r.setdefault(field,None)
pq.write_table(pa.Table.from_pylist(allrows),O/'secondary_population_1989_long.parquet',compression='zstd');pq.write_table(pa.Table.from_pylist(allbindings),O/'current_own_NP_bindings.parquet',compression='zstd');pq.write_table(pa.Table.from_pylist(added) if added else pq.read_table(B/'secondary_population_1989_long.parquet').slice(0,0),O/'additional_name_point_population_1989_long.parquet',compression='zstd');(H/'P31_subject_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(H/'P1082_claim_audit.json').write_text(json.dumps(claim_audit,ensure_ascii=False,indent=2)+'\n')
receipt={'inputs':inputs,'passing_name_point_candidates':len(candidates),'API_requests':requests,'physical_classes_rule':sorted(physical),'blocked_municipal_classes':sorted(municipal),'additional_GUIDs':len(added),'additional_subjects':len(newbindings),'additional_population_literal_min':sum(min({r['population_value'] for r in added if r['anchor_source_record_id']==b['anchor_source_record_id']}) for b in newbindings),'full_subjects':len(vals),'full_GUID_rows':len(allrows),'full_population_sum_min':sum(min(v) for v in vals.values()),'full_population_sum_max':sum(max(v) for v in vals.values()),'holds':dict(holds),'not_verified_primary_census_or_national_total':True,'frozen_inputs_unchanged':True,'outputs':{p.name:{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in O.glob('*.parquet')},'elapsed_seconds':round(time.monotonic()-start,1)};(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='API_requests'},ensure_ascii=False),flush=True)
