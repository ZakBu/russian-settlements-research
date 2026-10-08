from pathlib import Path
import json,gzip,hashlib,collections,re
import pandas as pd,duckdb
O=Path(__file__).parent;E=O.parents[1];t=pd.read_csv(O/'temporal_gap_trajectories.csv.gz',keep_default_na=False);t=t[(t.missing_year.eq(2002))&t.route.eq('no_selected_exact_name_or_current_code_third_year_row_observed_source_needed')];wanted={q for x in t.current_ownpoint_qids_json for q in json.loads(x)};paths=set();manifestpins={}
for p in [E/'cached_secondary_native_year_mass_reserve_20261008/source_manifest.json',E/'additional_uncached_census_histories_20261008/source_manifest.json']:
 d=json.loads(p.read_text());paths.update(d.get('raw_entity_cache',{}));manifestpins[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
paths.update(str(p)for p in Path('/workspace/settlements-raw/data/raw/wikidata_entities_full').glob('*.json.gz'));paths.update(str(p)for p in Path('/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007').glob('*.json.gz'));entities={};labels={};rawpins={}
for path in sorted(paths):
 p=Path(path)
 try:b=p.read_bytes();a=json.loads(gzip.decompress(b)if p.name.endswith('.gz')else b)
 except Exception:continue
 es=a.get('entities',a.get('payload',{}).get('entities',{}))if isinstance(a,dict)else{}
 if not isinstance(es,dict):continue
 for q,v in es.items():
  if not isinstance(v,dict):continue
  if v.get('labels',{}).get('ru',{}).get('value'):labels[q]=v['labels']['ru']['value']
  if q in wanted and(q not in entities or len(v.get('claims',{}).get('P1082',[]))>len(entities[q][0].get('claims',{}).get('P1082',[]))):entities[q]=(v,path);rawpins[path]=hashlib.sha256(b).hexdigest()
def val(s):return s.get('datavalue',{}).get('value')
def norm(v):return ' '.join(str(v).lower().replace('ё','е').split())
def explicit(text):return bool(re.search(r'перепис|census|vpn2002|впн',text,re.I))and('2002'in text or 'vpn2002'in text.lower())
rows=[];alias=[]
for r in t.to_dict('records'):
 qs=json.loads(r['current_ownpoint_qids_json']);qualified=[];generic=[];a_names=set();foundation=[];matched=[]
 for q in qs:
  if q not in entities:continue
  e,path=entities[q];matched.append(q);cs=e.get('claims',{});a_names.update(norm(x.get('value',''))for x in e.get('aliases',{}).get('ru',[]));a_names.add(norm(e.get('labels',{}).get('ru',{}).get('value','')))
  for st in cs.get('P571',[]):
   value=val(st.get('mainsnak',{}))
   if isinstance(value,dict):foundation.append(value.get('time',''))
  for st in cs.get('P1082',[]):
   amount=val(st.get('mainsnak',{}));dates=[val(x)for x in st.get('qualifiers',{}).get('P585',[])];refs=st.get('references',[])
   if not isinstance(amount,dict)or st.get('rank')=='deprecated'or st.get('qualifiers',{}).get('P518'):continue
   for date in dates:
    if not isinstance(date,dict)or not date.get('time','').startswith('+2002'):continue
    title=[val(sn).get('text','')for ref in refs for sn in ref.get('snaks',{}).get('P1476',[])if isinstance(val(sn),dict)];ids=[val(sn).get('id','')for ref in refs for sn in ref.get('snaks',{}).get('P248',[])if isinstance(val(sn),dict)];urls=[str(val(sn))for ref in refs for sn in ref.get('snaks',{}).get('P854',[])];proof=date.get('time','')[1:11]=='2002-10-09'or any(explicit(v)for v in title+urls+[labels.get(v,'')for v in ids]);point={'qid':q,'population2002':float(amount['amount']),'declared_date':date.get('time',''),'precision':date.get('precision'),'census_proof_available':proof,'source_file':path,'source_sha256':rawpins[path],'source_locator':f'entities.{q}.claims.P1082[{st.get("id","")}]','reference_titles':title,'reference_ids':ids,'reference_urls':urls};(qualified if proof else generic).append(point)
 rows.append({'trajectory_current_source_record_id':r['trajectory_current_source_record_id'],'name':r['name'],'region':r['region'],'current_county':r['current_county'],'maximum_observed_population_weight':r['maximum_observed_population'],'own_QIDs_json':r['current_ownpoint_qids_json'],'cached_own_QIDs_json':json.dumps(matched),'explicit_census2002_secondary_observations_json':json.dumps(qualified,ensure_ascii=False),'generic_dated2002_population_observations_json':json.dumps(generic,ensure_ascii=False),'explicit_census2002_candidate':len({x['population2002']for x in qualified})==1,'generic2002_count_available':bool(generic),'post2002_foundation_asserted_by_cached_item':any(v.startswith('+')and int(v[1:5])>2002 for v in foundation),'cached_P571_dates_json':json.dumps(foundation),'own_aliases_json':json.dumps(sorted(a_names),ensure_ascii=False),'new_population_credit_asserted':False})
 for n in a_names:
  if n:alias.append({'sid':r['trajectory_current_source_record_id'],'name':r['name'],'alias':n,'region':r['region'],'weight':r['maximum_observed_population']})
f=pd.DataFrame(rows);f.to_csv(O/'cached_2002_own_item_source_inventory.csv.gz',index=False,compression={'method':'gzip','mtime':0});sel=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');con=duckdb.connect(config={'threads':1,'memory_limit':'200MB'});old=con.execute('select source_record_id,settlement_name,settlement_type,region_norm,district_raw,population,source_file from read_parquet(?)where census_year=2002 and is_additive_settlement_record',[str(sel)]).fetchdf();old['n']=old.settlement_name.map(norm);ix={k:g for k,g in old.groupby(['n','region_norm'])};matches=[]
for a in alias:
 for v in ix.get((a['alias'],a['region']),pd.DataFrame()).to_dict('records'):matches.append({'trajectory_current_source_record_id':a['sid'],'current_name':a['name'],'cached_own_item_literal_alias':a['alias'],'region':a['region'],'maximum_observed_population_weight':a['weight'],'candidate_missing2002_source_record_id':v['source_record_id'],'candidate_native2002_name':v['settlement_name'],'candidate_native2002_type':v['settlement_type'],'candidate_native2002_county':v['district_raw'],'candidate_native2002_population':v['population'],'candidate_source_file':v['source_file'],'candidate_only_own_alias_does_not_prove_native_binding':True})
pd.DataFrame(matches).to_csv(O/'cached_alias_native2002_candidate_rows.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'status':'cached_source_route_inventory_only','targets':len(t),'wanted_own_QIDs':len(wanted),'cached_own_QIDs':len(entities),'cache_files_examined':len(paths),'explicit_census2002_candidate_trajectories':int(f.explicit_census2002_candidate.sum()),'explicit_census2002_population_weight':int(f.loc[f.explicit_census2002_candidate,'maximum_observed_population_weight'].sum()),'generic_dated2002_population_available_trajectories':int(f.generic2002_count_available.sum()),'generic_dated2002_population_weight':int(f.loc[f.generic2002_count_available,'maximum_observed_population_weight'].sum()),'cached_post2002_foundation_trajectories':int(f.post2002_foundation_asserted_by_cached_item.sum()),'native_alias_source_candidate_rows':len(matches),'input_pins':manifestpins|rawpins|{str(sel):hashlib.sha256(sel.read_bytes()).hexdigest()},'output_pins':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in O.glob('cached*csv.gz')},'generic_year2002_never_promoted_to_census2002_without_proof':True};(O/'cached_source_route_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items()if k not in ['input_pins','output_pins']},ensure_ascii=False))
