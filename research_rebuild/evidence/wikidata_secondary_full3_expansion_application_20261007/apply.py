from pathlib import Path
import sys,json,hashlib,time
import pandas as pd
O=Path(__file__).parent;E=O.parent;ROOT=E.parents[1];C=E/'wikidata_secondary_full3_expansion_20261007';sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from current_chain_state_20261007 import sha
T=time.monotonic();s=load(21);f=pd.read_csv(C/'review_ready_qualified_physical_observations.csv').fillna('');assert len(f)==1365 and f.trajectory_id.nunique()==455 and f.nonadditive_observation.sum()==910;credited={sid for sid in s.point_rows if s.years[s.uf.find(sid)]=={2002,2010,2021}};pins={};exclusions={}
paths=[PARTITION_MEMBERS,E/'wikidata_secondary_full3_application_20261007/preapplication_qualified_credit_ids_frozen.csv',E/'wikidata_secondary_full3_application_20261007/accepted_qualified_physical_observations.csv',E/'current_unpointed_own_wiki_mass_application_20261007/accepted_qualified_physical_observations.csv',E/'existing_event_scope_application_20261007/accepted_selected_source_id_credit_union.csv']+[E/d/'accepted_constituent_credit_union.csv' for d in ['named_urban_merger_application_20261007','next_named_urban_merger_application_20261007','further_urban_merger_application_20261007']]
for p in paths:
 d=pd.read_csv(p,dtype=str).fillna('');ids=set()
 for col in d.columns:
  if 'source_record_id' in col:ids.update(d[col])
 ids.discard('');credited.update(ids);exclusions[str(p)]={'sha256':sha(p),'source_ids':sorted(ids)}
credit=[]
for q,g in f.groupby('wikidata_id',sort=False):
 sid=str(g[g.year==2021].source_record_id.iloc[0]);n=s.by_id.loc[sid];point=s.point_rows[sid];assert n.is_additive_settlement_record
 for i,r in g.iterrows():
  hist=int(r.year)!=2021
  if hist:assert not r.source_record_id and r.nonadditive_observation
  else:assert r.population_source_value==n.population and r.population_quality==n.population_value_quality
  f.at[i,'latitude']=float(point['latitude']);f.at[i,'longitude']=float(point['longitude']);f.at[i,'point_binding_json']=json.dumps(point,ensure_ascii=False)
  for k in ['point_origin_file','point_origin_sha256','point_origin_locator']:f.at[i,k]=point.get(k,'')
  f.at[i,'selected_credit_previously_present']=not hist and sid in credited
 credit.append({'source_record_id':sid,'year':2021,'source_population':float(n.population),'trajectory_id':g.trajectory_id.iloc[0],'scope':'secondary_census_referenced_own_physical_locality_expansion','already_in_ordinary_partitions_qualified36_22_398_named9_union':sid in credited,'net_new_selected_ID_credit':sid not in credited})
f['decision_status']='qualified_accepted_secondary_census_referenced_own_item';f['accepted_physical_three_observed_census_year_path']=True;f['accepted_scoped_representative_point']=True;f['historical_native_selected_source_ID_binding_asserted']=False;f['population_primary_reference_verified']=False;f.to_csv(O/'accepted_qualified_physical_observations.csv',index=False);cr=pd.DataFrame(credit);cr.to_csv(O/'accepted_current_source_id_credit_union.csv',index=False)
for p in dict.fromkeys(s.inputs+paths+[C/'review_ready_qualified_physical_observations.csv',C/'verification_receipt.json',C/'fixed15_and_largest5_source_checks.csv',C/'source_manifest.json',ROOT/'research_rebuild/mass_linkage/working_state_20261007.py',Path(__file__)]):pins[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
raw=json.loads((C/'source_manifest.json').read_text());for k,v in raw.items():pins.setdefault(k,v)
receipt={'status':'applied_qualified_secondary_census_referenced_own_physical_series','baseline_stage':21,'accepted_series':455,'accepted_observations':1365,'historical_secondary_nonadditive_observations':910,'native2021_observations':455,'net_selected_source_id_credit_by_year':{'2002':{'rows':0,'population':0},'2010':{'rows':0,'population':0},'2021':{'rows':int(cr.net_new_selected_ID_credit.sum()),'population':int(cr.loc[cr.net_new_selected_ID_credit,'source_population'].sum())}},'already_credited_native2021_source_ids':int((~cr.net_new_selected_ID_credit).sum()),'qualified_actual_secondary_value_sums_not_national_credit':{str(int(y)):int(g.population_source_value.sum()) for y,g in f.groupby('year')},'proof':'910 actual historical GUID/value/date assertions and final fixed15+largest5 source checks completed in approved candidate','historical_population_observations':'explicit raw census reference title/label/date/database locators; primary source not independently authenticated; nonadditive; exact declared precision preserved','ordinary_graph_modified':False,'historical_conditional_native_IDs_admitted':False,'protected_population_values_modified':False,'current_points':'latest21 accepted independent own NP points retained; Wiki coordinates not imported','boundary_comparability':'UNKNOWN','error_rate':'uncalibrated','wall_seconds':time.monotonic()-T,'inputs':pins,'preexisting_credit_exclusions':exclusions,'outputs':{p.name:sha(p) for p in [O/'accepted_qualified_physical_observations.csv',O/'accepted_current_source_id_credit_union.csv']}}
# Receipt/status becomes visible only after complete accepted rows and credit outputs.
tmp=O/'application_receipt.tmp';tmp.write_text(json.dumps(receipt,indent=2,ensure_ascii=False));tmp.replace(O/'application_receipt.json');print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs','preexisting_credit_exclusions']},ensure_ascii=False))
