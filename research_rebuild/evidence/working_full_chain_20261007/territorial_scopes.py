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
            assert len(own)==int(row['constituent_count']) and int(own.population.sum())==int(row['population'])
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


def build(E,state,ordinary,componentpoints,partition_ids,qualified_ids,named_ids,federal,national,common,out,pin):
    frames=[]; receipts=[]
    city_edges=[]
    for dirname in ['large_absorbed_city_closed_scope_application_20261008','remaining_absorbed_city_published_closures_application_20261008']:
        folder=E/dirname
        if (folder/'application_receipt.json').exists():
            receipt,obs,members,points=cities(folder,state,out,pin)
            frames.append((obs,members,points));receipts.append(str(folder/'application_receipt.json'))
            city_edges.append(pd.read_csv(folder/'accepted_scope_edges.csv',keep_default_na=False))
    if city_edges: pd.concat(city_edges,ignore_index=True).to_csv(out/'complete_city_territorial_scope_relations.csv',index=False)
    folder=E/'complete_transferred_municipal_scope_application_20261008'
    if (folder/'application_receipt.json').exists():
        receipt,obs,members,points=municipal(folder,state,out,pin)
        frames.append((obs,members,points));receipts.append(str(folder/'application_receipt.json'))
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
    return {'status':'admitted_separate_complete_territorial_scopes','scopes':obs.scope_id.nunique(),'observations':len(obs),'native_constituent_references':len(members),'representative_scope_points':len(points),'ordinary_NP3_modified':False,'qualified_physical_series_modified':False,'named_merger_axis_modified':False,'boundary_comparability_asserted':False,'historical_individual_NP_point_coverage_asserted':False,'source_quality_limits':'City territories follow complete primary published source hierarchies by census year, with changed composition allowed. Transferred municipal scope uses primary native child rosters plus secondary own-municipality population/point witnesses and cached legal-agreement/own-article excerpts; an authenticated legal act roster is not asserted. The municipal2010 descriptive aggregate exceeds retained native constituents by1; municipal2021 is nonadditive under the federal territory.','application_receipts':receipts,'by_year':byyear},ids
