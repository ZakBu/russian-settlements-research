from pathlib import Path
import sys,json,re,hashlib,time,collections,csv
import pandas as pd
T=time.monotonic(); ROOT=Path('/workspace/russian-settlements-research'); E=ROOT/'research_rebuild/evidence'; OUT=E/'wikidata_actual_full3_mass_reserve_20261007'; W=Path('/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007')
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(17); metrics=s.metrics(); exclude=set(); pins={}
for p in [E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv']+[E/d/'accepted_constituent_credit_union.csv' for d in ['named_urban_merger_application_20261007','next_named_urban_merger_application_20261007','further_urban_merger_application_20261007']]+[E/'recreated_named_locality_event_application_20261007/accepted_qualified_physical_observations.csv']:
 if p.exists():
  b=p.read_bytes();pins[str(p)]=hashlib.sha256(b).hexdigest();f=pd.read_csv(p,dtype=str)
  for c in f.columns:
   if 'source_record_id' in c:exclude.update(f[c].dropna())
(OUT/'exclusion_frozen.json').write_text(json.dumps({'source_ids':sorted(exclude),'input_hashes':pins},ensure_ascii=False))
code_map=collections.defaultdict(list)
raw=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
for lineno,line in enumerate(raw.open(),1):
 parts=line.rstrip().split('\t')
 if len(parts)<6:continue
 qs=re.findall(r'Q\d+',parts[0]);codes=re.findall(r'\d{8,11}',parts[1]+' '+parts[2]);label=re.search(r'"(.*)"@ru',parts[4]);admin=re.search(r'"(.*)"@ru',parts[7]) if len(parts)>7 else None
 if not qs or not label:continue
 for code in codes:code_map[code].append((qs[0],label.group(1),admin.group(1) if admin else '',lineno))
targets=[]
for r in s.obs.itertuples():
 if r.census_year!=2021 or r.source_record_id not in s.point_rows or len(s.years[s.uf.find(r.source_record_id)])==3 or r.source_record_id in exclude:continue
 if not pd.notna(r.population) or r.population<0:continue
 p=s.point_rows[r.source_record_id]; loc=str(p.get('point_origin_locator',''))+' '+str(p.get('source_locator',''))+' '+str(p.get('coordinate_source_record_id','')); qids=sorted(set(re.findall(r'\bQ\d+\b',loc)))
 binding='accepted_own_point_QID_locator'
 if len(qids)!=1:
  matches=[]
  for code in [str(r.oktmo),str(r.okato)]:
   for q,label,admin,line in code_map.get(code,[]):
    if label.lower().replace('ё','е')==r.settlement_name.lower().replace('ё','е'):matches.append((q,label,admin,line))
  qids=sorted({m[0] for m in matches})
  if len(qids)!=1:continue
  binding='independent_exact_code_and_own_name_source_row; county='+matches[0][2]+'; tsv_line='+str(matches[0][3])
 targets.append({'sid':r.source_record_id,'qid':qids[0],'name':r.settlement_name,'type':r.settlement_type,'region':r.region_norm,'district':r.district_raw,'population_2021_selected':r.population,'oktmo':r.oktmo,'okato':r.okato,'identity_binding':binding,'point_origin_kind':p.get('point_origin_kind'),'point_origin_locator':p.get('point_origin_locator'),'latitude':p['latitude'],'longitude':p['longitude']})
targets.sort(key=lambda x:(-x['population_2021_selected'],x['sid']));targets=targets[:300];pd.DataFrame(targets).to_csv(OUT/'targets.csv',index=False)
wanted={x['qid'] for x in targets}; found={}; scanned=0; statements=0
paths=list(Path('/workspace/settlements-work/continuation_20261004').rglob('*.json'))
for p in paths:
 if not any(z in str(p).lower() for z in ['wikidata','entity','qid','q1','q2','q3','q4','q5','q6','q7','q8','q9']):continue
 try:a=json.loads(p.read_text())
 except (ValueError,UnicodeDecodeError):continue
 entities=a.get('entities',{}) if isinstance(a,dict) else {}
 if isinstance(a,dict) and 'claims'in a and 'id'in a:entities={a['id']:a}
 if not isinstance(entities,dict):continue
 for q,e in entities.items():
  if q not in wanted or not isinstance(e,dict):continue
  scanned+=1; cs=e.get('claims',{}); pop=cs.get('P1082',[]);statements+=len(pop)
  if not pop:continue
  if q not in found or len(pop)>len(found[q][0].get('claims',{}).get('P1082',[])):found[q]=(e,str(p))
 if scanned>=300 and not (OUT/'first_scan_yield.json').exists():(OUT/'first_scan_yield.json').write_text(json.dumps({'seconds':time.monotonic()-T,'matched_entity_records':scanned,'population_statements':statements,'distinct_matched_qids':len(found)}))
rows=[]; reserves=[]
def val(snak):return snak.get('datavalue',{}).get('value')
for t in targets:
 q=t['qid']
 if q not in found:continue
 e,path=found[q];cs=e.get('claims',{}); h=hashlib.sha256(Path(path).read_bytes()).hexdigest(); by=collections.defaultdict(list)
 for st in cs.get('P1082',[]):
  v=val(st.get('mainsnak',{}))
  if not isinstance(v,dict) or 'amount'not in v:continue
  for dt in st.get('qualifiers',{}).get('P585',[]):
   d=val(dt)
   if not isinstance(d,dict):continue
   year=int(d.get('time','+0000')[1:5])
   if year not in (2002,2010,2021):continue
   refs=st.get('references',[]);urls=[val(v) for ref in refs for v in ref.get('snaks',{}).get('P854',[])]; refitems=[val(v) for ref in refs for v in ref.get('snaks',{}).get('P248',[])]
   precision=d.get('precision'); date=d.get('time'); exact=date[1:11] in ('2002-10-09','2010-10-14','2021-10-01'); cls='exact_census_date_secondary' if exact else ('year_only_dated_secondary_claim' if precision==9 else 'non_census_date_observation_hold')
   row={**t,'year':year,'population':float(v['amount']),'declared_date':date,'date_precision':precision,'statement_id':st.get('id'),'rank':st.get('rank'),'references_count':len(refs),'reference_urls_json':json.dumps(urls,ensure_ascii=False),'reference_items_json':json.dumps(refitems),'date_class':cls,'source_path':path,'source_sha256':h,'locator':f"entities.{q}.claims.P1082[{st.get('id')}]",'status':'candidate_only_secondary_not_primary_verified'}
   rows.append(row);by[year].append(row)
 choices={y:[r for r in by[y] if r['date_class']!='non_census_date_observation_hold' and r['rank']!='deprecated'] for y in (2002,2010,2021)}
 if all(choices.values()):
  distinct={y:{r['population'] for r in rr} for y,rr in choices.items()}; coords=cs.get('P625',[]); kinds=[val(x.get('mainsnak',{})) for x in cs.get('P31',[])];des=e.get('descriptions',{}).get('ru',{}).get('value','');label=e.get('labels',{}).get('ru',{}).get('value','')
  hold=[]
  if t['region'] in ('крым','севастополь'):hold.append('2002_2010_not_Russian_census_scope')
  if any(r['date_class']=='year_only_dated_secondary_claim' and r['references_count']==0 for rr in choices.values() for r in rr):hold.append('year_only_no_census_reference')
  if any(len(z)!=1 for z in distinct.values()):hold.append('conflicting_population_values')
  # Multiple P625 is an optional coordinate-source flag; accepted own point retained.
  if any(z in des.lower() for z in ['муниципальное образование','муниципальный округ','муниципальный район','сельсовет','часть город']) or des.lower().startswith(('район ', 'городской округ ', 'сельское поселение ')):hold.append('municipality_or_citypart_description')
  reserves.append({**t,'p2002':next(iter(distinct[2002])),'p2010':next(iter(distinct[2010])),'p2021':next(iter(distinct[2021])),'wikidata_label':label,'description':des,'P31_json':json.dumps(kinds),'P625_count':len(coords),'hold_reason':';'.join(hold),'status':'candidate_only_identity_continuity_not_admitted','source_path':path,'source_sha256':h})
pd.DataFrame(rows).to_csv(OUT/'actual_target_year_claims.csv',index=False);pd.DataFrame(reserves).to_csv(OUT/'full3_candidates.csv',index=False)
receipt={'stage':17,'baseline':metrics,'wall_seconds':time.monotonic()-T,'targets':len(targets),'unique_target_qids':len(wanted),'matching_cached_entity_records':scanned,'cached_distinct_qids':len(found),'all_matching_population_statement_count':statements,'target_year_claim_rows':len(rows),'full3_candidates':len(reserves),'candidate_population_potential_2021':sum(r['population_2021_selected'] for r in reserves),'nonheld_candidate_population_potential_2021':sum(r['population_2021_selected'] for r in reserves if not r['hold_reason']),'new_admitted_gain':0,'error_rate':'uncalibrated','coordinate_bounds':'UNKNOWN','notes':'Candidate-only dated secondary claims. Year-only dates remain explicit, never assigned October date. January estimates held. Current point own QID from accepted locator; continuity requires source verification. No ordinary claim for absorbed or newly-created units.'}
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False));print(json.dumps(receipt,ensure_ascii=False))
