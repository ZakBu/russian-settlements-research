import json,gzip,re,sys,collections,hashlib
from pathlib import Path
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;W=Path('/workspace/settlements-work/annual_physical_class_extension_20261008');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km
M=R/'research_rebuild/evidence/annual_cached_own_native_history_v4_20261008';manifest=json.loads((M/'raw_source_manifest.json').read_text());native=json.loads((M/'native_state_input_manifest.json').read_text());selected=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');c=duckdb.connect(config={'threads':1});f=c.execute('select source_record_id,settlement_name,settlement_type,oktmo,region_norm,is_additive_settlement_record from read_parquet(?) where census_year=2021',[str(selected)]).fetchdf();c.close();targets={};codeall=collections.defaultdict(set)
for z in f.to_dict('records'):
 code=str(z['oktmo']).removesuffix('.0');codeall[code].add(z['source_record_id'])
 if z['is_additive_settlement_record']:targets[code]=z
cache={}
for path,pin in manifest.items():
 p=Path(path)
 try:d=json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith('.gz') else p.read_bytes())
 except:continue
 for q,e in d.get('entities',{}).items():
  if isinstance(e,dict) and e.get('claims') and (q not in cache or int(e.get('lastrevid',0))>int(cache[q][0].get('lastrevid',0))):cache[q]=(e,p,pin['sha256'])
def val(s):return s.get('datavalue',{}).get('value')
def actual(cs,k):return [x for x in cs.get(k,[]) if x.get('rank') in ('normal','preferred')]
def nk(v):return normalize(re.sub(r'\s*\([^)]*\)\s*$','',v))
physical={'Q532','Q3957','Q515','Q7930989','Q2514025','Q486972','Q771444','Q2023000','Q5084','Q2983893','Q1849719','Q747074','Q15284'};bad={'Q43229','Q56061','Q15284','Q17354472','Q1048835','Q5393308','Q755707','Q1136601','Q15916867','Q4167410'};qcodes=collections.defaultdict(set)
for q,(e,p,h) in cache.items():
 for x in actual(e['claims'],'P764'):
  v=val(x.get('mainsnak',{}))
  if isinstance(v,str):qcodes[v].add(q)
held=[]
for q,(e,p,h) in cache.items():
 cs=e['claims'];codes={val(x.get('mainsnak',{})) for x in actual(cs,'P764')};matches={v if v in targets else v[1:] for v in codes if isinstance(v,str) and (v in targets or (len(v)==11 and v.startswith('0') and v[1:] in targets))}
 if len(matches)!=1:continue
 code=next(iter(matches));r=targets[code]
 if len(codeall[code])!=1 or any(len(qcodes[x])!=1 for x in codes if x==code or x=='0'+code):continue
 names=[x.get('value','') for x in e.get('labels',{}).values()]+[x.get('value','') for lang in e.get('aliases',{}).values() for x in lang]
 if nk(r['settlement_name']) not in set(map(nk,names)):continue
 desc=e.get('descriptions',{}).get('ru',{}).get('value','').lower();p31={v.get('id') for x in actual(cs,'P31') if isinstance((v:=val(x.get('mainsnak',{}))),dict)}
 if p31&bad or re.search(r'^(муниципаль|сельсовет|сельское поселение|городской округ|район\b)|организац|предприяти|железнодорожная станция',desc):continue
 if p31&physical or re.search(r'деревн|село\b|пос[её]лок|город\b|аул\b|хутор\b|станиц',desc):continue
 held.append({'QID':q,**r,'P31':sorted(p31),'description':desc,'raw_entity_path':str(p),'raw_entity_sha256':h,'raw_entity':e})
(O/'unsupported_class_inventory.json').write_text(json.dumps({'candidate_count_without_full3_gate':len(held),'class_counts':dict(collections.Counter(v for z in held for v in z['P31'])),'cases':held},ensure_ascii=False,indent=2)+'\n');print(len(held));print(collections.Counter(v for z in held for v in z['P31']))
from decimal import Decimal
known={'Q24258416','Q27517483','Q27062006','Q20019082','Q15078955'}
# Reuse actual cached target witnesses; avoid graph reconstruction or coverage assertions.
candidates=[z for z in held if set(z['P31'])&known];ids={z['source_record_id'] for z in candidates};points={};pointpins={}
for path,h in native.items():
 p=Path(path)
 if not p.exists() or ('point' not in p.name):continue
 try:
  if p.suffix=='.parquet':db=duckdb.connect(config={'threads':1});d=db.execute('select * from read_parquet(?)',[path]).fetchdf();db.close()
  else:d=pd.read_csv(p,keep_default_na=False)
 except:continue
 if 'target_source_record_id' not in d:continue
 for a in d[d.target_source_record_id.isin(ids)].to_dict('records'):
  if a.get('coordinate_admission_status') not in {'reviewed_extension_rule_accepted','reviewed_accepted','accepted','accepted_same_physical_settlement','accepted_own_coordinate','reviewed_native_own_point_accepted'}:continue
  if 'latitude' not in a:a['latitude']=a.get('carrier_latitude');a['longitude']=a.get('carrier_longitude')
  points[a['target_source_record_id']]=a;pointpins[path]=h
# All known coordinate-risk targets excluded conservatively, including prior recovered targets.
risk=set()
for folder in ['native_mass_raw_roster_point_corrections_20261008','corrected_ownpoint_cached_history_followup_20261008','baseline_seven_ownpoint_recovery_20261008','inherited_extreme_Geo_ownpoint_correction_20261008']:
 for p in (R/'research_rebuild/evidence'/folder).glob('*rejected*point*.csv*'):
  try:risk.update(pd.read_csv(p,keep_default_na=False).target_source_record_id)
  except:pass
 for p in (R/'research_rebuild/evidence'/folder).glob('point_use_rejections.csv*'):
  risk.update(pd.read_csv(p,keep_default_na=False).target_source_record_id)
prior=set();priorpins={}
for folder in ['v3','v4_2']:
 p=Path('/workspace/settlements-work/annual_cached_own_native_history_20261008')/folder/'observations.csv.gz';prior.update(pd.read_csv(p).statement_guid);priorpins[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
rows=[];bindings=[];holds=collections.Counter();inputpins={**pointpins,**priorpins,str(selected):native[str(selected)]}
for z in candidates:
 sid=z['source_record_id'];e=z['raw_entity'];cs=e['claims'];q=z['QID'];inputpins[z['raw_entity_path']]=z['raw_entity_sha256']
 if sid in risk:holds['known_coordinate_risk_target_excluded']+=1;continue
 own=points.get(sid)
 if own is None:holds['no_pinned_accepted_current_ownpoint_witness']+=1;continue
 pts=[v for x in actual(cs,'P625') if isinstance((v:=val(x.get('mainsnak',{}))),dict) and v.get('globe')=='http://www.wikidata.org/entity/Q2'];coords={(a['latitude'],a['longitude']) for a in pts}
 if len(coords)!=1:holds['missing_or_multiple_physical_P625']+=1;continue
 xy=next(iter(coords));dist=distance_km(xy,(float(own['latitude']),float(own['longitude'])))
 if dist>5:holds['ownpoint_contradiction_over5km']+=1;continue
 binding={k:v for k,v in z.items() if k!='raw_entity'};binding.update({'wikidata_qid':q,'current_source_record_id':sid,'current_native_oktmo':z['oktmo'],'current_name':z['settlement_name'],'current_type':z['settlement_type'],'current_ownpoint_json':json.dumps(own,ensure_ascii=False),'own_P625_distance_km':dist,'current_full3_status':'not_reasserted_from_legacy_stage37_target_inventory; root_final_main_membership_separate','binding_rule':'unique_actual_current_native_physical_code_and_literal_name; supported_physical_settlement_class; own_cached_P625_within5km_pinned_accepted_current_ownpoint; known_coordinate_risk_targets_excluded'})
 count=0
 for st in actual(cs,'P1082'):
  guid=st.get('id','')
  if not guid or guid in prior:continue
  quals=st.get('qualifiers',{});dates=quals.get('P585',[])
  if quals.get('P518') or len(dates)!=1:continue
  dt=val(dates[0]);amount=val(st.get('mainsnak',{}))
  if not isinstance(dt,dict) or not isinstance(amount,dict):continue
  m=re.fullmatch(r'\+(\d{4,})-(\d\d)-(\d\d)T.*',dt.get('time',''));pr=dt.get('precision',0)
  if not m or pr<9 or dt.get('before',0) or dt.get('after',0):continue
  year=int(m[1])
  if year in (2002,2010,2021):continue
  if (pr==9 and (m[2],m[3])!=('00','00')) or (pr==10 and (m[2]=='00' or m[3]!='00')) or (pr>=11 and '00' in (m[2],m[3])):continue
  try:n=Decimal(amount['amount'])
  except:continue
  if not n.is_finite() or n<0 or n!=n.to_integral_value() or amount.get('unit')!='1':continue
  rows.append({'source_uid':'WIKIDATA:'+guid,'wikidata_qid':q,'statement_guid':guid,'observed_year':year,'raw_date_literal':dt['time'],'date_precision':pr,'date_calendar':dt.get('calendarmodel',''),'population_value':int(n),'raw_amount':amount['amount'],'rank':st['rank'],'raw_file_path':z['raw_entity_path'],'raw_file_sha256':z['raw_entity_sha256'],'raw_locator':'entities/'+q+'/claims/P1082/'+guid,'raw_statement_json':json.dumps(st,ensure_ascii=False),'population_scope':'literal_whole_item_no_P518','observation_class':'dated_secondary_population_observation','primary_verification':'primary_unverified','boundary_comparability':'UNKNOWN','coordinate_status':'current_own_point_only_retrospective_continuity_inference_not_historical_measurement','no_native_census_full3_credit':True});count+=1
 if count:bindings.append(binding)
for n,d in [('observations.csv.gz',rows),('current_bindings.csv.gz',bindings)]:pd.DataFrame(d).to_csv(W/n,index=False,compression={'method':'gzip','mtime':0})
summary={'status':'bounded cached physical class extension; no graph/census/count or national loader mutation','unsupported_item_candidates_before_full3_gate':len(held),'documented_physical_class_candidates':len(candidates),'accepted_current_entities':len(bindings),'observations':len(rows),'observed_years':sorted({z['observed_year'] for z in rows}),'holds':dict(holds),'physical_classes_reopened':sorted(known),'source_target_status':'current_physical_owncode/name/point bound; root final-main membership separate; no full3 assertion','input_pins':inputpins,'outputs':{str(W/n):hashlib.sha256((W/n).read_bytes()).hexdigest() for n in ['observations.csv.gz','current_bindings.csv.gz']}}
(O/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['input_pins','outputs']}))
# Keep immutable raw entities referenced externally instead of duplicating large entity JSON.
with gzip.open(O/'unsupported_class_inventory.json.gz','wt') as out:json.dump({'candidate_count':len(held),'class_counts':dict(collections.Counter(v for z in held for v in z['P31'])),'cases':[{k:v for k,v in z.items() if k!='raw_entity'} for z in held]},out,ensure_ascii=False)
(O/'unsupported_class_inventory.json').unlink()
