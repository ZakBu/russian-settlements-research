"""Load only root-admitted secondary historical physical observation packs."""
from pathlib import Path
import json, math
import pandas as pd

MISSING2002_SERIES={'temporal_missing2002_all_components_20261008':86,'temporal_missing2002_all_components_20261008/physical_grain_two_hold_followup':2}

PACKS=[
 ('wikidata_secondary_full3_application_20261007','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('current_unpointed_own_wiki_mass_application_20261007','applied_current_own_points_and_qualified_secondary_histories','qualified_accepted_secondary_own_census_history'),
 ('existing_event_scope_application_20261007','applied_reviewed_secondary_physical_three_census_scopes',None),
 ('wikidata_secondary_full3_expansion_application_20261007','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('remaining_large_own_points_followup_application_20261007','applied_current_own_points_and_qualified_secondary_histories','qualified_accepted_secondary_own_census_history'),
 ('cached_secondary_native_year_mass_application_20261008','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('additional_uncached_census_histories_application_20261008','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('own_dated2002_secondary_scope_20261008','accepted_actual_dated2002_temporal_display_separate_from_explicit_census_qualified_union','qualified_accepted_secondary_census_referenced_own_item'),
 ('temporal_missing2002_all_components_20261008','root_admitted_frozen_qualified_missing2002_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('temporal_missing2002_all_components_20261008/physical_grain_two_hold_followup','root_admitted_frozen_qualified_missing2002_series','qualified_accepted_secondary_census_referenced_own_item'),
]

def load(E,state,pin):
    packs=[];cached_hashes={}
    rawroot=Path('/workspace/settlements-raw');r2=Path('/workspace/settlements-work/sources/r2-missing')
    known_r2={'kaliningrad_2010_tom1.xlsx':r2/'kaliningrad_tom1.xlsx','murmansk_population_by_sex_municipalities.doc':r2/'murmansk_population.doc','arkhangelsk_2010_archived_original.html':r2/'arkhangelsk_2010_archived_original.html'}
    def meaningful(value):
        return pd.notna(value) and str(value) not in ['', 'None','nan','NaN']
    def resolve_source(row):
        source_path=row['source_path'];sid=row['source_record_id'];values=[source_path]
        if sid in state.by_id.index:
            selected=state.by_id.loc[sid];values += [selected.source_path,selected.source_file]
        for value in values:
            if not meaningful(value): continue
            path=Path(str(value));candidates=[path] if path.is_absolute() else [rawroot/path,E.parents[1]/path]
            if path.name in known_r2: candidates.append(known_r2[path.name])
            for candidate in candidates:
                if candidate.is_file(): return str(candidate),pin_once(candidate),'exact_cached_source_bytes'
        assert sid in state.by_id.index,('Missing admitted secondary raw-source bytes',source_path)
        return '','','original_native_source_cache_unresolved_imported_provenance_retained'
    def pin_once(path):
        path=Path(path);key=str(path)
        if key not in cached_hashes: cached_hashes[key]=pin(path)
        return cached_hashes[key]
    for dirname,status,decision in PACKS:
        folder=E/dirname;rp=folder/('qualified_application_receipt.json' if dirname in MISSING2002_SERIES else 'application_receipt.json')
        if not rp.exists(): continue
        pin(rp);receipt=json.loads(rp.read_text())
        assert status is not None, ('unconfigured root admission status',dirname)
        if dirname in MISSING2002_SERIES:
            assert receipt['qualified_series']==MISSING2002_SERIES[dirname] and receipt['qualified_observations']==3*MISSING2002_SERIES[dirname]
            assert receipt['ordinary_NP3_edges_or_points_added']==0 and not receipt['historical_native2002_UID_binding_asserted']
            for proof in ['report_helper.py','validate_full_sources.py']: pin_once(folder/proof)
            if MISSING2002_SERIES[dirname]==86: pin_once(folder/'cached_reference_item_witness.csv')
        else: assert receipt['status']==status,(dirname,receipt['status'])
        name='accepted_qualified_physical_observations.csv'
        outputs=receipt.get('outputs',receipt.get('output_hashes',{}))
        assert pin(folder/name)==outputs[name]
        for filename,h in outputs.items(): assert pin_once(folder/filename)==h
        for filename,h in receipt.get('input_hashes',receipt.get('input_pins',{})).items():
            path=Path(filename)
            if E/'working_full_chain_20261007' not in path.parents: assert pin_once(path)==h
        frame=pd.read_csv(folder/name,keep_default_na=False)
        if 'point_provenance.csv' in outputs:
            proof=pd.read_csv(folder/'point_provenance.csv',keep_default_na=False)
            assert not proof.trajectory_id.duplicated().any()
            frame=frame.merge(proof,on='trajectory_id',how='left',validate='many_to_one')
            assert len(frame)==3*len(proof)
        if 'decision_status' not in frame: frame['decision_status']=receipt.get('decision_status',status)
        for canonical,raw in [('source_path','raw_source_file'),('source_sha256','raw_source_sha256'),('source_locator','raw_source_locator')]:
            if canonical not in frame: frame[canonical]=frame[raw]
        assert len(frame) and not frame[['scope','trajectory_id','year']].duplicated().any()
        assert not frame.ordinary_NP3_asserted.any() and not frame.boundary_comparability_asserted.any()
        for field in ['accepted_physical_three_observed_census_year_path','accepted_scoped_representative_point']:
            if field not in frame: frame[field]=True
            assert frame[field].all()
        if decision: assert frame.decision_status.eq(decision).all()
        if dirname=='own_dated2002_secondary_scope_20261008':
            assert len(frame)==69 and frame.trajectory_id.nunique()==23
            assert frame.accepted_physical_three_observed_census_year_path.all()
            historical=frame[frame.year.eq(2002)]
            assert historical.source_population_is_census_known.all()
            assert historical.census_proof_class.eq('exact_or_explicit_census_reference').all()
        if dirname in MISSING2002_SERIES:
            assert len(frame)==3*MISSING2002_SERIES[dirname] and frame.trajectory_id.nunique()==MISSING2002_SERIES[dirname]
            historical=frame[frame.year.eq(2002)]
            assert historical.nonadditive_observation.all() and historical.source_record_id.eq('').all()
            assert historical.census_proof_class.eq('literal_cached2002_census_reference_label_or_title_or_URL').all()
        for _,group in frame.groupby(['scope','trajectory_id']):
            assert len(group)==3 and set(group.year)=={2002,2010,2021}
        actual_sources=[]
        for row in frame.to_dict('records'):
            assert math.isfinite(float(row['population_source_value']))
            assert -90<=float(row['latitude'])<=90 and -180<=float(row['longitude'])<=180
            actual_path,actual_hash,actual_status=resolve_source(row);actual_sources.append((actual_path,actual_hash,actual_status))
            if meaningful(row['source_sha256']) and actual_hash: assert actual_hash==row['source_sha256']
            for path_field,hash_field in [('secondary_source_path','secondary_source_sha256')]:
                if row.get(path_field): assert pin_once(Path(row[path_field]))==row[hash_field]
            assert pin_once(Path(row['point_origin_file']))==row['point_origin_sha256']
            year=int(row['year']);sid=row['source_record_id']
            if row['nonadditive_observation']:
                assert year in [2002,2010] and not sid
            else:
                assert sid in state.by_id.index
                selected=state.by_id.loc[sid]
                assert int(selected.census_year)==year and int(selected.population)==int(row['population_source_value'])
                assert selected.population_value_quality==row['population_quality']
                if dirname=='existing_event_scope_application_20261007':
                    assert state.uf.find(sid)==state.uf.find(row['current_source_record_id'])
            if dirname in ['cached_secondary_native_year_mass_application_20261008','additional_uncached_census_histories_application_20261008','own_dated2002_secondary_scope_20261008']+list(MISSING2002_SERIES):
                if not row['nonadditive_observation']:
                    assert state.uf.find(sid)==state.uf.find(row['native_current_source_record_id'])
                    if year!=2021: assert row['historical_native_selected_source_ID_binding_asserted'] and row['native_existing_component_binding']
                else:
                    assert row['census_proof_class'].startswith('explicit_') or row['census_proof_class'] in ['exact_P585_census_date','exact_or_explicit_census_reference','literal_cached2002_census_reference_label_or_title_or_URL']
            if dirname in ['wikidata_secondary_full3_application_20261007','wikidata_secondary_full3_expansion_application_20261007']:
                assert row['nonadditive_observation']==(year!=2021)
                if dirname=='wikidata_secondary_full3_application_20261007':
                    assert int(row['date_precision'])==9 and row['census_reference_ids']
                elif year in [2002,2010]:
                    assert int(row['date_precision'])==9 and row['census_proof_class'].startswith('explicit_')
                    assert json.loads(row['P248_ids_json']) or json.loads(row['census_reference_titles_json']) or json.loads(row['reference_urls_json'])
        frame[['source_actual_path','source_actual_sha256','source_actual_resolution_status']]=pd.DataFrame(actual_sources,index=frame.index)
        packs.append((dirname,receipt,frame))
    override_folder=E/'native_from_secondary_census_binding_application_20261007'
    if (override_folder/'application_receipt.json').exists():
        receipt_path=override_folder/'application_receipt.json';pin(receipt_path)
        override_receipt=json.loads(receipt_path.read_text())
        assert override_receipt['status']=='applied_native_history_qualified_sidecar_accepted_component_binding'
        for filename,h in override_receipt['outputs'].items(): assert pin_once(override_folder/filename)==h
        replacements=pd.read_csv(override_folder/'accepted_qualified_historical_replacements.csv',keep_default_na=False)
        alternatives=pd.read_csv(override_folder/'retained_secondary_historical_alternatives.csv',keep_default_na=False)
        keys=['scope','trajectory_id','year']
        assert len(replacements)==len(alternatives)==201 and not replacements[keys].duplicated().any()
        assert replacements.year.value_counts().to_dict()=={2010:122,2002:79}
        assert not replacements.nonadditive_observation.any() and not replacements.ordinary_NP3_asserted.any()
        assert not replacements.ordinary_graph_modified.any() and not replacements.ordinary_point_ledger_modified.any()
        assert not replacements.boundary_comparability_asserted.any()
        assert alternatives.nonadditive_observation.all() and alternatives.source_record_id.eq('').all()
        assert int(replacements.population_difference_flag.sum())==91 and int(replacements.native_population_scope_missing_legacy_flag.sum())==77
        native_actual=[]
        for row in replacements.to_dict('records'):
            sid=row['source_record_id'];current=row['bound_current_native_source_record_id'];selected=state.by_id.loc[sid]
            assert state.uf.find(sid)==state.uf.find(current)
            assert int(selected.census_year)==int(row['year']) and int(selected.population)==int(row['population_source_value'])
            assert selected.population_value_quality==row['population_quality']
            assert float(row['max_component_point_distance_km'])<=5
            actual_path,actual_hash,actual_status=resolve_source(row);native_actual.append((actual_path,actual_hash,actual_status))
            if meaningful(row['source_sha256']) and actual_hash: assert actual_hash==row['source_sha256']
            assert pin_once(Path(row['point_origin_file']))==row['point_origin_sha256']
        replacements[['source_actual_path','source_actual_sha256','source_actual_resolution_status']]=pd.DataFrame(native_actual,index=replacements.index)
        for row in alternatives.to_dict('records'):
            assert pin_once(Path(row['source_path']))==row['source_sha256']
        index=next(i for i,pack in enumerate(packs) if pack[0]=='wikidata_secondary_full3_expansion_application_20261007')
        dirname,packet_receipt,parent=packs[index];parent=parent.set_index(keys);replace=replacements.set_index(keys);alt=alternatives.set_index(keys)
        assert set(replace.index)==set(alt.index) and set(replace.index)<=set(parent.index)
        for key in replace.index:
            original=parent.loc[key];replacement=replace.loc[key];alternative=alt.loc[key]
            assert original.nonadditive_observation and not original.source_record_id
            assert float(original.population_source_value)==float(alternative.population_source_value)
            assert int(replacement.population_source_value)==int(alternative.preferred_native_population)
            trajectory_current=parent.loc[(key[0],key[1],2021),'source_record_id']
            assert trajectory_current==replacement.bound_current_native_source_record_id
        for column in replace.columns:
            if column not in parent: parent[column]=''
        for key in replace.index:
            for column in replace.columns: parent.loc[key,column]=replace.loc[key,column]
        parent=parent.reset_index()
        assert len(parent)==1365 and parent.trajectory_id.nunique()==455
        parent.to_csv(E/'working_full_chain_20261007/native_history_applied_expansion_observations.csv',index=False)
        alternatives.to_csv(E/'working_full_chain_20261007/retained_secondary_historical_alternatives.csv',index=False)
        packs[index]=(dirname,packet_receipt,parent)
    native7_folder=E/'old_native_from_existing_secondary_binding_application_20261007'
    if (native7_folder/'application_receipt.json').exists():
        rp=native7_folder/'application_receipt.json';pin(rp);native7_receipt=json.loads(rp.read_text())
        assert native7_receipt['status']=='applied_exact_own_census_native_source_bindings_direct_county_and_accepted_flanking_anchors'
        for filename,h in native7_receipt['outputs'].items(): assert pin_once(native7_folder/filename)==h
        refs=pd.read_csv(native7_folder/'accepted_native_reference_credit_union.csv',keep_default_na=False)
        assert len(refs)==7 and refs.year.value_counts().to_dict()=={2010:5,2002:2}
        assert not refs.source_population_values_modified.any() and refs.accepted_native_reference_to_existing_qualified_full3.all()
        index=next(i for i,pack in enumerate(packs) if pack[0]=='existing_event_scope_application_20261007')
        dirname,parent_receipt,parent=packs[index];parent=parent.set_index(['scope','trajectory_id','year'])
        alternatives=[]
        for ref in refs.to_dict('records'):
            key=(ref['scope'],ref['trajectory_id'],int(ref['year']));original=parent.loc[key].copy()
            assert original.nonadditive_observation and not original.source_record_id
            sid=ref['source_record_id'];current=original.current_source_record_id;selected=state.by_id.loc[sid]
            assert state.uf.find(sid)==state.uf.find(current)
            assert int(selected.census_year)==int(ref['year']) and int(selected.population)==int(ref['population_source_value'])
            alternate=original.to_dict();alternate.update({'scope':key[0],'trajectory_id':key[1],'year':key[2],'preferred_native_source_record_id':sid,'preferred_native_population':int(selected.population),'preferred_native_population_quality':selected.population_value_quality,'population_difference_flag':float(original.population_source_value)!=float(selected.population)})
            alternatives.append(alternate)
            row=original.to_dict();row.update({'scope':key[0],'trajectory_id':key[1],'year':key[2],'source_record_id':sid,'population_source_value':int(selected.population),'population_quality':selected.population_value_quality,'nonadditive_observation':False,'source_path':selected.source_path,'source_sha256':selected.source_sha256,'source_locator':selected.source_locator})
            actual_path,actual_hash,actual_status=resolve_source(row)
            update={'source_record_id':sid,'population_source_value':int(selected.population),'population_quality':selected.population_value_quality,'nonadditive_observation':False,'source_path':selected.source_path,'source_sha256':selected.source_sha256,'source_locator':selected.source_locator,'source_actual_path':actual_path,'source_actual_sha256':actual_hash,'source_actual_resolution_status':actual_status,'grain':'existing selected native census own-NP observation with root-admitted direct county or flanking-anchor binding','native_binding_proof_tier':ref['proof_tier'],'secondary_population_alternative':original.population_source_value,'population_difference_flag':float(original.population_source_value)!=float(selected.population)}
            for column,value in update.items():
                if column not in parent: parent[column]=''
                parent.loc[key,column]=value
        parent=parent.reset_index();assert len(parent)==1194 and parent.trajectory_id.nunique()==398
        pd.DataFrame(alternatives).to_csv(E/'working_full_chain_20261007/old_native7_retained_secondary_historical_alternatives.csv',index=False)
        packs[index]=(dirname,parent_receipt,parent)
    correction_folder=E/'full3_conflicting_modern_point_recovery_application_20261007'
    if (correction_folder/'application_receipt.json').exists():
        rp=correction_folder/'application_receipt.json';pin(rp);correction=json.loads(rp.read_text())
        assert correction['frozen_baseline_points_rejected']==0 and correction['accepted_repaired_full3_components']==23
        for filename,h in correction['output_pins'].items(): assert pin_once(correction_folder/filename)==h
        for filename,h in correction['independent_cached_binding_source_pins'].items(): assert pin_once(Path(filename))==h
        targets=set(pd.read_csv(correction_folder/'accepted_point_use_delta.csv').target_source_record_id)
        later_folder=E/'current_large_component_point_recovery_application_20261008'
        if later_folder/'accepted_point_use_delta.csv' in state.inputs:
            later_receipt_path=later_folder/'application_receipt.json';pin(later_receipt_path)
            later_receipt=json.loads(later_receipt_path.read_text())
            assert later_receipt['status']=='applied_coordinate_claim_recovery_existing_full_native_components'
            for filename,h in later_receipt['outputs'].items(): assert pin_once(later_folder/filename)==h
            targets |= set(pd.read_csv(later_folder/'accepted_point_use_delta.csv').target_source_record_id)
        retained=[]
        for index,(dirname,receipt,frame) in enumerate(packs):
            frame=frame.copy()
            for (scope,trajectory),group in frame.groupby(['scope','trajectory_id']):
                current=group.loc[group.year.eq(2021),'source_record_id'].iloc[0]
                if current not in targets: continue
                active=state.point_rows[current]
                for row_index in group.index:
                    old=frame.loc[row_index]
                    retained.append({'scope':scope,'trajectory_id':trajectory,'year':int(old.year),'current_native_source_record_id':current,'old_latitude':old.latitude,'old_longitude':old.longitude,'old_point_origin_file':old.point_origin_file,'old_point_origin_sha256':old.point_origin_sha256,'old_point_origin_locator':old.point_origin_locator,'old_point_binding_json':old.get('point_binding_json',''),'status':'retained_original_context_superseded_by_root_admitted_own_modern_point_correction'})
                    for column in ['latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_ledger_path']:
                        if column not in frame: frame[column]=''
                        frame.loc[row_index,column]=active.get(column,'')
                    if 'point_binding_json' not in frame: frame['point_binding_json']=''
                    frame.loc[row_index,'point_binding_json']=json.dumps(active,ensure_ascii=False,default=str)
                    if 'representative_point_context_status' not in frame: frame['representative_point_context_status']=''
                    frame.loc[row_index,'representative_point_context_status']='root_admitted_corrected_current_own_point_retrospective_context_not_historical_measurement'
                assert pin_once(Path(active['point_origin_file']))==active['point_origin_sha256']
            packs[index]=(dirname,receipt,frame)
        pd.DataFrame(retained,columns=['scope','trajectory_id','year','current_native_source_record_id','old_latitude','old_longitude','old_point_origin_file','old_point_origin_sha256','old_point_origin_locator','old_point_binding_json','status']).to_csv(E/'working_full_chain_20261007/qualified_point_context_retained_alternatives.csv',index=False)
    if (override_folder/'application_receipt.json').exists():
        final_expansion=next(frame for dirname,_,frame in packs if dirname=='wikidata_secondary_full3_expansion_application_20261007')
        final_expansion.to_csv(E/'working_full_chain_20261007/native_history_applied_expansion_observations.csv',index=False)
    return packs
