import sys,json
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
O=Path(__file__).parent
p=O/'accepted_point_use_delta.csv';f=pd.read_csv(p,keep_default_na=False);f['point_claim_quality']='auto_rule';f['historical_coordinate_quality']='inferred_continuity_no_historical_measurement';f['historical_population_boundary_comparability']='unknown';f.to_csv(p,index=False)
p=O/'accepted_identity_edge_delta.csv';f=pd.read_csv(p,keep_default_na=False);f['population_boundary_comparability']='unknown';f['population_quality_preservation']='unchanged_native_source_values_and_quality';f.to_csv(p,index=False)
s=load(30);before=s.metrics();inputs={str(p):sha(p) for p in s.inputs};s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();r={'stage':30,'before':before,'after':after,'marginal':{y:{'population':after[y]['covered_population']-before[y]['covered_population'],'rows':after[y]['covered_rows']-before[y]['covered_rows']} for y in before},'input_hashes':inputs,'frozen29_receipt_path':str(O/'receipt.json'),'frozen29_receipt_sha256':sha(O/'receipt.json'),'accepted_ledger_hashes':{p.name:sha(p) for p in [O/'accepted_identity_edge_delta.csv',O/'accepted_point_use_delta.csv']},'raw_parent_and_literal_audit_not_repeated':True,'code_bound_own_current_point_reused_retrospectively':True,'native_source_values_and_protected_quality_unchanged':True};assert all(r['marginal'][y]==json.load(open(O/'receipt.json'))['marginal'][y] for y in before);(O/'stage30_replay_receipt.json').write_text(json.dumps(r,indent=2,ensure_ascii=False));print(json.dumps(r['marginal']))
