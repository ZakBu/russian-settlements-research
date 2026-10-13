import sys,json,pandas as pd,duckdb,xlrd
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
O=Path(__file__).parent;s=load(27);d=s.obs
cases=[('нагорный','алтайский',7545,6358,6337),('сибирский','алтайский',8786,12046,10520),('подгорный','красноярский',6760,6164,5492)]
rows=[]
for name,region,p10,p02,p21 in cases:
 a=d[d.census_year.eq(2010)&d.region_norm.eq(region)&d.population.eq(p10)&d.name_norm.eq(name)].iloc[0];b=d[d.census_year.eq(2002)&d.region_norm.eq(region)&d.population.eq(p02)&d.name_norm.eq(name)].iloc[0];z=d[d.census_year.eq(2021)&d.region_norm.eq(region)&d.population.eq(p21)&d.name_norm.eq(name)].iloc[0]
 for x in [a,b,z]:
  print(name,x.census_year,x.source_record_id,sorted(s.years[s.uf.find(x.source_record_id)]),json.dumps(s.point_rows.get(x.source_record_id,{}),ensure_ascii=False))
 rows.append({'case':name,'region':region,'source2010':a.source_record_id,'source2002':b.source_record_id,'source2021':z.source_record_id,'current_okato':z.okato,'current_county':z.district_raw,'current_point':json.dumps(s.point_rows.get(z.source_record_id,{}),ensure_ascii=False)})
pd.DataFrame(rows).to_csv(O/'urban_type_bound_triplets.csv',index=False)
