"""Replay the authorized native-code/context extension from explicit stage 24."""
from pathlib import Path
import json,sys
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
O=Path(__file__).parent

def apply(state):
    receipt=json.loads((O/'application_receipt.json').read_text())
    for name,pin in receipt['output_pins'].items():assert sha(O/name)==pin
    assert state.metrics()==receipt['before']
    state.add_deltas(edge_paths=[O/'accepted_identity_edge_delta.csv'],point_paths=[O/'accepted_point_use_delta.csv'])
    assert state.metrics()==receipt['after']
    return state

if __name__=='__main__':
    s=apply(load(24))
    receipt=json.loads((O/'application_receipt.json').read_text());receipt['State_API_replay_passed']=True
    receipt['actual_protected_population_quality_rows']={}
    import pandas as pd
    for sid in pd.read_csv(O/'accepted_point_use_delta.csv').target_source_record_id:
        r=s.by_id.loc[sid];receipt['actual_protected_population_quality_rows'][sid]={'population':None if pd.isna(r.population) else float(r.population),'quality':str(r.population_value_quality)}
    (O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps(s.metrics(),ensure_ascii=False))
