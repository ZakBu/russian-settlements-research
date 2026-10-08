from pathlib import Path
import sys,json
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
A=Path(__file__).parent/'application';rec=json.loads((A/'application_receipt.json').read_text())
for p,h in rec['input_hashes'].items():assert sha(Path(p))==h,p
for p,h in rec['outputs'].items():assert sha(A/p)==h,p
s=load(28);before=s.metrics();assert before==rec['before'];s.add_deltas([A/'accepted_identity_edge_delta.csv'],[A/'accepted_point_use_delta.csv']);after=s.metrics();assert after==rec['after']
v={'status':'explicit_stage28_loader_replay_and_input_output_pins_verified','application_receipt_sha256':sha(A/'application_receipt.json'),'accepted_identity_edges':rec['accepted_identity_edges'],'accepted_point_uses':rec['accepted_point_uses'],'ordinary_joint_native_population_gain':rec['ordinary_joint_native_population_gain'],'final_mixed_native_union_net':rec['final_mixed_native_union_net'],'source_values_and_population_quality_modified':False};(A/'verification_receipt.json').write_text(json.dumps(v,ensure_ascii=False,indent=2));print(json.dumps(v,ensure_ascii=False))
