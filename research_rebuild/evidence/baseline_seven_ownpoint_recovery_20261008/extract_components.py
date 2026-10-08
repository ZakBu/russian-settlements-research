import sys,json,importlib.util
from pathlib import Path
import pandas as pd
Z=Path(__file__).resolve().parent;sys.path.insert(0,str(Z.parents[1]/'mass_linkage'))
from working_state_20261007 import load
s=load(55);d=pd.read_csv(Z.parent/'baseline_fullraw_point_code_conflict_scan_20261008/seven_full3_current_carrier_binding_conflicts.csv');out=[]
for r in d.itertuples():
 g=s.obs[s.obs.root.eq(s.uf.find(r.source_record_id))]; print(g.to_string(index=False)); out.append({'carrier':r.source_record_id,'observations':g.to_dict('records'),'points':{sid:s.point_rows.get(sid) for sid in g.source_record_id}})
(Z/'active_seven_components.json').write_text(json.dumps(out,ensure_ascii=False,default=str,indent=2));print('DONE',flush=True)
