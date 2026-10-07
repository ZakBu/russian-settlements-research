"""Compact actual-observation register for admitted physical scopes of all grains."""
import json
import pandas as pd
import pyarrow.parquet as pq

def build(E,W,OUT,selected_joint_ids,overlay_ids,common_controls,secondary_frames=()):
    records=[]
    def add(scope,trajectory,year,pop,sid,quality,grain,nonadditive):
        records.append({'scope':scope,'trajectory_id':trajectory,'year':int(year),'population_source_value':int(pop),'source_record_id':sid,'population_quality':quality,'grain':grain,'nonadditive_observation':nonadditive,'ordinary_NP3_asserted':False,'accepted_physical_three_observed_census_year_path':True,'accepted_scoped_representative_point':True,'already_in_ordinary_joint':sid in selected_joint_ids if sid else False,'already_in_joint_partition_union':sid in overlay_ids if sid else False})
    for r in pd.read_csv(E/'dygulybgey_event_path_20261005/accepted_series.csv').to_dict('records'):
        add('dygulybgey_event_aware',r['place'],r['year'],r['population_used'],r['source_record_id'],r['population_value_quality'],'village event-aware scope',False)
    for r in pq.read_table(W/'accepted_secondary_supported_troitsk_shcherbinka_trajectories/scoped_trajectory_observations.parquet').to_pylist():
        add('secondary_supported_troitsk_shcherbinka',r['subject_qid'],r['observation_year'],r['population'],r['source_record_id'],r['population_source_status'],r['source_population_scope'],r['observation_year']==2021)
    for name in ['talnakh','kayerkan']:
        for r in pq.read_table(W/f'accepted_{name}_typed_scope/scoped_primary_observations.parquet').to_pylist():
            add(name+'_typed',r['wikidata_claim_subject_qid'],r['observation_year'],r['population'],r['source_record_id'],r['source_status'],r['population_scope_grain'],r['observation_year']!=2002)
    for t in json.loads((W/'accepted_primary2010_auxiliary_temporal16_scope/accepted_trajectories.json').read_text())['trajectories']:
        for r in t['observations']:
            aux=int(r['year'])==2010
            add('primary2010_auxiliary16',t['trajectory_id'],r['year'],r['population_source_value'] if aux else r['selected_population'],r['source_record_id'],'official_auxiliary_primary_population' if aux else r['population_quality'],'auxiliary official settlement row' if aux else 'existing selected primary settlement row',aux)
    frame=pd.DataFrame(records)
    assert len(frame)==63 and len(frame[['scope','trajectory_id']].drop_duplicates())==21
    applied=pd.read_csv(E/'auxiliary_observed_years_application_20261007/accepted_qualified_physical_observations.csv')
    assert len(applied)==27 and len(applied[['scope','trajectory_id']].drop_duplicates())==9
    assert applied.nonadditive_observation.sum()==9
    applied['already_in_ordinary_joint']=applied.source_record_id.isin(selected_joint_ids)
    applied['already_in_joint_partition_union']=applied.source_record_id.isin(overlay_ids)
    frame=pd.concat([frame,applied],ignore_index=True)
    assert len(frame)==90 and len(frame[['scope','trajectory_id']].drop_duplicates())==30
    event_folder=E/'recreated_named_locality_event_application_20261007'
    if (event_folder/'application_receipt.json').exists():
        event=pd.read_csv(event_folder/'accepted_qualified_physical_observations.csv')
        assert len(event)==6 and event.trajectory_id.nunique()==2 and event.nonadditive_observation.sum()==2
        event['already_in_ordinary_joint']=event.source_record_id.isin(selected_joint_ids)
        event['already_in_joint_partition_union']=event.source_record_id.isin(overlay_ids)
        frame=pd.concat([frame,event],ignore_index=True)
    for secondary in secondary_frames:
        secondary=secondary.copy()
        secondary['already_in_ordinary_joint']=secondary.source_record_id.isin(selected_joint_ids)
        secondary['already_in_joint_partition_union']=secondary.source_record_id.isin(overlay_ids)
        frame=pd.concat([frame,secondary],ignore_index=True)
    assert not frame[['scope','trajectory_id','year']].duplicated().any()
    for _,g in frame.groupby(['scope','trajectory_id']): assert set(g.year)=={2002,2010,2021}
    frame.to_csv(OUT/'qualified_physical_observations.csv',index=False)
    unique=frame[~frame.nonadditive_observation].drop_duplicates('source_record_id')
    return {'admitted_series':len(frame[['scope','trajectory_id']].drop_duplicates()),'observed_rows':len(frame),'by_year':{int(y):{'observed_population_rows':len(g),'accepted_physical_full3_and_point_rows':len(g),'row_percent_of_qualified_scope':100.0,'descriptive_population_sum_all_grains_not_national_credit':int(g.population_source_value.sum()),'secondary_or_auxiliary_nonadditive_rows':int(g.nonadditive_observation.sum()),'unique_selected_population_credit_references':int(unique.year.eq(y).sum()),'unique_selected_population_credit_sum':int(unique.loc[unique.year.eq(y),'population_source_value'].sum()),'percent_of_common_control_from_selected_credit_references_only':100*int(unique.loc[unique.year.eq(y),'population_source_value'].sum())/common_controls[int(y)]} for y,g in frame.groupby('year')},'population_sum_comparability':'Descriptive actual source-value sums across different physical grains; not additive national coverage. National credit uses selected source-ID union only.','coordinates':'Accepted physical-place representative scope points; auxiliary dates use trajectory point context, not a direct historical measurement.'}
