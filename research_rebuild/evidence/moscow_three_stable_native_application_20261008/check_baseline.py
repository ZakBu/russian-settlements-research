import sys,json
sys.path.insert(0,'research_rebuild/mass_linkage')
from working_state_20261007 import load
s=load(25)
for end in [65584,68492,66986]:
 sid=f'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:{end}'
 print('CURRENT',s.by_id.loc[sid].to_dict(), '\nPOINT',s.point_rows[sid])
for lo,hi in [(8850,8868),(11480,11494),(9788,9800)]:
 for _,r in s.obs[s.obs.source_record_id.str.startswith('2010:010_')].iterrows():
  row=int(r.source_record_id.rsplit(':',1)[1])
  if lo<=row<=hi:
   comp=s.obs[s.obs.root.eq(s.uf.find(r.source_record_id))]
   print(row,r.settlement_name,r.settlement_type,r.population,[(x.census_year,x.district_raw) for x in comp.itertuples()],s.years[s.uf.find(r.source_record_id)])
print('METRICS',json.dumps(s.metrics()))
