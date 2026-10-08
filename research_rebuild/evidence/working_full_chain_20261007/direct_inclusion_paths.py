"""Separate included-in transformation paths; no child2021 count or same-place claim."""
from pathlib import Path
import math
import pandas as pd
from territorial_scopes import admitted


def load(folder,state,out,pin):
    receipt=admitted(folder,'applied_secondary_direct_included_in_transformation_path',out,pin)
    obs=pd.read_csv(folder/'accepted_historical_observations.csv',keep_default_na=False)
    points=pd.read_csv(folder/'accepted_former_locality_own_points.csv',keep_default_na=False)
    edges=pd.read_csv(folder/'accepted_included_in_event_edges.csv',keep_default_na=False)
    context=pd.read_csv(folder/'actual_receiving_city_three_census_context.csv',keep_default_na=False)
    credits=pd.read_csv(folder/'accepted_direct_event_native_credit_union.csv',keep_default_na=False)
    assert (len(obs),len(points),len(edges),len(context),len(credits))==(4,4,4,9,4)
    assert obs.scope_id.nunique()==3 and obs.source_record_id.is_unique
    assert not obs.child_2021_population_assigned.any() and not obs.whole_city_roster_closure_asserted.any()
    assert not obs.same_place_identity_asserted.any() and not obs.population_boundary_comparability_asserted.any()
    assert not obs.is_additive_to_original_final_mixed_census_axis.any()
    assert edges.relation.eq('included_in').all() and not edges.same_place.any() and not edges.graph_union_allowed.any()
    assert set(obs.source_record_id)==set(points.target_source_record_id)==set(edges.from_source_record_id)==set(credits.source_record_id)
    assert credits.qualifies_direct_transformation_path.all() and credits.own_historical_point_verified.all()
    assert credits.receiving_city_actual_2002_2010_2021_context_verified.all()
    assert not credits.is_additive_to_original_final_mixed_census_axis.any()
    assert context.is_receiving_city_context_only.all() and context.new_national_credit_population.eq(0).all()
    assert not context.child_count_substituted.any()
    for scope,frame in context.groupby('scope_id'):
        assert len(frame)==3 and set(frame.census_year)=={2002,2010,2021}
        if hasattr(state,'uf'): assert len({state.uf.find(sid) for sid in frame.source_record_id})==1
    for row in context.to_dict('records'):
        native=state.by_id.loc[row['source_record_id']]
        assert int(native.census_year)==int(row['census_year']) and float(native.population)==float(row['population'])
        assert native.population_value_quality==row['population_value_quality']
        active=state.point_rows[row['source_record_id']]
        assert (active['latitude'],active['longitude'])==(float(row['latitude']),float(row['longitude']))
    for row in obs.to_dict('records'):
        native=state.by_id.loc[row['source_record_id']]
        assert int(row['year']) in [2002,2010] and int(native.census_year)==int(row['year'])
        assert math.isfinite(float(native.population)) and float(native.population)==float(row['native_population'])
        assert native.population_value_quality==row['native_population_quality'] and row['own_point']
        point=points[points.target_source_record_id.eq(row['source_record_id'])].iloc[0]
        assert point.own_locality_point and not point.recipient_point_assigned_to_child
        assert (float(point.latitude),float(point.longitude))==(float(row['latitude']),float(row['longitude']))
        assert pin(Path(point.point_origin_file))==point.point_origin_sha256
        assert -90<=float(point.latitude)<=90 and -180<=float(point.longitude)<=180
        edge=edges[edges.from_source_record_id.eq(row['source_record_id'])].iloc[0]
        assert edge.to_source_record_id==row['receiving_city_2021_source_record_id'] and edge.event_date==row['event_date']
        assert pin(Path(edge.event_source_file))==edge.event_source_sha256
        parent=context[context.scope_id.eq(row['scope_id'])&context.census_year.eq(2021)].iloc[0]
        assert parent.source_record_id==edge.to_source_record_id and float(parent.population)==float(row['receiving_city_2021_count_context_only'])
        credit=credits[credits.source_record_id.eq(row['source_record_id'])].iloc[0]
        assert int(credit.year)==int(row['year']) and float(credit.source_population)==float(native.population)
    return receipt,obs,points,edges,context,credits


def build(E,state,ordinary,baseline_ids,federal,national,common,out,pin):
    folder=E/'moscow_three_direct_inclusion_events_application_20261008'
    if not (folder/'application_receipt.json').exists(): return {'status':'not_loaded_without_root_application_receipt'}
    receipt,obs,points,edges,context,credits=load(folder,state,out,pin)
    ids=set(credits.source_record_id);assert ids<=set(ordinary.source_record_id)
    credits['already_in_current_original_final_mixed_union']=credits.source_record_id.isin(baseline_ids)
    years={}
    for year,frame in ordinary.groupby('census_year'):
        year=int(year);before=int(frame.loc[frame.source_record_id.isin(baseline_ids),'population'].sum())+int(federal[year])
        after=int(frame.loc[frame.source_record_id.isin(baseline_ids|ids),'population'].sum())+int(federal[year])
        years[year]={'original_final_mixed_census_population':before,'direct_inclusion_native_ID_union_net_population':after-before,'separate_transformation_path_population':after,'percent_of_common_control':100*after/common[year],'percent_of_national_control':100*after/national[year],'gap_to_99_percent_common_on_separate_axis':max(0,math.ceil(.99*common[year])-after)}
    for name,frame in [('observations',obs),('points',points),('included_in_edges',edges),('receiving_context',context),('native_credit_union',credits)]: frame.to_csv(out/f'direct_inclusion_transformation_path_{name}.csv',index=False)
    return {'status':'admitted_separate_direct_inclusion_transformation_path','events':3,'old_native_observations':4,'receiving_city_context_observations':9,'ordinary_same_place_asserted':False,'child2021_population_assigned':False,'whole_city_roster_complete_asserted':False,'boundary_comparability_asserted':False,'original_final_mixed_census_definition_changed':False,'source_limits':receipt['weak_source_limit'],'by_year':years}
