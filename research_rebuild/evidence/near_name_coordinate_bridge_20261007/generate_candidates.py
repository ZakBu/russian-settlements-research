"""Bounded near-name old/current ownpoint candidates on residual graph only."""
import sys,re,json,math,difflib
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd,duckdb,numpy as np
from scipy.spatial import cKDTree
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=ROOT/'research_rebuild/evidence/near_name_coordinate_bridge_20261007';WORK=Path('/workspace/settlements-work/near_name_coordinate_bridge_20261007')
RAWPOOL=Path('/workspace/settlements-work/direct_old_geokladr_point_reserve_20261007/candidate_point_uses.csv')
EXCLUSIONS=ROOT/'research_rebuild/evidence/direct_old_geokladr_point_reserve_20261007_spatial_review/suggested_raw_point_exclusion_keys.csv'
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EVENT=ROOT/'research_rebuild/evidence/event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
def key_name(v):return re.sub(r'[^а-яa-z0-9]+',' ',normalize(v)).strip()
def expand(v):return re.sub(r'\bим\b','имени',v)
def bounded_edit(a,b,limit=2):
 if abs(len(a)-len(b))>limit:return limit+1
 prev=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
  if min(row)>limit:return limit+1
  prev=row
 return prev[-1]
def gender(v):return re.sub(r'(?:ский|ская|ское|ские|ый|ий|ой|ая|яя|ое|ее|ие)$','',v)
def variant(a,b):
 if a==b:return None
 if re.findall(r'\d+',a)!=re.findall(r'\d+',b):return None
 aa,bb=expand(a),expand(b)
 if aa==bb:return ('explicit_imeni_abbreviation',1.0)
 ratio=difflib.SequenceMatcher(None,aa,bb,autojunk=False).ratio()
 at,bt=aa.split(),bb.split()
 if len(at)==len(bt) and all(x==y or (len(gender(x))>=4 and gender(x)==gender(y)) for x,y in zip(at,bt)):return ('literal_name_gender_ending_variant',ratio)
 if ratio<.82:return None
 edit=bounded_edit(aa,bb)
 if edit<=2 and min(len(aa),len(bb))>=5:return ('one_or_two_literal_character_edits',ratio)
 return None
def physical(a):
 return bool(a['is_additive_settlement_record']) and a['region_norm'] not in ['москва','санкт петербург','севастополь','крым'] and not re.search(r'\(часть|\bитого\b|\bвсего\b',normalize(a['settlement_name'])) and 'объект' not in normalize(a['settlement_type'])
def sphere(lat,lon):
 a,b=math.radians(lat),math.radians(lon);return [math.cos(a)*math.cos(b),math.cos(a)*math.sin(b),math.sin(a)]
s=load(15);before=s.metrics();assert [before[str(y)]['covered_population'] for y in [2002,2010,2021]]==[126153231,123384459,123962647]
obs=s.obs.copy();obs['n']=obs.settlement_name.map(key_name);obs['county']=obs.district_raw.map(county_key);obs['root']=obs.source_record_id.map(s.uf.find)
rows=obs.to_dict('records');byid={a['source_record_id']:a for a in rows};members=defaultdict(list)
for a in rows:members[s.uf.find(a['source_record_id'])].append(a)
current=[a for a in rows if int(a['census_year'])==2021 and physical(a) and a['county'] and a['source_record_id'] in s.point_rows and s.years[s.uf.find(a['source_record_id'])]!={2002,2010,2021}]
currentgroups=defaultdict(list)
for a in current:currentgroups[(a['region_norm'],a['county'])].append(a)
indices={}
for key,g in currentgroups.items():
 coords=[sphere(s.point_rows[a['source_record_id']]['latitude'],s.point_rows[a['source_record_id']]['longitude']) for a in g];indices[key]=(g,cKDTree(coords))
raw=pd.read_csv(RAWPOOL,dtype=str,keep_default_na=False).set_index('source_record_id');excluded=set()
if EXCLUSIONS.is_file():
 x=pd.read_csv(EXCLUSIONS,dtype=str);excluded=set(x[x.columns[0]].dropna())
rawmap={sid:a for sid,a in raw.to_dict('index').items() if sid in byid and a['historical_okato_2011_raw'] not in excluded}
eventids=set(pd.read_csv(EVENT,dtype=str).source_record_id)
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
counts=Counter();pairs=[];boundedholds=[]
old=[a for a in rows if int(a['census_year']) in [2002,2010] and physical(a) and a['county'] and s.years[s.uf.find(a['source_record_id'])]!={2002,2010,2021}]
chord=2*math.sin(5/6371.0088/2)
for a in old:
 sid=a['source_record_id'];idx=indices.get((a['region_norm'],a['county']))
 if not idx:counts['no_residual_current_same_explicit_county']+=1;continue
 oldp=s.point_rows.get(sid);rawp=rawmap.get(sid)
 if oldp is None and rawp is None:counts['no_accepted_or_own_raw_old_point']+=1;continue
 point=oldp or rawp;lat,lon=float(point['latitude']),float(point['longitude'])
 near=idx[1].query_ball_point(sphere(lat,lon),chord)
 for j in near:
  b=idx[0][j];bid=b['source_record_id'];cp=s.point_rows[bid]
  if s.uf.find(sid)==s.uf.find(bid):counts['already_connected_nearby']+=1;continue
  v=variant(a['n'],b['n'])
  if v is None:counts['not_new_allowed_name_variant']+=1;continue
  reasons=[]
  if s.years[s.uf.find(sid)]&s.years[s.uf.find(bid)]:reasons.append('repeated_census_year_component_conflict')
  if sid in eventids or bid in eventids:reasons.append('known_event_scoped_endpoint')
  if sid in s.conflicting_point_targets or bid in s.conflicting_point_targets:reasons.append('accepted_point_alternatives_conflict')
  rawroute=oldp is None
  origin=str(point.get('point_origin_file',''))
  currentorigin=str(cp.get('point_origin_file',''))
  independent=bool(origin and currentorigin and origin!=currentorigin and str(point.get('coordinate_source_record_id',''))!=bid)
  if not rawroute and not independent:reasons.append('accepted_old_current_point_lineage_not_independent')
  if rawroute and currentorigin==origin:reasons.append('raw_old_current_point_same_lineage')
  dist=distance_km((lat,lon),(cp['latitude'],cp['longitude']))
  if dist>5:reasons.append('own_point_distance_over_5km')
  relevant=members[s.uf.find(sid)]+members[s.uf.find(bid)]
  if any(r['source_record_id'] in s.point_rows and distance_km((s.point_rows[r['source_record_id']]['latitude'],s.point_rows[r['source_record_id']]['longitude']),(cp['latitude'],cp['longitude']))>5 for r in relevant):reasons.append('accepted_component_point_contradiction_over_5km')
  for r in relevant:
   tid=r['source_record_id'];yr=int(r['census_year'])
   if tid not in s.point_rows and occupied.get((yr,cp['latitude'],cp['longitude']),set())-{tid}:reasons.append('new_point_occupied_same_year')
  if reasons:
   counts.update(set(reasons))
   if len(boundedholds)<150:boundedholds.append({'old_source_record_id':sid,'current_source_record_id':bid,'old_name':a['settlement_name'],'current_name':b['settlement_name'],'county':a['county'],'old_population':a['population'],'current_population':b['population'],'distance_km':dist,'reasons':';'.join(sorted(set(reasons)))})
   continue
  pairs.append({'old_source_record_id':sid,'old_year':int(a['census_year']),'current_source_record_id':bid,'old_name':a['settlement_name'],'current_name':b['settlement_name'],'old_type':a['settlement_type'],'current_type':b['settlement_type'],'type_variation_flag':normalize(a['settlement_type'])!=normalize(b['settlement_type']),'region_norm':a['region_norm'],'county_key':a['county'],'old_district_raw':a['district_raw'],'current_district_raw':b['district_raw'],'old_population':a['population'],'current_population':b['population'],'name_variant_family':v[0],'name_similarity':v[1],'distance_km':dist,'old_point_route':'own_raw_historical_exact_label_type_county' if rawroute else 'independently_originated_accepted_old_point','old_latitude':lat,'old_longitude':lon,'current_latitude':cp['latitude'],'current_longitude':cp['longitude'],'old_point_origin_file':origin,'old_point_origin_sha256':point.get('point_origin_sha256',''),'old_point_origin_locator':point.get('point_origin_locator',''),'old_point_ledger':point.get('point_ledger_path',''),'current_point_origin_file':currentorigin,'current_point_origin_sha256':cp.get('point_origin_sha256',''),'current_point_origin_locator':cp.get('point_origin_locator',''),'current_point_ledger':cp['point_ledger_path'],'historical_okato_2009_raw':rawp.get('historical_okato_2009_raw','') if rawp else '','historical_okato_2011_raw':rawp.get('historical_okato_2011_raw','') if rawp else '','raw_old_name_2009':rawp.get('name_raw_2009','') if rawp else '','raw_old_name_2011':rawp.get('name_raw_2011','') if rawp else '','old_source_file':a['source_file'],'old_source_sha256':a['source_sha256'],'old_source_locator':a['source_locator'],'current_okato':b['okato'],'current_oktmo':b['oktmo'],'candidate_status':'candidate_only_requires_review','population_boundary_comparability_asserted':False,'direct_historical_measurement':False})
# Unique alternatives are computed before any graph mutation, for each historical observation and each current/year target.
f=pd.DataFrame(pairs);f.to_csv(WORK/'preliminary_near_name_pairs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
if len(f):
 multiple=f.duplicated('old_source_record_id',keep=False)|f.duplicated(['old_year','current_source_record_id'],keep=False);counts['multiple_near_name_ownpoint_alternatives']=int(multiple.sum());f[ multiple].to_csv(WORK/'ambiguous_near_name_pairs.csv.gz',index=False,compression={'method':'gzip','mtime':0});f=f[~multiple].copy()
 # Existing native code equivalence is positive corroboration; numeric-provider-width comparisons are not inferred here.
 # Check every eligible endpoint against ALL current ownpoints, including full-three-year components.
 allcurrentgroups=defaultdict(list)
 for q in rows:
  if int(q['census_year'])==2021 and physical(q) and q['county'] and q['source_record_id'] in s.point_rows:allcurrentgroups[(q['region_norm'],q['county'])].append(q)
 allindices={}
 for k,g in allcurrentgroups.items():allindices[k]=(g,cKDTree([sphere(s.point_rows[q['source_record_id']]['latitude'],s.point_rows[q['source_record_id']]['longitude']) for q in g]))
 geo=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet')
 db=duckdb.connect(config={'threads':1,'memory_limit':'600MB'})
 rawcounts=db.execute('SELECT latitude_from_lat,longitude_from_long,count(DISTINCT historical_okato) distinct_raw_codes,min(historical_okato) single_code FROM read_parquet(?) WHERE NOT is_deleted AND latitude_from_lat IS NOT NULL AND longitude_from_long IS NOT NULL GROUP BY ALL',[str(geo)]).fetchdf()
 coordmap={(q.latitude_from_lat,q.longitude_from_long):(int(q.distinct_raw_codes),q.single_code) for q in rawcounts.itertuples()}
 qualified=[];validationholds=[]
 for q in f.to_dict('records'):
  g,tree=allindices[(q['region_norm'],q['county_key'])];alts=[]
  for j in tree.query_ball_point(sphere(q['old_latitude'],q['old_longitude']),chord):
   alt=g[j]
   if alt['source_record_id']==q['current_source_record_id']:continue
   if alt['n']==byid[q['old_source_record_id']]['n'] or variant(byid[q['old_source_record_id']]['n'],alt['n']):alts.append(alt['source_record_id'])
  n,code=coordmap.get((q['old_latitude'],q['old_longitude']),(0,''))
  reasons=[]
  if alts:reasons.append('alternative_all_current_ownpoint_same_county_label_or_variant')
  if n>1:reasons.append('raw_coordinate_shared_by_distinct_historical_codes')
  if n==0:reasons.append('old_coordinate_not_reproduced_in_full_raw_point_file')
  if code in excluded:reasons.append('raw_object_has_known_external_owncode_spatial_contradiction')
  q['raw_distinct_code_coordinate_count']=n;q['own_raw_historical_code_from_coordinate']=code
  q['all_current_ownpoint_alternative_count']=len(alts)
  if reasons:
   validationholds.append({**q,'all_current_alternative_source_record_ids':' | '.join(alts),'additional_hold_reasons':';'.join(reasons)});counts.update(reasons)
  else:qualified.append(q)
 pd.DataFrame(validationholds).to_csv(WORK/'all_current_and_raw_collision_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 f=pd.DataFrame(qualified,columns=[*f.columns,'raw_distinct_code_coordinate_count','own_raw_historical_code_from_coordinate','all_current_ownpoint_alternative_count'])
 f['exact_historical_current_okato_field_agreement']=f.own_raw_historical_code_from_coordinate.ne('')&f.own_raw_historical_code_from_coordinate.eq(f.current_okato.fillna('').astype(str))
 f['direct_historical_census_native_code_binding_asserted']=False
 f['current_okato_field_origin']='selected current source/provider field; not a printed historical census identifier'
 f['potential_complete_component']=f.apply(lambda a:s.years[s.uf.find(a.old_source_record_id)]|s.years[s.uf.find(a.current_source_record_id)]=={2002,2010,2021},axis=1)
 f['component_population_weight']=f.apply(lambda a:sum(float(z['population']) for root in [s.uf.find(a.old_source_record_id),s.uf.find(a.current_source_record_id)] for z in members[root] if pd.notna(z['population'])),axis=1)
 f=f.sort_values(['potential_complete_component','exact_historical_current_okato_field_agreement','component_population_weight'],ascending=False)
edges=[];pointuses=[];acceptedcand=[];extra=set();ledgerhash={}
for a in f.to_dict('records'):
 sid,bid=a['old_source_record_id'],a['current_source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid)
 if ra==rb:counts['already_connected_after_candidate_union']+=1;continue
 if s.years[ra]&s.years[rb]:counts['batch_repeated_year_conflict']+=1;continue
 cp=s.point_rows[bid];relevant=members[ra]+members[rb]
 if any(r['source_record_id'] not in s.point_rows and occupied.get((int(r['census_year']),cp['latitude'],cp['longitude']),set())-{r['source_record_id']} for r in relevant):counts['batch_same_year_point_collision']+=1;continue
 s.union(sid,bid);newroot=s.uf.find(sid);members[newroot]=relevant;acceptedcand.append(a);edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'candidate_only_requires_review','name_variant_family':a['name_variant_family'],'county_key':a['county_key']})
 ledger=Path(cp['point_ledger_path']);ledgerhash.setdefault(str(ledger),sha(ledger))
 for r in relevant:
  tid=r['source_record_id'];yr=int(r['census_year'])
  if tid in s.point_rows or tid in extra:continue
  pointuses.append({'target_source_record_id':tid,'target_year':yr,'latitude':cp['latitude'],'longitude':cp['longitude'],'coordinate_source_record_id':bid,'coordinate_admission_status':'candidate_only_requires_review','coordinate_origin_ledger':str(ledger),'coordinate_origin_ledger_sha256':ledgerhash[str(ledger)],'coordinate_origin_ledger_locator':'target_source_record_id='+bid,'direct_historical_measurement':False,'population_boundary_comparability_asserted':False});extra.add(tid);occupied[(yr,cp['latitude'],cp['longitude'])].add(tid)
cf=pd.DataFrame(acceptedcand);pd.DataFrame(edges,columns=['from_source_record_id','to_source_record_id','relation','decision_status','name_variant_family','county_key']).to_csv(WORK/'candidate_identity_edges.csv',index=False);pd.DataFrame(pointuses).to_csv(WORK/'candidate_point_uses.csv',index=False);cf.to_csv(WORK/'candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(boundedholds).to_csv(OUT/'bounded_holds.csv',index=False)
if len(cf):cf.head(5).to_csv(OUT/'largest5_candidates.csv',index=False);cf.sample(min(15,len(cf)),random_state=20261007).to_csv(OUT/'fixed15_candidates.csv',index=False)
after=s.metrics(extra_point_ids=extra)
receipt={'status':'candidate_only_no_admission','stage':15,'baseline':before,'simulation':after,'residual_current_accepted_point_rows':len(current),'residual_historical_explicit_county_rows':len(old),'raw_ownpoint_candidates_available':len(rawmap),'spatially_name_eligible_pairs':len(pairs),'candidate_edges':len(edges),'candidate_point_uses':len(pointuses),'marginal_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'marginal_full_three_rows':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'screen_counts':dict(counts),'inputs':{str(p):sha(p) for p in [*s.inputs,RAWPOOL,EXCLUSIONS,SEL,EVENT,Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet'),Path(__file__)] if p.is_file()},'donor_ledger_sha256':ledgerhash,'outputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [*WORK.glob('*.csv'),*WORK.glob('*.csv.gz'),*OUT.glob('*.csv')]},'limitations':['Name variants are candidates only; fuzzy name similarity never admits identity.','Literal numbers retained in order, no arbitrary words removed or names swapped.','Own raw historic point binding includes exact old label/type/county, raw-code point collision screen, and independently originated accepted current ownpoint agreement. Known external owncode spatial exclusions held.','Accepted old point must have a distinct source origin from current anchor; shared-lineage old-current pairs held.','Actual component years are disjoint, existing points cannot contradict by>5km, same-year new point collisions held, events/feature grains excluded.','Raw2011 official object code vs selected current OKATO field agreement recorded without code-width repairs; this is not a printed historical census identifier binding. No historical rename inferred.']}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');(OUT/'README.md').write_text('# Near-name ownpoint candidates\n\nOnly graph residual components are searched. Restricted literal spelling/abbreviation/gender-ending variants retain numerical tokens and source words, same explicit county/region and independent ownpoint consistency within5km. Candidates require separate source/identifier review before admission. Accepted current points and legacy inputs remain unchanged.\n')
print(json.dumps({k:receipt[k] for k in ['residual_current_accepted_point_rows','residual_historical_explicit_county_rows','spatially_name_eligible_pairs','candidate_edges','candidate_point_uses','marginal_population_gain','marginal_full_three_rows','screen_counts']},ensure_ascii=False))
