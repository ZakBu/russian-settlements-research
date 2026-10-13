"""Read-only baseline audit; no candidates admitted or source layers edited."""
from pathlib import Path
import hashlib,json,time,math
import pandas as pd
F=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
OUT=Path('/workspace/settlements-work/continuation_20261003/audit_99_20261003/root')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def run():
 start=time.monotonic(); coverage=json.loads((F/'coverage.json').read_text())
 cols=['observation_id','source_record_id','record_type','entity_id','observation_year','entity_category','legacy_is_federal_aggregate','latitude','longitude','population_value','population_value_quality','association_status','census_full_chain']
 x=pd.read_parquet(F/'settlements_long.parquet',columns=cols)
 assert x.observation_id.notna().all() and x.observation_id.is_unique
 assert x.latitude.notna().equals(x.longitude.notna())
 valid=x.latitude.notna()
 assert x.loc[valid,'latitude'].between(-90,90).all() and x.loc[valid,'longitude'].between(-180,180).all()
 c=x[x.record_type.eq('census')]; assert c.source_record_id.is_unique
 metrics=[]
 for saved in coverage['census_metrics']:
  y=c[c.observation_year.eq(saved['year'])]; ctl=saved['official_control']
  pt=y[y.latitude.notna()];fed=y[y.legacy_is_federal_aggregate.eq(True)]
  assert int(pt.population_value.sum())==saved['axes']['coordinate_admitted']['known_population']
  assert len(pt)==saved['axes']['coordinate_admitted']['rows']
  assert int(fed.population_value.sum())==saved['recognized_federal_territorial_aggregate']['known_population']
  assert fed.latitude.isna().all()
  missing=y[y.latitude.isna() & ~y.legacy_is_federal_aggregate.eq(True)]
  known=int(y.population_value.sum());fp=int(fed.population_value.sum());pp=int(pt.population_value.sum());mp=int(missing.population_value.sum());gap=ctl-known
  assert pp+fp+mp+gap==ctl
  rows={'year':saved['year'],'control':ctl,'known_selected_population':known,'source_population_gap':gap,'accepted_point_records':len(pt),'accepted_point_population':pp,'aggregate_population':fp,'unpointed_nonaggregate_records':len(missing),'unpointed_nonaggregate_population':mp,'availability_population':saved['axes']['coordinate_availability_by_exact_source_route']['known_population'],'physical_selected_point_coverage':pp/(known-fp),'canonical_national_point_coverage':pp/ctl,'targets':{},'axes':saved['axes'],'population_quality':saved['population_quality_categories']}
  for label,numerator,denominator in [('99_percent',99,100),('99_9_percent',999,1000)]:
   threshold=(ctl*numerator+denominator-1)//denominator
   rows['targets'][label]={'minimum_population':threshold,'required_additional_admitted_point_population':max(0,threshold-pp),'available_point_inventory_shortfall_even_if_all_correct':max(0,threshold-rows['availability_population']),'current_grain_nonaggregate_ceiling_shortfall':max(0,threshold-(known-fp)),'physical_selected_operational_threshold':((known-fp)*numerator+denominator-1)//denominator,'physical_selected_additional_needed':max(0,((known-fp)*numerator+denominator-1)//denominator-pp)}
  metrics.append(rows)
 result={'audit':'read_only_current_baseline_and_target_bounds','created_inputs':[{ 'path':str(F/p),'sha256':sha(F/p)} for p in ['settlements_long.parquet','coverage.json']],'checks':{'unique_observation_ids':True,'coordinate_pairs_and_ranges':True,'census_point_counts_population_equal_published_coverage':True,'aggregate_population_equal_published_coverage_and_no_settlement_points':True,'disjoint_population_partition_sums_to_full_control':True},'row_count':len(x),'census_rows':len(c),'metrics':metrics,'no_admissions':True,'inventory_is_not_accuracy':True,'additional_years_national_denominators':'not_defined','seconds':round(time.monotonic()-start,3)}
 (OUT/'baseline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'checks':result['checks'],'years':[{k:v for k,v in r.items() if k not in ['axes','population_quality']} for r in metrics],'seconds':result['seconds']},ensure_ascii=False,indent=2))
 return result
if __name__=='__main__': run()
