"""Population-first diagnostics; mixed-scope scenarios are conditional, not admissions."""
from pathlib import Path
import json
import pandas as pd
F=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
O=Path('/workspace/settlements-work/continuation_20261003/audit_99_20261003/root')
x=pd.read_parquet(F/'settlements_long.parquet',columns=['record_type','source_record_id','observation_year','entity_id','population_value','latitude','legacy_is_federal_aggregate','census_full_chain','association_status'])
controls={m['year']:m['official_control'] for m in json.loads((F/'coverage.json').read_text())['census_metrics']};out=[]
for year in controls:
 y=x[x.record_type.eq('census')&x.observation_year.eq(year)];big=y[y.population_value.ge(2000)];phys=big[~big.legacy_is_federal_aggregate.eq(True)];small=y[y.population_value.lt(2000)];accepted=y[y.latitude.notna()];missingbig=phys[phys.latitude.isna()];fed=big[big.legacy_is_federal_aggregate.eq(True)];threshold=(controls[year]*99+99)//100
 hypothetical=int(accepted.population_value.sum()+missingbig.population_value.sum()+fed.population_value.sum())
 out.append({'year':year,'threshold':2000,'comparison':'>=','large_rows':len(big),'large_population':int(big.population_value.sum()),'large_population_fraction_full_control':float(big.population_value.sum()/controls[year]),'large_physical_rows':len(phys),'large_physical_unpointed_rows':len(missingbig),'large_physical_unpointed_population':int(missingbig.population_value.sum()),'small_known_population':int(small.population_value.sum()),'small_already_pointed_population':int(small.loc[small.latitude.notna(),'population_value'].sum()),'conditional_spatial_population_if_all_large_resolved_and_federal_territories_represented':hypothetical,'conditional_fraction':hypothetical/controls[year],'conditional_remaining_to_99':max(0,threshold-hypothetical),'conditional_not_admitted_and_mixed_explicit_spatial_scope':True,'large_linked_population':int(big.loc[big.association_status.eq('accepted_same_place_component'),'population_value'].sum()),'large_full_chain_population':int(big.loc[big.census_full_chain.eq(True),'population_value'].sum())})
(O/'population_priority_ge2000.json').write_text(json.dumps({'inputs':{'table_sha256':'0826f554d9100c52b5e430327cb209d030d035f7c52dd19caa7cf7c902969a72'},'no_admissions':True,'years':out},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'years':len(out),'no_admissions':True}))
