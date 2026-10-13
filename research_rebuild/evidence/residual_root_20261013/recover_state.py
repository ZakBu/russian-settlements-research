"""Recover the frozen application15 from verified stage71 without old local caches.

Unchanged point metadata stays in its immutable published snapshot. The in-memory
State uses core point fields for graph application; full point export preserves
unchanged original rows. Prior rejected claim evidence is not re-admitted.
"""
from pathlib import Path
import csv, hashlib, json, sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
sys.path.insert(0,str(ROOT/'research_rebuild/evidence/over500_root_20261009'))
from current_chain_state_20261007 import State
from build_long_table import UnionFind, ACCEPTED_COORDINATE_STATUSES
from apply_packets import append_reviewed_observations, apply_reviewed_component_partitions
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def recover():
    base=ROOT/'publication/stage71';r=ROOT/'research_rebuild/evidence/over500_root_20261009'
    assets={x['name']:x for x in json.loads((base/'release-assets-manifest.json').read_text())['assets']}
    for n in ['applied_state_observations.parquet','applied_component_snapshot.csv.gz','applied_point_snapshot.parquet']:
        assert sha(base/n)==assets[n]['sha256'] and (base/n).stat().st_size==assets[n]['bytes']
    s=State.__new__(State);s.obs=pd.read_parquet(base/'applied_state_observations.parquet');s.by_id=s.obs.set_index('source_record_id',drop=False)
    assert s.obs.source_record_id.is_unique
    roots=pd.read_csv(base/'applied_component_snapshot.csv.gz',keep_default_na=False)
    assert set(roots.source_record_id)==set(s.obs.source_record_id)
    s.uf=UnionFind(s.obs.source_record_id);s.uf.parent=dict(zip(roots.source_record_id,roots.root));s.years={}
    for sid,yr in zip(s.obs.source_record_id,s.obs.census_year):s.years.setdefault(s.uf.find(sid),set()).add(int(yr))
    assert s.obs.root.tolist()==[s.uf.find(x) for x in s.obs.source_record_id]
    core=['source_record_id','target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path']
    import pyarrow.parquet as pq
    cols=[x for x in core if x in pq.ParquetFile(base/'applied_point_snapshot.parquet').schema.names]
    p=pd.read_parquet(base/'applied_point_snapshot.parquet',columns=cols).fillna('')
    s.point_rows={}
    for row in p.to_dict('records'):
        sid=row.pop('source_record_id');assert row['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES;s.point_rows[sid]=row
    s.point_alternatives=[];s.conflicting_point_targets=set();s.inputs=[base/'applied_state_observations.parquet',base/'applied_point_snapshot.parquet']
    recipe=json.loads((r/'fifteenth_recipe.json').read_text());receipt=json.loads((r/'fifteenth_application_receipt.json').read_text());pins=receipt['input_pins']
    for ps in recipe.values():
        for rel in ps:
            path=ROOT/rel
            recorded=pins.get(str(path))
            if recorded is None:recorded=next(v for k,v in pins.items() if k.endswith('/'+rel))
            assert sha(path)==recorded['sha256'] and path.stat().st_size==recorded['bytes']
    def paths(k):return [ROOT/x for x in recipe.get(k,[])]
    append_reviewed_observations(s,paths('observations'));apply_reviewed_component_partitions(s,paths('component_partitions'))
    unavailable=[];rejected=set()
    for path in paths('point_rejections'):
        for row in csv.DictReader(path.open()):
            sid=row['target_source_record_id'];old=s.point_rows[sid]
            assert row['rejection_status'] in {'reviewed_rejected_coordinate_claim_only','reviewed_superseded_representative_point_only'}
            assert (float(old['latitude']),float(old['longitude']))==(float(row['old_latitude']),float(row['old_longitude']))
            assert old['point_ledger_path']==row['origin_ledger']
            ledger=Path(row['origin_ledger'])
            if ledger.is_file():assert sha(ledger)==row['origin_ledger_sha256']
            else:unavailable.append(dict(target_source_record_id=sid,origin_ledger=str(ledger),previously_recorded_sha256=row['origin_ledger_sha256'],prior_admission_reopened=False,replayed_frozen_rejection_packet_sha256=sha(path)))
            del s.point_rows[sid];rejected.add(sid)
    s.add_deltas(edge_paths=paths('edges'),point_paths=paths('points'))
    q=pd.read_csv(r/'applied_over500_working_checkpoint.csv.gz',keep_default_na=False,low_memory=False)
    now=s.obs.set_index('source_record_id')
    for row in q.to_dict('records'):
        sid=row['source_record_id'];assert now.loc[sid,'root']==row['root'];assert float(now.loc[sid,'population'])==float(row['population'])
        assert (sid in s.point_rows)==(str(row['has_ownpoint']).lower()=='true')
        if sid in s.point_rows:
            assert (float(s.point_rows[sid]['latitude']),float(s.point_rows[sid]['longitude']))==(float(row['accepted_ownpoint_latitude']),float(row['accepted_ownpoint_longitude']))
    assert len(s.obs)==465929 and len(s.point_rows)==447362
    metadata={'recovery_status':'verified_against_frozen_application15','native_observations':len(s.obs),'active_points':len(s.point_rows),'threshold_current_rows_checked':len(q),'unavailable_rejected_historical_ledger_caches':unavailable,'core_points_only_in_memory':True,'unchanged_full_point_metadata_preserved_in_published_snapshot':True}
    return s,metadata,recipe,rejected
def export_points(state,recipe,rejected,path,extra_point_paths=()):
    # Full sparse metadata of unchanged baseline rows is retained byte-value-wise;
    # newly accepted and superseding rows retain their own packet metadata.
    base=ROOT/'publication/stage71/applied_point_snapshot.parquet'
    import duckdb
    con=duckdb.connect(config={'threads':2,'memory_limit':'2GB'})
    changed=set(rejected)
    for rel in recipe['points']:changed.update(pd.read_csv(ROOT/rel,usecols=['target_source_record_id']).target_source_record_id)
    for p in extra_point_paths:changed.update(pd.read_csv(p,usecols=['target_source_record_id']).target_source_record_id)
    delta=pd.DataFrame([dict(state.point_rows[sid],source_record_id=sid) for sid in sorted(changed) if sid in state.point_rows])
    removed=pd.DataFrame({'source_record_id':sorted(changed)})
    con.register('delta',delta);con.register('removed',removed)
    con.execute('CREATE TABLE fullpoints AS SELECT b.* FROM read_parquet(?) b ANTI JOIN removed USING(source_record_id) UNION ALL BY NAME SELECT * FROM delta',[str(base)])
    assert con.execute('SELECT count(*), count(DISTINCT source_record_id) FROM fullpoints').fetchone()==(len(state.point_rows),len(state.point_rows))
    con.execute("COPY fullpoints TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",[str(path)])
    con.close()
if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    s,meta,recipe,rejected=recover();s.obs.to_parquet(out/'applied_state_observations.parquet',index=False)
    export_points(s,recipe,rejected,out/'applied_point_snapshot.parquet')
    (out/'recovery_receipt.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta,indent=2))
