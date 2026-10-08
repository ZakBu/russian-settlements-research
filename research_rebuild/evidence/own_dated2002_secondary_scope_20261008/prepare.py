from pathlib import Path
import sys,json,gzip,re,collections,math,hashlib
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from current_chain_state_20261007 import normalize,distance_km,sha
O=Path(__file__).parent;E=O.parent;T=E/'legacy_coordinate_current_ownpoint_mass_20261008/missing_third_year_priority/proposed_bounded_2002_source_batch.csv.gz';network=json.loads((O/'network_receipt.json').read_text());s=load(33);pins={str(p):sha(p)for p in s.inputs};pins[str(T)]=sha(T);pins[str(O/'network_receipt.json')]=sha(O/'network_receipt.json');entities={};origin={}
for rec in network['records']:
 if not rec.get('cache_path'):continue
 p=Path(rec['cache_path']);assert sha(p)==rec['sha256'];pins[str(p)]=rec['sha256']
 for q,e in json.loads(gzip.decompress(p.read_bytes()))['entities'].items():entities[q]=e;origin[q]=str(p)
# Exclude already admitted scoped/native references and the independently prepared native dated-count batch34.
credit=set();future=set()
for p in [PARTITION_MEMBERS,E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'working_full_chain_20261007/named_merger_lineage_constituents.csv',E/'working_full_chain_20261007/complete_territorial_scope_constituents.csv']:
 f=pd.read_csv(p,dtype=str,keep_default_na=False);pins[str(p)]=sha(p)
 if 'source_record_id'in f:credit.update(f.source_record_id)
F=E/'native_alias_remaining_mass_20261008/nationwide_dated_count_native_bindings_followup/accepted_identity_edge_delta.csv';f=pd.read_csv(F,dtype=str,keep_default_na=False);pins[str(F)]=sha(F);future.update(f.from_source_record_id);future.update(f.to_source_record_id)
byroot={k:list(g.source_record_id)for k,g in s.obs.groupby('root')};current=collections.defaultdict(list)
for r in s.obs[s.obs.census_year.eq(2021)&s.obs.is_additive_settlement_record.fillna(False)].itertuples():
 if r.source_record_id in s.point_rows:current[(normalize(r.name_norm),normalize(r.region_norm))].append(r.source_record_id)
def value(sn):return sn.get('datavalue',{}).get('value')
def typedname(n):return re.sub(r'^(?:поселок|село|деревня|хутор|город)\s+','',normalize(n))
def clean_code(v):
 if pd.isna(v):return ''
 n=str(v);return n[:-2]if n.endswith('.0')else n
rows=[];holds=[];proof=[];native_alias=[];manifest={};seen=set()
for t in pd.read_csv(T,keep_default_na=False).to_dict('records'):
 sid=t['trajectory_current_source_record_id'];cur=s.by_id.loc[sid];ids=byroot[s.uf.find(sid)]
 if set(s.by_id.loc[ids,'census_year'])!={2010,2021}:holds.append({'sid':sid,'name':cur.settlement_name,'reason':'no_longer_exact_native2010_2021_pair'});continue
 if set(ids)&(credit|future):holds.append({'sid':sid,'name':cur.settlement_name,'reason':'already_scoped_credited_or_pending_native34'});continue
 cp=s.point_rows[sid];near=[]
 for bid in current[(normalize(cur.name_norm),normalize(cur.region_norm))]:
  p=s.point_rows[bid]
  if distance_km((p['latitude'],p['longitude']),(cp['latitude'],cp['longitude']))<=5:near.append(bid)
 if near!=[sid]:holds.append({'sid':sid,'name':cur.settlement_name,'reason':'current_same_name_region_ownpoint_competitors_5km'});continue
 selected=[];itemholds=[]
 for q in json.loads(t['own_QIDs_json']):
  if q not in entities:continue
  e=entities[q];cs=e.get('claims',{});label=e.get('labels',{}).get('ru',{}).get('value','');aliases=[x['value']for x in e.get('aliases',{}).get('ru',[])];desc=e.get('descriptions',{}).get('ru',{}).get('value','');names={typedname(x)for x in [label]+aliases};codes={str(value(x['mainsnak']))for prop in ['P763','P764']for x in cs.get(prop,[])if value(x['mainsnak'])};codepositive=bool(codes&{clean_code(cur.okato),clean_code(cur.oktmo)});namepositive=typedname(cur.settlement_name)in names;physical=bool(re.match(r'^(?:село|деревня|пос[её]лок|хутор|станица|аул|город\b|сельский насел)',desc,re.I));wrong=bool(re.match(r'^(?:муниципал|городской округ|сельское поселение|район\b|сельсовет|часть города|квартал|микрорайон)',desc,re.I))or any(x in normalize(label)for x in ['сельское поселение','муниципальный район','городской округ']);foundation=[]
  for x in cs.get('P571',[]):
   v=value(x.get('mainsnak',{}))
   if isinstance(v,dict)and v.get('time','').startswith('+'):foundation.append(v['time'])
  if wrong or not(namepositive and(codepositive or physical)):itemholds.append(q+':own_item_native_name_code_physical_grain_not_positive');continue
  if any(int(x[1:5])>2002 for x in foundation):itemholds.append(q+':post2002_foundation_hold');continue
  for st in cs.get('P1082',[]):
   v=value(st.get('mainsnak',{}))
   if not isinstance(v,dict)or st.get('rank')=='deprecated'or st.get('qualifiers',{}).get('P518'):continue
   try:pop=float(v['amount'])
   except Exception:continue
   if not math.isfinite(pop)or pop<0:continue
   for dt in st.get('qualifiers',{}).get('P585',[]):
    date=value(dt)
    if not isinstance(date,dict)or not date.get('time','').startswith('+2002')or date.get('precision',0)<9:continue
    refs=st.get('references',[]);titles=[value(sn).get('text','')for ref in refs for sn in ref.get('snaks',{}).get('P1476',[])if isinstance(value(sn),dict)];rq=[value(sn).get('id','')for ref in refs for sn in ref.get('snaks',{}).get('P248',[])if isinstance(value(sn),dict)];urls=[str(value(sn))for ref in refs for sn in ref.get('snaks',{}).get('P854',[])];known=date['time'][1:11]=='2002-10-09'or any(('2002'in tx and re.search('перепис|census|впн',tx,re.I))or'vpn2002'in tx.lower()for tx in titles+urls);path=origin[q];selected.append({'qid':q,'amount':pop,'date':date['time'],'precision':date['precision'],'census_known':known,'titles':titles,'P248_ids':rq,'urls':urls,'statement_id':st.get('id',''),'source_file':path,'source_sha256':pins[path],'own_label':label,'own_aliases':aliases,'own_description':desc,'own_code_positive':codepositive,'own_name_or_alias_positive':namepositive,'foundation':foundation})
 if not selected:holds.append({'sid':sid,'name':cur.settlement_name,'reason':';'.join(itemholds)or'no_actual_dated2002_population_claim'});continue
 if any(v['census_known']for v in selected):selected=[v for v in selected if v['census_known']]
 if len({v['amount']for v in selected})!=1 or len({v['qid']for v in selected})!=1:holds.append({'sid':sid,'name':cur.settlement_name,'reason':'conflicting_actual2002_population_or_own_item'});continue
 st=sorted(selected,key=lambda x:(-x['precision'],x['date']))[0];q=st['qid'];trajectory='own_dated2002_year_secondary:'+q
 if q in seen:holds.append({'sid':sid,'name':cur.settlement_name,'reason':'same_own_item_multiple_current_native_records'});continue
 if any(x in s.conflicting_point_targets for x in ids)or any(distance_km((s.point_rows[x]['latitude'],s.point_rows[x]['longitude']),(cp['latitude'],cp['longitude']))>5 for x in ids):holds.append({'sid':sid,'name':cur.settlement_name,'reason':'accepted_native_component_point_conflict'});continue
 seen.add(q);pointpath=Path(cp['point_origin_file']);ph=sha(pointpath);assert ph==cp['point_origin_sha256'];pins[str(pointpath)]=ph;pointledger=Path(cp['point_ledger_path']);pins[str(pointledger)]=sha(pointledger)
 base={'trajectory_id':trajectory,'scope':'own_dated2002_secondary_temporal_year_20261008','settlement_name':cur.settlement_name,'region_norm':cur.region_norm,'county_context':cur.district_raw,'latitude':cp['latitude'],'longitude':cp['longitude'],'wikidata_id':q,'decision_status':'qualified_accepted_secondary_own_actual_dated_year_primary_unverified','ordinary_NP3_asserted':False,'boundary_comparability_asserted':False,'boundary_comparability':'UNKNOWN','accepted_physical_three_observed_year_path':True,'accepted_physical_three_observed_census_year_path':False,'accepted_scoped_representative_point':True,'population_primary_reference_verified':False,'retrospective_point_use_is_continuity_inference':True,'point_binding_json':json.dumps(cp,ensure_ascii=False),'point_origin_file':str(pointpath),'point_origin_sha256':ph,'point_origin_locator':cp['point_origin_locator'],'native_current_source_record_id':sid,'native_existing_component_binding':True,'own_code_positive':st['own_code_positive'],'own_name_or_alias_positive':st['own_name_or_alias_positive'],'own_physical_description':st['own_description'],'current_same_name_region_all_ownpoint_candidates_checked':True,'current_5km_ownpoint_candidate_IDs_json':json.dumps(near),'own_item_binding':'current native own code and own label/alias plus independently admitted current own physical locality point','historical_census_comparability_asserted':False}
 row=base|{'year':2002,'population_source_value':st['amount'],'source_record_id':'','population_quality':'secondary_actual_dated_year_population_primary_unverified','grain':'own physical locality actual dated secondary year2002 population; census designation unknown unless explicitly referenced','nonadditive_observation':True,'source_path':st['source_file'],'source_sha256':st['source_sha256'],'source_locator':f'entities.{q}.claims.P1082[{st["statement_id"]}]','declared_date':st['date'],'date_precision':st['precision'],'source_date_precision':st['precision'],'source_population_is_census_known':st['census_known'],'census_proof_class':'exact_or_explicit_census_reference'if st['census_known']else'actual_P585_calendar_year_population_census_identity_unverified','census_reference_titles_json':json.dumps(st['titles'],ensure_ascii=False),'P248_ids_json':json.dumps(st['P248_ids']),'reference_urls_json':json.dumps(st['urls']),'statement_id':st['statement_id'],'historical_native_selected_source_ID_binding_asserted':False};rows.append(row)
 for oldid in ids:
  old=s.by_id.loc[oldid];p=Path('/workspace/settlements-raw')/old.source_file
  native_missing=not p.is_file()
  if native_missing:
   h=str(old.source_sha256)if pd.notna(old.source_sha256)else''
   # Retain an existing admitted native observation; missing legacy raw bytes do not create a new claim of source verification.
   facts=Path('/workspace/settlements-work/continuation_20261004/R4/exact_population_source_inventory/parser_runtime/karelia/karelia_2010_rural_docx_source_facts.json')
   if 'KARELIA'in oldid and facts.is_file():pins[str(facts)]=sha(facts)
  else:h=sha(p);pins[str(p)]=h
  rows.append(base|{'year':int(old.census_year),'population_source_value':float(old.population),'source_record_id':oldid,'population_quality':old.population_value_quality,'grain':'already accepted own locality native census observation, original count and quality retained','nonadditive_observation':False,'source_path':str(p),'source_sha256':h,'source_locator':str(old.source_locator)if pd.notna(old.source_locator)else'original_selected_native_source_record_id='+oldid,'declared_date':'','date_precision':'','source_date_precision':'','source_population_is_census_known':True,'native_raw_source_missing_flag':native_missing,'native_raw_source_resolution_status':'existing_imported_native_provenance_retained_raw_cache_unresolved'if native_missing else'exact_cached_native_source_bytes_pinned','census_proof_class':'existing_selected_native_census_row_in_accepted_own_NP_component','census_reference_titles_json':'[]','P248_ids_json':'[]','reference_urls_json':'[]','statement_id':'','historical_native_selected_source_ID_binding_asserted':True})
 proof.append({'trajectory_id':trajectory,'current_source_record_id':sid,'wikidata_id':q,'own_label':st['own_label'],'own_aliases_json':json.dumps(st['own_aliases'],ensure_ascii=False),'own_description':st['own_description'],'own_code_positive':st['own_code_positive'],'own_name_or_alias_positive':st['own_name_or_alias_positive'],'raw2002_source_file':st['source_file'],'raw2002_source_sha256':st['source_sha256'],'actual2002_population':st['amount'],'source2002_date':st['date'],'source2002_precision':st['precision'],'source2002_is_census_known':st['census_known'],'P571_dates_json':json.dumps(st['foundation']),'native_source_IDs_json':json.dumps(ids),'native2010_population':float(s.by_id.loc[[x for x in ids if int(s.by_id.loc[x,'census_year'])==2010][0],'population']),'native2021_population':float(cur.population)})
 # Separate native alias candidates; actual old raw aliases and counts are evidence, never population equality alone.
 for old in s.obs[s.obs.census_year.eq(2002)&s.obs.region_norm.eq(cur.region_norm)].itertuples():
  oldname=typedname(old.settlement_name);aliasnames={typedname(x)for x in st['own_aliases']};aliasnames.add(typedname(st['own_label']));abbr=lambda v:re.sub(r'\bим\.?\s+','имени ',v)
  if not(oldname in aliasnames or abbr(oldname)in{abbr(x)for x in aliasnames}):continue
  if float(old.population)!=st['amount']:continue
  native_alias.append({'current_source_record_id':sid,'wikidata_id':q,'native2002_source_record_id':old.source_record_id,'native2002_name':old.settlement_name,'current_name':cur.settlement_name,'native2002_population':float(old.population),'secondary2002_literal_population':st['amount'],'native2002_printed_county':old.district_raw,'current_county':cur.district_raw,'native2002_source_file':old.source_file,'native2002_source_locator':old.source_locator,'documented_own_alias_positive':oldname in aliasnames,'explicit_im_abbreviation_positive':abbr(oldname)in{abbr(x)for x in aliasnames},'source2002_kind':'actual selected native published2002 row','candidate_only_native_county_code_and_existing_component_conflicts_must_be_resolved':True,'already_credited_or_native34_reserved':old.source_record_id in credit|future})
f=pd.DataFrame(rows);pr=pd.DataFrame(proof);census_ids=set(pr.loc[pr.source2002_is_census_known,'trajectory_id']);qualified=f[f.trajectory_id.isin(census_ids)].copy();display=f[~f.trajectory_id.isin(census_ids)].copy()
qualified['decision_status']='qualified_accepted_secondary_census_referenced_own_item';qualified['accepted_physical_three_observed_census_year_path']=True;qualified['scope']='own_explicit_census2002_secondary_20261008';qualified.loc[qualified.year.eq(2002),'population_quality']='secondary_explicit_census_referenced_own_item_primary_unverified'
display['accepted_working_temporal_year_observation_for_display']=True;display['national_mixed_census_source_ID_credit_asserted']=False;display['strict_census_three_year_path_asserted']=False
qualified.to_csv(O/'accepted_qualified_physical_observations.csv',index=False);display.to_csv(O/'accepted_working_temporal_year_observations.csv',index=False);pr.to_csv(O/'own_binding_and_dated_source_witnesses.csv',index=False);pd.DataFrame(holds).to_csv(O/'held_cases.csv',index=False);pd.DataFrame(native_alias).to_csv(O/'separate_native2002_alias_binding_candidates.csv',index=False)
qnative=qualified[~qualified.nonadditive_observation];qnative[['source_record_id','year','population_source_value','population_quality','native_current_source_record_id']].to_csv(O/'accepted_qualified_native_source_ID_credit_union.csv',index=False)
allnative=f[~f.nonadditive_observation];allnative[['source_record_id','year','population_source_value','population_quality','native_current_source_record_id']].to_csv(O/'retained_display_native_source_ID_references.csv',index=False)
r={'status':'accepted_actual_dated2002_temporal_display_separate_from_explicit_census_qualified_union','baseline_stage':33,'accepted_total_temporal_year_trajectories':len(proof),'generic2002_display_only_trajectories':display.trajectory_id.nunique(),'explicit_census2002_qualified_trajectories':qualified.trajectory_id.nunique(),'explicit_census2002_qualified_native_ID_union_net':{str(y):{'rows':len(g),'population':int(g.population_source_value.sum())}for y,g in qnative.groupby('year')},'all_retained_native_ID_references_population_for_display_not_national_credit':{str(y):{'rows':len(g),'population':int(g.population_source_value.sum())}for y,g in allnative.groupby('year')},'secondary2002_actual_population_for_display_not_native_credit':int(f.loc[f.year.eq(2002),'population_source_value'].sum()),'secondary2002_actual_literal_zero_observations':int((f.year.eq(2002)&f.population_source_value.eq(0)).sum()),'ordinary_NP3_asserted':False,'ordinary_graph_or_point_ledgers_modified':False,'generic2002_mixed_census_union_credit':False,'native_source_population_or_quality_modified':False,'source_dates_and_precision_preserved':True,'post2002_foundation_candidates_held':True,'held_cases':len(holds),'native_alias_candidate_rows':len(native_alias),'input_hashes':pins,'outputs':{p.name:sha(p)for p in O.glob('*.csv')}}
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:r[k]for k in ['accepted_total_temporal_year_trajectories','generic2002_display_only_trajectories','explicit_census2002_qualified_trajectories','explicit_census2002_qualified_native_ID_union_net','all_retained_native_ID_references_population_for_display_not_national_credit','secondary2002_actual_population_for_display_not_native_credit','held_cases','native_alias_candidate_rows']},ensure_ascii=False))
