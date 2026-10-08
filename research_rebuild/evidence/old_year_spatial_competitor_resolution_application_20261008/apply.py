"""Reproduce the authorized spatial native-identity subset from explicit stage 25."""
import json,sys
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
O=Path(__file__).parent

def apply(state):
    receipt=json.loads((O/'application_receipt.json').read_text())
    for name,pin in receipt['output_pins'].items():assert sha(O/name)==pin
    assert state.metrics()==receipt['before'], 'Expected explicit stage 25 baseline'
    state.add_deltas(edge_paths=[O/'accepted_identity_edge_delta.csv'],point_paths=[O/'accepted_point_use_delta.csv'])
    assert state.metrics()==receipt['after']
    return state

if __name__=='__main__':
    state=apply(load(25))
    p=O/'application_receipt.json';receipt=json.loads(p.read_text());receipt['State_API_replay_passed']=True;receipt['status']='Authorized accepted spatial-rule application ready for loader integration; explicit stage 25 State API replay passed'
    receipt['output_hashes']={str(q):sha(q) for q in O.iterdir() if q.is_file() and q.name!='application_receipt.json'}
    p.write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(state.metrics(),ensure_ascii=False))
