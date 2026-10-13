from pathlib import Path
from decimal import Decimal
import duckdb,pyarrow as pa,pyarrow.parquet as pq
import csv,json,re,collections,hashlib,unicodedata,math,time
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/rsfsr1989_secondary_mass_20261013');O.mkdir(exist_ok=True,parents=True)
C=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');P=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_population.tsv');E=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');L=Path('/workspace/scratch/tochno-np-attach-20261013/native_np_latest_all_attributes.parquet')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def norm(x):return ' '.join(unicodedata.normalize('NFKC',str(x or '')).casefold().replace('ё','е').split())
def name(x):return norm(re.sub(r'\s*\([^)]*\)\s*$','',x))
def rdf(v):
 if v is None:return ''
 v=re.sub(r'@\w+(-\w+)?$','',v)
 try:return json.loads(v) if v.startswith('"') else v
 except ValueError:return v.strip('"')
def qid(x):
 m=re.search(r'/(Q\d+)>?$',x or '');return m[1] if m else ''
def point(x):
 m=re.fullmatch(r'POINT\(([-+0-9.]+) ([-+0-9.]+)\)',str(x or ''))
 return (float(m[2]),float(m[1])) if m else None
def distance(a,b):
 la,lo,lb,lp=map(math.radians,[*a,*b]);v=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2;return 12742*math.asin(min(1,math.sqrt(v)))
start=time.monotonic();pins={str(p):sha(p) for p in [C,P,E,L]}
fields=['source_record_id','census_year','root','settlement_name','settlement_type','region_norm','district_raw','oktmo','accepted_point_present','accepted_latitude','accepted_longitude','is_additive_settlement_record']
current={r['source_record_id']:r for r in pq.read_table(C,columns=fields).to_pylist() if r['census_year']==2021}
latest=pq.read_table(L,columns=['source_record_id','native_source_object_level','tochno_latest__oktmo_new','tochno_latest__oktmo','tochno_latest__region']).to_pylist();level={r['source_record_id']:r for r in latest};codes=collections.defaultdict(set);axis=collections.defaultdict(dict)
for sid,r in current.items():
 if sid not in level or level[sid]['native_source_object_level']!='Населенный пункт' or r['region_norm'] in ['крым','севастополь']:continue
 for col,v in [('native_raw',r['oktmo']),('tochno_20260925_oktmo_new_undated',level[sid]['tochno_latest__oktmo_new'])]:
  if not isinstance(v,str) or not re.fullmatch(r'\d{10,11}',v):continue
  for code in [v]+(['0'+v] if len(v)==10 else []):codes[code].add(sid);axis[sid][code]=col
c=duckdb.connect(config={'threads':2,'memory_limit':'1GB'})
c.execute("create temp table pop as select * from (select row_number() over()-1 as row0,* from read_csv(?,delim='\t',quote='',header=true,all_varchar=true)) where \"?date\" like '1989-%'",[str(P)])
ps=c.execute('select * from pop').fetchall();pnames=[x[0] for x in c.description];p_rows=[dict(zip(pnames,r)) for r in ps];qs={qid(r['?item']) for r in p_rows}
c.execute("create temp table entity as select * from (select row_number() over()-1 as row0,* from read_csv(?,delim='\t',quote='',header=true,all_varchar=true)) where \"?item\" in (select distinct \"?item\" from pop)",[str(E)])
es=c.execute('select * from entity').fetchall();enames=[x[0] for x in c.description];entities=collections.defaultdict(list)
for r in es:
 v=dict(zip(enames,r));entities[qid(v['?item'])].append(v)
# Cross-item competition is evaluated over the nationwide1989 source inventory.
codeq=collections.defaultdict(set)
for q,er in entities.items():
 for e in er:codeq[rdf(e['?oktmo'])].add(q)
pointpath=Path('/workspace/scratch/tochno-enrichment-20261013/applied/applied_core_point_snapshot.parquet')
pins[str(pointpath)]=sha(pointpath)
direct=collections.defaultdict(set);directproof={}
for pr in pq.read_table(pointpath).to_pylist():
 sid=pr['source_record_id'];r=current.get(sid)
 if not r or sid not in level or level[sid]['native_source_object_level']!='Населенный пункт' or r['region_norm'] in ['крым','севастополь']:continue
 if pr.get('point_origin_kind')!='wikidata_truthy_p625_raw_claim':continue
 m=re.search(r'entity=(Q\d+);claim=P625',pr.get('point_origin_locator') or '')
 if m:direct[m[1]].add(sid);directproof[sid]=pr
bindings={};held=collections.Counter();heldrows=[]
for q,er in entities.items():
 item_codes={rdf(e['?oktmo']) for e in er};matches=set()
 for code in item_codes:
  if len(codes[code])==1 and len(codeq[code])==1:matches.update(codes[code])
 route='code'
 if len(matches)!=1:
  if len(direct[q])!=1:held['no_unique_literal_own_NP_code_or_accepted_direct_QID']+=1;continue
  matches=set(direct[q]);route='accepted_direct_QID'
 sid=next(iter(matches));r=current[sid];names={name(rdf(e['?label'])) for e in er}
 if name(r['settlement_name']) not in names:held['literal_name_mismatch']+=1;heldrows.append({'qid':q,'sid_candidate':sid,'native_name':r['settlement_name'],'names_json':json.dumps(sorted(names),ensure_ascii=False),'reason':'literal_name_mismatch'});continue
 if any(re.search(r'сельсовет|муниципаль|район|сельское поселение|городской округ|\(станция\)|\(разъезд\)',norm(rdf(e['?label']))) for e in er):held['aggregate_or_asset_label']+=1;continue
 pts={pt for e in er if (pt:=point(e['?coord']))}
 if len(pts)!=1 or not r['accepted_point_present'] or not all(isinstance(r[k],(float,int)) and math.isfinite(r[k]) for k in ['accepted_latitude','accepted_longitude']):held['point_unavailable_or_ambiguous']+=1;continue
 pt=next(iter(pts));km=distance(pt,(r['accepted_latitude'],r['accepted_longitude']))
 if km>5:held['current_own_point_disagreement']+=1;continue
 common=sorted(item_codes&axis[sid].keys());bindings[q]={'wikidata_qid':q,'anchor_source_record_id':sid,'root':r['root'],'current_name':r['settlement_name'],'current_type':r['settlement_type'],'current_region':r['region_norm'],'source_region_raw':level[sid]['tochno_latest__region'],'native_code_raw':r['oktmo'],'binding_code_literals_json':json.dumps(common),'binding_code_axes_json':json.dumps([axis[sid][v] for v in common]),'own_point_distance_km':km,'accepted_direct_QID_point_provenance_json':json.dumps(directproof.get(sid),ensure_ascii=False,default=str) if route=='accepted_direct_QID' else None,'identity_rule':('unique_own_NP10or11_code_exact_or_single_leading0' if route=='code' else 'existing_unique_accepted_native_direct_QID_P625_binding')+'_plus_literal_name_plus_unique_accepted_current_own_point_within5km','subject_scope':'physical_NP_current_item_attachment_historical_boundary_UNKNOWN','source_entity_rows_json':json.dumps(sorted({e['row0'] for e in er})),'current_point_reference_only':True}
# Two explicitly requested historical city subjects; never reinterpret their count as current federal territory.
for q,city in [('Q649','Москва'),('Q656','Санкт-Петербург')]:
 candidates=[r for r in current.values() if r['settlement_name']==city and r['region_norm'] in ['москва','санкт петербург']]
 er=entities.get(q,[])
 if len(candidates)!=1 or not er:continue
 r=candidates[0];names={name(rdf(e['?label'])) for e in er}
 if name(city) not in names:continue
 bindings[q]={'wikidata_qid':q,'anchor_source_record_id':r['source_record_id'],'root':r['root'],'current_name':city,'current_type':'historical_city_subject','current_region':r['region_norm'],'source_region_raw':city,'native_code_raw':r['oktmo'],'binding_code_literals_json':json.dumps(sorted({rdf(e['?oktmo']) for e in er})),'binding_code_axes_json':'["explicit_known_city_QID_and_literal_city_name_not_current_federal_population_scope"]','own_point_distance_km':None,'identity_rule':'explicit_historical_Moscow_Leningrad_city_subject_QID_literal_name_source_code_claim','subject_scope':'historical_city_1989_not_current_federal_territory_NOT_plus_federal_children','source_entity_rows_json':json.dumps(sorted({e['row0'] for e in er})),'current_point_reference_only':True}
rows=[];seen=set()
for p in p_rows:
 q=qid(p['?item']);b=bindings.get(q)
 if not b:continue
 rank=p['?rank'] or ''
 if not (rank.endswith('NormalRank>') or rank.endswith('PreferredRank>')):held['deprecated_or_unknown_rank']+=1;continue
 try:n=Decimal(p['?population'])
 except Exception:held['quantity_unparseable']+=1;continue
 if not n.is_finite() or n<0 or n!=n.to_integral_value():held['invalid_count']+=1;continue
 st=p['?statement'];key=(q,st.casefold())
 if key in seen:continue
 seen.add(key);rows.append({**b,'observed_year':1989,'source_date_raw':p['?date'],'date_precision':'UNKNOWN_flat_cache_not_preserved','population_value':int(n),'raw_population_literal':p['?population'],'population_basis':'UNKNOWN','source_rank_raw':rank,'statement_uri_raw':st,'source_tier':'wikidata_cached_flat_dated_secondary','primary_verification':'primary_unverified','boundary_comparability':'UNKNOWN','whole_item_qualifiers_verification':'UNKNOWN_flat_cache_not_preserved','quantity_unit_verification':'UNKNOWN_flat_cache_not_preserved','source_population_file':str(P),'source_population_sha256':pins[str(P)],'source_population_row_0based':p['row0'],'source_entity_file':str(E),'source_entity_sha256':pins[str(E)],'do_not_override_primary':True,'historical_coordinates_observed':False,'source_census_method_verification':'UNKNOWN_generic_dated_P1082_not_automatically_census'})
vals=collections.defaultdict(set)
for r in rows:vals[r['anchor_source_record_id']].add(r['population_value'])
for r in rows:r['same_NP_year_value_conflict']=len(vals[r['anchor_source_record_id']])>1
pq.write_table(pa.Table.from_pylist(rows),O/'secondary_population_1989_long.parquet',compression='zstd');pq.write_table(pa.Table.from_pylist(list(bindings.values())),O/'current_own_NP_bindings.parquet',compression='zstd')
with (H/'held_literal_name_candidates.csv').open('w') as f:w=csv.DictWriter(f,heldrows[0].keys() if heldrows else ['qid']);w.writeheader();w.writerows(heldrows)
primarypath=H.parent/'rsfsr1989_urban_mass_20261013/image_checked_source_current_reference_bindings.csv';primary=[]
if primarypath.exists():
 with primarypath.open() as f:primary=list(csv.DictReader(f))
primaryids={r['anchor_source_record_id'] for r in primary};disjoint={k:v for k,v in vals.items() if k not in primaryids}
receipt={'inputs':pins,'source1989_rows':len(p_rows),'source1989_QIDs':len(qs),'current_bound_QIDs':len(bindings),'secondary1989_rows_GUID_deduplicated':len(rows),'own1989_NP_or_explicit_city_subjects':len(vals),'source_bounded_population_sum_min':sum(min(v) for v in vals.values()),'source_bounded_population_sum_max':sum(max(v) for v in vals.values()),'single_value_subjects':sum(len(v)==1 for v in vals.values()),'conflicting_subjects':sum(len(v)>1 for v in vals.values()),'primary_city_roster_reference':str(primarypath) if primary else None,'primary_roster_subjects_excluded_from_secondary_disjoint_count':len(primaryids&vals.keys()),'secondary_disjoint_min':sum(min(v) for v in disjoint.values()),'secondary_disjoint_max':sum(max(v) for v in disjoint.values()),'holds':dict(held),'not_a_primary_census_or_boundary_verified_national_total':True,'missing_flat_qualifier_precision_unit_provenance_explicit':True,'new_downloads_used':False,'outputs':{p.name:{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in O.glob('*.parquet')},'elapsed_seconds':round(time.monotonic()-start,2)}
(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
