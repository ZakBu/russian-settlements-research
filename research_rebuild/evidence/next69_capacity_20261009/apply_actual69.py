"""One bounded State API application on certified68 snapshots; preserve raw counts."""
from pathlib import Path
import sys,json,math,time,hashlib
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]; E=ROOT/'research_rebuild/evidence'; M=ROOT/'research_rebuild/mass_linkage'
OUT=E/'main_axis_residual_application69_20261009'; OUT.mkdir(exist_ok=True)
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
    p1=pd.read_csv(pin(packets[0]/'accepted_point_use_delta.csv.gz'),keep_default_na=False)
    p2=pd.read_csv(pin(packets[1]/'accepted_point_use_delta.csv'),keep_default_na=False)
    former=pd.read_csv(eventfolder/'accepted_former_locality_own_points.csv',keep_default_na=False)
    points=pd.concat([p1,p2,former],ignore_index=True).fillna('');assert points.target_source_record_id.is_unique
    edges=pd.read_csv(pin(packets[1]/'accepted_identity_edge_delta.csv'),keep_default_na=False)
    # The preceding Zmanovo row is outside the 2002 county caption. Only the
    # two following in-county flanks and the explicit rival group support admission.
    edges['admission_rule']='Literal major Kuznechikha row under 2002 Kuznechikhinsky county caption, followed by Biserovo and Borisovo; same two following literal 2010 rows. Distinct Glebovsky namesake has different four flanks. Preceding Zmanovo is excluded from county evidence.'
    assert len(points)==280 and len(edges)==1
    assert points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all()
    assert edges.decision_status.isin(ACCEPTED_EDGE_STATUSES).all()
    before_points=set(state.point_rows);assert not before_points.intersection(points.target_source_record_id)
    # Every reuse has an existing accepted own-place donor, not a municipal centre.
    for r in points.to_dict('records'):
        sid=r['target_source_record_id'];donor=r['coordinate_source_record_id']
        if sid in set(former.target_source_record_id):
            assert r['own_locality_point'] and not r['recipient_point_assigned_to_child']
            continue
        assert donor in before_points
        assert (float(r['latitude']),float(r['longitude']))==(state.point_rows[donor]['latitude'],state.point_rows[donor]['longitude'])
        if sid in set(p1.target_source_record_id):assert state.uf.find(sid)==state.uf.find(donor)
        for member in c.loc[c.root.eq(state.uf.find(sid)),'source_record_id']:
            if member in before_points:assert distance_km((float(r['latitude']),float(r['longitude'])),(state.point_rows[member]['latitude'],state.point_rows[member]['longitude']))<=5
    for r in edges.to_dict('records'):
        a,b=r['from_source_record_id'],r['to_source_record_id']
        assert not state.years[state.uf.find(a)].intersection(state.years[state.uf.find(b)])
    pointpath=OUT/'accepted_point_use_delta.csv.gz';edgepath=OUT/'accepted_identity_edge_delta.csv.gz'
    points.to_csv(pointpath,index=False,compression={'method':'gzip','mtime':0});edges.to_csv(edgepath,index=False,compression={'method':'gzip','mtime':0})
    state.add_deltas(edge_paths=[edgepath],point_paths=[pointpath])
    pd.testing.assert_frame_equal(original.drop(columns='root'),state.obs.drop(columns='root'))
    assert len(state.point_rows)==446435 and set(state.point_rows)==before_points|set(points.target_source_record_id)
    credited=pd.read_csv(BASE/'applied_primary_credited_UID_roster.csv.gz',usecols=['source_record_id']);oldids=set(credited.source_record_id)
    all3={root for root,years in state.years.items() if years=={2002,2010,2021}}
    for sid in state.obs.source_record_id:
        if sid not in state.point_rows:all3.discard(state.uf.find(sid))
    for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None):
        if pd.isna(pop) or not math.isfinite(float(pop)):all3.discard(state.uf.find(sid))
    ordinary=state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((state.obs.census_year==2021)&state.obs.region_norm.eq('крым'))]
    new=ordinary[ordinary.root.isin(all3)&~ordinary.source_record_id.isin(oldids)].copy()
    new_ordinary_roots=set(new.root)
    eventcredits=pd.read_csv(eventfolder/'accepted_direct_event_native_credit_union.csv')
    eventids=set(eventcredits.source_record_id);assert len(eventids)==2 and not eventids&oldids
    eventobs=ordinary[ordinary.source_record_id.isin(eventids)].copy()
    assert len(eventobs)==2 and eventobs.census_year.eq(2002).all() and int(eventobs.population.sum())==5669
    assert not eventids&set(new.source_record_id)
    new=pd.concat([new,eventobs],ignore_index=True)
    assert not set(new.source_record_id)&oldids
    overlaypath=pin(ROOT/'publication/stage68/applied_primary_population_source_overlay_2010.csv.gz')
    overlay=pd.read_csv(overlaypath);ov=overlay.set_index('original_source_record_id')
    new['effective_population']=new.population
    for idx,row in new[new.census_year.eq(2010)].iterrows():
        if row.source_record_id in ov.index:
            source=ov.loc[row.source_record_id];assert float(source.original_population)==float(row.population)
            new.loc[idx,'effective_population']=source.population
    gain={str(int(y)):int(g.effective_population.sum()) for y,g in new.groupby('census_year')}
    rawgain={str(int(y)):int(g.population.sum()) for y,g in new.groupby('census_year')}
    current=json.loads(pin(ROOT/'publication/stage68/current_primary_coverage_receipt.json').read_text())
    print('baseline effective receipt schema',list(current))
    new.to_csv(OUT/'actual_new_primary_native_UIDs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    common={2002:145166731,2010:142856536,2021:144699673};before={2002:144117690,2010:141787299,2021:144013793}
    after={str(y):{'population':before[y]+gain.get(str(y),0),'control':common[y],'coverage_percent':100*(before[y]+gain.get(str(y),0))/common[y],'remaining':common[y]-before[y]-gain.get(str(y),0)} for y in common}
    receipt={'status':'actual_State_API_applied_source_values_unchanged','working_stage':69,'baseline_stage':68,'new_identity_edges':len(edges),'new_point_uses':len(points),'new_full3_histories':len(new_ordinary_roots),'new_typed_inclusion_cases':2,'typed_inclusion_population_gain':{'2002':5669,'2010':0,'2021':0},'new_primary_UIDs':len(new),'raw_primary_population_gain':rawgain,'effective_primary_population_gain':gain,'effective_primary_coverage':after,'before_State_metrics':baseline['after_State_metrics'],'after_State_metrics':state.metrics(),'point_hydration':hydration,'raw_observation_fields_unchanged':True,'no_lost_primary_UIDs':True,'population_quality_not_promoted':True,'source2010_shortfall_unchanged':300190,'input_pins':pins,'wall_seconds':round(time.monotonic()-started,3)}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt['effective_primary_coverage'],indent=2),flush=True)
    # Small ordinary export delta; preserve the existing unknown-count exclusion.
    import importlib.util
    spec=importlib.util.spec_from_file_location('export69',E/'working_full_chain_20261007/export_full3.py');ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    exportdir=OUT/'wide_delta';exportdir.mkdir(exist_ok=True);ex.DEST=exportdir
    roots=new_ordinary_roots;unknownroots={state.uf.find(sid) for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(pop) and state.years[state.uf.find(sid)]=={2002,2010,2021}}
    subset=ordinary[ordinary.root.isin(roots|unknownroots)];ids=set(subset.source_record_id)&set(state.point_rows)
    state.inputs=[pointpath,edgepath]
    for path in state.inputs:pin(path)
    ex.build(state,subset,ids,69,pins,OUT)
    print('actual69 complete',round(time.monotonic()-started,3),flush=True)

if __name__=='__main__':main()
