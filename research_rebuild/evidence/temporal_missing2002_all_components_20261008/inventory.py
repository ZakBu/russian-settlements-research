from pathlib import Path
import sys,json,gzip,re,collections,hashlib
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;E=O.parent;s=load(34);pins={str(p):sha(p) for p in s.inputs};exclude=E/'legacy_coordinate_current_ownpoint_mass_20261008/missing_third_year_priority/proposed_bounded_2002_source_batch.csv.gz';queue=pd.read_csv(exclude,keep_default_na=False);excluded_sid=set(queue.trajectory_current_source_record_id);excluded_q={q for x in queue.own_QIDs_json for q in json.loads(x)};pins[str(exclude)]=sha(exclude)
# Existing accepted source-ID references and existing supplemental histories mark already covered source rows.
credits=set()
for p in [PARTITION_MEMBERS,E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'working_full_chain_20261007/named_merger_lineage_constituents.csv',E/'working_full_chain_20261007/complete_territorial_scope_constituents.csv']:
 if p.exists():
  f=pd.read_csv(p,dtype=str,keep_default_na=False);pins[str(p)]=sha(p)
  if 'source_record_id' in f:credits.update(f.source_record_id)
for folder in ['qualified_scoped_municipal_three_census_20261008','city_primary2002_mass_application_20261008','source_closed_city_territory_application_20261008']:
 for p in (E/folder).glob('*credit*csv'):
  f=pd.read_csv(p,dtype=str,keep_default_na=False);pins[str(p)]=sha(p)
  if 'source_record_id' in f:credits.update(f.source_record_id)
# Native classifier TSV extraction is discovery only. Exact code collisions retained; no admission asserted.
T=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');pins[str(T)]=sha(T);qcode=collections.defaultdict(set)
for line in T.open():
 v=line.rstrip().split('\t');qs=re.findall(r'Q\d+',v[0]) if v else []
 if qs and len(v)>=3:
  for k in re.findall(r'\d{8,11}',v[1]+' '+v[2]):qcode[k].add(qs[0])
def code(v):
 if pd.isna(v):return ''
 try:return str(int(v))
 except:return str(v).removesuffix('.0')
rows=[]
for root,g in s.obs.groupby('root',sort=False):
 if set(g.census_year)!={2010,2021} or len(g)!=2 or not g.is_additive_settlement_record.fillna(False).all():continue
 if g.region_norm.isin(['москва','санкт петербург','севастополь','крым']).any():continue
 ids=list(g.source_record_id)
 if not all(x in s.point_rows and x not in s.conflicting_point_targets for x in ids):continue
 cur=g[g.census_year.eq(2021)].iloc[0];old=g[g.census_year.eq(2010)].iloc[0];sid=cur.source_record_id;cp=s.point_rows[sid];direct=set(re.findall(r'\bQ\d+\b',str(cp.get('coordinate_source_record_id',''))+' '+str(cp.get('point_origin_locator',''))));qs=direct|qcode.get(code(cur.okato),set())|qcode.get(code(cur.oktmo),set());excluded=bool(sid in excluded_sid or qs&excluded_q)
 rows.append({'current_source_record_id':sid,'native2010_source_record_id':old.source_record_id,'name':cur.settlement_name,'native2010_name':old.settlement_name,'region':cur.region_norm,'current_county':cur.district_raw,'native2010_county':old.district_raw,'current_type':cur.settlement_type,'population2010':old.population,'population2021':cur.population,'maximum_observed_population_weight':max(old.population,cur.population),'current_native_okato':code(cur.okato),'current_native_oktmo':code(cur.oktmo),'direct_own_point_QIDs_json':json.dumps(sorted(direct)),'own_native_code_QID_candidates_json':json.dumps(sorted(qs)),'excluded_pending_queue':excluded,'already_source_ID_credit_union':bool(set(ids)&credits),'current_point_latitude':cp['latitude'],'current_point_longitude':cp['longitude'],'current_point_origin_file':cp.get('point_origin_file',''),'current_point_origin_locator':cp.get('point_origin_locator',''),'current_point_source_record_id':cp.get('coordinate_source_record_id',''),'current_point_origin_sha256':cp.get('point_origin_sha256',''),'native_point_measurement2002_asserted':False})
f=pd.DataFrame(rows).sort_values('maximum_observed_population_weight',ascending=False);f.to_csv(O/'all_two_year_components.csv.gz',index=False,compression={'method':'gzip','mtime':0});f.head(100).to_csv(O/'all_components_top100.csv',index=False);active=f[~f.excluded_pending_queue&~f.already_source_ID_credit_union].copy();active.head(100).to_csv(O/'disjoint_components_top100.csv',index=False);wanted={q for x in active.own_native_code_QID_candidates_json for q in json.loads(x)}
# Inventory the existing raw caches named by source manifests, plus known national caches. No network.
paths=set()
for p in [E/'cached_secondary_native_year_mass_reserve_20261008/source_manifest.json',E/'additional_uncached_census_histories_20261008/source_manifest.json']:
 if p.exists():pins[str(p)]=sha(p);paths.update(json.load(open(p)).get('raw_entity_cache',{}))
for root,pat in [('/workspace/settlements-raw/data/raw/wikidata_entities_full','*.json.gz'),('/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007','*.json.gz'),('/workspace/settlements-work/additional_uncached_census_histories_20261008','*.json.gz'),('/workspace/settlements-work/continuation_20261004/R4/residual_alias_fetch/raw_entity_batches','*.json')]:paths.update(str(p) for p in Path(root).glob(pat))
entities={};labels={};rawpins={};files_read=0
for path in sorted(paths):
 p=Path(path)
 try:
  b=p.read_bytes();a=json.loads(gzip.decompress(b) if p.name.endswith('.gz') else b)
 except:continue
 es=a.get('entities',a.get('payload',{}).get('entities',{})) if isinstance(a,dict) else {}
 if not isinstance(es,dict):continue
 files_read+=1
 for q,z in es.items():
  if not isinstance(z,dict):continue
  lab=z.get('labels',{}).get('ru',{}).get('value')
  if lab:labels[q]=lab
  if q in wanted:
   if q not in entities or len(z.get('claims',{}).get('P1082',[]))>len(entities[q][0].get('claims',{}).get('P1082',[])):entities[q]=(z,path);rawpins[path]=hashlib.sha256(b).hexdigest()
def val(s):return s.get('datavalue',{}).get('value')
def explicit(text):return bool(re.search(r'перепис|census|vpn2002|впн',str(text),re.I)) and ('2002' in str(text) or 'vpn2002' in str(text).lower())
inventory=[];claims=[];aliases=[]
for a in active.to_dict('records'):
 qs=json.loads(a['own_native_code_QID_candidates_json']);qualified=[];generic=[];bound=[];cached=[];foundation=[]
 for q in qs:
  if q not in entities:continue
  z,path=entities[q];cached.append(q);cs=z.get('claims',{});p764=[val(x['mainsnak']) for x in cs.get('P764',[]) if x.get('rank')!='deprecated'];p721=[val(x['mainsnak']) for x in cs.get('P721',[]) if x.get('rank')!='deprecated'];direct=q in json.loads(a['direct_own_point_QIDs_json']);exactcode=a['current_native_oktmo'] in p764 or a['current_native_okato'] in p721;coords=[val(x['mainsnak']) for x in cs.get('P625',[]) if x.get('rank')!='deprecated'];owncoords=[v for v in coords if isinstance(v,dict) and 'latitude' in v];near=any(distance_km((a['current_point_latitude'],a['current_point_longitude']),(v['latitude'],v['longitude']))<=1 for v in owncoords);binding=direct or (exactcode and near)
  if binding:bound.append(q)
  names={normalize(v['value']) for v in z.get('aliases',{}).get('ru',[])};names.add(normalize(z.get('labels',{}).get('ru',{}).get('value','')))
  for name in names:
   if name:aliases.append({'current_source_record_id':a['current_source_record_id'],'qid':q,'alias':name,'own_entity_bound':binding,'raw_source_file':path,'raw_source_sha256':rawpins[path]})
  for x in cs.get('P571',[]):
   value=val(x.get('mainsnak',{}))
   if isinstance(value,dict):foundation.append(value.get('time',''))
  for x in cs.get('P1082',[]):
   amount=val(x.get('mainsnak',{}));dates=[val(v) for v in x.get('qualifiers',{}).get('P585',[])];refs=x.get('references',[])
   if not isinstance(amount,dict) or x.get('rank')=='deprecated' or x.get('qualifiers',{}).get('P518'):continue
   for date in dates:
    if not isinstance(date,dict) or not date.get('time','').startswith('+2002'):continue
    titles=[val(sn).get('text','') for ref in refs for sn in ref.get('snaks',{}).get('P1476',[]) if isinstance(val(sn),dict)];ids=[val(sn).get('id','') for ref in refs for sn in ref.get('snaks',{}).get('P248',[]) if isinstance(val(sn),dict)];urls=[str(val(sn)) for ref in refs for sn in ref.get('snaks',{}).get('P854',[])];proof=date.get('time','')[1:11]=='2002-10-09' or any(explicit(t) for t in titles+urls+[labels.get(x,'') for x in ids]);claim={'current_source_record_id':a['current_source_record_id'],'name':a['name'],'region':a['region'],'qid':q,'population2002':float(amount['amount']),'date':date.get('time',''),'precision':date.get('precision'),'explicit_census2002_proof':proof,'own_entity_bound':binding,'bound_by_direct_point_QID':direct,'native_code_exact_cached_claim':exactcode,'own_P625_within1km':near,'raw_entity_file':path,'raw_entity_sha256':rawpins[path],'raw_locator':f'entities.{q}.claims.P1082[{x.get("id","")}]','reference_titles_json':json.dumps(titles,ensure_ascii=False),'reference_ids_json':json.dumps(ids),'reference_urls_json':json.dumps(urls),'reference_item_labels_json':json.dumps([labels.get(x,'') for x in ids],ensure_ascii=False),'maximum_observed_population_weight':a['maximum_observed_population_weight'],'claim2002_population_not_admitted':True};claims.append(claim);(qualified if proof and binding else generic).append(claim)
 distinct=set(x['population2002'] for x in qualified);post=any(t.startswith('+') and int(t[1:5])>2002 for t in foundation)
 inventory.append({**a,'cached_own_QIDs_json':json.dumps(cached),'independently_bound_cached_QIDs_json':json.dumps(bound),'explicit_census2002_own_observation_count':len(qualified),'explicit_census2002_unique_population':len(distinct)==1,'candidate_secondary_population2002':next(iter(distinct)) if len(distinct)==1 else '', 'generic_or_unbound2002_claims':len(generic),'post2002_foundation_cached':post,'cached_foundation_dates_json':json.dumps(foundation)})
i=pd.DataFrame(inventory);i.to_csv(O/'disjoint_cached_claim_inventory.csv.gz',index=False,compression={'method':'gzip','mtime':0});cf=pd.DataFrame(claims);cf.to_csv(O/'cached_dated2002_claims.csv.gz',index=False,compression={'method':'gzip','mtime':0});af=pd.DataFrame(aliases);af.to_csv(O/'cached_literal_aliases.csv.gz',index=False,compression={'method':'gzip','mtime':0})
# Literal aliases and own current native code retrieve all native2002 rivals before any identity gate.
old=s.obs[s.obs.census_year.eq(2002)&s.obs.is_additive_settlement_record.fillna(False)].copy();old['n']=old.settlement_name.map(normalize);ix={k:g for k,g in old.groupby(['n','region_norm'])};old['code']=old.okato.map(code);cx={k:g for k,g in old[old.code.ne('')].groupby('code')};regions=active.set_index('current_source_record_id').region.to_dict();matches=[]
for a in aliases:
 for b in ix.get((a['alias'],regions[a['current_source_record_id']]),pd.DataFrame()).to_dict('records'):
  matches.append({'current_source_record_id':a['current_source_record_id'],'qid':a['qid'],'matching_own_item_literal_alias':a['alias'],'own_entity_bound':a['own_entity_bound'],'native2002_source_record_id':b['source_record_id'],'native2002_name':b['settlement_name'],'native2002_county':b['district_raw'],'native2002_population':b['population'],'native2002_source_file':b['source_file'],'native2002_source_locator':b['source_locator'],'native2002_component_years':json.dumps(sorted(s.years[s.uf.find(b['source_record_id'])])),'native2002_already_credit_union':b['source_record_id'] in credits,'candidate_only':True})
for a in active.to_dict('records'):
 for b in cx.get(a['current_native_okato'],pd.DataFrame()).to_dict('records'):
  matches.append({'current_source_record_id':a['current_source_record_id'],'qid':'','matching_own_item_literal_alias':'native_current_own_okato_exact','own_entity_bound':False,'native2002_source_record_id':b['source_record_id'],'native2002_name':b['settlement_name'],'native2002_county':b['district_raw'],'native2002_population':b['population'],'native2002_source_file':b['source_file'],'native2002_source_locator':b['source_locator'],'native2002_component_years':json.dumps(sorted(s.years[s.uf.find(b['source_record_id'])])),'native2002_already_credit_union':b['source_record_id'] in credits,'candidate_only':True})
m=pd.DataFrame(matches);m.to_csv(O/'cached_alias_or_code_native2002_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'stage':34,'status':'disjoint_all_components_diagnostic_only','ordinary_two_year_ownpoint_components':len(f),'all_population2010':int(f.population2010.sum()),'all_population2021':int(f.population2021.sum()),'all_max_population_weight':int(f.maximum_observed_population_weight.sum()),'excluded_pending_queue_components':int(f.excluded_pending_queue.sum()),'excluded_already_credit_components':int(f.already_source_ID_credit_union.sum()),'active_disjoint_components':len(active),'active_population2010':int(active.population2010.sum()),'active_population2021':int(active.population2021.sum()),'active_max_population_weight':int(active.maximum_observed_population_weight.sum()),'wanted_QIDs':len(wanted),'cache_files_read':files_read,'wanted_cached_QIDs':len(entities),'explicit_census2002_unique_own_observation_components':int(i.explicit_census2002_unique_population.sum()),'explicit_census2002_unique_existing2010_weight':int(i.loc[i.explicit_census2002_unique_population,'population2010'].sum()),'explicit_census2002_unique_existing2021_weight':int(i.loc[i.explicit_census2002_unique_population,'population2021'].sum()),'explicit_census2002_unique_max_weight':int(i.loc[i.explicit_census2002_unique_population,'maximum_observed_population_weight'].sum()),'native2002_alias_or_code_candidate_rows':len(m),'input_pins':pins|rawpins,'no_network':True,'no_population_credit_or_native_identity_admission_asserted':True};(O/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));i[i.explicit_census2002_unique_population].head(100).to_csv(O/'cached_census2002_positive_top100.csv',index=False);print(json.dumps({k:v for k,v in r.items() if k!='input_pins'},ensure_ascii=False))
