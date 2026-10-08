from pathlib import Path
import sys,json,gzip,re,collections,math
import pandas as pd
R=Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
s=load(44);pins={str(p):sha(p) for p in s.inputs};credits=set();excluded=set()
for p in [E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'working_full_chain_20261007/named_merger_lineage_constituents.csv',E/'working_full_chain_20261007/complete_territorial_scope_constituents.csv',E/'working_full_chain_20261007/complete_publisher_partition_members.csv',E/'native2010_whole_region_name_type_mass_20261008/accepted_source_binding_witness.csv.gz',E/'ownlegacy_ownpoint_route_gap_mass_20261008/accepted_native_observation_pins.csv.gz']:
 if p.exists():
  f=pd.read_csv(p,dtype=str,keep_default_na=False);pins[str(p)]=sha(p)
  for k in f:
   if 'source_record_id' in k:
    (excluded if 'native2010_whole' in str(p) or 'ownlegacy_ownpoint' in str(p) else credits).update(f[k])
T=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');pins[str(T)]=sha(T);qcode=collections.defaultdict(set)
for line in T.open():
 v=line.rstrip().split('\t');q=re.findall('Q[0-9]+',v[0]) if v else []
 if q and len(v)>=3:
  for code in re.findall('[0-9]{8,11}',v[1]+' '+v[2]):qcode[code].add(q[0])
def code(v):return '' if pd.isna(v) else str(v).removesuffix('.0')
def typed(v):return re.sub(r'^(?:поселок|село|деревня|хутор|город)\s+','',normalize(v))
rows=[];current=collections.defaultdict(list)
for x in s.obs[s.obs.census_year.eq(2021)&s.obs.is_additive_settlement_record.fillna(False)].itertuples():
 if x.source_record_id in s.point_rows:current[(normalize(x.name_norm),normalize(x.region_norm))].append(x.source_record_id)
for root,g in s.obs.groupby('root',sort=False):
 if set(g.census_year)!={2002,2021} or len(g)!=2 or not g.is_additive_settlement_record.fillna(False).all():continue
 ids=list(g.source_record_id)
 if set(ids)&(credits|excluded) or any(i not in s.point_rows or i in s.conflicting_point_targets for i in ids):continue
 cur=g[g.census_year.eq(2021)].iloc[0];old=g[g.census_year.eq(2002)].iloc[0];sid=cur.source_record_id;cp=s.point_rows[sid];direct=set(re.findall(r'\bQ[0-9]+\b',str(cp.get('coordinate_source_record_id',''))+' '+str(cp.get('point_origin_locator',''))));qs=direct|qcode[code(cur.okato)]|qcode[code(cur.oktmo)];rows.append({'current_source_record_id':sid,'native2002_source_record_id':old.source_record_id,'name':cur.settlement_name,'native2002_name':old.settlement_name,'current_type':cur.settlement_type,'region':cur.region_norm,'current_county':cur.district_raw,'native2002_county':old.district_raw,'population2002':old.population,'population2021':cur.population,'priority_weight':max(old.population,cur.population),'current_okato':code(cur.okato),'current_oktmo':code(cur.oktmo),'own_QIDs_json':json.dumps(sorted(qs)),'direct_QIDs_json':json.dumps(sorted(direct)),'current_point_json':json.dumps(cp,ensure_ascii=False)})
f=pd.DataFrame(rows).sort_values('priority_weight',ascending=False);f.to_csv(O/'current44_disjoint_missing2010.csv.gz',index=False,compression={'method':'gzip','mtime':0});wanted={q for x in f.own_QIDs_json for q in json.loads(x)};paths=set()
for file in [E/'temporal_missing2002_all_components_20261008/receipt.json',E/'own_uncached2002_secondary_scope_20261008/queue_receipt.json']:
 if file.exists():paths.update(Path(p) for p in json.load(open(file))['input_pins'] if p.endswith('.json.gz') or p.endswith('.json'))
for folder in ['/workspace/settlements-raw/data/raw/wikidata_entities_full','/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007','/workspace/settlements-work/additional_uncached_census_histories_20261008','/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007','/workspace/settlements-work/own_dated2002_secondary_scope_20261008','/workspace/settlements-work/own_uncached2002_secondary_scope_20261008']:
 paths.update(Path(folder).glob('*.json.gz'))
entities={};labels={};rawpins={}
for p in sorted(paths):
 if not p.exists():continue
 try:b=p.read_bytes();d=json.loads(gzip.decompress(b) if p.name.endswith('.gz') else b)
 except:continue
 es=d.get('entities',d.get('payload',{}).get('entities',{})) if isinstance(d,dict) else {}
 if not isinstance(es,dict):continue
 for q,e in es.items():
  if not isinstance(e,dict):continue
  label=e.get('labels',{}).get('ru',{}).get('value','')
  if label:labels[q]=label
  if q in wanted and(q not in entities or len(e.get('claims',{}).get('P1082',[]))>len(entities[q][0].get('claims',{}).get('P1082',[]))):entities[q]=(e,str(p));rawpins[str(p)]=sha(p)
def val(sn):return sn.get('datavalue',{}).get('value')
physical={'Q532','Q5084','Q486972','Q2514025','Q15078955','Q24258416','Q27062006','Q27517483'};claims=[];holds=[];aliases=[];codes=collections.Counter(code(x) for x in s.obs.loc[s.obs.census_year.eq(2021)&s.obs.is_additive_settlement_record.fillna(False),'oktmo'])
for a in f.to_dict('records'):
 cp=json.loads(a['current_point_json']);near=[sid for sid in current[(normalize(a['name']),normalize(a['region']))] if distance_km((cp['latitude'],cp['longitude']),(s.point_rows[sid]['latitude'],s.point_rows[sid]['longitude']))<=5];allitems=[]
 for q in json.loads(a['own_QIDs_json']):
  if q not in entities:continue
  e,path=entities[q];cs=e.get('claims',{});label=e.get('labels',{}).get('ru',{}).get('value','');names=[label]+[x['value'] for x in e.get('aliases',{}).get('ru',[])];namepositive=bool({typed(a['name']),typed(a['native2002_name'])}&{typed(n) for n in names});p31={val(x['mainsnak']).get('id') for x in cs.get('P31',[]) if isinstance(val(x.get('mainsnak',{})),dict) and x.get('rank')!='deprecated'};codepositive=a['current_okato'] in [val(x['mainsnak']) for x in cs.get('P721',[]) if x.get('rank')!='deprecated'] or a['current_oktmo'] in [val(x['mainsnak']) for x in cs.get('P764',[]) if x.get('rank')!='deprecated'];owncoords=[val(x['mainsnak']) for x in cs.get('P625',[]) if x.get('rank')!='deprecated'];pointpositive=any(isinstance(v,dict) and 'latitude' in v and distance_km((cp['latitude'],cp['longitude']),(v['latitude'],v['longitude']))<=1 for v in owncoords);direct=q in json.loads(a['direct_QIDs_json']);bound=namepositive and bool(p31&physical) and(direct or(codepositive and pointpositive)) and near==[a['current_source_record_id']] and codes[a['current_oktmo']]==1
  for n in names:
   if n:aliases.append({'current_source_record_id':a['current_source_record_id'],'qid':q,'alias':n,'own_entity_bound':bound,'raw_source_path':path,'raw_sha256':rawpins[path]})
  foundation=[val(x['mainsnak']).get('time','') for x in cs.get('P571',[]) if isinstance(val(x.get('mainsnak',{})),dict)];post2010=any(v.startswith('+') and int(v[1:5])>2010 for v in foundation)
  for st in cs.get('P1082',[]):
   amount=val(st.get('mainsnak',{}))
   if not isinstance(amount,dict) or st.get('rank')=='deprecated' or st.get('qualifiers',{}).get('P518'):continue
   for x in st.get('qualifiers',{}).get('P585',[]):
    date=val(x)
    if not isinstance(date,dict) or not date.get('time','').startswith('+2010') or date.get('precision',0)<9:continue
    refs=st.get('references',[]);titles=[val(v).get('text','') for r in refs for v in r.get('snaks',{}).get('P1476',[]) if isinstance(val(v),dict)];ids=[val(v).get('id','') for r in refs for v in r.get('snaks',{}).get('P248',[]) if isinstance(val(v),dict)];urls=[str(val(v)) for r in refs for v in r.get('snaks',{}).get('P854',[])];methods=[val(v).get('id','') for v in st.get('qualifiers',{}).get('P459',[]) if isinstance(val(v),dict)];proof=date['time'].startswith('+2010-10-14') or any(labels.get(m)=='перепись населения' for m in methods) or any(re.search('перепис|census|впн|vpn2010',t,re.I) and '2010' in t for t in titles+urls+[labels.get(i,'') for i in ids]);claim={**a,'qid':q,'own_label':label,'own_aliases_json':json.dumps(names,ensure_ascii=False),'own_entity_bound':bound,'own_native_code_positive':codepositive,'own_P625_within1km':pointpositive,'own_direct_QID_positive':direct,'P31_json':json.dumps(sorted(p31)),'population2010':float(amount['amount']),'date':date['time'],'precision':date['precision'],'explicit_census2010_proof':proof,'P459_ids_json':json.dumps(methods),'P459_labels_json':json.dumps([labels.get(m,'') for m in methods],ensure_ascii=False),'reference_titles_json':json.dumps(titles,ensure_ascii=False),'reference_ids_json':json.dumps(ids),'reference_labels_json':json.dumps([labels.get(i,'') for i in ids],ensure_ascii=False),'reference_urls_json':json.dumps(urls),'raw_entity_path':path,'raw_entity_sha256':rawpins[path],'statement_id':st.get('id',''),'post2010_foundation':post2010,'foundation_dates_json':json.dumps(foundation),'all_current_5km_name_candidates_json':json.dumps(near)};claims.append(claim)
cf=pd.DataFrame(claims);cf.to_csv(O/'cached_literal2010_claims.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(aliases).to_csv(O/'cached_literal_own_aliases.csv.gz',index=False,compression={'method':'gzip','mtime':0});positive=cf[cf.own_entity_bound&cf.explicit_census2010_proof&~cf.post2010_foundation].copy() if len(cf) else cf;positive.to_csv(O/'positive_bound_census2010_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});p=positive.drop_duplicates('current_source_record_id');receipt={'baseline_stage':44,'remaining_missing2010_disjoint_components':len(f),'own_QIDs_wanted':len(wanted),'own_QIDs_cached':len(entities),'literal_dated2010_claims':len(cf),'bound_explicit_census2010_components':len(p),'population_existing_native2002_potential':int(p.population2002.sum()) if len(p) else 0,'population_existing_native2021_potential':int(p.population2021.sum()) if len(p) else 0,'secondary2010_literal_population':int(p.population2010.sum()) if len(p) else 0,'no_network':True,'no_native2010_binding_or_count_credit_asserted':True,'input_pins':pins|rawpins,'output_pins':{p.name:sha(p) for p in O.glob('*.csv.gz')}};(O/'inventory_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
