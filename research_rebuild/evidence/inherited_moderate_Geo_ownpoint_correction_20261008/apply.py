"""Apply only reviewed old representative-point supersessions to a compatible state."""
import json
from pathlib import Path
O=Path(__file__).parent
def apply(state):
 from current_chain_state_20261007 import sha
 r=json.loads((O/'application_receipt.json').read_text())
 assert r['State_API_replay_passed']
 for p,h in r['input_pins'].items():assert sha(Path(p))==h,p
 for p,h in r['output_pins'].items():assert sha(O/p)==h,p
 cols=['source_record_id','population','population_value_quality','settlement_name','settlement_type','oktmo','okato','root'];protected=state.obs[cols].copy();before=state.metrics()
 state.reject_point_uses(O/'point_use_rejections.csv.gz');state.add_deltas(point_paths=[O/'accepted_point_use_delta.csv.gz'])
 assert protected.equals(state.obs[cols]);assert before==state.metrics();return state
