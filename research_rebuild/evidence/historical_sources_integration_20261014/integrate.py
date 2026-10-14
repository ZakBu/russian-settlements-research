"""Preserve prior observations, add bounded secondary facts, clarify known source scope."""
from pathlib import Path
import json,hashlib,math
import pandas as pd
E=Path(__file__).resolve().parent;B=E.parent
base=B/'historical_100k_source_acquisition_20261014/population_1989_selected_long.parquet'
facts=E/'bounded_secondary_source_observations.parquet'
b=pd.read_parquet(base);f=pd.read_parquet(facts);assert f.root.is_unique
rows=[];overlaps=[]
for r in f.to_dict('records'):
 if r['root'] in set(b.root):
  o=b[b.root==r['root']].iloc[0];overlaps.append({'root':r['root'],'new_source_url':r['source_url'],'source_population':int(r['present_total']),'selected_population_preserved':int(o.population),'same_numeric_value':int(r['present_total'])==int(o.population)});continue
 row={k:None for k in b.columns}
 row.update(root=r['root'],anchor_source_record_id=r['anchor_source_record_id'],year=1989,historical_name=r['name'],current_region={'Тверская область':'тверская','Вологодская область':'вологодская'}[r['region']],population=int(r['present_total']),population_basis='UNKNOWN',source_kind=r['source_kind'],source_record_id=str(r['provider_id'])+':1989',source_url=r['source_url'],source_sha256=r['source_sha256'],source_locator=r['source_locator'],latitude=r['latitude'],longitude=r['longitude'],coordinate_source_record_id=r['coordinate_source_record_id'],coordinate_source_sha256='8be41d46b832310fc68bc48c715e71af87e5c525fc7e1c4d7264ce71931a623a',point_identity_grade='accepted_native_own_NP_point_retrospective_continuity_inference',external_identity_asserted=False,binding_status=r['binding_status'],linked_census_years=r['linked_census_years'],current_full3_chain=r['current_full3_chain'],retrospective_current_point_inference=True,historical_boundary_comparability='UNKNOWN',population_value_quality='secondary_literal_year_primary_unverified',source_date_raw='1989',source_date_precision='year',date_basis='secondary_table_column_label_1989_census_primary_unverified',source_claim_proofs_json=json.dumps({'historical_name':r['name'],'historical_region':r['region'],'historical_district':r['district'],'table_1989_literal':r['present_total'],'table_2002_comparison':r['population2002_comparison'],'raw_source_columns':{k:v for k,v in r.items() if k.endswith('_raw') and not pd.isna(v)},'source2002_differences_against_native_layer_do_not_change_selected_census_values':r['region']=='Вологодская область'},ensure_ascii=False))
 rows.append(row)
delta=pd.DataFrame(rows,columns=b.columns);combined=pd.concat([b,delta],ignore_index=True)
mask=combined.source_record_id.str.startswith('stavropol1989:',na=False)
combined.loc[mask,'historical_boundary_comparability']='official_1989_values_adjusted_for_post_census_administrative_changes_not_native_boundary_observation'
combined.loc[mask,'population_value_quality']='regional_published_census_population_basis_retained_adjusted_administrative_scope'
combined.loc[mask,'date_basis']='1989_census_values_adjusted_for_post_census_administrative_changes'
combined.to_parquet(E/'population_1989_selected_long.parquet',index=False);combined.to_csv(E/'population_1989_selected_long.csv.gz',index=False,compression={'method':'gzip','mtime':0});delta.to_parquet(E/'new_1989_secondary_records.parquet',index=False)
pd.DataFrame(overlaps).to_csv(E/'overlapping_secondary_observations.csv',index=False)
assert len(combined)==20453 and combined.root.is_unique and int(combined.population.sum())==120016762
assert len(delta)==27 and int(delta.population.sum())==4319
assert all(math.isfinite(x) for x in combined.latitude) and all(math.isfinite(x) for x in combined.longitude)
assert combined.iloc[:len(b)].population.tolist()==b.population.tolist()
assert combined.iloc[:len(b)].root.tolist()==b.root.tolist()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r={'1979_objects_unchanged':8140,'1979_population_unchanged':102131774,'1989_objects':len(combined),'1989_mixed_source_population':int(combined.population.sum()),'new_secondary_objects':len(delta),'new_secondary_population':int(delta.population.sum()),'new_explicit_secondary_zeros':int((delta.population==0).sum()),'new_objects_current_full3_presence':int(delta.current_full3_chain.sum()),'new_population_current_full3_presence':int(delta.loc[delta.current_full3_chain,'population'].sum()),'existing_stavropol_source_scope_clarified':int(mask.sum()),'stavropol_new_objects':0,'source_overlaps_kept':len(overlaps),'old_population_values_changed':0,'old_root_values_changed':0,'2002_2010_2021_mutated':False,'unknown_values_imputed':0,'target_per_year':100000,'remaining_objects':{'1979':91860,'1989':100000-len(combined)},'inputs':{str(p):sha(p) for p in [base,facts]},'output_sha256':sha(E/'population_1989_selected_long.parquet')}
(E/'run_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
