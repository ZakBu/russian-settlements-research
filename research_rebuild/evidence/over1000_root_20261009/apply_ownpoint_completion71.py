"""Apply source-bound own points to already-admitted histories; never alter counts."""
from pathlib import Path
import argparse,json,sys,time,math,hashlib
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];E=ROOT/'research_rebuild/evidence';M=ROOT/'research_rebuild/mass_linkage'
sys.path.insert(0,str(M))
from working_state_20261007 import load
from current_chain_state_20261007 import sha

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--packet',action='append',required=True);parser.add_argument('--export-dir');args=parser.parse_args()
    start=time.monotonic();out=E/'main_axis_ownpoint_completion71_20261009';out.mkdir(exist_ok=True)
    pins={}
    def pin(path):
        path=Path(path);pins[str(path)]={'sha256':sha(path),'bytes':path.stat().st_size};return path
    state=load(70);original=state.obs.copy(deep=True);before_points=set(state.point_rows)
    baseline=ROOT/'publication/stage70'
    for name in ['applied_state_observations.parquet','applied_component_snapshot.csv.gz','applied_point_snapshot.parquet','applied_primary_credited_UID_roster.csv.gz','application_receipt.json']:pin(baseline/name)
    scopepath=pin(E/'large_ownpoint_scope_disambiguation_20261009/scope_overlay.csv');scope=pd.read_csv(scopepath,keep_default_na=False)
    assert len(scope)==38 and scope.source_record_id.is_unique
    scope.to_csv(out/'accepted_large_record_scope_classification_overlay.csv',index=False)
    frames=[];coarse_frames=[]
    for folder in map(Path,args.packet):
        for path in folder.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:pin(path)
        frame=pd.read_csv(folder/'accepted_point_use_delta.csv',keep_default_na=False)
        assert frame.target_source_record_id.is_unique
        frame['coordinate_admission_status']='reviewed_rule_accepted'
        assert set(frame.target_source_record_id)<=set(state.obs.source_record_id)
        scoped=frame[frame.target_source_record_id.isin(set(scope.source_record_id))].copy()
        if len(scoped):
            kinds=scope.set_index('source_record_id').scope_class
            assert set(scoped.target_source_record_id.map(kinds))=={'literal_part_source_observation'}
            scoped['coordinate_admission_status']='reviewed_coarse_whole_locality_association_only'
            scoped['own_historical_part_point_asserted']=False
            scoped['historical_part_exact_coordinate']='UNKNOWN'
            coarse_frames.append(scoped)
            frame=frame[~frame.target_source_record_id.isin(set(scope.source_record_id))].copy()
        if folder.name=='large_existing_credited_east_ownpoints_20261009':
            for ix,row in frame.iterrows():
                if str(row.get('point_origin_file','')).startswith('http'):
                    capture=folder/('wikipedia_abagur_point_witness.json' if 'Абагур' in row['point_origin_file'] else 'wikipedia_article_point_witnesses.json');assert capture.exists()
                    frame.loc[ix,'point_origin_original_URL']=row['point_origin_file']
                    frame.loc[ix,'point_origin_file']=str(pin(capture));frame.loc[ix,'point_origin_sha256']=sha(capture)
        if folder.name=='large_existing_credited_north_ownpoints_20261009':
            review=E/'crosscheck_large_north_ownpoint_binding_20261009'
            for path in review.iterdir():
                if path.is_file():pin(path)
            corrections=pd.read_csv(review/'point_article_coordinate_corrections.csv',keep_default_na=False)
            assert len(corrections)==5
            for correction in corrections.to_dict('records'):
                selected=frame.target_source_record_id.eq(correction['target_source_record_id']);assert selected.sum()==1
                ix=frame.index[selected][0]
                frame.loc[ix,'superseded_unapplied_candidate_latitude']=frame.loc[ix,'latitude']
                frame.loc[ix,'superseded_unapplied_candidate_longitude']=frame.loc[ix,'longitude']
                frame.loc[ix,'superseded_unapplied_candidate_source_record_id']=frame.loc[ix,'coordinate_source_record_id']
                frame.loc[ix,'latitude']=correction['replacement_latitude'];frame.loc[ix,'longitude']=correction['replacement_longitude']
                for field,value in correction.items():
                    if field not in ['replacement_latitude','replacement_longitude','coordinate_admission_status','target_source_record_id']:frame.loc[ix,field]=value
                frame.loc[ix,'coordinate_admission_status']='reviewed_rule_accepted'
                frame.loc[ix,'coordinate_accuracy_calibration_status']='not independently calibrated; source rounding/approximation retained'
                frame.loc[ix,'retrospective_point_use_is_continuity_inference']=True
        frame['root_accepted_ownpoint_packet']=str(folder)
        frames.append(frame)
    if coarse_frames:pd.concat(coarse_frames,ignore_index=True).fillna('').to_csv(out/'accepted_typed_coarse_part_spatial_associations_from_point_packets.csv',index=False)
    points=pd.concat(frames,ignore_index=True).fillna('')
    assert points.target_source_record_id.is_unique,'Disjoint cohort target UID repeated'
    for row in points.to_dict('records'):
        assert math.isfinite(float(row['latitude'])) and math.isfinite(float(row['longitude']))
        assert -90<=float(row['latitude'])<=90 and -180<=float(row['longitude'])<=180
        assert row['target_source_record_id'] not in before_points,'This pass only adds absent own points'
    delta=out/'accepted_point_use_delta.csv';points.to_csv(delta,index=False);state.add_deltas(point_paths=[delta])
    pd.testing.assert_frame_equal(original,state.obs)
    observation=state.obs.copy();observation['effective_population']=observation.population
    overlay=pd.read_csv(pin(baseline/'applied_primary_population_source_overlay_2010.csv.gz')).set_index('original_source_record_id')
    for ix,row in observation[observation.census_year.eq(2010)&observation.source_record_id.isin(overlay.index)].iterrows():observation.loc[ix,'effective_population']=overlay.loc[row.source_record_id,'population']
    eligible=observation[observation.is_additive_settlement_record.fillna(False)&((observation.population>1000)|(observation.effective_population>1000))&~observation.source_record_id.isin(set(scope.source_record_id))]
    missing=eligible[~eligible.source_record_id.isin(state.point_rows)];missing.to_csv(out/'remaining_whole_NP_over1000_without_ownpoint.csv',index=False)
    previous=json.loads((baseline/'application_receipt.json').read_text())
    receipt={'status':'actual_State_API_ownpoint_application','working_stage':'71_ownpoint_completion','new_own_point_uses':len(points),'all_native_records_above_threshold_have_ownpoint_after_scope_classification':len(missing)==0,'remaining_whole_NP_over1000_without_ownpoint':len(missing),'explicit_part_admin_territory_scope_exemptions':len(scope),'raw_population_quality_and_identity_graph_unchanged':True,'effective_primary_coverage':previous['effective_primary_coverage'],'input_pins':pins,'wall_seconds':round(time.monotonic()-start,3)}
    (out/'application_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='input_pins'},indent=2),flush=True)
    if args.export_dir:
        assert len(missing)==0,'Full completion export requires zero whole-NP ownpoint residual'
        sys.path.insert(0,str(E/'over1000_final_export_20261009'));from export_final_state_v3 import export_final_state
        credited=pd.read_csv(baseline/'applied_primary_credited_UID_roster.csv.gz',keep_default_na=False)
        flags=[c for c in credited if c.startswith('explicit_') or c=='final_typed_available_year_or_event_credit']
        eventids=set(credited[credited[flags].astype(str).apply(lambda column:column.str.lower().eq('true')).any(axis=1)].source_record_id)
        joint=pd.read_csv(baseline/'accepted_typed_joint_reporting_scope_spatial_associations.csv',keep_default_na=False)
        originalscope=pd.read_csv(baseline/'accepted_source_scope_interpretation_overlay.csv',keep_default_na=False)
        originalscope.to_csv(out/'accepted_source_scope_interpretation_overlay.csv',index=False)
        joint.to_csv(out/'accepted_typed_joint_reporting_scope_spatial_associations.csv',index=False)
        pd.read_csv(baseline/'ordinary_population_scope_equivalence_exclusions.csv').to_csv(out/'ordinary_population_scope_equivalence_exclusions.csv',index=False)
        result=export_final_state(state=state,credited_ids=set(credited.source_record_id),output_dir=args.export_dir,recipe_output_dir=out,pins=pins,stage_label=receipt['working_stage'],event_ids=eventids,joint=joint,scope=originalscope,expected_coverage=receipt['effective_primary_coverage']);print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
