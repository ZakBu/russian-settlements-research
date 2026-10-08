"""Replay the bounded native printed type/context application from frozen stage27."""
import json,sys
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha
O=Path(__file__).parent

def apply(state):
 receipt=json.loads((O/'application_receipt.json').read_text())
 for path,expected in receipt['input_pins'].items():assert sha(Path(path))==expected,path
 for name,expected in receipt['output_pins'].items():assert sha(O/name)==expected,name
 assert state.metrics()==receipt['before'],'Frozen stage27 baseline differs'
 state.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv'])
 assert state.metrics()==receipt['after']
 return state

if __name__=='__main__':
 from working_state_20261007 import load
 s=apply(load(27));print('Source/output pins and frozen27 State API replay passed')
