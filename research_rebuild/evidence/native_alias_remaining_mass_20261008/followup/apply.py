"""Reproduce native type/context and receivingcore point recovery from actual29."""
import json,sys,importlib.util
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha
O=Path(__file__).parent

def apply(state):
 receipt=json.loads((O/'application_receipt.json').read_text())
 for path,h in receipt['input_pins'].items():assert sha(Path(path))==h,path
 for name,h in receipt['output_pins'].items():assert sha(O/name)==h,name
 assert state.metrics()==receipt['before'],'Frozen actual29 metrics differ'
 state.reject_point_uses(O/'accepted_point_rejection_delta.csv')
 state.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv'])
 assert state.metrics()==receipt['after']
 return state

if __name__=='__main__':
 from working_state_20261007 import load
 s=apply(load(29));print('Actual29, source/output pins, identity/point rejection replay passed')
