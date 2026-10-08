"""Reproduce the12 coordinate-only repairs from explicit stage25."""
from pathlib import Path
import sys,json,hashlib
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
P=Path(__file__).parent
if __name__=='__main__':
 r=json.loads((P/'application_receipt.json').read_text())
 for n,h in r['outputs'].items():assert hashlib.sha256((P/n).read_bytes()).hexdigest()==h,n
 s=load(25);before=s.metrics()
 s.reject_point_uses(P/'accepted_point_rejection_delta.csv')
 s.add_deltas(point_paths=[P/'accepted_point_use_delta.csv']);after=s.metrics()
 staged=json.loads((P/'ordinary_repair_staging_receipt.json').read_text())
 assert before==staged['legacy_per_record_metrics_before']
 assert after==staged['legacy_per_record_metrics_after']
 print(json.dumps({'status':'passed','before':before,'after':after}))
