import sys,json
from pathlib import Path
from collections import defaultdict
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km
O=Path(__file__).parent;f=pd.read_csv(R/'research_rebuild/evidence/working_full_chain_20261007/own_point_full3_components_missing_other_year_points.csv');s=load(22);roots={s.uf.find(sid) for sid in f.source_record_id};m=defaultdict(list)
for a in s.obs.to_dict('records'):
 if s.uf.find(a['source_record_id']) in roots:m[s.uf.find(a['source_record_id'])].append(a)
rows=[]
for root,group in m.items():
 if s.years[root]!={2002,2010,2021}:continue
 if all(a['source_record_id'] in s.point_rows for a in group):continue
 for a in group:
  sid=a['source_record_id'];p=s.point_rows.get(sid,{})
  rows.append({'root':root,'source_record_id':sid,'year':a['census_year'],'name':a['settlement_name'],'type':a['settlement_type'],'county':a['district_raw'],'region':a['region_norm'],'population':a['population'],'component_population_sum':sum(float(z['population']) for z in group),'haspoint':bool(p),'point_origin_kind':p.get('point_origin_kind',''),'point_origin_file':p.get('point_origin_file',''),'point_origin_locator':p.get('point_origin_locator',''),'point_ledger_path':p.get('point_ledger_path',''),'latitude':p.get('latitude'),'longitude':p.get('longitude'),'point_json':json.dumps(p,ensure_ascii=False,default=str)})
g=pd.DataFrame(rows).sort_values(['component_population_sum','root','year'],ascending=[False,True,True]);g.to_csv(O/'existing_full3_point_conflicts.csv',index=False);print('components',g.root.nunique());print(g.drop(columns=['point_json','point_origin_locator','point_ledger_path']).to_string(index=False))
