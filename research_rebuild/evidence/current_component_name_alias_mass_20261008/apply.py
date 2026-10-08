import json,sys,importlib.util
from pathlib import Path
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
sp=importlib.util.spec_from_file_location('fm',R/'research_rebuild/evidence/working_full_chain_20261007/replay_additional_native_20261008.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
def apply(s):
 r=json.loads((O/'application_receipt.json').read_text())
 for p,h in r['input_pins'].items():assert sha(Path(p))==h,p
 for p,h in r['output_pins'].items():assert sha(O/p)==h,p
 assert s.metrics()==r['before'];assert fm.finite(s)==r['before_finite_all3_all_points'];cols=['source_record_id','population','population_value_quality','settlement_name','settlement_type'];protected=s.obs[cols].copy()
 s.add_deltas([O/'accepted_identity_edge_delta.csv.gz'],[O/'accepted_point_use_delta.csv.gz'])
 assert s.metrics()==r['after'];assert fm.finite(s)==r['after_finite_all3_all_points'];assert protected.equals(s.obs[cols]);return s
if __name__=='__main__':
 s=apply(load(55));r=json.loads((O/'application_receipt.json').read_text());r.update(status='Frozen actual55 source/output pins and independent State API finite/full3 replay passed',State_API_replay_passed=True);(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({'accepted_cases':r['accepted_cases'],'net':r['net_finite_all3_all_points'],'State_API_replay_passed':True},ensure_ascii=False))
