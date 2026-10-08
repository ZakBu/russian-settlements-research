"""Explicit complete territorial scopes; no ordinary NP or constant-boundary claim."""
from pathlib import Path
import json, math
import pandas as pd


def admitted(folder, status, out, pin):
    receipt_path=folder/'application_receipt.json'
    pin(receipt_path); receipt=json.loads(receipt_path.read_text())
    assert receipt['status']==status, (str(folder),receipt['status'])
    outputs=receipt.get('outputs',receipt.get('output_sha256',{}))
    for name,claimed in outputs.items(): assert pin(folder/name)==claimed
    manifests=[receipt.get('inputs_sha256',{}),receipt.get('source_manifest',{}),receipt.get('input_packet_sha256',{})]
    if 'source_manifest.json' in outputs:
        manifests.append(json.loads((folder/'source_manifest.json').read_text()))
    for manifest in manifests:
        for source,claimed in manifest.items():
            path=Path(source)
            # Previous report-output hashes remain baseline references in receipts.
            if out not in path.parents: assert pin(path)==claimed
    return receipt


def validate_members(members,state,pin):
    assert not members[['scope_id','year','source_record_id']].duplicated().any()
    for row in members.to_dict('records'):
        selected=state.by_id.loc[row['source_record_id']]
        assert int(selected.census_year)==int(row['year'])
        assert math.isfinite(float(selected.population)) and float(selected.population)==float(row['native_population'])
        assert selected.population_value_quality==row['native_population_quality']
        assert pin(Path(row['raw_source_path']))==row['raw_source_sha256']
        assert not row['point_assigned_to_individual_NP']


def municipal(folder,state,out,pin):
    receipt=admitted(folder,'applied_complete_transferred_municipal_scope_secondary_sources',out,pin)
    obs=pd.read_csv(folder/'accepted_transferred_municipal_scope_observations.csv',keep_default_na=False)
    members=pd.read_csv(folder/'accepted_native_scope_constituents.csv',keep_default_na=False)
    points=pd.read_csv(folder/'accepted_municipal_representative_points.csv',keep_default_na=False)
    assert len(obs)==3 and len(points)==1 and len(members)==38
    assert set(obs.census_year)=={2002,2010,2021}
    assert obs.scope_id.nunique()==1 and set(obs.scope_id)==set(points.scope_id)==set(members.scope_id)
    assert not obs.own_NP_series_asserted.any() and not obs.same_place_edge_created.any()
    assert not obs.population_boundary_comparability_asserted.any() and not obs.modern_boundary_harmonized.any()
    assert obs.selected_source_record_id.eq('').all() and obs.national2021_credit_population.eq(0).all()
    assert not members.is_additive_to_ordinary_selected_denominator.any()
    assert members.is_exclusive_constituent_at_own_scope.all()
    validate_members(members,state,pin)
    for row in obs.to_dict('records'):
        assert pin(Path(row['population_source_file']))==row['population_source_sha256']
        own=members[members.year==row['census_year']]
        assert len(own)==int(row['native_members_count'])
        if len(own): assert int(own.native_population.sum())==int(row['native_constituent_sum'])
    assert int(obs.loc[obs.census_year==2010,'population'].iloc[0])-int(members.loc[members.year==2010,'native_population'].sum())==1
    assert points.individual_NP_point_uses_created.eq(0).all() and not points.boundary_comparability_asserted.any()
    for row in points.to_dict('records'):
        assert pin(Path(row['point_origin_file']))==row['point_origin_sha256']
        assert -90<=float(row['latitude'])<=90 and -180<=float(row['longitude'])<=180
        assert obs.latitude.eq(row['latitude']).all() and obs.longitude.eq(row['longitude']).all()
    obs['territorial_identity_axis']='complete_transferred_municipal_territory'
    return receipt,obs,members,points


def cities(folder,state,out,pin):
    receipt=admitted(folder,'applied_complete_published_city_territorial_scope',out,pin)
    obs=pd.read_csv(folder/'accepted_group_observations.csv',keep_default_na=False)
    members=pd.read_csv(folder/'accepted_constituent_credit_union.csv',keep_default_na=False)
    points=pd.read_csv(folder/'accepted_representative_scope_points.csv',keep_default_na=False)
    edges=pd.read_csv(folder/'accepted_scope_edges.csv',keep_default_na=False)
    groups=int(receipt['groups'])
    assert len(obs)==3*groups and len(members)==int(receipt['atomic_members']) and len(points)==groups and len(edges)==2*groups
    auxiliary_by_scope_year={}
    if folder.name=='nakhoda_complete_published_scope_aux5_application_20261008':
        import xlrd
        assert groups==1 and len(members)==14 and receipt['actual_primary_atomic_members']==15
        assert members.groupby('census_year').size().to_dict()=={2002:6,2010:4,2021:4}
        auxiliary=pd.read_csv(folder/'actual_primary_auxiliary2002_atom.csv',keep_default_na=False)
        assert len(auxiliary)==1
        atom=auxiliary.iloc[0]
        assert atom.selected_source_record_id=='' and not atom.national_additive_credit
        assert atom.raw_label=='маяк Поворотный' and atom.raw_type=='маяк' and int(atom.population)==5
        assert atom.population_quality=='direct_primary_census_named_atomic_leaf_absent_selectedNP_layer'
        assert pin(Path(atom.raw_file))==atom.raw_sha256
        raw=xlrd.open_workbook(atom.raw_file).sheet_by_name(atom.raw_sheet).row_values(int(atom.raw_row_1based)-1)
        assert raw==json.loads(atom.raw_original_row_json)
        assert raw[1].strip()==atom.raw_label and int(raw[2])==5
        witnesses=pd.read_csv(folder/'complete_scope_source_witnesses.csv',keep_default_na=False)
        witness=witnesses[witnesses.year.eq(2002)].iloc[0]
        assert Path(atom.raw_file).name==witness.rural_file and int(float(witness.rural_block_start))<=int(atom.raw_row_1based)<int(float(witness.rural_block_end))
        assert int(witness.primary_parent_control or json.loads(witness.parent_raw_row)[1])==178813
        auxiliary_by_scope_year[(obs.iloc[0]['group'],2002)]=5
        assert obs.sort_values('census_year').population.tolist()==[178813,160760,141035]
    if folder.name=='city_territory_mass_final_two_application_20261008':
        import xlrd
        assert groups==2 and len(members)==119 and receipt['actual_published_atomic_members']==120
        auxiliary=pd.read_csv(folder/'actual_published_auxiliary_atom.csv',keep_default_na=False)
        assert len(auxiliary)==1
        atom=auxiliary.iloc[0]
        assert atom.group=='published_closed_city_scope_Владимир' and int(atom.census_year)==2010
        assert atom.selected_source_record_id=='' and not atom.national_additive_credit
        assert atom.raw_label=='турбаза "Ладога"' and atom.raw_type=='турбаза' and int(atom.population)==201
        assert atom.population_quality=='actual_published_secondary_confidentiality_protected_named_atomic_leaf_absent_selectedNP_layer'
        assert pin(Path(atom.raw_file))==atom.raw_sha256
        raw=xlrd.open_workbook(atom.raw_file).sheet_by_name(atom.raw_sheet).row_values(int(atom.raw_row_1based)-1)
        original_witness=json.loads(atom.raw_original_row_json)
        assert len(original_witness)==11 and raw[:11]==original_witness and raw[3].strip()==atom.raw_label and int(raw[4])==201
        control=pd.read_csv(folder/'printed_controls_atomic_conservation.csv',keep_default_na=False)
        control=control[control.group.eq(atom.group)&control.year.eq(2010)].iloc[0]
        assert (int(control.complete_selected_atomic_sum),int(control.complete_published_atomic_sum),int(control.difference_not_allocated))==(347837,348038,-7)
        assert control.protected2010_difference_not_distributed and control.source_quality_difference_preserved
        auxiliary_by_scope_year[(atom.group,2010)]=201
    if folder.name=='next_absorbed_city_closed_scopes_followup_application_20261008':
        import xlrd
        assert groups==3 and len(members)==26
        auxiliary=pd.read_csv(folder/'actual_published_auxiliary_atom.csv',keep_default_na=False)
        assert len(auxiliary)==1
        atom=auxiliary.iloc[0]
        assert atom.group=='published_closed_city_scope_Пермь' and int(atom.census_year)==2010
        assert atom.selected_source_record_id=='' and not atom.national_additive_credit
        assert atom.raw_label=='Казарма 30-й км' and atom.raw_type=='not_printed_in_raw_label' and int(atom.population)==6
        assert atom.population_quality=='actual_published_secondary_confidentiality_protected_named_atomic_leaf_absent_selectedNP_layer'
        assert pin(Path(atom.raw_file))==atom.raw_sha256
        raw=xlrd.open_workbook(atom.raw_file).sheet_by_name(atom.raw_sheet).row_values(int(atom.raw_row_1based)-1)
        original_witness=json.loads(atom.raw_original_row_json)
        assert len(original_witness)>=8 and raw[:len(original_witness)]==original_witness
        assert raw[5].strip()==atom.raw_label and int(raw[6])==6 and int(raw[7])==10
        control=pd.read_csv(folder/'printed_controls_atomic_conservation.csv',keep_default_na=False)
        control=control[control.group.eq(atom.group)&control.year.eq(2010)].iloc[0]
        assert (int(control.printed_parent_or_complete_city_control),int(control.complete_selected_atomic_sum),int(control.difference_not_allocated))==(991170,991173,-3)
        assert control.protected2010_difference_not_distributed and control.source_quality_difference_preserved
        auxiliary_by_scope_year[(atom.group,2010)]=6
    for frame in [obs,members,points,edges]:
        assert frame.identity_axis.eq('published_complete_city_territory_scope').all()
        assert frame.boundary_comparability.eq('UNKNOWN').all()
        for field in ['candidate_only','ordinary_same_place','exact_annexation_roster_claimed','legal_annexation_asserted','historical_individual_point_asserted']:
            assert not frame[field].any()
    assert obs.roster_complete.all() and members.source_population_unmodified.all()
    assert members.exclusive_source_ID_credit.all() and not members.separate_population_credit_in_addition_to_group.any()
    for group,frame in obs.groupby('group'):
        assert set(frame.census_year)=={2002,2010,2021} and len(frame)==3
        for row in frame.to_dict('records'):
            own=members[(members.group==group)&(members.census_year==row['census_year'])]
            auxiliary_population=auxiliary_by_scope_year.get((group,int(row['census_year'])),0)
            assert len(own)==int(row['constituent_count']) and int(own.population.sum())+auxiliary_population==int(row['population'])
            if folder.name=='nakhoda_complete_published_scope_aux5_application_20261008':
                assert int(row['actual_primary_auxiliary_population_sum'])==auxiliary_population
                assert int(row['native_selected_population_sum'])==int(own.population.sum())
                assert int(row['actual_primary_atomic_constituent_count'])==len(own)+int(auxiliary_population>0)
            if folder.name=='city_territory_mass_final_two_application_20261008':
                assert int(row['actual_published_auxiliary_population_sum'])==auxiliary_population
                assert int(row['native_selected_population_sum'])==int(own.population.sum())
                assert int(row['actual_published_auxiliary_member_count'])==int(auxiliary_population>0)
                assert int(row['actual_published_atomic_constituent_count'])==len(own)+int(auxiliary_population>0)
            if folder.name=='next_absorbed_city_closed_scopes_followup_application_20261008':
                assert int(row['actual_published_auxiliary_population_sum'])==auxiliary_population
                assert int(row['native_selected_population_sum'])==int(own.population.sum())
            assert set(own.source_record_id)==set(json.loads(row['source_record_ids_json']))
        lookup=dict(zip(frame.census_year,frame.observation_id));own_edges=edges[edges.group==group]
        assert set(zip(own_edges.from_observation_id,own_edges.to_observation_id))=={(lookup[2002],lookup[2010]),(lookup[2010],lookup[2021])}
    for row in points.to_dict('records'):
        assert row['scope_point_role']=='representative_scope'
        active=state.point_rows[row['parent_source_record_id']]
        assert (float(row['latitude']),float(row['longitude']))==(active['latitude'],active['longitude'])
        proof=json.loads(row['point_provenance_json'])
        assert pin(Path(proof['point_origin_file']))==proof['point_origin_sha256']
    # Preserve original packet columns alongside the shared validation/export fields.
    obs['scope_id']=obs.group;obs['territorial_identity_axis']=obs.identity_axis
    points['scope_id']=points.group
    members['scope_id']=members.group;members['year']=members.census_year
    members['native_population']=members.population;members['native_population_quality']=members.source_population_quality
    members['raw_source_path']=members.source_file;members['raw_source_sha256']=members.source_file_sha256
    members['point_assigned_to_individual_NP']=False
    validate_members(members,state,pin)
    return receipt,obs,members,points


def moscow_sourceyear_municipal(folder,state,out,pin):
    receipt=admitted(folder,'applied_complete_sourceyear_municipal_scope_secondary_sources',out,pin)
    obs=pd.read_csv(folder/'accepted_transferred_municipal_scope_observations.csv',keep_default_na=False)
    members=pd.read_csv(folder/'accepted_native_scope_constituents.csv',keep_default_na=False)
    points=pd.read_csv(folder/'accepted_municipal_representative_points.csv',keep_default_na=False)
    controls=pd.read_csv(folder/'source_controls.csv',keep_default_na=False)
    followup=folder.name=='sourceyear_scopes_followup_application_20261008'
    scope_count=5 if followup else 4
    assert (len(obs),len(members),len(points),len(controls))==((15,162,5,10) if followup else (12,110,4,8))
    assert obs.scope_id.nunique()==scope_count and set(obs.scope_id)==set(members.scope_id)==set(points.scope_id)
    assert not obs.own_NP_series_asserted.any() and not obs.same_place_edge_created.any()
    assert not obs.population_boundary_comparability_asserted.any() and not obs.modern_boundary_harmonized.any()
    assert obs.selected_source_record_id.eq('').all() and obs.national2021_credit_population.eq(0).all()
    assert members.is_exclusive_constituent_at_own_scope.all() and not members.own_NP_2021_count_asserted.any()
    validate_members(members,state,pin)
    assert controls.complete_sourceyear_roster.all()
    assert not members.is_additive_to_ordinary_selected_denominator.any()
    qualifiers=pd.read_csv(folder/'accepted_sourceyear_composition_change_qualifiers.csv',keep_default_na=False)
    assert len(qualifiers)==scope_count and not qualifiers.same_place_identity_asserted.any() and not qualifiers.full_modern_boundary_series_asserted.any()
    raw_frames={int(year):pd.read_excel(group.raw_source_path.iloc[0],header=None) for year,group in members.groupby('year')}
    for row in pd.read_csv(folder/'actual_raw_reopened_rows.csv',keep_default_na=False).to_dict('records'):
        raw=raw_frames[int(row['year'])].iloc[int(row['row_1based'])-1,:6].tolist()
        assert [None if pd.isna(value) else value for value in raw]==json.loads(row['raw_cells_json'])
    unknown=pd.DataFrame()
    if followup:
        unknown=pd.read_csv(folder/'auxiliary_unknown_count_rows.csv',keep_default_na=False)
        assert len(unknown)==4 and unknown.source_record_id.eq('').all() and unknown.native_population.eq('').all()
        assert unknown.population_unknown.all() and not unknown.selected_native_source_ID.any()
        assert unknown.national_native_credit_population.eq(0).all() and not unknown.point_assigned_to_individual_NP.any()
        assert not unknown.population_sum_closure_asserted.any() and not unknown.constituent_populations_complete.any()
        assert unknown.groupby('scope_id').size().to_dict()=={'moscow_sourceyear_mikhailovo_yartsevskoye':3,'moscow_sourceyear_filimonkovskoye':1}
        for atom in unknown.to_dict('records'):
            assert pin(Path(atom['raw_source_path']))==atom['raw_source_sha256']
            raw=raw_frames[int(atom['census_year'])].iloc[int(atom['raw_row_1based'])-1,:6].tolist()
            raw=[None if pd.isna(value) else value for value in raw]
            assert raw==json.loads(atom['raw_first_cells_json']) and raw[3].strip()==atom['raw_label']
            assert atom['raw_label'].startswith(atom['raw_type']+' ')
            assert raw[4]==json.loads(atom['raw_population_symbol_json']) and raw[4] is None
        assert obs.independently_published_whole_population.all()
        assert obs.loc[obs.census_year.eq(2002),'population_sum_closure_asserted'].all()
        assert not obs.loc[obs.census_year.eq(2010),'population_sum_closure_asserted'].any()
    for row in obs.to_dict('records'):
        assert pin(Path(row['population_source_file']))==row['population_source_sha256']
        own=members[members.scope_id.eq(row['scope_id'])&members.year.eq(row['census_year'])]
        assert len(own)==int(row['native_members_count'])
        if int(row['census_year']) in [2002,2010]:
            assert int(own.native_population.sum())==int(float(row['native_constituent_sum']))
            control=controls[controls.scope_id.eq(row['scope_id'])&controls.year.eq(row['census_year'])]
            assert len(control)==1
            control=control.iloc[0]
            unknown_count=int(((unknown.scope_id.eq(row['scope_id']))&(unknown.census_year.eq(row['census_year']))).sum()) if followup else 0
            assert int(control.raw_children_count)==len(own)+unknown_count and int(control.selected_children_sum)==int(own.native_population.sum())
            assert int(control.whole_published_observation_population)==int(row['population'])
            difference=control.finite_selected_sum_minus_independent_whole_observation if followup else control.selected_sum_minus_municipal_claim
            assert int(control.selected_children_sum)-int(row['population'])==int(difference)
            if followup:
                assert int(row['complete_raw_roster_members_count'])==len(own)+unknown_count
                assert int(row['auxiliary_unknown_count_members'])==unknown_count
                assert bool(row['constituent_populations_complete'])==(unknown_count==0)
                if int(row['census_year'])==2002: assert int(row['population'])==int(own.native_population.sum())
        else:
            assert not len(own) and row['native_constituent_sum']=='' and int(row['date_precision'])==9
    if not followup: assert set(obs.loc[obs.census_year.eq(2021),'population'].astype(int))=={101050,59580,93474,12104}
    for row in points.to_dict('records'):
        assert int(row['individual_NP_point_uses_created'])==0 and not row['population_boundary_comparability_asserted']
        assert row['historical_representative_is_territorial_inference_only'] and not row['historical_census_date_geography_measured']
        assert pin(Path(row['point_origin_file']))==row['point_origin_sha256']
        assert -90<=float(row['latitude'])<=90 and -180<=float(row['longitude'])<=180
        own=obs[obs.scope_id.eq(row['scope_id'])]
        assert own.latitude.eq(row['latitude']).all() and own.longitude.eq(row['longitude']).all()
    obs['territorial_identity_axis']='complete_sourceyear_municipal_predecessor_territory'
    return receipt,obs,members,points


def remaining_moscow_sourceyear_municipal(folder,state,out,pin):
    receipt=admitted(folder,'applied_complete_sourceyear_municipal_scope_secondary_sources',out,pin)
    read=lambda name:pd.read_csv(folder/name,keep_default_na=False)
    obs=read('accepted_transferred_municipal_scope_observations.csv')
    roster=read('accepted_native_scope_constituents.csv')
    members=roster[roster.selected_native_source_ID].copy()
    points=read('accepted_municipal_representative_points.csv')
    controls=read('source_controls.csv')
    unknown=read('auxiliary_unknown_count_rows.csv');zero=read('auxiliary_actual_raw_zero_row.csv')
    assert (len(obs),obs.scope_id.nunique(),len(roster),len(members),len(points),len(controls),len(unknown),len(zero))==(18,6,267,251,6,12,15,1)
    assert set(obs.scope_id)==set(members.scope_id)==set(points.scope_id)
    assert not obs.own_NP_series_asserted.any() and not obs.same_place_edge_created.any()
    assert not obs.population_boundary_comparability_asserted.any() and not obs.modern_boundary_harmonized.any()
    assert obs.selected_source_record_id.eq('').all() and obs.national2021_credit_population.eq(0).all()
    assert roster.is_exclusive_constituent_at_own_scope.all() and not roster.own_NP_2021_count_asserted.any()
    assert not roster.point_assigned_to_individual_NP.any()
    validate_members(members,state,pin)
    assert controls.complete_sourceyear_roster.all()
    qualifiers=read('accepted_sourceyear_composition_change_qualifiers.csv')
    assert len(qualifiers)==6 and not qualifiers.same_place_identity_asserted.any() and not qualifiers.modern_boundary_series_asserted.any()
    raw_frames={}
    for atom in roster.to_dict('records'):
        path=Path(atom['raw_source_path']);assert pin(path)==atom['raw_source_sha256']
        key=(int(atom['year']),atom['raw_sheet'])
        if key not in raw_frames: raw_frames[key]=pd.read_excel(path,sheet_name=atom['raw_sheet'],header=None)
    for witness in read('actual_raw_reopened_rows.csv.gz').to_dict('records'):
        expected=json.loads(witness['raw_cells_json'])
        raw=raw_frames[(int(witness['year']),witness['raw_sheet'])].iloc[int(witness['row_1based'])-1,:len(expected)].tolist()
        assert [None if pd.isna(v) else v for v in raw]==expected
    auxiliary=pd.concat([unknown,zero],ignore_index=True)
    assert auxiliary.source_record_id.eq('').all() and auxiliary.native_population.eq('').all()
    assert not auxiliary.selected_native_source_ID.any() and not auxiliary.point_assigned_to_individual_NP.any()
    assert auxiliary.new_native_population_if_scope_admitted.eq(0).all()
    assert len(roster[~roster.selected_native_source_ID])==len(auxiliary)
    assert set(roster.loc[~roster.selected_native_source_ID,'observed_raw_row_id'])==set(auxiliary.observed_raw_row_id)
    for atom in auxiliary.to_dict('records'):
        raw=raw_frames[(int(atom['year']),atom['raw_sheet'])].iloc[int(atom['raw_row_1based'])-1]
        label_col,value_col=(1,2) if int(atom['year'])==2002 else (3,4)
        assert raw.iloc[label_col]==atom['raw_label']
        if atom['native_population_quality']=='actual_raw_zero_absent_selected_layer_nonadditive':
            assert int(atom['year'])==2002 and int(atom['raw_row_1based'])==3672
            assert atom['raw_label'].strip()=='хутора Гуляевы' and float(raw.iloc[value_col])==float(atom['raw_population'])==0
        else:
            assert atom['native_population_quality']=='raw_count_blank_unknown_not_zero' and int(atom['year'])==2010
            assert pd.isna(raw.iloc[value_col]) and atom['raw_population']==''
    members['native_population']=pd.to_numeric(members.native_population)
    members['is_additive_to_ordinary_selected_denominator']=False
    for row in obs.to_dict('records'):
        assert pin(Path(row['population_source_file']))==row['population_source_sha256']
        year=int(row['census_year']);own=members[members.scope_id.eq(row['scope_id'])&members.year.eq(year)]
        rawown=roster[roster.scope_id.eq(row['scope_id'])&roster.year.eq(year)]
        if year in [2002,2010]:
            control=controls[controls.scope_id.eq(row['scope_id'])&controls.year.eq(year)]
            assert len(control)==1;control=control.iloc[0]
            assert int(row['native_members_count'])==len(rawown)
            assert int(control.raw_children_count)==len(rawown)
            assert float(row['native_constituent_sum'])==float(own.native_population.sum())==float(control.selected_children_sum)
            assert float(control.whole_published_observation_population)==float(row['population'])
            assert float(control.selected_sum_minus_municipal_claim)==float(own.native_population.sum())-float(row['population'])
            assert int(control.raw_count_unknown_rows)==int((unknown.scope_id.eq(row['scope_id'])&unknown.year.eq(year)).sum())
            if year==2002: assert float(row['population'])==float(own.native_population.sum())
        else: assert not len(own) and row['native_constituent_sum']=='' and int(row['date_precision'])==9
    for point in points.to_dict('records'):
        assert int(point['individual_NP_point_uses_created'])==0 and not point['population_boundary_comparability_asserted']
        assert point['historical_representative_is_territorial_inference_only']
        assert pin(Path(point['point_origin_file']))==point['point_origin_sha256']
        assert -90<=float(point['latitude'])<=90 and -180<=float(point['longitude'])<=180
        own=obs[obs.scope_id.eq(point['scope_id'])]
        assert own.latitude.eq(point['latitude']).all() and own.longitude.eq(point['longitude']).all()
    obs['source_packet_roster_members_count']=obs.native_members_count
    obs['complete_raw_roster_members_count']=[len(roster[roster.scope_id.eq(r.scope_id)&roster.year.eq(r.census_year)]) for r in obs.itertuples()]
    obs['native_members_count']=[len(members[members.scope_id.eq(r.scope_id)&members.year.eq(r.census_year)]) for r in obs.itertuples()]
    obs['auxiliary_unknown_count_members']=[int((unknown.scope_id.eq(r.scope_id)&unknown.year.eq(r.census_year)).sum()) for r in obs.itertuples()]
    obs['auxiliary_actual_raw_zero_members']=[int((zero.scope_id.eq(r.scope_id)&zero.year.eq(r.census_year)).sum()) for r in obs.itertuples()]
    obs['territorial_identity_axis']='complete_sourceyear_municipal_predecessor_territory'
    obs['population_sum_closure_asserted']=obs.census_year.eq(2002)
    obs['constituent_populations_complete']=[not (unknown.scope_id.eq(r.scope_id)&unknown.year.eq(r.census_year)).any() for r in obs.itertuples()]
    return receipt,obs,members,points,unknown,zero


def build(E,state,ordinary,componentpoints,partition_ids,qualified_ids,named_ids,federal,national,common,out,pin):
    frames=[]; receipts=[]
    city_edges=[]; auxiliary_frames=[]
    for dirname in ['large_absorbed_city_closed_scope_application_20261008','remaining_absorbed_city_published_closures_application_20261008','nakhoda_complete_published_scope_aux5_application_20261008','city_territory_mass_followup_application_20261008','city_territory_mass_final_two_application_20261008','next_absorbed_city_closed_scopes_application_20261008','next_absorbed_city_closed_scopes_followup_application_20261008']:
        folder=E/dirname
        if (folder/'application_receipt.json').exists():
            receipt,obs,members,points=cities(folder,state,out,pin)
            frames.append((obs,members,points));receipts.append(str(folder/'application_receipt.json'))
            city_edges.append(pd.read_csv(folder/'accepted_scope_edges.csv',keep_default_na=False))
            for filename in ['actual_primary_auxiliary2002_atom.csv','actual_published_auxiliary_atom.csv']:
                if (folder/filename).exists():
                    atoms=pd.read_csv(folder/filename,keep_default_na=False)
                    if 'group' not in atoms: atoms['group']=obs.iloc[0]['group']
                    if 'census_year' not in atoms: atoms['census_year']=2002
                    atoms['application_receipt']=str(folder/'application_receipt.json')
                    auxiliary_frames.append(atoms)
    if city_edges: pd.concat(city_edges,ignore_index=True).to_csv(out/'complete_city_territorial_scope_relations.csv',index=False)
    if auxiliary_frames: pd.concat(auxiliary_frames,ignore_index=True).to_csv(out/'complete_territorial_scope_auxiliary_atoms.csv',index=False)
    folder=E/'complete_transferred_municipal_scope_application_20261008'
    if (folder/'application_receipt.json').exists():
        receipt,obs,members,points=municipal(folder,state,out,pin)
        frames.append((obs,members,points));receipts.append(str(folder/'application_receipt.json'))
    folder=E/'moscow_complete_scope_mass_application_20261008'
    if (folder/'application_receipt.json').exists():
        receipt,obs,members,points=moscow_sourceyear_municipal(folder,state,out,pin)
        frames.append((obs,members,points));receipts.append(str(folder/'application_receipt.json'))
    folder=E/'sourceyear_scopes_followup_application_20261008'
    if (folder/'application_receipt.json').exists():
        receipt,obs,members,points=moscow_sourceyear_municipal(folder,state,out,pin)
        frames.append((obs,members,points));receipts.append(str(folder/'application_receipt.json'))
        pd.read_csv(folder/'auxiliary_unknown_count_rows.csv',keep_default_na=False).to_csv(out/'complete_territorial_scope_unknown_auxiliary_atoms.csv',index=False)
    folder=E/'remaining_moscow_complete_sourceyear_scopes_application_20261008'
    if (folder/'application_receipt.json').exists():
        receipt,obs,members,points,unknown,zero=remaining_moscow_sourceyear_municipal(folder,state,out,pin)
        frames.append((obs,members,points));receipts.append(str(folder/'application_receipt.json'))
        prior=pd.read_csv(out/'complete_territorial_scope_unknown_auxiliary_atoms.csv',keep_default_na=False)
        pd.concat([prior,unknown],ignore_index=True).to_csv(out/'complete_territorial_scope_unknown_auxiliary_atoms.csv',index=False)
        zero.to_csv(out/'complete_territorial_scope_actual_raw_zero_auxiliary_atoms.csv',index=False)
    if not frames: return {'status':'not_loaded_without_root_application_receipt'},set()
    obs=pd.concat([f[0] for f in frames],ignore_index=True)
    members=pd.concat([f[1] for f in frames],ignore_index=True)
    points=pd.concat([f[2] for f in frames],ignore_index=True)
    ids=set(members.source_record_id);assert ids<=set(ordinary.source_record_id)
    blocked={state.uf.find(sid) for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(pop) or not math.isfinite(float(pop))}
    before={sid for sid in componentpoints if state.uf.find(sid) not in blocked}|set(partition_ids)|set(qualified_ids)|set(named_ids)
    after=before|ids;byyear={}
    for year,frame in ordinary.groupby('census_year'):
        year=int(year);baseline=int(frame.loc[frame.source_record_id.isin(before),'population'].sum())+int(federal[year])
        final=int(frame.loc[frame.source_record_id.isin(after),'population'].sum())+int(federal[year])
        byyear[year]={'finite_ordinary_partitions_qualified_named_federal_population':baseline,'territorial_net_population_added_by_exclusive_source_ID_union':final-baseline,'new_unique_selected_source_IDs':int(frame.source_record_id.isin(ids-before).sum()),'extended_complete_territorial_population':final,'official_national_control':int(national[year]),'common_three_census_control':int(common[year]),'percent_of_national_control':100*final/national[year],'percent_of_common_control':100*final/common[year],'gap_to_99_percent_common':max(0,math.ceil(.99*common[year])-final)}
    members['already_in_finite_ordinary_partitions_qualified_named_union']=members.source_record_id.isin(before)
    for name,frame in [('observations',obs),('constituents',members),('points',points)]:frame.to_csv(out/f'complete_territorial_scope_{name}.csv',index=False)
    return {'status':'admitted_separate_complete_territorial_scopes','scopes':obs.scope_id.nunique(),'observations':len(obs),'native_constituent_references':len(members),'representative_scope_points':len(points),'ordinary_NP3_modified':False,'qualified_physical_series_modified':False,'named_merger_axis_modified':False,'boundary_comparability_asserted':False,'historical_individual_NP_point_coverage_asserted':False,'source_quality_limits':'City territories follow complete primary published source hierarchies by census year, with changed composition allowed. Transferred municipal scope uses primary native child rosters plus secondary own-municipality population/point witnesses and cached legal-agreement/own-article excerpts; an authenticated legal act roster is not asserted. Ryazan municipal2010 descriptive aggregate exceeds retained native constituents by1. Four further municipal/predecessor source-year rosters retain explicit changed compositions and protected-value discrepancies, with no fixed modern-boundary projection. Municipal2021 is nonadditive under the federal territory. Actual raw auxiliary leaves5 (Nakhoda2002 primary),201 (Vladimir2010 confidentiality-protected secondary) and6 (Perm2010 confidentiality-protected secondary, with unprinted raw type and alternative cell10 retained) complete their published scopes but retain blank selected native IDs and zero national additive credit; all protected source/control discrepancies remain unallocated. Five further municipality source-year scopes use independently published actual whole observations; the Mikhailovo-Yartsevskoye and Filimonkovskoye2010 rosters contain four raw UNKNOWN counts with blank selected native IDs. Finite native subtotals never reconstruct whole observations, unknowns are never zero-filled, and only2002 whole-parent population closure is asserted. Six more municipal source-year scopes retain independently published whole observations, fifteen further UNKNOWN2010 raw leaves and one actual raw2002 zero leaf absent from the selected layer; auxiliary selected IDs remain blank, receive no points and add no native population credit.','application_receipts':receipts,'by_year':byyear},ids
