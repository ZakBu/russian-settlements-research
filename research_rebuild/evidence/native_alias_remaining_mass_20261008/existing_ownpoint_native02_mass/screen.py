import sys,json,importlib.util
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km
s=load(38)
p=O.parent/'all_cached_native2002_context_followup/apply.py';spec=importlib.util.spec_from_file_location('frozen39',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.apply(s)
old=s.obs[s.obs.census_year.eq(2002)];current=s.obs[s.obs.census_year.eq(2021)]
# Index all native02 records first; full histories and namesakes stay in competitor sets.
idx={k:g for k,g in old.groupby(['region_norm','name_norm','type_norm'],dropna=False)}
rows=[];kinds={};oldeligible=0;currenteligible=0
for _,n in current.iterrows():
 if s.years[s.uf.find(n.source_record_id)]!={2010,2021} or n.source_record_id not in s.point_rows:continue
 currenteligible+=1;np=s.point_rows[n.source_record_id];key=(n.region_norm,n.name_norm,n.type_norm)
 if key not in idx:continue
 peers=idx[key];near=[]
 for _,a in peers.iterrows():
  op=s.point_rows.get(a.source_record_id)
  if op:
   d=distance_km((np['latitude'],np['longitude']),(op['latitude'],op['longitude']))
   if d<=5:near.append((a,op,d))
 for a,op,d in near:
  if s.years[s.uf.find(a.source_record_id)]!={2002}:continue
  kind=op.get('point_origin_kind','');kinds[kind]=kinds.get(kind,0)+1
  rows.append({'current_source_record_id':n.source_record_id,'old_source_record_id':a.source_record_id,'name':n.settlement_name,'region':n.region_norm,'native_type':a.settlement_type,'native02_county':a.district_raw,'current_county':n.district_raw,'population2002':a.population,'population2021':n.population,'distance_km':d,'all_native02_same_name_type_count':len(peers),'all_native02_point_within5_count':len(near),'all_native02_competitor_ids':json.dumps(peers.source_record_id.tolist()),'old_admitted_point_json':json.dumps(op,ensure_ascii=False),'current_admitted_point_json':json.dumps(np,ensure_ascii=False),'old_point_origin_kind':kind})
df=pd.DataFrame(rows)
if len(df):df.sort_values('population2002',ascending=False).to_csv(O/'exact_native_name_type_ownpoint_candidates.csv.gz',index=False,compression='gzip')
print(json.dumps({'baseline':'actual38 plus frozen five-case39 CSV application','current_missing02_ownpoint_components':currenteligible,'candidate_pairs':len(rows),'candidate_current_components':df.current_source_record_id.nunique() if len(df) else 0,'population2002_candidate_unique_old':float(df.drop_duplicates('old_source_record_id').population2002.sum()) if len(df) else 0,'old_point_origin_kind_counts':kinds,'top':df[['name','region','population2002','distance_km','all_native02_same_name_type_count','all_native02_point_within5_count','old_point_origin_kind']].head(25).to_dict('records') if len(df) else []},ensure_ascii=False))
