import sys,json,re
from pathlib import Path
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize
O=Path(__file__).parent;s=load(26)
import importlib.util
sp=importlib.util.spec_from_file_location('a',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);s=m.apply(s)
d=s.obs;d['key']=d.settlement_name.map(normalize)
res=d[d.census_year.eq(2010)&d.is_additive_settlement_record.fillna(False)&d.source_record_id.map(lambda x:s.years[s.uf.find(x)]!={2002,2010,2021})&~d.region_norm.isin(['москва','санкт петербург','севастополь'])].copy()
# Narrow lexical hypotheses: explicit standalone settlement types/designators; each requires source binding below.
rules=[('trailing_type',r'\s+(?:п\.|пгт|рп|с\.|д\.|пос\.|ст\.|село|деревня|поселок|посёлок)$'),('leading_type',r'^(?:п\.|пгт|рп|с\.|д\.|пос\.|ст\.|село|деревня|поселок|посёлок)\s+')]
rows=[]
for _,a in res.iterrows():
 for rule,pat in rules:
  key=normalize(re.sub(pat,'',a.key))
  if key==a.key:continue
  for _,b in d[d.census_year.ne(2010)&d.region_norm.eq(a.region_norm)&d.key.eq(key)].iterrows():
   rows.append(dict(source_record_id=a.source_record_id,name=a.settlement_name,type=a.type_norm,region=a.region_norm,population=a.population,rule=rule,key=key,to_source_record_id=b.source_record_id,to_year=b.census_year,to_name=b.settlement_name,to_type=b.type_norm,to_county=b.district_raw,to_code=b.okato,to_population=b.population,source_file=a.source_file,from_years=str(sorted(s.years[s.uf.find(a.source_record_id)])),to_years=str(sorted(s.years[s.uf.find(b.source_record_id)])),to_point=json.dumps(s.point_rows.get(b.source_record_id,{}),ensure_ascii=False)))
f=pd.DataFrame(rows);f.to_csv(O/'explicit_type_variant_screen.csv',index=False);print(f[['name','region','population','rule','to_name','to_type','to_population','from_years','to_years']].to_string(index=False));print(res.groupby('source_file').population.agg(['count','sum']).sort_values('sum',ascending=False).head(20).to_string())
# Also record endpoint exact-name hypotheses for mass source-context gap.
rows=[]
for _,a in res[res.population.ge(1500)].iterrows():
 for _,b in d[d.census_year.ne(2010)&d.region_norm.eq(a.region_norm)&d.key.eq(a.key)].iterrows():
  if s.uf.find(a.source_record_id)==s.uf.find(b.source_record_id):continue
  rows.append(dict(source_record_id=a.source_record_id,name=a.settlement_name,type=a.type_norm,region=a.region_norm,population=a.population,to_source_record_id=b.source_record_id,to_year=b.census_year,to_type=b.type_norm,to_county=b.district_raw,to_code=b.okato,to_population=b.population,source_file=a.source_file,from_years=str(sorted(s.years[s.uf.find(a.source_record_id)])),to_years=str(sorted(s.years[s.uf.find(b.source_record_id)])),to_point=json.dumps(s.point_rows.get(b.source_record_id,{}),ensure_ascii=False)))
pd.DataFrame(rows).to_csv(O/'large_exact_name_context_screen.csv',index=False)
