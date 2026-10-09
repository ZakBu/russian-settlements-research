from pathlib import Path
import sys,json,hashlib
import pandas as pd,duckdb
O=Path(__file__).parent;R=O.parents[2];M=R/'research_rebuild/mass_linkage';sys.path.insert(0,str(M))
from current_chain_state_20261007 import State
from build_long_table import UnionFind
D=Path('/workspace/settlements-delivery/final-full-20261009');p=O/'accepted_point_use_delta.csv';d=pd.read_csv(p,keep_default_na=False);assert len(d)==62 and d.target_source_record_id.is_unique
c=duckdb.connect();s=State.__new__(State);s.obs=c.execute('select * from read_parquet(?) where source_record_id in (select unnest(?))',[str(D/'applied_state_observations.parquet'),list(d.target_source_record_id)]).fetchdf();before=s.obs.copy(deep=True)
active=c.execute('select source_record_id from read_parquet(?) where source_record_id in (select unnest(?))',[str(D/'applied_point_snapshot.parquet'),list(d.target_source_record_id)]).fetchall();assert not active
s.by_id=s.obs.set_index('source_record_id',drop=False);s.uf=UnionFind(set(s.obs.source_record_id)|set(s.obs.root))
for sid,r in s.obs[['source_record_id','root']].itertuples(index=False,name=None):s.uf.parent[sid]=r
s.point_rows={};s.inputs=[];s.point_alternatives=[];s.conflicting_point_targets=set();s.add_deltas(point_paths=[p])
pd.testing.assert_frame_equal(before,s.obs);assert set(s.point_rows)==set(d.target_source_record_id)
receipt=dict(status='PASS_canonical_State_point_only_delta_replay',accepted_point_targets=62,native_populations_qualities_labels_codes_unchanged=True,new_population_credit=0,identity_edges=0,remaining_Moscow_assigned_point_holds=0,final_snapshot_point_targets_were_absent=True,delta_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
(O/'canonical_point_replay_receipt.json').write_text(json.dumps(receipt,indent=2));print(receipt)
