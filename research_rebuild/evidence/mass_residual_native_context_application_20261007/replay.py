import sys,json
from pathlib import Path
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
s=load(stage=19);r=json.loads((OUT/'application_receipt.json').read_text());assert s.metrics()==r['before']
s.add_deltas([OUT/'accepted_identity_edge_delta.csv'],[OUT/'accepted_point_use_delta.csv']);assert s.metrics()==r['after'];r['disk_replay_stage19_plus_accepted_delta_metrics_verified']=True;r['outputs']={p.name:sha(p) for p in OUT.glob('*.csv')};(OUT/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('Stage19 +18 edge/23 point delta disk replay matches receipt.')
