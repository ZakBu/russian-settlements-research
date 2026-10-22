#!/usr/bin/env python3
"""Additional cold-source audit of retail/pickup construct sensitivity."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
B=Path(__file__).resolve().parents[2];R=Path(__file__).resolve().parent

def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 result=R/'support_point_profiles.parquet';wide=B/'national_integration_20261019/places/places_settlement_features.parquet';long=B/'national_integration_20261019/places/places_objects_and_crosswalk.parquet'
 d=pd.read_parquet(result).set_index('id');q=pd.read_parquet(wide).set_index('id').reindex(d.index);p=pd.read_parquet(long,columns=['function_group','source_category','name_signal_wildberries','name_signal_ozon','baseline_uid','conditional_uid','nearest_uid_unaccepted','source_geography_scope','country_polygon_conflict','source_operating_status'])
 eligible=p.source_geography_scope.eq('axis_linkage_eligible')&~p.country_polygon_conflict.fillna(True)&p.nearest_uid_unaccepted.isin(d.index)&~p.source_operating_status.fillna('unknown').astype(str).str.lower().eq('permanently_closed');p=p.loc[eligible].copy()
 named=p.function_group.eq('retail_store')&p.source_category.eq('shopping')&(p.name_signal_wildberries.fillna(False)|p.name_signal_ozon.fillna(False));checks=[];stats={}
 for scope,legal,physical,wb in [('baseline','legal_native','physical_baseline','wb_strict'),('conditional','legal_conditional','physical_conditional','wb_name_relaxed')]:
  uid=p.baseline_uid if scope=='baseline' else p.baseline_uid.fillna(p.conditional_uid);retail=p.function_group.isin(['retail_store','market']);original=uid.loc[retail].value_counts().reindex(d.index,fill_value=0).to_numpy();expected=q.places_baseline_retail_store_count.to_numpy()+q.places_baseline_market_count.to_numpy()
  if scope=='conditional':expected+=q.places_conditional_retail_store_count.to_numpy()+q.places_conditional_market_count.to_numpy()
  checks.append({'name':scope+'_raw_retail_source_reconstruction','pass':bool(np.array_equal(original,expected))})
  clean=uid.loc[retail&~named].value_counts().reindex(d.index,fill_value=0).to_numpy();physical_fields=[c for c in d if c.startswith(physical+'_unmerged_function_') and c.endswith('_witness')];functions=[c[len(physical+'_unmerged_function_'):-len('_witness')] for c in physical_fields];a=d[physical_fields].to_numpy(bool);a[:,functions.index('retail')]=clean>0
  for source in [legal,wb]:a|=d[[source+'_unmerged_function_'+f+'_witness' for f in functions]].to_numpy(bool)
  count=a.sum(axis=1)-(a[:,functions.index('retail')]&a[:,functions.index('marketplace_pickup')]);checks.append({'name':scope+'_clean_scenario_from_cold_source','pass':bool(np.array_equal(count,d[scope+'_retail_name_filtered_function_diversity'].to_numpy()))})
  checks.append({'name':scope+'_trade_OR','pass':bool(np.array_equal(d[scope+'_function_trade_access_witness'].to_numpy(),d[scope+'_unmerged_function_retail_witness'].to_numpy()|d[scope+'_unmerged_function_marketplace_pickup_witness'].to_numpy()))})
  expected_primary=d[scope+'_unmerged_function_diversity'].to_numpy()-(d[scope+'_unmerged_function_retail_witness'].to_numpy()&d[scope+'_unmerged_function_marketplace_pickup_witness'].to_numpy());checks.append({'name':scope+'_primary_vs_unmerged_count_identity','pass':bool(np.array_equal(expected_primary,d[scope+'_function_diversity'].to_numpy()))})
  stats[scope]={'original_accepted_retail_records':int(original.sum()),'filtered_accepted_retail_records':int(clean.sum()),'named_shopping_records_excluded':int(original.sum()-clean.sum()),'primary_multiple_to_single_from_trade_merge_UID':int((d[scope+'_unmerged_profile_category'].eq('multiple_observed_functions')&d[scope+'_profile_category'].eq('single_observed_function')).sum())}
 checks.append({'name':'healthcare_Ozon_names_never_filtered_as_shopping','pass':not (named&p.function_group.eq('healthcare')).any()})
 report={'pass':all(x['pass'] for x in checks),'checks':checks,'source_reconstruction':stats,'input_sha256':{str(f.relative_to(B)):digest(f) for f in [result,wide,long]},'code_sha256':digest(Path(__file__)),'scope':'Additional author cold-source construct check; independent agent validation is separate.'}
 (R/'RETAIL_CONSTRUCT_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');assert report['pass'],checks
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
