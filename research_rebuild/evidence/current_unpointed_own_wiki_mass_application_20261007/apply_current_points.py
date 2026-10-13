"""Replay the root-admitted point packet against explicit stage18."""
import hashlib,json,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km

def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    folder=Path(__file__).resolve().parent
    receipt=json.loads((folder/'application_receipt.json').read_text())
    assert receipt['status']=='applied_current_own_points_and_qualified_secondary_histories'
    for name,h in receipt['outputs'].items():assert digest(folder/name)==h
    state=load(18);assert state.metrics()==receipt['root_baseline_metrics']
    frame=pd.read_csv(folder/'accepted_point_use_delta.csv',keep_default_na=False)
    assert len(frame)==43 and not frame.target_source_record_id.duplicated().any()
    assert not set(frame.target_source_record_id)&set(state.point_rows)
    for r in frame.to_dict('records'):
        sid=r['target_source_record_id'];assert sid in state.by_id.index
        assert int(state.by_id.loc[sid,'census_year'])==int(r['target_year'])
        assert digest(r['point_origin_file'])==r['point_origin_sha256']
        assert -90<=float(r['latitude'])<=90 and -180<=float(r['longitude'])<=180
        root=state.uf.find(sid)
        for other,point in state.point_rows.items():
            if state.uf.find(other)==root:
                assert distance_km((r['latitude'],r['longitude']),(point['latitude'],point['longitude']))<=5
    state.add_deltas(point_paths=[folder/'accepted_point_use_delta.csv'])
    assert state.metrics()==receipt['root_after_metrics']
    print(json.dumps({'status':'root_applied_packet_replay_verified','point_uses':len(frame),'after':state.metrics()},ensure_ascii=False))
if __name__=='__main__':main()
