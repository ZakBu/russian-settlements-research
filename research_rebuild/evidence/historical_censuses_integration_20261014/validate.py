"""Bounded checks of published inputs and selected historical observations."""
from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
E=Path(__file__).resolve().parent
r=json.loads((E/'integration_receipt.json').read_text())
for p,sha in r['inputs'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha,p
out={};frames={}
for year in [1979,1989]:
 d=pd.read_parquet(E/f'population_{year}_selected_long.parquet');frames[year]=d
 assert not d.root.duplicated().any()
 assert np.isfinite(d[['latitude','longitude']].values).all()
 assert d.latitude.between(-90,90).all() and d.longitude.between(-180,180).all()
 ext=d[d.external_id.notna()&d.external_id.ne('')];assert not ext.external_id.duplicated().any()
 k=d.assign(name=d.historical_name.str.casefold().str.strip(),lat5=d.latitude.round(5),lon5=d.longitude.round(5))
 assert not k.duplicated(['current_region','name','lat5','lon5']).any()
 sex=d[d.population_male.notna()&d.population_female.notna()];assert (sex.population_male+sex.population_female==sex.population).all()
 assert int(d.population.sum())==r['years'][str(year)]['selected_population_mixed_basis']
 assert len(d)==r['years'][str(year)]['subjects']
 out[str(year)]={'subjects':len(d),'population_mixed_basis':int(d.population.sum()),'root_duplicates':0,'asserted_external_id_duplicates':0,'same_name_region_point_duplicates':0,'invalid_points':0,'sex_balanced_rows':len(sex),'sex_balance_failures':0}
a,b=frames[1979],frames[1989];joint=set(a.loc[a.current_full3_chain,'root'])&set(b.loc[b.current_full3_chain,'root'])
out['five_year_record_presence']={'roots':len(joint),'1979_population':int(a.loc[a.root.isin(joint),'population'].sum()),'1989_population':int(b.loc[b.root.isin(joint),'population'].sum()),'not_proof_of_unchanged_boundaries_or_all_own_NP_counts':True}
j=a.merge(b,on='root',suffixes=('_1979','_1989'));g=j[(j.population_1979>0)&(j.population_1989>0)&((j.population_1989/j.population_1979>=21)|(j.population_1979/j.population_1989>=21))]
(E/'growth_diagnostic.json').write_text(json.dumps({'absolute_factor_threshold':21,'flags_not_automatically_deleted_or_smoothed':g[['root','historical_name_1979','population_1979','population_1989','source_kind_1979','source_kind_1989']].to_dict('records')},ensure_ascii=False,indent=2))
out['growth_flags_1979_1989']=len(g);out['all_input_hashes_pass']=True
(E/'validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
