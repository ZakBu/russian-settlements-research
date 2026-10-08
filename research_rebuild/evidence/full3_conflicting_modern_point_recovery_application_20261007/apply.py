"""Reproduce the authorized coordinate-only extension from explicit stage 23."""
import json,sys
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
O=Path(__file__).parent

def apply(state):
    receipt=json.loads((O/'application_receipt.json').read_text())
    for name,value in receipt['output_pins'].items():
        assert sha(O/name)==value, name
    before=state.metrics()
    assert before==receipt['before'], 'Expected explicit stage 23 baseline'
    state.reject_point_uses(O/'accepted_point_rejection_delta.csv')
    state.add_deltas(point_paths=[O/'accepted_point_use_delta.csv'])
    assert state.metrics()==receipt['after']
    return state

if __name__=='__main__':
    s=apply(load(23))
    print(json.dumps(s.metrics(),ensure_ascii=False,indent=2))
