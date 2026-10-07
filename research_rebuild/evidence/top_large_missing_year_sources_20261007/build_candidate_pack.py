from pathlib import Path
import sys,json,gzip,hashlib,re
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(stage=8)
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def safe(x):
 return None if pd.isna(x) else x
base=ROOT/'research_rebuild/evidence/working_full_chain_20261007'
inputs=[base/('top100_strict_joint_residual_'+str(y)+'.csv') for y in (2002,2010)]
rank=pd.concat([pd.read_csv(p,keep_default_na=False) for p in inputs]);rank=rank[~rank.covered_by_complete_partition_scope&~rank.covered_by_qualified_physical_scope];rank=rank.sort_values('population',ascending=False).drop_duplicates(['settlement_name','region_norm']).head(15)
entities=json.load(gzip.open(OUT/'live_wikidata_entities.json.gz','rt'))['entities']
byname={e.get('labels',{}).get('ru',{}).get('value'):e for e in entities.values()}
byname['Московский']=entities['Q159261'];byname['Пашковский']=entities['Q4347629']
rawfile=OUT/'live_wikidata_entities.json.gz';rawsha=sha(rawfile)
allclaims=[];missing=[];focus=[];points=[]
for target in rank.itertuples(index=False):
 row=s.by_id.loc[target.source_record_id];root=s.uf.find(target.source_record_id);component=s.obs[s.obs.source_record_id.map(s.uf.find).eq(root)];ys=set(map(int,component.census_year));needs=sorted({2002,2010,2021}-ys)
 e=byname.get(target.settlement_name,{})
 ownname=e.get('labels',{}).get('ru',{}).get('value');qid=e.get('id','');populationclaims=e.get('claims',{}).get('P1082',[]);available={};dates=[]
 for claim in populationclaims:
  try:count=int(float(claim['mainsnak']['datavalue']['value']['amount']))
  except Exception:continue
  if claim.get('rank')=='deprecated':continue
  for ts in claim.get('qualifiers',{}).get('P585',[]):
   tv=ts.get('datavalue',{}).get('value',{});date=tv.get('time','');match=re.match(r'\+(\d{4})-',date)
   if not match:continue
   y=int(match[1]);dates.append(y)
   record={'focus_source_record_id':target.source_record_id,'settlement_name':target.settlement_name,'region_norm':target.region_norm,'wikidata_qid':qid,'wikidata_label_ru':ownname,'observation_year':y,'population_as_printed':count,'observation_date_raw':date,'observation_date_precision':tv.get('precision'),'exact_calendar_date_asserted':tv.get('precision',0)>=11,'statement_id':claim.get('id'),'rank':claim.get('rank'),'source_path':str(rawfile),'source_sha256':rawsha,'source_locator':'entities.'+qid+'.claims.P1082[id='+claim.get('id','')+']','references_json':json.dumps(claim.get('references',[]),ensure_ascii=False),'has_attached_original_references':bool(claim.get('references')),'method_qualifier_json':json.dumps(claim.get('qualifiers',{}).get('P459',[]),ensure_ascii=False),'source_class':'dated_wikidata_secondary_statement','source_exact_original_census_count_verified':False,'population_scope':'own_Wikidata_entity_statement_pending_physical_boundary_review','analysis_population_additive':False,'selected_national_population_credit_allowed':False,'protected_2010_precision_preserved':True,'ordinary_new_settlement_admission_allowed':False,'candidate_status':'candidate_only'}
   if y in (2002,2010,2021):allclaims.append(record)
   if y in needs:
    aliases=s.obs[s.obs.census_year.eq(y)&s.obs.region_norm.eq(target.region_norm)&s.obs.name_norm.eq(row.name_norm)]
    record['already_selected_same_year_name_region_alias_ids']=json.dumps(list(aliases.source_record_id),ensure_ascii=False)
    record['new_auxiliary_observation_needed']=aliases.empty
    record['candidate_status']='candidate_only_new_auxiliary_observation' if aliases.empty else 'candidate_only_existing_native_observation_identity_review'
    missing.append(record);available.setdefault(y,[]).append(record)
 componentpoints=[(sid,s.point_rows[sid]) for sid in component.source_record_id if sid in s.point_rows]
 point=componentpoints[0][1] if componentpoints else None
 if point:
  points.append({'focus_source_record_id':target.source_record_id,'settlement_name':target.settlement_name,'point_target_source_record_id':componentpoints[0][0],**{k:v for k,v in point.items() if k!='point_ledger_path'},'coordinate_claim_role':'existing_accepted_own_locality_representative_point_candidate_reuse','coordinate_measurement_at_census_date_asserted':False,'new_coordinate_admission':False})
 status='missing_year_dated_secondary_candidate' if available else 'no_required_year_own_count_found'
 note='No2021 ownplacecount: datedpreabsorptionlastcounts remain their printedyear, receivingparentpopulation notreassigned.'
 if target.settlement_name=='Власиха':note='Ownentity2002 count16309, yearprecision9, noattachedreferences. Historicalclosedmilitarytown before2009 ZATO formation. Qualifiedphysicalseries candidate only; verifyoriginalsource/boundary. Selected2010protected25394 preserved despiteWDofficialreported26359. Auxiliary2002 within2002parent census mustnotenterordinarynationalselecteddenominator.'
 if target.settlement_name=='Сходня':note='Livearticle ownneighborhood18994 explicitly2020; WDownentity27100 explicitly2007. Neither is2010or2021. No year relabelling.'
 if target.settlement_name=='Московский':note='OwncityWD series ends2020=59218; no2021 claim. Do notsubstitute settlementМосковский municipalterritory aggregate/cityMoscow total.'
 focus.append({'focus_source_record_id':target.source_record_id,'settlement_name':target.settlement_name,'region_norm':target.region_norm,'existing_component_years':json.dumps(sorted(ys)),'missing_years':json.dumps(needs),'existing_component_source_ids':json.dumps(list(component.source_record_id),ensure_ascii=False),'existing_component_populations_json':json.dumps({str(int(r.census_year)):safe(r.population) for r in component.itertuples()},ensure_ascii=False),'existing_component_population_qualities_json':json.dumps({str(int(r.census_year)):r.population_value_quality for r in component.itertuples()},ensure_ascii=False),'wikidata_qid':qid,'secondary_population_latest_year':max(dates) if dates else None,'required_year_dated_claims_found':json.dumps(sorted(available)),'own_representative_point_available':point is not None,'disposition':status,'caveat':note})
 # Missingyear credit is restricted to alreadyselectednative endpoints once; auxiliaryyear credit stays0.
 for m in [m for m in missing if m['focus_source_record_id']==target.source_record_id]:
  m['all_required_years_observed_if_candidate_admitted']=set(needs)<=set(available)
  m['physical_scope_interpretation']=note
  if target.settlement_name=='Власиха' and m['observation_year']==2002:
   secondary=OUT/'vlasikha_2012_nsportal.html.gz';html=gzip.open(secondary,'rt').read()
   assert '16309' in html and '24.01.2012 - 19:42' in html
   m.update(additional_dated_secondary_url='https://nsportal.ru/shkola/geografiya/library/2012/01/24/zato-vlasikha',additional_dated_secondary_source_path=str(secondary),additional_dated_secondary_source_sha256=sha(secondary),additional_dated_secondary_locator='articlepublished2012-01-24T19:42(localtimezoneunspecified);bodyparagraphbeginningПо переписи населения2002года',additional_secondary_publication_date='2012-01-24',additional_secondary_author='Костромина Ирина Павловна',additional_source_reports_census_year=2002,additional_source_reports_same_population=16309,independence_from_historical_Wikipedia_not_asserted=True,preliminary_2010_26339_not_admitted=True);m['existing_component_source_ids']=json.dumps(list(component.source_record_id),ensure_ascii=False)
  for y in (2002,2010,2021):m['conditional_existing_selected_credit_'+str(y)]=sum(float(r.population) for r in component.itertuples() if int(r.census_year)==y)
  if point:m.update(representative_latitude=point['latitude'],representative_longitude=point['longitude'],point_origin_file=point.get('point_origin_file'),point_origin_sha256=point.get('point_origin_sha256'),point_origin_locator=point.get('point_origin_locator'))
pd.DataFrame(focus).to_csv(OUT/'top15_required_year_dispositions.csv',index=False)
pd.DataFrame(allclaims).to_csv(OUT/'all_dated_2002_2010_2021_own_entity_claims.csv',index=False)
pd.DataFrame(missing).to_csv(OUT/'missing_year_observation_candidates.csv',index=False)
pd.DataFrame(points).to_csv(OUT/'existing_own_representative_points.csv',index=False)
# Existingsource search receipt: archives/claims/module sources searched beforelive revision fetch.
cached=[ROOT/'research_rebuild/evidence/mass_joint_20261004/reviewed_increments_after_eighth/independent_review/large_current4_official_rosstat_correction_review/review_receipt.json',Path('/workspace/settlements-work/wikidata/entities.parquet'),Path('/workspace/settlements-work/wikidata/claims.parquet'),Path('/workspace/settlements-work/sources/annual_module_recovery/raw_population_assertions.parquet'),Path('/workspace/settlements-work/sources/annual_module_bindings_v1/possible_module_entry_bindings.parquet'),Path('/workspace/settlements-work/continuation_20261004/federal_and_history/krasnodar_large_included_places/wikipedia_kalinino_article_revision.json'),Path('/workspace/settlements-work/continuation_20261004/federal_and_history/krasnodar_large_included_places/wikipedia_pashkovsky_article_revision.json'),Path('/workspace/settlements-work/continuation_20261004/regions/large2010_residual20_v1/raw_wikipedia/moskovskiy_city.json')]
(OUT/'cached_source_search_manifest.json').write_text(json.dumps([{'path':str(p),'sha256':sha(p)} for p in cached+inputs],indent=2))
(OUT/'graph_inputs_manifest.json').write_text(json.dumps([{'path':str(p),'sha256':sha(p)} for p in s.inputs],indent=2))
summary={'places_reviewed':len(focus),'own_missing_year_claim_candidates':len(missing),'genuine_new_auxiliary_year_candidates':sum(r['new_auxiliary_observation_needed'] for r in missing),'already_selected_native_year_identity_candidates':sum(not r['new_auxiliary_observation_needed'] for r in missing),'three_year_completion_candidate_places':list(dict.fromkeys(r['settlement_name'] for r in missing if r['all_required_years_observed_if_candidate_admitted'])),'candidate_places':list(dict.fromkeys(r['settlement_name'] for r in missing)),'candidate_missing_year_populations':[{k:r[k] for k in ['settlement_name','observation_year','population_as_printed','has_attached_original_references']} for r in missing],'conditional_existing_native_population_credit_once':{str(y):sum(r.get('conditional_existing_selected_credit_'+str(y),0) for r in missing if r['all_required_years_observed_if_candidate_admitted']) for y in (2002,2010,2021)},'auxiliary_population_added_to_national_selected':0,'actual_admitted_population_gain':0,'no_receiving_parent_population_reassignment':True,'no_year_interpolation_or_forward_fill':True,'limitation':'14largeplaces have no complete missing-required-yearowncount series in their currentWikipedia table/Wikidata datedclaims; this does not prove absence fromallpossible census/internaldistrict publications.'}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
