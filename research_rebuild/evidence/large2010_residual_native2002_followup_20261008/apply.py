import sys,json,importlib.util
from pathlib import Path
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
sp=importlib.util.spec_from_file_location('finite',R/'research_rebuild/evidence/working_full_chain_20261007/replay_additional_native_20261008.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
def apply(state):
 receipt=json.loads((O/'application_receipt.json').read_text())
 for p,h in receipt['input_pins'].items():assert sha(Path(p))==h,p
 for p,h in receipt['output_pins'].items():assert sha(O/p)==h,p
 assert state.metrics()==receipt['before'];assert fm.finite(state)==receipt['before_finite_all3_all_points']
 old=state.obs[['source_record_id','population','population_value_quality','settlement_name','settlement_type']].copy()
 state.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv'])
 assert state.metrics()==receipt['after'];assert fm.finite(state)==receipt['after_finite_all3_all_points'];assert old.equals(state.obs[old.columns])
 return state
if __name__=='__main__':
 state=apply(load(46));receipt=json.loads((O/'application_receipt.json').read_text());receipt['State_API_replay_passed']=True;receipt['status']='Frozen actual46 source/output pins and independent State API finite/full3 replay passed';(O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({'accepted_cases':receipt['accepted_cases'],'net':receipt['net_finite_all3_all_points'],'State_API_replay_passed':True},ensure_ascii=False))
