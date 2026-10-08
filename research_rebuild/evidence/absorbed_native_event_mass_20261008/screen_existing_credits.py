from pathlib import Path
import pandas as pd,json
O=Path(__file__).parent;E=O.parent
folders=['named_urban_merger_application_20261007','next_named_urban_merger_application_20261007','existing_event_scope_application_20261007','voronezh_closed_roster_application_20261008','large_absorbed_city_closed_scope_application_20261008','remaining_absorbed_city_published_closures_application_20261008','city_territory_mass_followup_application_20261008','city_territory_mass_final_two_application_20261008','nakhoda_complete_published_scope_aux5_application_20261008','moscow_complete_scope_mass_application_20261008']
ids=set();ledgers=[]
for f in folders:
 for p in (E/f).glob('accepted*union*.csv'):
  d=pd.read_csv(p,dtype=str,keep_default_na=False)
  for k in ['source_record_id','constituent_source_record_id']: 
   if k in d:ids.update(d[k])
  ledgers.append(str(p))
 for p in (E/f).glob('accepted_group_observations.csv'):
  d=pd.read_csv(p,dtype=str,keep_default_na=False)
  if 'source_record_ids_json'in d:
   for x in d.source_record_ids_json:ids.update(json.loads(x))
  ledgers.append(str(p))
h=pd.read_csv(O/'ranked_historical_targets.csv');h['mixed_precredited']=h.source_record_id.isin(ids);h.to_csv(O/'ranked_historical_targets.csv',index=False)
x=h[~h.mixed_precredited];print('notmixed',len(x));print(x[['settlement_name','census_year','region_norm','district_raw','population']].to_string(index=False))
rows=json.loads((O/'cached_event_candidates.json').read_text());
for z in rows:z['mixed_precredited']=z['source_record_id']in ids
(O/'cached_event_candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print('cached event residual',[(z['title'],z['region'],z['population'])for z in rows if not z['mixed_precredited']])
(O/'existing_credit_inputs.json').write_text(json.dumps(ledgers,indent=2))
