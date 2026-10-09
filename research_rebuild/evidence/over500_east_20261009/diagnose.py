from pathlib import Path
import pandas as pd,re,json,hashlib
O=Path(__file__).parent
D=pd.read_parquet('/dev/shm/over500-20261009/east_obs_direct.parquet').fillna('')
R=pd.read_csv(O/'assigned.csv').fillna('')
def county(x):
 x=re.sub(r'[^а-яё0-9 ]',' ',str(x).lower().replace('ё','е'))
 x=re.sub(r'\b(муниципальный|район|округ|городской|город|города|г|го|улус|национальный|кожуун)\b',' ',x)
 return ' '.join(x.split())
D['county']=D.district_raw.map(county)
# Only two-sided immediate source-order anchoring, requiring identical accepted county labels.
rootco=D[D.county.ne('')].groupby('root').county.agg(lambda a:set(a))
for i,row in D[D.county.eq('')].iterrows():
 c=rootco.get(row.root,set())
 if len(c)==1:D.at[i,'county']=next(iter(c))
D['ord']=D.source_record_id.str.extract(r':(\d+)$').astype(float)
D['county_basis']='native_printed_or_existing_accepted_component'
for f,g in D[D.census_year.eq(2010)].groupby('source_file'):
 g=g.sort_values('ord');known=g[g.county.ne('')]
 for i,row in g[g.county.eq('')].iterrows():
  before=known[known.ord.lt(row.ord)].tail(1);after=known[known.ord.gt(row.ord)].head(1)
  if len(before) and len(after) and before.county.iloc[0]==after.county.iloc[0] and row.ord-before.ord.iloc[0]<100 and after.ord.iloc[0]-row.ord<100:
   D.at[i,'county']=before.county.iloc[0];D.at[i,'county_basis']='two_sided_accepted_native_source_order_county_bracket:'+before.source_record_id.iloc[0]+'|'+after.source_record_id.iloc[0]
D.to_pickle('/dev/shm/over500-20261009/east_enriched.pkl')
rows=[]
for r in R.itertuples():
 t=D[D.source_record_id.eq(r.source_record_id)].iloc[0];g=D[D.region_norm.eq(t.region_norm)&D.name_norm.eq(t.name_norm)&D.county.eq(t.county)] if t.county else D.iloc[:0]
 rows.append(dict(source_record_id=t.source_record_id,name=t.settlement_name,county=t.county,region=t.region_norm,years=','.join(map(str,sorted(set(g.census_year)))),unique=not g.census_year.duplicated().any(),n=len(g),members='|'.join(g.source_record_id)))
pd.DataFrame(rows).to_csv(O/'diagnostic.csv',index=False)
print(pd.DataFrame(rows).groupby(['years','unique']).size().to_string())
