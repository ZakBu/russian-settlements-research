"""Check both prospective historical years against all trusted accepted stage14 points."""
import sys,json
from pathlib import Path
import pandas as pd
from collections import defaultdict
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
OUT=Path(__file__).resolve().parent;WORK=Path('/workspace/settlements-work/secondary_2010_new_triplets_20261007')
s=load(14);baseline=s.metrics();assert [baseline[str(y)]['covered_population'] for y in [2002,2010,2021]]==[126150476,123382596,123960048]
p=pd.read_csv(WORK/'candidate_point_uses.csv');occupied=defaultdict(set)
for sid,r in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),r['latitude'],r['longitude'])].add(sid)
holds=[]
for r in p.to_dict('records'):
 other=occupied.get((int(r['target_year']),r['latitude'],r['longitude']),set())-{r['target_source_record_id']}
 if other:holds.append({'target_source_record_id':r['target_source_record_id'],'year':r['target_year'],'other_accepted_ids':sorted(other)})
receipt={'status':'passed' if not holds else 'held','stage':14,'point_uses_checked':len(p),'both_historical_years_checked':True,'held_rows':holds,'inputs_sha256':{str(p):sha(p) for p in [WORK/'candidate_point_uses.csv',Path(__file__),*s.inputs]}}
(OUT/'both_historical_year_point_collision_audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':receipt['status'],'point_uses_checked':len(p),'held_rows':len(holds)}));assert not holds
