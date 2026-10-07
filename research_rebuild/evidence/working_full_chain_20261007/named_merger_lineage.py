"""Separate admitted named merger/event scope; never ordinary NP3 identity."""
from pathlib import Path
import json,math
import pandas as pd

FILES={'observations':'accepted_group_observations.csv','constituents':'accepted_constituent_credit_union.csv','points':'accepted_representative_scope_points.csv','events':'accepted_event_edges.csv'}
STATUS='applied_separate_complete_named_merger_event_lineage'

def build(E,state,ordinary,componentpoints,partition_ids,qualified_ids,federal,national,common,out,pin):
    frames_by_key={key:[] for key in FILES}; receipts=[]
    for dirname in ['named_urban_merger_application_20261007','next_named_urban_merger_application_20261007','further_urban_merger_application_20261007']:
        folder=E/dirname;rp=folder/'application_receipt.json'
        if not rp.exists(): continue
        pin(rp);receipt=json.loads(rp.read_text())
        assert receipt['status']==STATUS,receipt['status']
        receipts.append(str(rp))
        for key,name in FILES.items():
            assert pin(folder/name)==receipt['outputs'][name]
            frames_by_key[key].append(pd.read_csv(folder/name))
    if not receipts:
        return {'status':'not_loaded_without_root_application_receipt','ordinary_NP3_modified':False,'qualified_physical_series_modified':False}
    frames={key:pd.concat(parts,ignore_index=True) for key,parts in frames_by_key.items()}
    observations,members,points,events=(frames[k] for k in ['observations','constituents','points','events'])
    groups=observations.group.nunique()
    assert len(observations)==3*groups and len(points)==groups and len(events)==2*groups
    assert not points.group.duplicated().any()
    assert not observations[['group','census_year']].duplicated().any()
    assert not members.source_record_id.duplicated().any()
    assert observations.roster_complete.all() and not observations.ordinary_same_place.any()
    assert observations.boundary_comparability.eq('UNKNOWN').all() and not observations.official_act_verified.any()
    assert not events.ordinary_same_place.any() and events.boundary_comparability.eq('UNKNOWN').all()
    assert not points.historical_constituent_own_point_asserted.any()
    for frame in [observations,events]:
        if 'candidate_only' in frame: assert not frame.candidate_only.any()
    ordinary_ids=set(ordinary.source_record_id);ids=set(members.source_record_id)
    assert ids<=ordinary_ids
    for r in members.to_dict('records'):
        current=state.by_id.loc[r['source_record_id']]
        assert int(current.census_year)==int(r['census_year']) and math.isfinite(float(current.population)) and int(current.population)==int(r['population'])
        assert r['source_population_unmodified'] and not r['ordinary_same_place_edge_created']
        assert r['exclusive_source_ID_credit'] and not r['separate_population_credit_in_addition_to_group']
        imported_hash=current.source_sha256
        if pd.notna(imported_hash) and str(imported_hash): assert imported_hash==r['source_file_sha256']
        imported_path=current.source_path
        path=Path(str(imported_path)) if pd.notna(imported_path) and str(imported_path) else Path('/workspace/settlements-raw')/current.source_file
        if not path.is_absolute(): path=Path('/workspace/settlements-raw')/path
        assert pin(path)==r['source_file_sha256']
    for group,g in observations.groupby('group'):
        assert set(g.census_year)=={2002,2010,2021}
        for r in g.to_dict('records'):
            source_ids=json.loads(r['source_record_ids_json']);subset=members[(members.group==group)&(members.census_year==r['census_year'])]
            assert len(set(source_ids))==len(source_ids)==int(r['constituent_count'])
            assert set(source_ids)==set(subset.source_record_id) and int(subset.population.sum())==int(r['population'])
            assert r['identity_axis']=='named_merger_event_lineage' and r['point_role']=='representative_scope'
            for law in json.loads(r['legal_basis_json']):
                if 'compressed_path' in law:
                    path=E.parents[1]/law['compressed_path'];claimed=law['compressed_sha256']
                else:
                    path=Path(law.get('actual_source_path') or law.get('source_path') or law['asset_path']);claimed=law.get('source_sha256') or law['asset_sha256']
                    assert not law.get('official_verified',False)
                assert pin(path)==claimed
        lookup={int(r.census_year):r.observation_id for r in g.itertuples()}
        actual=events[events.group==group]
        assert set(zip(actual.from_observation_id,actual.to_observation_id))=={(lookup[2002],lookup[2010]),(lookup[2010],lookup[2021])}
    for r in points.to_dict('records'):
        parent=r['parent_source_record_id'];active=state.point_rows[parent]
        assert r['scope_point_role']=='representative_scope'
        assert (float(r['latitude']),float(r['longitude']))==(active['latitude'],active['longitude'])
        provenance=json.loads(r['point_provenance_json'])
        assert provenance['target_source_record_id']==parent
        assert pin(Path(provenance['point_origin_file']))==provenance['point_origin_sha256']
    # Exclude the whole unknown-population identity component in every census year.
    blocked={state.uf.find(sid) for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(pop) or not math.isfinite(float(pop))}
    finite={sid for sid in componentpoints if state.uf.find(sid) not in blocked}
    before=finite|set(partition_ids)|set(qualified_ids);after=before|ids
    byyear={}
    for y,g in ordinary.groupby('census_year'):
        y=int(y);old=g[g.source_record_id.isin(before)];new=g[g.source_record_id.isin(after)];added=g[g.source_record_id.isin(ids-before)]
        population=int(new.population.sum())+int(federal[y]);baseline=int(old.population.sum())+int(federal[y])
        byyear[y]={'finite_ordinary_plus_partitions_qualified_federal_population':baseline,'named_lineage_descriptive_group_population_sum':int(observations.loc[observations.census_year==y,'population'].sum()),'new_unique_selected_source_IDs':len(added),'named_lineage_net_population_added_by_exclusive_source_ID_union':population-baseline,'selected_source_ID_union_rows':len(new),'selected_source_ID_union_population':int(new.population.sum()),'federal_territory_population':int(federal[y]),'extended_named_lineage_population':population,'official_national_control':int(national[y]),'common_three_census_control':int(common[y]),'percent_of_national_control':100*population/national[y],'percent_of_common_control':100*population/common[y],'gap_to_99_percent_common':max(0,math.ceil(.99*common[y])-population)}
    exports={}
    for key,frame in frames.items():
        filename='named_merger_lineage_'+key+'.csv'
        if key=='constituents':
            frame=frame.copy()
            frame['already_in_finite_ordinary_partitions_qualified_union']=frame.source_record_id.isin(before)
            frame['selected_population_quality_as_imported']=frame.source_record_id.map(state.by_id.population_value_quality)
            frame['selected_oktmo_as_imported']=frame.source_record_id.map(state.by_id.oktmo)
            frame['selected_okato_as_imported']=frame.source_record_id.map(state.by_id.okato)
            frame['selected_source_path_as_imported']=frame.source_record_id.map(state.by_id.source_path)
            frame['selected_source_sha256_as_imported']=frame.source_record_id.map(state.by_id.source_sha256)
        frame.to_csv(out/filename,index=False)
        exports[key]=filename
    return {'status':'admitted_separate_named_merger_event_lineage','groups':groups,'observations':len(observations),'constituent_source_ID_references':len(members),'representative_scope_points':len(points),'event_edges':len(events),'ordinary_NP3_modified':False,'qualified_physical_series_modified':False,'identity_axis':'named_merger_event_lineage','population_series_scope':'Complete named event rosters by census year; boundary comparability UNKNOWN. Historical constituents are not asserted as individually observed through all three years.','coordinate_axis':'One admitted receiving-parent representative scope point per lineage; historical constituent own-point coverage is not asserted.','legal_source_quality':'Secondary documented event sources, including actual act-text mirrors and own Wikipedia event witnesses; source classes and exact excerpts retained per observation. Official act authentication not asserted.','application_receipts':receipts,'exports':exports,'by_year':byyear}
