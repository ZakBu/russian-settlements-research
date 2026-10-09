"""One bounded State API application on certified68 snapshots; preserve raw counts."""
from pathlib import Path
import sys,json,math,time,hashlib
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]; E=ROOT/'research_rebuild/evidence'; M=ROOT/'research_rebuild/mass_linkage'
OUT=E/'main_axis_residual_application70_south_20261009'; OUT.mkdir(exist_ok=True)
BASE=E/'main_axis_residual_application68_20261008'
sys.path.insert(0,str(M)); sys.path.insert(0,str(BASE))
from current_chain_state_20261007 import State,sha,distance_km
from build_long_table import UnionFind,ACCEPTED_COORDINATE_STATUSES,ACCEPTED_EDGE_STATUSES
from hydrate_point_snapshot import hydrate_active_point_rows

def main():
    started=time.monotonic(); pins={}
    def pin(p,expected=None):
        p=Path(p); h=sha(p)
        if expected: assert h==expected,(str(p),h,expected)
        pins[str(p)]={'sha256':h,'bytes':p.stat().st_size};return p
    baseline=json.loads(pin(BASE/'application_receipt.json').read_text())
    assert baseline['intended_working_stage']==68 and baseline['canonical_State_API_replay_passed']
    for name in ['applied_state_observations.parquet','applied_component_snapshot.csv.gz','applied_point_snapshot.parquet','applied_primary_credited_UID_roster.csv.gz']:
        pin(BASE/name,baseline['output_pins'][name]['sha256'])
    packets=[E/'next69_lifecycle_points_20261009/version2',E/'next69_temporal_20261009']
    for packet in packets:
        sourcepins=json.loads(pin(packet/'source_pins.json').read_text())
        for path,record in sourcepins.items():pin(record.get('path',path) if isinstance(record,dict) else path,record['sha256'] if isinstance(record,dict) else record)
    eventfolder=E/'next69_event_mass_20261009'
    eventreceipt=json.loads(pin(eventfolder/'packet_receipt.json').read_text())
    for path,h in eventreceipt['input_pins'].items():pin(path,h)
    for name,h in eventreceipt['output_pins'].items():pin(eventfolder/name,h)
    review=E/'next69_independent_check_20261009/review_receipt_v2.json'
    approval=json.loads(pin(review).read_text());assert approval['application_approved'],approval
    state=State.__new__(State);state.obs=pd.read_parquet(BASE/'applied_state_observations.parquet');original=state.obs.copy(deep=True)
    state.by_id=state.obs.set_index('source_record_id',drop=False);state.inputs=[]
    c=pd.read_csv(BASE/'applied_component_snapshot.csv.gz',dtype=str,keep_default_na=False)
    state.uf=UnionFind(state.obs.source_record_id)
    for root,group in c.groupby('root'):
        for sid in group.source_record_id:state.uf.union(root,sid)
    assert dict(zip(c.source_record_id,c.root))=={sid:state.uf.find(sid) for sid in state.obs.source_record_id}
    state.years={root:set(map(int,group)) for root,group in state.obs.groupby('root').census_year}
    state.point_rows,hydration=hydrate_active_point_rows(BASE/'applied_point_snapshot.parquet',ACCEPTED_COORDINATE_STATUSES)
    state.point_alternatives=[];state.conflicting_point_targets=set()
    assert len(state.point_rows)==446155 and state.metrics()==baseline['after_State_metrics']
    prev=E/'main_axis_residual_application69_20261009'
    state.add_deltas(edge_paths=[pin(prev/'accepted_identity_edge_delta.csv.gz')],point_paths=[pin(prev/'accepted_point_use_delta.csv.gz')])
    tula=E/'main_axis_residual_application70_tula_20261009'
    state.add_deltas(edge_paths=[pin(tula/'accepted_identity_edge_delta.csv')],point_paths=[pin(tula/'accepted_point_use_delta.csv')])
    packet=E/'over1000_south_20261009'
    for f in packet.iterdir():
        if f.is_file():pin(f)
    rejection=pd.read_csv(packet/'reviewed_identity_edge_rejection.csv').iloc[0]
    pin(rejection.origin_ledger_path,rejection.origin_ledger_sha256)
    members={sid for sid in state.obs.source_record_id if state.uf.find(sid)==state.uf.find(rejection.from_source_record_id)}
    assert members=={rejection.from_source_record_id,rejection.to_source_record_id},members
    oldroot=state.uf.find(rejection.from_source_record_id);state.years.pop(oldroot)
    for sid in members:
        state.uf.parent[sid]=sid;state.years[sid]={int(state.by_id.loc[sid,'census_year'])}
    rejpoint=pd.read_csv(packet/'point_use_rejections.csv.gz').iloc[0]
    sid=rejpoint.target_source_record_id;active=state.point_rows[sid]
    assert (active['latitude'],active['longitude'])==(float(rejpoint.latitude),float(rejpoint.longitude))
    normalized=pd.DataFrame([{'target_source_record_id':sid,'rejection_status':'reviewed_rejected_coordinate_claim_only','old_latitude':active['latitude'],'old_longitude':active['longitude'],'origin_ledger':active['point_ledger_path'],'origin_ledger_sha256':sha(Path(active['point_ledger_path']))}])
    normalized.to_csv(OUT/'accepted_point_rejections.csv',index=False)
    state.reject_point_uses(OUT/'accepted_point_rejections.csv')
    edges=pd.read_csv(packet/'accepted_identity_edge_delta.csv.gz',keep_default_na=False)
    points=pd.concat([pd.read_csv(packet/'accepted_point_use_delta.csv.gz',keep_default_na=False),pd.read_csv(packet/'accepted_former_locality_own_points.csv',keep_default_na=False)],ignore_index=True).fillna('')
    assert points.target_source_record_id.is_unique
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv',index=False);points.to_csv(OUT/'accepted_point_use_delta.csv',index=False)
    state.add_deltas(edge_paths=[OUT/'accepted_identity_edge_delta.csv'],point_paths=[OUT/'accepted_point_use_delta.csv'])
    pd.testing.assert_frame_equal(original.drop(columns='root'),state.obs.drop(columns='root'))
    oldids=set(pd.read_csv(BASE/'applied_primary_credited_UID_roster.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(prev/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(tula/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)
    all3={root for root,years in state.years.items() if years=={2002,2010,2021}}
    for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None):
        if sid not in state.point_rows or pd.isna(pop) or not math.isfinite(float(pop)):all3.discard(state.uf.find(sid))
    ordinary=state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((state.obs.census_year==2021)&state.obs.region_norm.eq('крым'))].copy()
    eventids=set(pd.read_csv(packet/'accepted_direct_event_native_credit_union.csv').source_record_id)|set(pd.read_csv(packet/'new_Duchi_actual_available_year_event.csv').source_record_id)
    assert all(sid in state.point_rows for sid in eventids)
    new=ordinary[(ordinary.root.isin(all3)|ordinary.source_record_id.isin(eventids))&~ordinary.source_record_id.isin(oldids)].copy()
    overlay=pd.read_csv(pin(ROOT/'publication/stage68/applied_primary_population_source_overlay_2010.csv.gz')).set_index('original_source_record_id')
    ordinary['effective_population']=ordinary.population
    for idx,r in ordinary[ordinary.census_year.eq(2010)].iterrows():
        if r.source_record_id in overlay.index:ordinary.loc[idx,'effective_population']=overlay.loc[r.source_record_id,'population']
    new=ordinary[ordinary.source_record_id.isin(new.source_record_id)].copy()
    new.to_csv(OUT/'actual_new_primary_native_UIDs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    ids=oldids|set(new.source_record_id)
    rem=ordinary[~ordinary.source_record_id.isin(ids)&((ordinary.population>1000)|(ordinary.effective_population>1000))].copy()
    rem.to_csv(OUT/'remaining_over1000_raw_or_primary.csv',index=False)
    previous=json.loads((tula/'application_receipt.json').read_text())
    gains={str(int(y)):int(g.effective_population.sum()) for y,g in new.groupby('census_year')}
    after={}
    for y,v in previous['effective_primary_coverage'].items():
        n=v['population']+gains.get(y,0);after[y]={'population':n,'control':v['control'],'coverage_percent':100*n/v['control'],'remaining':v['control']-n}
    receipt={'working_stage':'70_south_increment','status':'actual_State_API_applied','new_identity_edges':len(edges),'new_point_uses':len(points),'new_primary_UIDs':len(new),'effective_population_gain':gains,'effective_primary_coverage':after,'remaining_over1000_source_year_records':len(rem),'remaining_by_year':{str(int(y)):len(g) for y,g in rem.groupby('census_year')},'raw_population_unchanged':True,'absent_years_not_zero':True,'source_packet_erratum':'None; exact rejected Duchi identity component split and only new southern Duchi wrong point rejected; old northern point retained','input_pins':pins,'wall_seconds':round(time.monotonic()-started,3)}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='input_pins'},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
