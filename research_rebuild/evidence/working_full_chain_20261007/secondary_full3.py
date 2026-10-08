"""Load only root-admitted secondary historical physical observation packs."""
from pathlib import Path
import json, math, re, hashlib, subprocess
import pandas as pd

MISSING2002_SERIES={'cached_current_bound_secondary2002_mass_20261008':26,'temporal_missing2002_all_components_20261008':86,'temporal_missing2002_all_components_20261008/physical_grain_two_hold_followup':2}

PACKS=[
 ('cached_current_bound_secondary2002_mass_20261008','root_admitted_frozen_qualified_missing2002_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('uncached_missing2010_dated_source_mass_20261008','accepted_uncached2010_native_route_and_disjoint_secondary_census_fallback','qualified_accepted_secondary_census_referenced_own_item'),
 ('cached_missing2010_dated_source_mass_20261008','accepted_cached2010_native_route_and_disjoint_secondary_census_fallback','qualified_accepted_secondary_census_referenced_own_item'),
 ('wikidata_secondary_full3_application_20261007','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('current_unpointed_own_wiki_mass_application_20261007','applied_current_own_points_and_qualified_secondary_histories','qualified_accepted_secondary_own_census_history'),
 ('existing_event_scope_application_20261007','applied_reviewed_secondary_physical_three_census_scopes',None),
 ('wikidata_secondary_full3_expansion_application_20261007','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('remaining_large_own_points_followup_application_20261007','applied_current_own_points_and_qualified_secondary_histories','qualified_accepted_secondary_own_census_history'),
 ('cached_secondary_native_year_mass_application_20261008','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('additional_uncached_census_histories_application_20261008','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('own_uncached2002_secondary_scope_20261008','accepted_actual_dated2002_temporal_display_separate_from_explicit_census_qualified_union','qualified_accepted_secondary_census_referenced_own_item'),
 ('own_dated2002_secondary_scope_20261008','accepted_actual_dated2002_temporal_display_separate_from_explicit_census_qualified_union','qualified_accepted_secondary_census_referenced_own_item'),
 ('temporal_missing2002_all_components_20261008','root_admitted_frozen_qualified_missing2002_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('temporal_missing2002_all_components_20261008/physical_grain_two_hold_followup','root_admitted_frozen_qualified_missing2002_series','qualified_accepted_secondary_census_referenced_own_item'),
]

def load(E,state,pin,stage=55):
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
        if dirname=='cached_current_bound_secondary2002_mass_20261008':
            folder=E/dirname;root_path=folder/'root_application_receipt.json'
            if stage<57: continue
            assert root_path.is_file(),('Missing root-qualified secondary26 admission',str(root_path))
            pin(root_path);root_admission=json.loads(root_path.read_text())
            assert root_admission['status']==status and root_admission['intended_working_stage']<=stage
            assert root_admission['source_replay_passed'] and root_admission['selected_source_ID_credits_are_union_not_secondary_population']
            assert pin(folder/'qualified_application_receipt.json')==root_admission['source_application_sha256']
            assert not root_admission['ordinary_NP3_edges_or_points_added'] and not root_admission['historical_native2002_UID_binding_asserted']
            assert not root_admission['population_primary_reference_verified'] and not root_admission['boundary_comparability_asserted']
            for filename,h in root_admission['outputs'].items(): assert pin_once(folder/filename)==h
        folder=E/dirname;rp=folder/('qualified_application_receipt.json' if dirname in MISSING2002_SERIES else 'application_receipt.json')
        if not rp.exists(): continue
        pin(rp);receipt=json.loads(rp.read_text())
        assert status is not None, ('unconfigured root admission status',dirname)
        if dirname in MISSING2002_SERIES:
            assert receipt['qualified_series']==MISSING2002_SERIES[dirname] and receipt['qualified_observations']==3*MISSING2002_SERIES[dirname]
            assert receipt['ordinary_NP3_edges_or_points_added']==0 and not receipt['historical_native2002_UID_binding_asserted']
            proofs=['prepare_qualified.py','verify.py'] if dirname=='cached_current_bound_secondary2002_mass_20261008' else ['report_helper.py','validate_full_sources.py']
            for proof in proofs: pin_once(folder/proof)
            if MISSING2002_SERIES[dirname] in [86,26]: pin_once(folder/'cached_reference_item_witness.csv')
        else: assert receipt['status']==status,(dirname,receipt['status'])
        name='accepted_qualified_physical_observations.csv'
        outputs=receipt.get('outputs',receipt.get('output_hashes',receipt.get('output_pins',{})))
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
        if dirname in ['own_dated2002_secondary_scope_20261008','own_uncached2002_secondary_scope_20261008']:
            expected_series=37 if dirname=='own_uncached2002_secondary_scope_20261008' else 23
            assert len(frame)==3*expected_series and frame.trajectory_id.nunique()==expected_series
            assert frame.accepted_physical_three_observed_census_year_path.all()
            historical=frame[frame.year.eq(2002)]
            assert historical.source_population_is_census_known.all()
            if dirname=='own_uncached2002_secondary_scope_20261008':
                assert historical.census_proof_class.isin(['actual_P585_year2002_with_literal_P459_census_method','literal2002_census_reference_title_label_or_URL']).all()
            else: assert historical.census_proof_class.eq('exact_or_explicit_census_reference').all()
        if dirname in ['cached_missing2010_dated_source_mass_20261008','uncached_missing2010_dated_source_mass_20261008']:
            expected_series=242 if dirname.startswith('uncached_') else 120
            assert receipt['qualified_series']==expected_series and receipt['qualified_observations']==3*expected_series
            assert len(frame)==3*expected_series and frame.trajectory_id.nunique()==expected_series
            missing=frame[frame.year.eq(2010)]
            assert missing.nonadditive_observation.all() and missing.source_record_id.eq('').all() and missing.source_population_is_census_known.all()
            assert missing.census_proof_class.eq('actual2010year_with_literal_census_method').all()
        if dirname in MISSING2002_SERIES:
            assert len(frame)==3*MISSING2002_SERIES[dirname] and frame.trajectory_id.nunique()==MISSING2002_SERIES[dirname]
            historical=frame[frame.year.eq(2002)]
            assert historical.nonadditive_observation.all() and historical.source_record_id.eq('').all()
            allowed=['literal_cached2002_census_reference_label_or_title_or_URL']
            if dirname=='cached_current_bound_secondary2002_mass_20261008': allowed+=['actual_P585_year2002_with_literal_P459_census_method']
            assert historical.census_proof_class.isin(allowed).all()
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
            if dirname in ['cached_secondary_native_year_mass_application_20261008','additional_uncached_census_histories_application_20261008','own_dated2002_secondary_scope_20261008','own_uncached2002_secondary_scope_20261008','cached_missing2010_dated_source_mass_20261008','uncached_missing2010_dated_source_mass_20261008']+list(MISSING2002_SERIES):
                if not row['nonadditive_observation']:
                    assert state.uf.find(sid)==state.uf.find(row['native_current_source_record_id'])
                    if year!=2021: assert row['historical_native_selected_source_ID_binding_asserted'] and row['native_existing_component_binding']
                else:
                    assert row['census_proof_class'].startswith('explicit_') or row['census_proof_class'] in ['exact_P585_census_date','exact_or_explicit_census_reference','literal_cached2002_census_reference_label_or_title_or_URL','actual_P585_year2002_with_literal_P459_census_method','literal2002_census_reference_title_label_or_URL','actual2010year_with_literal_census_method']
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
                # Later frozen rejections take precedence over inherited recovery overlays.
                if stage>=57 and current not in state.point_rows: continue
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
    if stage>=57:
        packs=project_corrected_sidecar_points(E,state,pin,packs,stage=stage)
    if (override_folder/'application_receipt.json').exists():
        final_expansion=next(frame for dirname,_,frame in packs if dirname=='wikidata_secondary_full3_expansion_application_20261007')
        final_expansion.to_csv(E/'working_full_chain_20261007/native_history_applied_expansion_observations.csv',index=False)
    return packs


def project_corrected_sidecar_points(E,state,pin,packs,stage=57):
    """Project only root-decided own points; hold complete source histories otherwise."""
    assert verify_exact_provider_carrier_regression()
    out=E/'working_full_chain_20261007';folder=E/'combined_ownpoint_correction_application_20261008'
    rp=folder/'application_receipt.json';root_hash=pin(rp);receipt=json.loads(rp.read_text())
    assert receipt['status']=='root_applied_ownpoint_rejections_and_independent_recoveries'
    assert receipt['intended_working_stage']==57
    audit_path=Path(receipt['own_population_identity_audit_path'])
    assert pin(audit_path)==receipt['own_population_identity_audit_sha256']
    for filename,h in receipt['outputs'].items(): assert pin(folder/filename)==h
    audit=json.loads(audit_path.read_text())
    for source,claimed in audit['input_pins'].items(): assert pin(Path(source))==claimed
    for source,claimed in audit['checked_sidecar_sha256'].items():
        path=Path(source)
        if out in path.parents:
            blob=subprocess.run(['git','show','fce754a35ddd2a182b242d6d415797e177860532:'+str(path.relative_to(out.parents[2]))],cwd=out.parents[2],capture_output=True)
            assert blob.returncode==0 and hashlib.sha256(blob.stdout).hexdigest()==claimed,('Exact historical55 audit source mismatch',source)
        else: assert pin(path)==claimed
    rejected=set(pd.read_csv(folder/'point_use_rejections.csv.gz',keep_default_na=False).target_source_record_id)
    decisions={(r['scope'],r['trajectory_id']):r for r in receipt['qualified_sidecar_projection_decisions']}
    assert len(decisions)==7
    root59_hash=None
    if stage>=59:
        folder59=E/'corrected_ownpoint_cached_history_followup_20261008';rp59=folder59/'root_application_receipt.json';root59_hash=pin(rp59);root59=json.loads(rp59.read_text())
        assert root59['status']=='root_applied_independent_point_corroboration_or_hold' and root59['intended_working_stage']==59
        assert pin(folder59/'application_receipt.json')==root59['source_application_sha256']
        for name,h in root59['outputs'].items(): assert pin(folder59/name)==h
        actions_path=Path(root59['qualified_scope_point_actions_path']);assert pin(actions_path)==root59['qualified_scope_point_actions_sha256']
        actions=pd.read_csv(actions_path,keep_default_na=False)
        assert len(actions)==2
        for action in actions.to_dict('records'):
            key=next(k for k in decisions if k[1]==action['trajectory_id']);decision=decisions[key].copy()
            assert decision['current_source_record_id']==action['native_current_source_record_id'] and action['identity_and_population_values_unchanged']
            decision['decision']='hold' if action['decision'].startswith('hold_') else 'replace_independent_own_point'
            decision['reason']='root59 '+action['decision']
            decision['replacement_target_source_record_id']='' if decision['decision']=='hold' else action['native_current_source_record_id']
            decision['root59_point_json']=action['point_json'];decisions[key]=decision
    root60_hash=None
    if stage>=60:
        rp60=E/'combined_inherited_ownpoint_application_20261008/application_receipt.json';root60_hash=pin(rp60);root60=json.loads(rp60.read_text())
        assert root60['status']=='root_composed_independent_ownpoint_representatives_and_explicit_holds'
        for update in root60.get('qualified_sidecar_projection_decisions',[]):
            key=(update['scope'],update['trajectory_id']);assert key in decisions
            assert update['current_source_record_id']==decisions[key]['current_source_record_id']
            assert update['decision'] in ['hold','replace_independent_own_point']
            if update['decision']=='replace_independent_own_point':
                assert update['own_population_identity_rechecked'] and not update['trajectory_id'].endswith('Q19820596')
            old=decisions[key];decisions[key]=dict(old,**update);decisions[key]['root59_point_json']=''
    held=[];retained=[];seen=set();result=[]
    for dirname,source_receipt,frame in packs:
        frame=frame.copy();drop=[]
        for key,group in frame.groupby(['scope','trajectory_id']):
            if key not in decisions: continue
            decision=decisions[key];seen.add(key)
            assert len(group)==3 and set(group.year)=={2002,2010,2021}
            current=group.loc[group.year.eq(2021),'source_record_id'].iloc[0]
            assert current==decision['current_source_record_id']
            original=group.copy();original['point_correction_root_receipt_sha256']=root_hash
            original['point_correction_reason']=decision['reason']
            if decision['decision']=='hold':
                original['point_correction_status']='held_source_observations_no_admitted_point_or_joint_credit'
                original['accepted_physical_three_observed_census_year_path']=False
                original['accepted_scoped_representative_point']=False
                original['joint_selected_source_ID_credit_admitted']=False
                held.append(original);drop.extend(group.index);continue
            assert decision['decision']=='replace_independent_own_point'
            assert decision['replacement_target_source_record_id']==current and current in state.point_rows
            active=state.point_rows[current]
            if stage<60 or not decision.get('own_population_identity_rechecked'):
                assert active['point_origin_kind'] in ['independent_raw_own_coded_GeoKLADR2011_locality_point','independent_owncoded_cached_Wikidata_point']
            else:
                assert active['point_origin_kind']!='tochno_2021_dadata_raw_parquet_point' and 'wiki' in str(active['point_origin_kind']).lower()
            if decision.get('root59_point_json'):
                proof=json.loads(decision['root59_point_json'])
                for field in ['latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator']: assert active[field]==proof[field]
            assert pin(Path(active['point_origin_file']))==active['point_origin_sha256']
            original['point_correction_status']='retained_original_rejected_point_context_superseded_by_independent_own_coded_point'
            retained.append(original)
            for column in ['latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator']:
                frame.loc[group.index,column]=active[column]
            frame.loc[group.index,'point_binding_json']=json.dumps(active,ensure_ascii=False,default=str)
            frame.loc[group.index,'retrospective_point_use_is_continuity_inference']=True
            frame.loc[group.index,'representative_point_context_status']='root57_independent_own_coded_point_population_identity_rechecked_not_historical_coordinate_measurement'
        result.append((dirname,source_receipt,frame.drop(index=drop)))
    assert seen==set(decisions)
    for _,_,frame in result:
        for row in frame.to_dict('records'):
            assert raw_provider_carrier(row) not in rejected,('Rejected raw provider point recreated by qualified overlay',row['trajectory_id'])
    held_frame=pd.concat(held,ignore_index=True);retained_frame=pd.concat(retained,ignore_index=True)
    expected_held=sum(d['decision']=='hold' for d in decisions.values())
    assert len(held_frame)==3*expected_held and held_frame.trajectory_id.nunique()==expected_held
    assert len(retained_frame)==3*(7-expected_held) and retained_frame.trajectory_id.nunique()==7-expected_held
    held_frame.to_csv(out/'qualified_point_correction57_held_source_observations.csv',index=False)
    retained_frame.to_csv(out/'qualified_point_correction57_retained_rejected_point_context.csv',index=False)
    admission={'status':'root_admitted_source_specific_qualified_point_projection_and_identity_holds',
        'intended_stage':stage,'root60_application_sha256':root60_hash,'root59_application_sha256':root59_hash,'root_application_receipt':str(rp),'root_application_sha256':root_hash,
        'own_population_identity_audit_path':str(audit_path),'own_population_identity_audit_sha256':receipt['own_population_identity_audit_sha256'],
        'decisions':list(decisions.values()),'held_series':expected_held,'held_observations':3*expected_held,'replacement_series':7-expected_held,'replacement_observations':3*(7-expected_held),
        'frozen_population_sources_modified':False,'population_values_transferred_to_new_item':False,
        'ordinary_identity_modified':False,'held_source_observations_selected_credit_admitted':False,
        'source_application_inputs_verified_live_except_exact_historical55_Git_controls':True,
        'exact_provider_carrier_regression':'PASS717_vs7172_and_full_UID',
        'outputs':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['qualified_point_correction57_held_source_observations.csv','qualified_point_correction57_retained_rejected_point_context.csv']}}
    (out/'qualified_point_projection57_admission_receipt.json').write_text(json.dumps(admission,ensure_ascii=False,indent=2)+'\n')
    return result


def raw_provider_carrier(row):
    if not str(row.get('point_origin_file','')).endswith('2021_tochno/data_allsettlements_anon_156_v20251217.parquet'): return None
    match=re.search(r'parquet[_ ]row[_ ](?:1based|1-based)\s*=\s*(\d+)',str(row.get('point_origin_locator','')))
    return '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+match.group(1) if match else None


def verify_exact_provider_carrier_regression():
    path='/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
    uid='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:717'
    assert raw_provider_carrier({'point_origin_file':path,'point_origin_locator':'parquet row 1-based=717; fields=x'})==uid
    assert raw_provider_carrier({'point_origin_file':path,'point_origin_locator':'parquet row 1-based=7172; fields=x'})==uid+'2'
    assert raw_provider_carrier({'point_origin_file':path,'point_origin_locator':'parquet row 1-based=7172; fields=x'}) not in {uid}
    assert uid not in json.loads(json.dumps([uid+'2']))
    return True
