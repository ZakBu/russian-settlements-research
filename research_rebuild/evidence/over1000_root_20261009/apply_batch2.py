"""One bounded State API application on certified68 snapshots; preserve raw counts."""
from pathlib import Path
import sys,json,math,time,hashlib
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]; E=ROOT/'research_rebuild/evidence'; M=ROOT/'research_rebuild/mass_linkage'
OUT=E/'main_axis_residual_application70_batch2_20261009'; OUT.mkdir(exist_ok=True)
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
    south=E/'main_axis_residual_application70_south_20261009'
    packet=E/'over1000_south_20261009/version2'
    manifest=json.loads(pin(packet/'manifest.json').read_text())
    for name,v in manifest['files'].items():pin(packet/name,v['sha256'])
    edges=pd.read_csv(packet/'accepted_identity_edge_delta.csv.gz',keep_default_na=False)
    points=pd.concat([pd.read_csv(packet/'accepted_point_use_delta.csv.gz',keep_default_na=False),pd.read_csv(packet/'accepted_former_locality_own_points.csv',keep_default_na=False)],ignore_index=True).fillna('')
    edges.to_csv(OUT/'accepted_identity_edge_delta_v2.csv',index=False);points.to_csv(OUT/'accepted_point_use_delta_v2.csv',index=False)
    state.add_deltas(edge_paths=[OUT/'accepted_identity_edge_delta_v2.csv'],point_paths=[OUT/'accepted_point_use_delta_v2.csv'])
    southv2=E/'main_axis_residual_application70_southv2_20261009'
    packet=E/'over1000_bash_amur_20261009/version3'
    manifest=json.loads(pin(packet/'freeze_manifest.json').read_text())
    for v in manifest['pins']:pin(ROOT/v['path'],v['sha256'])
    edges=pd.read_csv(packet/'accepted_identity_edge_delta.csv',keep_default_na=False)
    conflicts=[]; admitted=[]
    for row in edges.to_dict('records'):
        try: state.union(row['from_source_record_id'],row['to_source_record_id']); admitted.append(row)
        except ValueError as exc: conflicts.append(dict(row,root_application_conflict=str(exc)))
    if conflicts:
        pd.DataFrame(conflicts).to_csv(OUT/'held_identity_edges_actual_conflicts.csv',index=False)
        print('EXCLUDED_CONFLICTS',[(r['from_source_record_id'],r['to_source_record_id']) for r in conflicts],flush=True)
    edges=pd.DataFrame(admitted)
    points=pd.read_csv(packet/'accepted_point_use_delta.csv',keep_default_na=False)
    blocked={r['from_source_record_id'] for r in conflicts}|{r['to_source_record_id'] for r in conflicts}
    points=points[~points.target_source_record_id.isin(blocked)]
    edges.to_csv(OUT/'accepted_identity_edge_delta_bash.csv',index=False);points.to_csv(OUT/'accepted_point_use_delta_bash.csv',index=False)
    state.add_deltas(edge_paths=[OUT/'accepted_identity_edge_delta_bash.csv'],point_paths=[OUT/'accepted_point_use_delta_bash.csv'])
    bash=E/'main_axis_residual_application70_bash_amur_20261009'
    packet=E/'over1000_moscow_20261009'
    manifest=json.loads(pin(packet/'FINAL_manifest.json').read_text())
    for f in packet.iterdir():
        if f.is_file():pin(f)
    pin(E/'over1000_crosscheck_moscow_20261009/receipt.json')
    rejected=pd.read_csv(packet/'accepted_identity_edge_rejection_delta.csv',keep_default_na=False)
    a=rejected.iloc[0]['from_source_record_id'];root=state.uf.find(a)
    members={sid for sid in state.obs.source_record_id if state.uf.find(sid)==root}
    assert len(members)==3 and {int(state.by_id.loc[sid,'census_year']) for sid in members}=={2002,2010,2021}
    lostids={sid for sid in members if int(state.by_id.loc[sid,'census_year'])!=2010}
    assert sorted(state.by_id.loc[list(lostids),'population'].tolist())==[1,2]
    state.years.pop(root)
    for sid in members:state.uf.parent[sid]=sid;state.years[sid]={int(state.by_id.loc[sid,'census_year'])}
    state.union(*sorted(lostids))
    pointreject=pd.read_csv(packet/'accepted_point_rejection_delta.csv',keep_default_na=False)
    normalized=[]
    for row in pointreject.to_dict('records'):
        sid=row['target_source_record_id'];active=state.point_rows[sid]
        assert (active['latitude'],active['longitude'])==(float(row['old_latitude']),float(row['old_longitude']))
        normalized.append(dict(row,origin_ledger=active['point_ledger_path'],origin_ledger_sha256=sha(Path(active['point_ledger_path']))))
    pd.DataFrame(normalized).to_csv(OUT/'accepted_moscow_point_rejections.csv',index=False)
    state.reject_point_uses(OUT/'accepted_moscow_point_rejections.csv')
    edges=pd.concat([pd.read_csv(packet/'accepted_identity_edge_delta.csv',keep_default_na=False),pd.read_csv(packet/'conditional_after_rejection_correct_identity_edges.csv',keep_default_na=False)],ignore_index=True).fillna('')
    points=pd.concat([pd.read_csv(packet/n,keep_default_na=False) for n in ['accepted_point_use_delta.csv','accepted_former_locality_own_points.csv','conditional_after_rejection_correct_point_uses.csv']],ignore_index=True).fillna('')
    assert points.target_source_record_id.is_unique
    edges.to_csv(OUT/'accepted_moscow_identity_edges.csv',index=False);points.to_csv(OUT/'accepted_moscow_point_uses.csv',index=False)
    state.add_deltas(edge_paths=[OUT/'accepted_moscow_identity_edges.csv'],point_paths=[OUT/'accepted_moscow_point_uses.csv'])
    moscow=E/'main_axis_residual_application70_moscow_20261009'
    newedges=[];newpoints=[];newtyped=set();batchconflicts=[]
    folders=[E/'over1000_south_20261009/pervomaysky_followup',E/'over1000_moscow_geonames_continuation_20261009',E/'over1000_moscow_pominovo_event_20261009',E/'over1000_tula_temporal_v4_20261009']
    folders += [p for p in (E/'over1000_rest_B_20261009').glob('version*') if p.name.split('_')[0] in {'version3','version4','version5','version6','version7','version9','version10','version11','version12','version13','version14','version15'}]
    folders += [p for p in (E/'over1000_rest_20261009').glob('A112_v*') if p.name.startswith(('A112_v3_','A112_v4_','A112_v5_','A112_v6_'))]
    involved=set()
    for folder in sorted(folders):
        for f in folder.iterdir():
            if f.is_file():pin(f)
        rejects=[p for p in folder.iterdir() if p.name in {'point_rejections.csv','accepted_point_rejection_delta.csv','accepted_point_rejections.csv'}]
        # A duplicate alone is not evidence against low Stanovoye's location.
        if folder.name.startswith('version4_'):rejects=[]
        for path in rejects:
            z=pd.read_csv(path,keep_default_na=False);norm=[]
            for row in z.to_dict('records'):
                sid=row['target_source_record_id'];old=state.point_rows[sid]
                assert (float(row.get('old_latitude',row.get('latitude'))),float(row.get('old_longitude',row.get('longitude'))))==(old['latitude'],old['longitude'])
                norm.append(dict(row,rejection_status='reviewed_rejected_coordinate_claim_only',origin_ledger=old['point_ledger_path'],origin_ledger_sha256=sha(Path(old['point_ledger_path']))))
            if not norm:continue
            out=OUT/(folder.name+'_point_rejection.csv');pd.DataFrame(norm).to_csv(out,index=False);state.reject_point_uses(out)
        edgefiles=[p for p in folder.iterdir() if p.suffix=='.csv' and (p.name=='accepted_identity_edge_delta.csv' or 'edge_candidate' in p.name)]
        if (folder/'accepted_identity_edge_delta.csv.gz').exists():edgefiles.append(folder/'accepted_identity_edge_delta.csv.gz')
        for path in edgefiles:
            for row in pd.read_csv(path,keep_default_na=False).to_dict('records'):
                assert row.get('relation')=='same_place'
                row['decision_status']='checked_rule_accepted';row['root_review_evidence_packet']=str(folder)
                a,b=row['from_source_record_id'],row['to_source_record_id']
                try:state.union(a,b)
                except ValueError as ex:batchconflicts.append(dict(row,root_conflict=str(ex)));continue
                newedges.append(row);involved.update([a,b])
        for name in ['accepted_point_use_delta.csv','accepted_point_use_delta.csv.gz','accepted_former_locality_own_points.csv']:
            path=folder/name
            if path.exists():newpoints.extend(pd.read_csv(path,keep_default_na=False).to_dict('records'))
        for name in ['accepted_direct_event_native_credit_union.csv','accepted_actual_available_year_observations.csv.gz','accepted_historical_observations.csv']:
            path=folder/name
            if path.exists():newtyped.update(pd.read_csv(path).source_record_id)
        if folder.name=='over1000_tula_temporal_v4_20261009':
            z=pd.read_csv(folder/'source_year_status.csv',keep_default_na=False)
            newtyped.update(z[z.source_record_id.ne('')&z.place.isin(['Центральный','Социалистический','Славный','Туношна-городок 26'])].source_record_id)
    edges=pd.DataFrame(newedges);points=pd.DataFrame(newpoints).fillna('')
    if len(points):
        assert points.target_source_record_id.is_unique
        points.to_csv(OUT/'accepted_regional_point_uses.csv',index=False);state.add_deltas(point_paths=[OUT/'accepted_regional_point_uses.csv'])
    # Retrospective own-point use follows these newly source-bound same-place edges.
    transfer=[]
    involvedroots={state.uf.find(x) for x in involved}
    componentmembers={}
    for sid in state.obs.source_record_id:
        r=state.uf.find(sid)
        if r in involvedroots:componentmembers.setdefault(r,[]).append(sid)
    for root,members in componentmembers.items():
        donors=[sid for sid in members if sid in state.point_rows]
        if not donors:continue
        donor=max(donors,key=lambda sid:int(state.by_id.loc[sid,'census_year']));d=state.point_rows[donor]
        for sid in members:
            if sid in state.point_rows:continue
            row=dict(d,target_source_record_id=sid,coordinate_source_record_id=donor,coordinate_admission_status='reviewed_rule_accepted',retrospective_point_use_is_continuity_inference=True,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,root_review_source_bound_edges=True)
            transfer.append(row)
    if transfer:
        transferpath=OUT/'accepted_source_bound_retrospective_points.csv';pd.DataFrame(transfer).fillna('').to_csv(transferpath,index=False);state.add_deltas(point_paths=[transferpath])
    edges.to_csv(OUT/'accepted_regional_identity_edges.csv',index=False)
    if batchconflicts:pd.DataFrame(batchconflicts).to_csv(OUT/'held_regional_identity_conflicts.csv',index=False)
    state.obs['root']=state.obs.source_record_id.map(state.uf.find)
    regional=E/'main_axis_residual_application70_regional_batch_20261009'
    # Two source-proven repairs: preserve valid surviving links inside each component.
    repairfolders=[E/'over1000_crosscheck_bash_20261009',E/'over1000_rest_B_20261009/version8_novolisiino_crosswire']
    for folder in repairfolders:
        for f in folder.iterdir():
            if f.is_file():pin(f)
        name='reviewed_identity_edge_rejection.csv' if 'crosscheck_bash' in folder.name else 'identity_edge_rejections.csv'
        rejected=pd.read_csv(folder/name,keep_default_na=False)
        for row in rejected.to_dict('records'):
            left,right=row['from_source_record_id'],row['to_source_record_id'];root=state.uf.find(left)
            assert state.uf.find(right)==root
            members={sid for sid in state.obs.source_record_id if state.uf.find(sid)==root}
            assert len(members) in {2,3},members
            # Each rejected link connects the wrong 2021 name/code to a predecessor.
            assert int(state.by_id.loc[right,'census_year'])==2021
            detached=left if 'crosscheck_bash' in folder.name else right
            retained=members-{detached};state.years.pop(root)
            for sid in members:state.uf.parent[sid]=sid;state.years[sid]={int(state.by_id.loc[sid,'census_year'])}
            retained=sorted(retained)
            for sid in retained[1:]:state.union(retained[0],sid)
        rejectfile=folder/('point_use_rejection_witness.csv' if 'crosscheck_bash' in folder.name else 'point_rejections.csv')
        normalized=[]
        for row in pd.read_csv(rejectfile,keep_default_na=False).to_dict('records'):
            sid=row['target_source_record_id'];old=state.point_rows[sid]
            lat=row.get('old_latitude',row.get('latitude'));lon=row.get('old_longitude',row.get('longitude'))
            assert (float(lat),float(lon))==(old['latitude'],old['longitude'])
            normalized.append(dict(row,old_latitude=lat,old_longitude=lon,rejection_status='reviewed_rejected_coordinate_claim_only',origin_ledger=old['point_ledger_path'],origin_ledger_sha256=sha(Path(old['point_ledger_path']))))
        out=OUT/(folder.name+'_reviewed_point_rejections.csv');pd.DataFrame(normalized).to_csv(out,index=False);state.reject_point_uses(out)
    # Review proves both physical Subkh lineages; administrative rename is not merger.
    rural='2002:041_4b428edd23_Bashkiria_new.xls:Sheet1:5834'
    pgt='2002:1_TOM_01_04.xls:0:5224'
    large='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:148581'
    small='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:148583'
    subkh=pd.DataFrame([dict(from_source_record_id=pgt,to_source_record_id=large,relation='same_place',decision_status='checked_rule_accepted',admission_rule='Independent raw-source type and own locality history: PGT→selo2006; original population unchanged'),dict(from_source_record_id=rural,to_source_record_id=small,relation='same_place',decision_status='checked_rule_accepted',admission_rule='Independent2008literal rural-village rename to OldSubkh; Nurkeevsky council and distinct own codes; no merger')])
    subkhpath=OUT/'corrected_subkh_identity_edges.csv';subkh.to_csv(subkhpath,index=False);state.add_deltas(edge_paths=[subkhpath])
    subpoint=dict(state.point_rows[small],target_source_record_id=rural,coordinate_source_record_id=small,coordinate_admission_status='reviewed_rule_accepted',retrospective_point_use_is_continuity_inference=True,historical_census_coordinate_asserted=False)
    subpointpath=OUT/'corrected_old_rural_subkh_point.csv';pd.DataFrame([subpoint]).to_csv(subpointpath,index=False);state.add_deltas(point_paths=[subpointpath])
    folders2=[E/'over1000_bash_amur_20261009/version6',E/'over1000_rest_B_20261009/version8_novolisiino_crosswire',E/'over1000_moscow_remaining13_20261009',E/'over1000_moscow_last10_sources_20261009',E/'over1000_tula_oktyabrsky_v5_20261009',E/'over1000_crimea_rodnikovoe_20261009',E/'over1000_moscow_inner_territories_20261009']
    folders2 += [p for p in (E/'over1000_rest_B_20261009').glob('version*') if p.name.split('_')[0] in {'version16','version17','version18'}]
    folders2 += [p for p in (E/'over1000_rest_20261009').glob('A112_v*') if p.name.startswith(('A112_v7_','A112_v7_1_','A112_v8_','A112_v8_1_','A112_v9_','A112_v10_','A112_v11_','A112_v12_','A112_v13_','A112_v15_','A112_v17_','A112_v18_','A112_v19_1_','A112_v20_'))]
    folders2 += [E/'over1000_five_regions_20261009'/n for n in ['batch1','batch2_available','batch3_publication_absence','batch4_inclusions']]
    kfolder=E/'over1000_five_regions_20261009/batch4_konstantinovka_coordinate_rejection'
    for f in kfolder.iterdir():
        if f.is_file():pin(f)
    krej=pd.read_csv(kfolder/'reviewed_point_use_rejection.csv',keep_default_na=False)
    normalized=[]
    for row in krej.to_dict('records'):
        sid=row['target_source_record_id'];old=state.point_rows[sid]
        assert (float(row.get('old_latitude',row.get('latitude'))),float(row.get('old_longitude',row.get('longitude'))))==(old['latitude'],old['longitude'])
        normalized.append(dict(row,old_latitude=old['latitude'],old_longitude=old['longitude'],origin_ledger=old['point_ledger_path'],origin_ledger_sha256=sha(Path(old['point_ledger_path']))))
    kp=OUT/'Konstantinovka_exact_wrong_object_point_rejection.csv';pd.DataFrame(normalized).to_csv(kp,index=False);state.reject_point_uses(kp)
    newedges2=[];newpoints2=[];newtyped2=set();involved2={pgt,rural,large,small}
    for folder in sorted(folders2):
        for f in folder.iterdir():
            if f.is_file():pin(f)
        if folder.name=='over1000_moscow_last10_sources_20261009':
            norm=[]
            for row in pd.read_csv(folder/'accepted_point_rejection_delta.csv',keep_default_na=False).to_dict('records'):
                sid=row['target_source_record_id'];old=state.point_rows[sid]
                lat=row.get('old_latitude',row.get('latitude'));lon=row.get('old_longitude',row.get('longitude'))
                assert (float(lat),float(lon))==(old['latitude'],old['longitude'])
                norm.append(dict(row,rejection_status='reviewed_rejected_coordinate_claim_only',old_latitude=lat,old_longitude=lon,origin_ledger=old['point_ledger_path'],origin_ledger_sha256=sha(Path(old['point_ledger_path']))))
            out=OUT/'Popovka_exact_wrong_point_rejection.csv';pd.DataFrame(norm).to_csv(out,index=False);state.reject_point_uses(out)
        edgefiles=[p for p in folder.iterdir() if p.suffix=='.csv' and (p.name.startswith('accepted_identity_edge_delta') or 'edge_candidate' in p.name)]
        for path in edgefiles:
            for row in pd.read_csv(path,keep_default_na=False).to_dict('records'):
                assert row.get('relation')=='same_place';row['decision_status']='checked_rule_accepted';row['root_review_evidence_packet']=str(folder)
                a,b=row['from_source_record_id'],row['to_source_record_id']
                try:state.union(a,b)
                except ValueError as exc:batchconflicts.append(dict(row,root_conflict=str(exc)));continue
                newedges2.append(row);involved2.update([a,b])
        for name in ['accepted_point_use_delta.csv','accepted_point_use_delta.csv.gz','accepted_point_use_delta_v6.csv','accepted_former_locality_own_points.csv','accepted_own_point_use.csv','accepted_2002_locality_point_uses.csv']:
            path=folder/name
            if path.exists():
                
                try:z=pd.read_csv(path,keep_default_na=False)
                except pd.errors.EmptyDataError:continue
                z=z.rename(columns={k:v for k,v in {'lat':'latitude','lon':'longitude'}.items() if k in z.columns and v not in z.columns});
                if 'target_source_record_id' not in z.columns:z['target_source_record_id']=z['source_record_id']
                z['coordinate_admission_status']='reviewed_rule_accepted';newpoints2.extend(z.to_dict('records'))
        for name in ['accepted_direct_event_native_credit_union.csv','accepted_newly_formed_native_credit_union.csv','accepted_actual_available_year_observations.csv','accepted_actual_available_year_observations.csv.gz','accepted_historical_observations.csv']:
            path=folder/name
            if path.exists():newtyped2.update(pd.read_csv(path).source_record_id)
        if folder.name=='version6':
            ledger=pd.read_csv(folder/'primary_year_credit_ledger_v6.csv',keep_default_na=False)
            newtyped2.update(ledger[ledger.credited_source_uid.ne('')].credited_source_uid)
        for name in ['existing_2010_2021_component.csv','existing_2010_2021_component_and_point.csv']:
            path=folder/name
            if path.exists():
                z=pd.read_csv(path,keep_default_na=False);newtyped2.update(z.source_record_id);involved2.update(z.source_record_id)
    points2=pd.DataFrame(newpoints2).fillna('')
    for sid, group in points2.groupby('target_source_record_id'):
        coordinates={(float(r.latitude),float(r.longitude)) for r in group.itertuples()}
        assert len(coordinates)==1, (sid, coordinates)
    points2=points2.drop_duplicates('target_source_record_id',keep='last')
    
    conflicts=[]
    for row in points2.to_dict('records'):
        sid=row['target_source_record_id']
        if sid in state.point_rows:
            old=state.point_rows[sid]
            if distance_km((float(row['latitude']),float(row['longitude'])),(old['latitude'],old['longitude']))>5:conflicts.append({'sid':sid,'old_lat':old['latitude'],'old_lon':old['longitude'],'new_lat':row['latitude'],'new_lon':row['longitude']})
    if conflicts:raise ValueError(conflicts)
    pointpath=OUT/'accepted_batch2_point_uses.csv';points2.to_csv(pointpath,index=False);state.add_deltas(point_paths=[pointpath])
    edges2=pd.DataFrame(newedges2);edges2.to_csv(OUT/'accepted_batch2_identity_edges.csv',index=False)
    roots2={state.uf.find(sid) for sid in involved2};members2={}
    for sid in state.obs.source_record_id:
        r=state.uf.find(sid)
        if r in roots2:members2.setdefault(r,[]).append(sid)
    transfers2=[]
    for r,members in members2.items():
        donors=[sid for sid in members if sid in state.point_rows]
        if not donors:continue
        donor=max(donors,key=lambda sid:int(state.by_id.loc[sid,'census_year']));d=state.point_rows[donor]
        for sid in members:
            if sid in state.point_rows:continue
            transfers2.append(dict(d,target_source_record_id=sid,coordinate_source_record_id=donor,coordinate_admission_status='reviewed_rule_accepted',retrospective_point_use_is_continuity_inference=True,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False))
    if transfers2:
        out=OUT/'accepted_batch2_source_bound_retrospective_points.csv';pd.DataFrame(transfers2).fillna('').to_csv(out,index=False);state.add_deltas(point_paths=[out])
    state.obs['root']=state.obs.source_record_id.map(state.uf.find)
    pd.testing.assert_frame_equal(original.drop(columns='root'),state.obs.drop(columns='root'))
    oldids=set(pd.read_csv(BASE/'applied_primary_credited_UID_roster.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(prev/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(tula/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(south/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(southv2/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(bash/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(moscow/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)|set(pd.read_csv(regional/'actual_new_primary_native_UIDs.csv.gz',usecols=['source_record_id']).source_record_id)
    all3={root for root,years in state.years.items() if years=={2002,2010,2021}}
    for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None):
        if sid not in state.point_rows or pd.isna(pop) or not math.isfinite(float(pop)):all3.discard(state.uf.find(sid))
    ordinary=state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((state.obs.census_year==2021)&state.obs.region_norm.eq('крым'))].copy()
    oldids-=set(pd.read_csv(moscow/'withdrawn_false_primary_native_UIDs.csv').source_record_id)
    lostids=set()
    eventids={sid for sid in newtyped2 if sid in state.point_rows}
    new=ordinary[(ordinary.root.isin(all3)|ordinary.source_record_id.isin(eventids))&~ordinary.source_record_id.isin(oldids)].copy()
    overlay=pd.read_csv(pin(ROOT/'publication/stage68/applied_primary_population_source_overlay_2010.csv.gz')).set_index('original_source_record_id')
    ordinary['effective_population']=ordinary.population
    for idx,r in ordinary[ordinary.census_year.eq(2010)].iterrows():
        if r.source_record_id in overlay.index:ordinary.loc[idx,'effective_population']=overlay.loc[r.source_record_id,'population']
    new=ordinary[ordinary.source_record_id.isin(new.source_record_id)].copy()
    new.to_csv(OUT/'actual_new_primary_native_UIDs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    ids=(oldids-lostids)|set(new.source_record_id)
    lost=ordinary[ordinary.source_record_id.isin(lostids)].copy();lost.to_csv(OUT/'withdrawn_false_primary_native_UIDs.csv',index=False)
    rem=ordinary[~ordinary.source_record_id.isin(ids)&((ordinary.population>1000)|(ordinary.effective_population>1000))].copy()
    rem.to_csv(OUT/'remaining_over1000_raw_or_primary.csv',index=False)
    previous=json.loads((regional/'application_receipt.json').read_text())
    gains={str(int(y)):int(g.effective_population.sum()) for y,g in new.groupby('census_year')}
    losses={str(int(y)):int(g.effective_population.sum()) for y,g in lost.groupby('census_year')}
    gains={y:gains.get(y,0)-losses.get(y,0) for y in ['2002','2010','2021']}
    after={}
    for y,v in previous['effective_primary_coverage'].items():
        n=v['population']+gains.get(y,0);after[y]={'population':n,'control':v['control'],'coverage_percent':100*n/v['control'],'remaining':v['control']-n}
    receipt={'working_stage':'70_batch2_increment','status':'actual_State_API_applied','new_identity_edges':len(edges2)+2,'new_point_uses':len(points2)+len(transfers2)+1,'new_primary_UIDs':len(new),'effective_population_gain':gains,'effective_primary_coverage':after,'remaining_over1000_source_year_records':len(rem),'remaining_by_year':{str(int(y)):len(g) for y,g in rem.groupby('census_year')},'raw_population_unchanged':True,'absent_years_not_zero':True,'source_packet_erratum':'Subkh rural versus former PGT and Novolisino high versus low source identities repaired; Popovka exact wrong point superseded; frozen raw observations unchanged','input_pins':pins,'wall_seconds':round(time.monotonic()-started,3)}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='input_pins'},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
