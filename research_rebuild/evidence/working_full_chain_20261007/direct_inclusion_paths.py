"""Separate included-in transformation paths; no child2021 count or same-place claim."""
from pathlib import Path
import math, json
import pandas as pd
from territorial_scopes import admitted


def load(folder,state,out,pin,receipt=None,followup=False):
    if receipt is None: receipt=admitted(folder,'applied_secondary_direct_included_in_transformation_path',out,pin)
    def read(accepted,candidate):
        return pd.read_csv(folder/(candidate if followup else accepted),keep_default_na=False)
    obs=read('accepted_historical_observations.csv','candidate_historical_observations.csv.gz')
    points=read('accepted_former_locality_own_points.csv','candidate_former_locality_own_points.csv.gz')
    edges=read('accepted_included_in_event_edges.csv','candidate_included_in_event_edges.csv.gz')
    context=read('actual_receiving_city_three_census_context.csv','actual_receiving_city_three_census_context.csv.gz')
    credits=read('accepted_direct_event_native_credit_union.csv','candidate_direct_event_native_credit_union.csv.gz')
    expected_observations=int(receipt['historical_native_observations'] if followup else receipt['historical_observations'])
    expected_events=int(receipt['positive_events'] if followup else receipt['events'])
    expected_context=int(receipt['receiving_city_context_observations'] if followup else receipt['receiving_context_observations'])
    assert expected_observations>0 and expected_events>0 and expected_context==3*expected_events
    assert (len(obs),len(points),len(edges),len(context),len(credits))==(expected_observations,expected_observations,expected_observations,expected_context,expected_observations)
    assert obs.scope_id.nunique()==expected_events and obs.source_record_id.is_unique
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


def build(E,state,ordinary,baseline_ids,federal,national,common,out,pin,stage=46):
    folder=E/'moscow_three_direct_inclusion_events_application_20261008'
    if not (folder/'application_receipt.json').exists(): return {'status':'not_loaded_without_root_application_receipt'}
    receipt,obs,points,edges,context,credits=load(folder,state,out,pin)
    limits=[receipt['weak_source_limit']]
    for dirname in ['absorbed_large_direct_events_followup_20261008','absorbed_residual_direct_events_next_20261008']:
        followup=E/dirname
        root_admission=followup/'root_application_receipt.json'
        if not root_admission.exists(): continue
        pin(root_admission);admission=json.loads(root_admission.read_text())
        assert admission['status']=='applied_secondary_direct_included_in_transformation_path'
        if admission['admitted_working_stage']>stage: continue
        assert admission['positive_events']>0 and admission['historical_native_observations']>0
        assert admission['receiving_city_context_observations']==3*admission['positive_events']
        assert not admission['ordinary_same_place_graph_union_allowed'] and not admission['child2021_population_assigned']
        assert not admission['boundary_harmonization_asserted'] and not admission['original_final_mixed_population_credit_allowed']
        assert pin(Path(admission['canonical_frozen_candidate_receipt']))==admission['canonical_frozen_candidate_sha256']
        for raw,claimed in admission['input_pins'].items():
            path=Path(raw)
            if out not in path.parents: assert pin(path)==claimed
        for name,claimed in admission['output_pins'].items(): assert pin(followup/name)==claimed
        extra=load(followup,state,out,pin,admission,True)
        obs,points,edges,context,credits=[pd.concat([old,new],ignore_index=True) for old,new in zip([obs,points,edges,context,credits],extra[1:])]
        assert obs.source_record_id.is_unique and credits.source_record_id.is_unique
        limits.append(admission['weak_source_limit'])
        if 'murmansk_DOC_mount_clarification' in admission: limits.append(admission['murmansk_DOC_mount_clarification'])

    ids=set(credits.source_record_id);assert ids<=set(ordinary.source_record_id)
    credits['already_in_current_original_final_mixed_union']=credits.source_record_id.isin(baseline_ids)
    years={}
    for year,frame in ordinary.groupby('census_year'):
        year=int(year);before=int(frame.loc[frame.source_record_id.isin(baseline_ids),'population'].sum())+int(federal[year])
        after=int(frame.loc[frame.source_record_id.isin(baseline_ids|ids),'population'].sum())+int(federal[year])
        years[year]={'original_final_mixed_census_population':before,'direct_inclusion_native_ID_union_net_population':after-before,'separate_transformation_path_population':after,'percent_of_common_control':100*after/common[year],'percent_of_national_control':100*after/national[year],'gap_to_99_percent_common_on_separate_axis':max(0,math.ceil(.99*common[year])-after)}
    for name,frame in [('observations',obs),('points',points),('included_in_edges',edges),('receiving_context',context),('native_credit_union',credits)]: frame.to_csv(out/f'direct_inclusion_transformation_path_{name}.csv',index=False)
    formation=formation_union(E,state,ordinary,baseline_ids,ids,federal,national,common,out,pin,stage)
    return {'sourceyear_formation_and_direct_lifecycle_union':formation,'status':'admitted_separate_direct_inclusion_transformation_path','events':obs.scope_id.nunique(),'old_native_observations':len(obs),'receiving_city_context_observations':len(context),'ordinary_same_place_asserted':False,'child2021_population_assigned':False,'whole_city_roster_complete_asserted':False,'boundary_comparability_asserted':False,'original_final_mixed_census_definition_changed':False,'source_limits':limits,'by_year':years}

def formation_union(E,state,ordinary,baseline_ids,direct_ids,federal,national,common,out,pin,stage,write=True):
    """Admitted source-year formation evidence; selected UID union, no NP3 edges."""
    if stage<49: return {'status':'not_loaded_before_root_admitted_stage49'}
    root=E/'remaining_moscow_complete_sourceyear_scopes_20261008'
    packs={};limits=[]
    for dirname in ['urban_predecessor_formation_event_candidate','mosrentgen_formation_branch_followup_candidate']:
        folder=root/dirname;rp=folder/'root_formation_application_receipt.json'
        assert rp.is_file(),('Missing explicit formation admission',str(rp))
        pin(rp);r=json.loads(rp.read_text())
        assert r['status']=='root_accepted_separate_sourceyear_municipal_formation_and_containment_path'
        assert r['intended_working_stage']<=stage and r['native_sourceUID_credit_requires_current_union']
        for flag in ['own_individual_NP2021_population_created','own2002_new_municipality_population_created','ordinary_full3_identity_asserted','fixed_modern_boundary_population_reconstructed','original_final_mixed_population_credit_allowed']: assert not r[flag]
        assert pin(Path(r['frozen_candidate_receipt']))==r['frozen_candidate_receipt_sha256']
        for p,h in r['input_pins'].items(): assert pin(Path(p))==h
        frames={}
        for name,h in r['output_pins'].items():
            assert pin(folder/name)==h
            frame=pd.read_csv(folder/name,keep_default_na=False)
            for path_field,hash_field in [('source_file','source_sha256'),('point_source_file','point_source_sha256'),('raw_file','raw_sha256'),('raw_source_file','raw_source_sha256'),('classifier_file','classifier_sha256'),('population_source_file','population_source_sha256'),('raw_source_path','raw_source_sha256')]:
                if path_field in frame and hash_field in frame:
                    for p,claimed in set(zip(frame[path_field],frame[hash_field])):
                        if p: assert pin(Path(p))==claimed
            if 'latitude' in frame:
                assert frame.latitude.between(-90,90).all() and frame.longitude.between(-180,180).all()
            if write:
                delivered=frame.copy();delivered['root_admission_status']=r['status'];delivered['root_admission_receipt']=str(rp)
                delivered.to_csv(out/f'formation_path_{dirname}_{name}',index=False)
            frames[name]=frame
        packs[dirname]=frames;limits.append(r['weak_source_limit'])
    urban=packs['urban_predecessor_formation_event_candidate'];mosr=packs['mosrentgen_formation_branch_followup_candidate']
    pgt=urban['candidate_historical_own_PGT_observations.csv'];leaf=mosr['candidate_complete2010_native_constituents.csv']
    assert len(pgt)==4 and pgt.case_id.nunique()==2 and set(pgt.census_year)=={2002,2010}
    assert pgt.point_grain.eq('own_physical_PGT').all() and not pgt.municipal_P625_projected_to_NP.any()
    assert not pgt.source_values_modified.any() and not pgt.ownNP2021_count_created.any() and not pgt.ordinary_graph_changed.any()
    assert len(leaf)==3 and leaf.year.eq(2010).all() and int(leaf.native_population.sum())==12350
    assert not leaf.individual_NP_point_assigned.any() and not leaf.source_values_modified.any() and not leaf.national2021_child_population_created.any()
    credits=[]
    for frame,yearfield,popfield,qualityfield,grain in [(pgt,'census_year','population','population_quality','own_historical_PGT_point'),(leaf,'year','native_population','native_quality','complete2010_municipal_roster_represented_at_municipal_point')]:
        for row in frame.to_dict('records'):
            sid=row['source_record_id'];native=state.by_id.loc[sid];year=int(row[yearfield])
            assert int(native.census_year)==year and math.isfinite(float(native.population)) and float(native.population)==float(row[popfield])
            assert native.population_value_quality==row[qualityfield]
            credits.append({'source_record_id':sid,'year':year,'source_population':float(native.population),'population_quality':native.population_value_quality,'credit_grain':grain,'individual_NP2021_population_created':False,'original_final_mixed_credit_allowed':False})
    credits=pd.DataFrame(credits);assert credits.source_record_id.is_unique
    assert pgt.groupby('census_year').population.sum().astype(int).to_dict()=={2002:18156,2010:19694}
    for frame in [urban['candidate_whole_municipal_observations.csv'],mosr['candidate_whole_municipal_observations.csv']]:
        assert set(frame.census_year)=={2010,2021} and not frame.ordinary_same_place.any()
        flag='national2021_native_population_credit' if 'national2021_native_population_credit' in frame else 'national2021_native_credit'
        assert frame[flag].eq(0).all()
    assert not urban['candidate_separate_formation_event_edges.csv'].ordinary_graph_changed.any()
    medges=mosr['candidate_separate_formation_and_containment_edges.csv']
    assert not medges.ordinary_same_place.any() and not medges.source_population_allocated_to_modern_subset.any() and not medges.predecessor_UID_credit_newly_added.any()
    predecessors=mosr['existing2002_complete_predecessor_native_contexts.csv']
    assert len(predecessors)==24 and predecessors.year.eq(2002).all() and predecessors.new_population_credit.eq(0).all()
    assert set(predecessors.source_record_id)<=baseline_ids
    refs=mosr['existing2002_shared_predecessor_observation_references.csv']
    assert len(refs)==2 and refs.new_population_credit.eq(0).all() and not refs.new_observation_created.any()
    prior_path=E/'moscow_complete_scope_mass_application_20261008'/'accepted_transferred_municipal_scope_observations.csv'
    pin(prior_path);prior=pd.read_csv(prior_path,keep_default_na=False)
    for row in refs.to_dict('records'):
        actual=prior[prior.observation_id.eq(row['observation_id'])];assert len(actual)==1 and float(actual.iloc[0].population)==float(row['population'])
    control=mosr['sourceyear_whole_control_and_unallocated_difference.csv'];r2010=control[control.year.eq(2010)].iloc[0]
    assert int(r2010.whole_municipal_observation)==17004 and int(r2010.control_difference_unallocated)==4654 and not control.raw_counts_redistributed.any()
    own=mosr['candidate_separate_own_properNP_physical_point.csv'];assert len(own)==1 and not own.municipal_P625_substituted.any() and not own.ownNP2021_count_created.any()
    added_ids=set(credits.source_record_id);assert added_ids<=set(ordinary.source_record_id)
    credits['already_in_original_mixed_union']=credits.source_record_id.isin(baseline_ids)
    credits['already_in_direct_lifecycle_union']=credits.source_record_id.isin(baseline_ids|direct_ids)
    years={}
    for year,frame in ordinary.groupby('census_year'):
        year=int(year);base=int(frame.loc[frame.source_record_id.isin(baseline_ids),'population'].sum())+int(federal[year])
        direct=int(frame.loc[frame.source_record_id.isin(baseline_ids|direct_ids),'population'].sum())+int(federal[year])
        combined=int(frame.loc[frame.source_record_id.isin(baseline_ids|direct_ids|added_ids),'population'].sum())+int(federal[year])
        years[year]={'original_final_mixed_census_population':base,'direct_lifecycle_population':direct,'formation_additional_native_UID_union_population':combined-direct,'lifecycle_plus_formation_population':combined,'percent_of_common_control':100*combined/common[year],'percent_of_national_control':100*combined/national[year],'gap_to_99_percent_common':max(0,math.ceil(.99*common[year])-combined)}
    if write: credits.to_csv(out/'formation_path_native_credit_union.csv',index=False)
    return {'status':'admitted_separate_sourceyear_formation_plus_direct_lifecycle_selected_UID_union','formation_cases':3,'historical_own_PGT_native_observations':4,'Mosrentgen_complete2010_native_roster_constituents':3,'own_whole_municipal_2010_2021_observations':6,'reused2002_predecessor_observation_references':2,'reused2002_predecessor_native_constituents':24,'Mosrentgen2010_control_difference_unallocated':4654,'ordinary_NP3_asserted':False,'own2002_Mosrentgen_municipality_created':False,'own_NP2021_child_population_created':False,'original_final_mixed_definition_changed':False,'source_values_and_quality_changed':False,'boundary_comparability_asserted':False,'source_limits':limits,'by_year':years,'all_three_years_99_percent_common_goal_met':all(row['percent_of_common_control']>=99 for row in years.values())}
