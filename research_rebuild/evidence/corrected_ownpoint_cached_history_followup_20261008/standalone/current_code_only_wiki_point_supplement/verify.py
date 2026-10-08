import sys,json,importlib.util,hashlib
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;P=O.parent.parent;sys.path.insert(0,str(P));sys.path.insert(0,'/workspace/russian-settlements-research/research_rebuild/mass_linkage')
import current_chain_state_20261007 as m
orig=m.sha;cache={}
def sha(p):
 p=Path(p);st=p.stat();k=(str(p),st.st_size,st.st_mtime_ns)
 if k not in cache:cache[k]=orig(p)
 return cache[k]
m.sha=sha
from frozen_working_state58 import load
s=load(58);s.reject_point_uses(P/'point_use_rejections.csv.gz');s.add_deltas(point_paths=[P/'accepted_point_use_delta.csv.gz']);sp=importlib.util.spec_from_file_location('ff',P.parent/'native_singleton_rural_mass_20261008/frozen_finite.py');ff=importlib.util.module_from_spec(sp);sp.loader.exec_module(ff);before=ff.finite(s);graph={i:s.uf.find(i) for i in s.by_id.index};protected=s.obs[['source_record_id','population','population_value_quality']].copy();s.add_deltas(point_paths=[O/'accepted_point_use_delta.csv.gz']);after=ff.finite(s);assert graph=={i:s.uf.find(i) for i in s.by_id.index};pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);r={'status':'PASS fresh State58 plus frozen59 plus supplement StateAPI replay','before':before,'after':after,'net_finite_population_by_year':{y:after['populations_by_year'][y]-before['populations_by_year'][y] for y in before['populations_by_year']},'raw_population_and_identity_unchanged':True,'input_pins':{str(p):sha(p) for p in [*s.inputs,P/'frozen_asset_manifest.json',O/'accepted_point_use_delta.csv.gz',O/'verify.py',O/'accept.py',O/'scan.py']}};(O/'independent_replay_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'}))
