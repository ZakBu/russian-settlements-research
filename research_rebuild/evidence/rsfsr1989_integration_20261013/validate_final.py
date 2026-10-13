import pandas as pd,numpy as np,json,hashlib
from pathlib import Path
p=Path(__file__).resolve().parent; repo=p.parents[2]
d=pd.read_parquet(p/'population_1989_selected_long.parquet'); r=json.loads((p/'integration_receipt.json').read_text())
assert len(d)==20424 and int(d.population.sum())==120006238
assert not d.root.duplicated().any()
assert np.isfinite(d[['latitude','longitude']].values).all()
assert d.latitude.between(-90,90).all() and d.longitude.between(-180,180).all()
e=d.external_id.dropna();e=e[e.astype(str).str.len()>0];assert not e.duplicated().any()
sex=d[d.population_male.notna()&d.population_female.notna()]; bad=sex[sex.population_male+sex.population_female!=sex.population]
assert len(bad)==0
assert not (d.external_id.fillna('')=='Q193909').any()
for name,sha in r['inputs'].items():
 assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha,name
c=pd.read_parquet('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
c=c[c.census_year==2002][['root','population','source_record_id']]; c=c[c.population.notna()].sort_values('source_record_id').drop_duplicates('root')
g=d.merge(c,on='root',suffixes=('_1989','_2002'));g=g[(g.population_1989>0)&(g.population_2002/g.population_1989>=21)]
(p/'large_growth_diagnostic.json').write_text(json.dumps({'threshold_growth_percent':2000,'not_automatically_removed':True,'rows':g[['root','historical_name','current_region','population_1989','population_2002']].to_dict('records')},ensure_ascii=False,indent=2))
k=d.assign(name=d.historical_name.str.casefold().str.strip(),lat5=d.latitude.round(5),lon5=d.longitude.round(5));dup=k[k.duplicated(['current_region','name','lat5','lon5'],keep=False)]
assert len(dup)==0, 'unresolved same-name region point collision'
(p/'same_physical_point_diagnostic.json').write_text(json.dumps({'same_literal_name_region_point_5dec_duplicate_rows':len(dup),'rows':dup[['root','historical_name','current_region','latitude','longitude']].to_dict('records')},ensure_ascii=False,indent=2))
(p/'final_validation.json').write_text(json.dumps({'selected_subjects':len(d),'population_mixed_basis':int(d.population.sum()),'root_duplicates':0,'asserted_external_id_duplicates':0,'invalid_points':0,'sex_balanced_rows':len(sex),'sex_balance_failures':0,'all_input_hashes_verified':True,'known_seversk_nonadditive_claim_excluded':True,'growth_flags_1989_2002':len(g),'same_name_region_point_duplicate_rows':len(dup)},ensure_ascii=False,indent=2))
d.to_csv(p/'population_1989_selected_long.csv.gz',index=False,compression='gzip')
print((p/'final_validation.json').read_text())
