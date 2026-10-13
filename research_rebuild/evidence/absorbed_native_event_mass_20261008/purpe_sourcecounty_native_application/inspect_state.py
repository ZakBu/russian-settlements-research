from pathlib import Path
import sys,pandas as pd,json
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(35);a=s.obs[s.obs.region_norm.eq('ямало ненецкий')].copy();a['full3']=a.root.map(lambda x:s.years[x]=={2002,2010,2021});a['component_years']=a.root.map(lambda x:str(sorted(s.years[x])));a['ownpoint']=a.source_record_id.isin(s.point_rows)
a.to_csv(O/'native_yamal_actual35.csv',index=False)
names=['Пурпе','Харампур','Халясавэй','Толька','Самбург','Пуровск','Сывдарма','Ханымей']; b=a[a.settlement_name.str.lower().isin([x.lower()for x in names])];print(b[['source_record_id','settlement_name','settlement_type','census_year','district_raw','population','full3','component_years','ownpoint','okato','oktmo']].to_string(index=False)); print('POINTS')
for sid in b.source_record_id:
 if sid in s.point_rows:print(sid,json.dumps(s.point_rows[sid],ensure_ascii=False))
