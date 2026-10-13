"""Apply reviewed native linkage packets to recovered application15.

Frozen source numbers and current national controls are preserved. Credit is an
exact native UID union; graph corrections are applied before new identity edges.
"""
from pathlib import Path
import argparse, csv, hashlib, json, math, sys, time
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];E=ROOT/'research_rebuild/evidence'
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import State, distance_km
from build_long_table import UnionFind, ACCEPTED_COORDINATE_STATUSES
CONTROLS={2002:145166731,2010:142856536,2021:144699673}
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def yes(v):return str(v).lower() in {'true','1'}
def load_current(path):
    receipt=json.loads((path/'recovery_receipt.json').read_text());assert receipt['recovery_status']=='verified_against_frozen_application15'
    s=State.__new__(State);s.obs=pd.read_parquet(path/'applied_state_observations.parquet');assert s.obs.source_record_id.is_unique
    s.by_id=s.obs.set_index('source_record_id',drop=False);s.uf=UnionFind(s.obs.source_record_id);s.uf.parent=dict(zip(s.obs.source_record_id,s.obs.root));s.years={}
    for root,yr in zip(s.obs.root,s.obs.census_year):s.years.setdefault(root,set()).add(int(yr))
    cols=['source_record_id','target_source_record_id','latitude','longitude','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path']
    p=pd.read_parquet(path/'applied_point_snapshot.parquet',columns=cols).fillna('');s.point_rows={}
    for row in p.to_dict('records'):
        sid=row.pop('source_record_id');assert row['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES
        row['latitude']=float(row['latitude']);row['longitude']=float(row['longitude']);s.point_rows[sid]=row
    assert len(s.obs)==465929 and len(s.point_rows)==447362
    s.point_alternatives=[];s.conflicting_point_targets=set();s.inputs=[]
    return s,receipt
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--state-dir',required=True);ap.add_argument('--output',required=True);ap.add_argument('--full-output',required=True);ap.add_argument('--include-broad',action='store_true');args=ap.parse_args()
    start=time.monotonic();out=Path(args.output);full=Path(args.full_output);out.mkdir(parents=True,exist_ok=True);full.mkdir(parents=True,exist_ok=True)
    state_path=Path(args.state_dir);s,recovery=load_current(state_path);original=s.obs.drop(columns='root').copy(deep=True);pins={}
    def read(p,**kw):
        p=Path(p);pins[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
        return pd.read_csv(p,keep_default_na=False,**kw)
    for n in ['applied_state_observations.parquet','applied_point_snapshot.parquet','recovery_receipt.json']:
        p=state_path/n;pins[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
    scope=read(ROOT/'publication/stage71/accepted_large_record_scope_classification_overlay.csv')
    scope2=read(E/'over500_route_audit_20261009/accepted_scope_overlay.csv');scopeids=set(scope.source_record_id)|set(scope2.source_record_id)
    overlay=read(ROOT/'publication/stage71/applied_primary_population_source_overlay_2010.csv.gz').set_index('original_source_record_id')
    def ordinary():
        a=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','крым','севастополь'])&~s.obs.source_record_id.isin(scopeids)].copy()
        a['point']=a.source_record_id.isin(s.point_rows);a['finite']=a.population.map(lambda p:pd.notna(p) and math.isfinite(float(p)))
        g=a.groupby('root').agg(n=('source_record_id','size'),years=('census_year','nunique'),points=('point','all'),finite=('finite','all'))
        roots=set(g[(g.n==3)&(g.years==3)&g.points&g.finite].index)
        return set(a.loc[a.root.isin(roots),'source_record_id']),roots
    oldfull,oldroots=ordinary();assert len(oldroots)==142696
    partition_path=E/'residual_east_20261013/accepted_identity_partition_proposals.json';pins[str(partition_path)]={'sha256':sha(partition_path),'bytes':partition_path.stat().st_size}
    partitions=json.loads(partition_path.read_text())
    for row in partitions:
        before=row['expected_current_full_members'];after=row['after_partitions'];proof=Path(row['evidence_file']);assert sha(proof)==row['evidence_sha256']
        pins[str(proof)]={'sha256':sha(proof),'bytes':proof.stat().st_size}
        assert len(before)==len(set(before));oldroot=s.uf.find(before[0]);actual=set(s.obs.loc[s.obs.source_record_id.map(s.uf.find).eq(oldroot),'source_record_id']);assert actual==set(before)
        flat=[x for group in after for x in group];assert len(flat)==len(set(flat)) and set(flat)==actual
        del s.years[oldroot]
        for sid in before:s.uf.parent[sid]=sid;s.years[sid]={int(s.by_id.loc[sid,'census_year'])}
        for group in after:
            for sid in group[1:]:s.union(group[0],sid)
    s.obs['root']=s.obs.source_record_id.map(s.uf.find)
    edge_paths=[E/'residual_east_20261013/accepted_identity_edge_delta.csv',E/'residual_east_20261013/accepted_identity_edge_delta_after_partitions.csv',E/'residual_center_20261013/accepted_identity_edge_delta.csv',E/'residual_northwest_20261013/accepted_identity_edge_delta.csv',E/'residual_northwest_20261013/ushakovo_identity_edge_delta.csv']
    proposal=read(E/'residual_volga_south_20261013/accepted_identity_edge_proposals.csv')
    assert not proposal.name.eq('Калинин').any(), 'Independent review withdrew ambiguous Kalinin'
    volga=proposal.rename(columns={'left_source_record_id':'from_source_record_id','right_source_record_id':'to_source_record_id'}).copy();volga['relation']='same_place';volga['decision_status']='checked_rule_accepted';volga['admission_rule']=volga['rule']
    volga.to_csv(out/'accepted_volga_identity_edge_delta.csv',index=False);edge_paths.append(out/'accepted_volga_identity_edge_delta.csv')
    if args.include_broad:edge_paths.append(E/'residual_broad_native_20261013/accepted_identity_edge_delta.csv')
    point_paths=[E/'residual_east_20261013/accepted_point_use_delta.csv',E/'residual_east_20261013/accepted_point_use_delta_after_partitions.csv',E/'residual_northwest_20261013/accepted_point_use_delta.csv',E/'residual_northwest_20261013/ushakovo_point_use_delta.csv',E/'residual_northwest_20261013/bereznik_point_use_delta.csv']
    beforepoint={sid:(r['latitude'],r['longitude']) for sid,r in s.point_rows.items()}
    rejected=[]
    for p in [E/'residual_northwest_20261013/ushakovo_point_rejection_delta.csv',E/'residual_northwest_20261013/bereznik_point_rejection_delta.csv']:
        for row in read(p).to_dict('records'):
            sid=row['target_source_record_id'];old=s.point_rows[sid]
            assert row['rejection_status']=='reviewed_rejected_coordinate_claim_only'
            assert (old['latitude'],old['longitude'])==(float(row['old_latitude']),float(row['old_longitude']))
            for k in ['point_origin_file','point_origin_sha256','point_origin_locator']:
                if row.get(k):assert old[k]==row[k],(sid,k)
            rejected.append(dict(row,old_active_point_ledger=old['point_ledger_path']));del s.point_rows[sid]
    # The station point was inferred through the disproved main-place chain. Its
    # physical position is unknown; withdrawal concerns the use/binding, not a
    # geographic assertion that the original coordinate itself is impossible.
    station='2002:057_9b18a354f1_02c_Sverdlovskaja_oblast.xls:Sheet1:214'
    oldstation=s.point_rows.pop(station)
    rejected.append(dict(target_source_record_id=station,rejection_status='reviewed_rejected_coordinate_claim_only',old_latitude=oldstation['latitude'],old_longitude=oldstation['longitude'],reason='Inherited ownpoint use depended on disproved main-Vorontsovka temporal identity; independent station ownsite remains unknown.',point_itself_geographically_rejected=False,old_active_point_ledger=oldstation['point_ledger_path']))
    edges=[]
    for p in edge_paths:
        f=read(p);edges.extend(dict(row,applied_input_packet=str(p)) for row in f.to_dict('records'))
    for p in point_paths:read(p)
    # Qualified own-object evidence in the reviewed homonym corrections may
    # replace an inherited point more than 5km away. Supersede the old use first,
    # keeping its claim and the exact reason rather than relaxing add_deltas.
    for p in point_paths:
        for row in pd.read_csv(p,keep_default_na=False).to_dict('records'):
            sid=row['target_source_record_id']
            if sid in s.point_rows:
                old=s.point_rows[sid]
                if distance_km((float(row['latitude']),float(row['longitude'])),(old['latitude'],old['longitude']))>5:
                    assert p.name=='accepted_point_use_delta_after_partitions.csv', 'Unexpected large coordinate correction requires its own review'
                    rejected.append(dict(target_source_record_id=sid,rejection_status='reviewed_rejected_coordinate_claim_only',old_latitude=old['latitude'],old_longitude=old['longitude'],reason='Reviewed homonym partition and distinct own-object article supersede inherited rival-object point use.',old_active_point_ledger=old['point_ledger_path'],replacement_packet=str(p)))
                    del s.point_rows[sid]
    s.add_deltas(edge_paths=edge_paths,point_paths=point_paths)
    pd.testing.assert_frame_equal(original,s.obs.drop(columns='root'))
    newfull,newroots=ordinary();seed=read(E/'over500_lifecycle_integration_20261009/applied/integrated_credited_UID_roster.csv.gz');seedids=set(seed.source_record_id)
    lost=oldfull-newfull;assert lost=={station},lost
    ids=(seedids-lost)|newfull;gained=ids-seedids;withdrawn=seedids-ids;assert withdrawn=={station}
    obs=s.obs.copy();obs['effective_population']=obs.source_record_id.map(overlay.population).combine_first(obs.population)
    obs['accepted_point_present']=obs.source_record_id.isin(s.point_rows)
    obs['accepted_latitude']=obs.source_record_id.map(lambda sid:s.point_rows.get(sid,{}).get('latitude',float('nan')))
    obs['accepted_longitude']=obs.source_record_id.map(lambda sid:s.point_rows.get(sid,{}).get('longitude',float('nan')))
    obs['finite_ordinary_full3_all_ownpoints']=obs.source_record_id.isin(newfull)
    obs['working_credit_present']=obs.source_record_id.isin(ids);obs['new_credit_this_application']=obs.source_record_id.isin(gained)
    federal=read(ROOT/'publication/stage71/accepted_common_federal_territory_axis.csv');assert len(federal)==6 and federal.population_source_record_id.is_unique and not set(federal.population_source_record_id)&ids
    fed=federal.groupby('census_year').territory_population.sum().to_dict();coverage=[]
    previous=read(E/'over500_lifecycle_integration_20261009/applied/coverage.csv').set_index('year')
    for y in CONTROLS:
        n=int(obs.loc[obs.census_year.eq(y)&obs.source_record_id.isin(ids),'effective_population'].sum()+fed[y]);prior=int(previous.loc[y,'credited_population']) if 'credited_population' in previous else int(previous.loc[y,'population'])
        coverage.append(dict(census_year=y,credited_population=n,denominator=CONTROLS[y],coverage_percent=100*n/CONTROLS[y],remaining_to_100=CONTROLS[y]-n,net_population_gain=n-prior))
    pd.DataFrame(coverage).to_csv(out/'coverage.csv',index=False)
    cols=['source_record_id','census_year','effective_population','root','finite_ordinary_full3_all_ownpoints','accepted_point_present','working_credit_present','new_credit_this_application']
    obs.loc[obs.source_record_id.isin(ids),cols].sort_values('source_record_id').to_csv(out/'integrated_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    obs[obs.source_record_id.isin(gained|withdrawn)].to_csv(out/'changed_credit_native_records.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    initial=read(E/'residual_root_20261013/initial_over500_residual.csv')
    remaining=obs[obs.source_record_id.isin(initial.source_record_id)&~obs.working_credit_present]
    remaining.to_csv(out/'remaining_initial_over500_residual.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(edges).to_csv(out/'applied_identity_edges.csv',index=False);pd.DataFrame(rejected).to_csv(out/'applied_coordinate_use_rejections.csv',index=False)
    declared=set()
    for p in point_paths:declared.update(pd.read_csv(p,usecols=['target_source_record_id']).target_source_record_id)
    pd.DataFrame([s.point_rows[sid] for sid in sorted(declared)]).to_csv(out/'applied_point_use_delta.csv',index=False)
    # Only a narrow full current long layer is regenerated. Rich unchanged point
    # metadata remains available in the pinned application15 snapshot and all
    # replacement qualifiers in the applied delta. No metadata-complete new
    # national release is claimed.
    obs.to_parquet(full/'integrated_spatial_temporal_records.parquet',index=False,compression='zstd')
    s.obs.to_parquet(full/'applied_state_observations.parquet',index=False,compression='zstd')
    core=[dict(source_record_id=sid,**{k:r.get(k,'') for k in ['latitude','longitude','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path']}) for sid,r in s.point_rows.items()]
    pd.DataFrame(core).to_parquet(full/'applied_core_point_snapshot.parquet',index=False,compression='zstd')
    ratio=[]
    byid=obs.set_index('source_record_id')
    for row in edges:
        a,b=byid.loc[row['from_source_record_id']],byid.loc[row['to_source_record_id']]
        x,y=float(a.effective_population),float(b.effective_population)
        ratio.append(dict(from_source_record_id=a.name,to_source_record_id=b.name,from_population=x,to_population=y,ratio=y/x if x else '',extreme_flag=(x==0 and y>0) or (x>0 and y/x>21) or (y==0 and x>0) or (y>0 and x/y>21)))
    pd.DataFrame(ratio).to_csv(out/'new_edge_population_ratio_screen.csv',index=False)
    receipt={'status':'applied_reviewed_native_batch','controls_unchanged':CONTROLS,'source_counts_quality_metadata_unchanged':True,'ordinary_full3_before':len(oldroots),'ordinary_full3_after':len(newroots),'applied_identity_edge_rows':len(edges),'corrected_identity_components':len(partitions),'new_credited_UIDs':len(gained),'withdrawn_credited_UIDs':sorted(withdrawn),'final_credited_native_UIDs':len(ids),'active_ownpoints':len(s.point_rows),'new_point_uses':len(set(s.point_rows)-set(beforepoint)),'withdrawn_point_uses':sorted(set(beforepoint)-set(s.point_rows)),'corrected_existing_point_uses':sum((r['latitude'],r['longitude'])!=beforepoint[sid] for sid,r in s.point_rows.items() if sid in beforepoint),'initial_over500_uncredited_records':len(initial),'initial_over500_resolved_records':len(initial)-len(remaining),'initial_over500_remaining_records':len(remaining),'extreme_ratio_flags':sum(r['extreme_flag'] for r in ratio),'federal_rows_counted_once':6,'coverage':coverage,'input_pins':pins,'previous_state_recovery':recovery,'full_output_hashes':{p.name:sha(p) for p in full.glob('*.parquet')},'runtime_seconds':round(time.monotonic()-start,3),'full_point_metadata_references':'Pinned application15 full snapshot for unchanged rows, applied point-use delta for replacements; core snapshot is intentionally not a complete metadata export.'}
    (out/'application_receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','previous_state_recovery']},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
