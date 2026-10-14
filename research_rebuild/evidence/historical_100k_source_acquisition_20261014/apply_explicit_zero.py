"""Preserve an explicitly published zero; missing values never become zero."""
from pathlib import Path
import hashlib,json
import pandas as pd
E=Path(__file__).resolve().parent;B=E.parent
base=B/'historical_censuses_integration_20261014/population_1989_selected_long.parquet'
fact=E/'literal_zero_1989_ready_fact.parquet'
d=pd.read_parquet(base);f=pd.read_parquet(fact).iloc[0].to_dict()
assert f['population']==0 and f['zero_basis']=='explicit_observed_literal_not_unknown_or_imputed'
assert f['own_point_distance_km']<0.2 and f['root'] not in set(d.root)
assert not f['contradictory_selected_or_long_1989_values']
corepath=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
c=pd.read_parquet(corepath,columns=['root','census_year']);years=sorted(set(c.loc[c.root==f['root'],'census_year']))
row={k:None for k in d.columns}
for k in ['root','anchor_source_record_id','year','population','historical_name','current_region','source_kind','population_basis','source_record_id','source_url','source_sha256','source_locator','latitude','longitude','binding_status','retrospective_current_point_inference','historical_boundary_comparability']:row[k]=f[k]
row.update(population_value_quality='secondary_explicit_zero_primary_unverified',linked_census_years='|'.join(map(str,years)),current_full3_chain=years==[2002,2010,2021],point_identity_grade='unique_native_own_NP_name_region_county_article_point_within_0.2km',external_identity_asserted=False,date_basis='literal_dated_year_not_automatically_census',source_date_precision='UNKNOWN',source_claim_proofs_json=json.dumps({k:f[k] for k in ['context','raw_population_literal','zero_basis','revision_sha1','citation_url_unfetched']},ensure_ascii=False))
out=pd.concat([d,pd.DataFrame([row])],ignore_index=True)
assert len(out)==20426 and not out.root.duplicated().any()
assert int(out.population.sum())==int(d.population.sum())==120012443
out.to_parquet(E/'population_1989_selected_long.parquet',index=False)
out.to_csv(E/'population_1989_selected_long.csv.gz',index=False,compression={'method':'gzip','mtime':0})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r={'target_objects_per_year':100000,'1979_objects_unchanged':8140,'1989_objects':len(out),'1989_population_unchanged':int(out.population.sum()),'added_explicit_zero_subjects':1,'added_population':0,'unknown_values_imputed':0,'remaining_objects_to_target':{'1979':91860,'1989':79574},'inputs':{str(p):sha(p) for p in [base,fact,corepath]},'output_sha256':sha(E/'population_1989_selected_long.parquet')}
(E/'run_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
