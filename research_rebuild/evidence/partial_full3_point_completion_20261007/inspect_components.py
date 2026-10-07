import sys,json
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km
s=load(stage=10);d=pd.read_csv(R/'research_rebuild/evidence/working_full_chain_20261007/own_point_full3_components_missing_other_year_points.csv');roots=set(d.source_record_id.map(s.uf.find));s.obs['root']=s.obs.source_record_id.map(s.uf.find)
for root,g in s.obs[s.obs.root.isin(roots)].groupby('root'):
 p=[(sid,s.point_rows[sid]) for sid in g.source_record_id if sid in s.point_rows];base=max(p,key=lambda t:int(s.by_id.loc[t[0],'census_year']))[1];coord=(base['latitude'],base['longitude']);checks=[]
 for r in g.itertuples():
  raw=(r.latitude,r.longitude);dist=distance_km(coord,raw) if pd.notna(r.latitude) and pd.notna(r.longitude) else None
  checks.append({'id':r.source_record_id,'year':r.census_year,'type':r.settlement_type,'county':r.district_raw,'point':r.source_record_id in s.point_rows,'rawdistance':dist,'native':raw})
 print(g.iloc[0].settlement_name,json.dumps(checks,ensure_ascii=False))
