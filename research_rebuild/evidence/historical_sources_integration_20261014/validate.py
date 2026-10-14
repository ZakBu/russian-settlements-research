from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
E=Path(__file__).resolve().parent;B=E.parent
b=pd.read_parquet(B/'historical_100k_source_acquisition_20261014/population_1989_selected_long.parquet');d=pd.read_parquet(E/'population_1989_selected_long.parquet');n=pd.read_parquet(E/'new_1989_secondary_records.parquet');r=json.loads((E/'run_receipt.json').read_text())
assert len(d)==20453 and d.root.is_unique and d.population.sum()==120016762
assert len(n)==27 and n.population.sum()==4319 and (n.population==0).sum()==3
assert np.isfinite(d[['latitude','longitude']].to_numpy(dtype=float)).all()
assert d.latitude.between(-90,90).all() and d.longitude.between(-180,180).all()
old=d.iloc[:len(b)];updated={'historical_boundary_comparability','population_value_quality','date_basis'}
for col in b.columns:
 if col not in updated:
  assert old[col].fillna('__NULL__').astype(str).tolist()==b[col].fillna('__NULL__').astype(str).tolist(),col
changed=old.historical_boundary_comparability.ne(b.historical_boundary_comparability)
assert changed.sum()==706 and old.loc[changed,'source_record_id'].str.startswith('stavropol1989:').all()
assert hashlib.sha256((E/'population_1989_selected_long.parquet').read_bytes()).hexdigest()==r['output_sha256']
accepted=pd.read_parquet(E/'bounded_secondary_source_observations.parquet');assert accepted.root.is_unique and len(accepted)==35
corepath=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
assert hashlib.sha256(corepath.read_bytes()).hexdigest()=='8be41d46b832310fc68bc48c715e71af87e5c525fc7e1c4d7264ce71931a623a'
c=pd.read_parquet(corepath,columns=['source_record_id','census_year','root','settlement_name','settlement_type','region_norm','district_raw','population'])
growth=[];comparisons=[]
for q in accepted.to_dict('records'):
 a=c[c.source_record_id==q['anchor_source_record_id']];assert len(a)==1 and a.iloc[0].root==q['root']
 t=c[(c.root==q['root'])&(c.census_year==2002)];assert len(t)==1
 comparisons.append({'root':q['root'],'name':q['name'],'region':q['region'],'source_2002_comparison':int(q['population2002_comparison']),'selected_2002_preserved':int(t.iloc[0].population),'same_numeric_value':int(q['population2002_comparison'])==int(t.iloc[0].population)})
for q in n.to_dict('records'):
 t=c[c.root==q['root']].sort_values('census_year')
 for v in t.to_dict('records'):
  oldpop=int(q['population']);newpop=int(v['population']);ratio=newpop/oldpop if oldpop>0 else None
  growth.append({'root':q['root'],'name':q['historical_name'],'from_year':1989,'to_year':int(v['census_year']),'from_population':oldpop,'to_population':newpop,'ratio':ratio,'growth_over_2000_percent':ratio is not None and ratio>21,'zero_base_no_percentage':oldpop==0})
pd.DataFrame(growth).to_csv(E/'new_records_growth_diagnostic.csv',index=False);pd.DataFrame(comparisons).to_csv(E/'source_2002_reconciliation.csv',index=False)
z={'unique_roots':True,'finite_valid_points':True,'old_values_preserved_except_706_documented_scope_metadata_updates':True,'core_sha256_unchanged':True,'growth_over_2000_percent':sum(x['growth_over_2000_percent'] for x in growth),'new_zero_bases_not_divided':3,'vologda_2002_source_differences':sum(x['region']=='Вологодская область' and not x['same_numeric_value'] for x in comparisons),'goal_100k_reached':False}
(E/'validation.json').write_text(json.dumps(z,ensure_ascii=False,indent=2));print(json.dumps(z,ensure_ascii=False,indent=2))
