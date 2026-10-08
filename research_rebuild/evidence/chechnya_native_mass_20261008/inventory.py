import sys,json
from pathlib import Path
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(29);o=s.obs[s.obs.region_norm.eq('чеченская')].copy();o['years']=o.source_record_id.map(lambda x:str(sorted(s.years[s.uf.find(x)])));o['point']=o.source_record_id.map(lambda x:x in s.point_rows)
o.to_csv(Path(__file__).parent/'regional_inventory.csv',index=False)
for y in [2002,2010,2021]:
 d=o[(o.census_year==y)&o.years.ne('[2002, 2010, 2021]')];print(y,len(d));print(d[['settlement_name','district_raw','population','years','point']].to_string(index=False))
