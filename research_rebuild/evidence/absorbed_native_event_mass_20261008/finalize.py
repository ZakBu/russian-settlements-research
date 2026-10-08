from pathlib import Path
import json,pandas as pd,hashlib
O=Path(__file__).parent;E=O.parent
ids=set()
for p in [E/'further_urban_merger_application_20261007/accepted_constituent_credit_union.csv',E/'norilsk_talnakh_kayerkan_series_20261005/accepted_series.csv']:
 d=pd.read_csv(p,dtype=str,keep_default_na=False)
 for k in ['source_record_id','constituent_source_record_id']:
  if k in d:ids.update(d[k])
h=pd.read_csv(O/'ranked_historical_targets.csv');h['mixed_precredited']=h.mixed_precredited|h.source_record_id.isin(ids)
h=h[~h.region_norm.isin(['москва','санкт петербург','севастополь'])]
h.to_csv(O/'ranked_historical_targets.csv',index=False)
rows=json.loads((O/'cached_event_candidates.json').read_text());holds=[]
exclude=['Востряково','Лопатинский','Ожерелье','Мыс','Прибрежный','Сокольники','Краснооктябрьский','Белоярск','Красный Октябрь','Заречный','Росляково','Новые Ляды','Неклюдово','Поволжский']
for z in rows:
 z['mixed_precredited']=z['mixed_precredited']or z['source_record_id']in ids
 if z['mixed_precredited']:reason='already mixed credited; zero incremental source ID mass'
 elif z['name'] in exclude:reason='excluded concurrent parent/city/Moscow agent family'
 elif z['title']=='Власиха (Московская область)':reason='ZATO administrative scope event; not documented NP absorption'
 elif z['title']=='Манас (Дагестан)':reason='ordinary historical transport/municipal text; not NP absorption'
 else:reason='unverified sourcecounty/homonym; no qualified dated inclusion'
 holds.append({'old_source_record_id':z['source_record_id'],'title':z['title'],'year':z['year'],'region':z['region'],'population':z['population'],'reason':reason,'cached_source_path':z['sourcepath'],'cached_source_sha256':z['sha256'],'cached_source_locator':z['locator'],'cached_revision':z['revision']})
(O/'cached_event_candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
pd.DataFrame(holds).to_csv(O/'event_candidate_dispositions.csv',index=False)
n=h[~h.mixed_precredited & ~h.settlement_name.isin(exclude)].copy();n.to_csv(O/'remaining_bounded_source_targets.csv',index=False)
receipt={'status':'bounded_cached_event_extraction_complete_no_new_qualified_event_application','state':'working_state_20261007.load(34)','historical_targets_ranked':len(h),'top100_native_population_by_year':h.head(100).groupby('census_year').population.sum().to_dict(),'cached_article_documents':174,'cached_event_name_hits':len(rows),'cached_entity_files_screened':163,'cached_entities_screened':7479,'new_accepted_event_edges':0,'incremental_population_by_year':{'2002':0,'2010':0,'2021':0},'remaining_noncredited_nonexcluded_rows':len(n),'remaining_noncredited_native_population_by_year':n.groupby('census_year').population.sum().to_dict(),'restriction':'Only existing cached ownarticles/entities; no fetching. Homonym title match is only candidate, never accepted identity. Existing city scope credits are excluded from any net gain. Native child 2021 population never created. No same_place edge inferred from absorption. No receiver point substituted for old NP.'}
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print(json.dumps(receipt,ensure_ascii=False,indent=2)); print(n[['settlement_name','census_year','region_norm','population']].head(35).to_string(index=False))
