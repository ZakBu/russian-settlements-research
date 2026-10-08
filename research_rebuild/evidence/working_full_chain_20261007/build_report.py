#!/usr/bin/env python3
"""Bounded, source-ID-union receipt. No source or accepted ledger is modified."""
from pathlib import Path
import sys, json, time, math, hashlib, collections, re
import pandas as pd
import pyarrow.parquet as pq
import duckdb

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
M = ROOT / 'research_rebuild/mass_linkage'
sys.path.insert(0, str(M))
from working_state_20261007 import load, PARTITION_MEMBERS, PARTITION_SERIES
from current_chain_state_20261007 import State, sha
from build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_COORDINATE_STATUSES
from measure_event_aware_path_union_20261005 import EDGES, POINTS, SELECTED, EDGE_DELTAS, POINT_DELTAS
E = ROOT / 'research_rebuild/evidence'
W = Path('/workspace/settlements-work/continuation_20261004/root')
YEARS = (2002, 2010, 2021)
NATIONAL = dict(zip(YEARS, (145166731, 142856536, 147182123)))
COMMON = dict(zip(YEARS, (145166731, 142856536, 144699673)))
EXPECTED = dict(zip(YEARS, (125865264, 123114035, 123670785)))
BASELINE = dict(zip(YEARS, (125417164, 122682881, 123226794)))
DENOM = dict(zip(YEARS, (130111032, 125979957, 126087650)))

def plain(v):
    if isinstance(v, dict): return {str(k): plain(x) for k,x in v.items()}
    if isinstance(v, (list,tuple,set)): return [plain(x) for x in v]
    if hasattr(v, 'item'): return v.item()
    return v

def write_json(name, value):
    (OUT/name).write_text(json.dumps(plain(value), ensure_ascii=False, indent=2)+'\n')

def main(stage=7,reuse_ordinary_export=False,auxiliary_iteration=None,baseline_snapshot=None):
    start=time.monotonic(); pins={}
    def pin(p):
        p=Path(p); h=sha(p)
        if str(p) in pins: assert pins[str(p)]['sha256']==h
        pins[str(p)]={'sha256':h,'bytes':p.stat().st_size}
        return h
    # Freeze all stage input bytes before computing metrics.
    for p in [SELECTED,EDGES,POINTS,M/'working_state_20261007.py',M/'current_chain_state_20261007.py']+[p for p,_,_ in EDGE_DELTAS]+POINT_DELTAS: pin(p)
    # Pin accepted loader paths before replay; candidate packets are not loaded.
    for relative in re.findall(r'E\s*/\s*[\"\']([^\"\']+)[\"\']',(M/'working_state_20261007.py').read_text()):
        p=E/relative
        if p.is_file(): pin(p)
    base=State(); state=load(stage=stage)
    for p in dict.fromkeys(base.inputs+state.inputs+[Path(__file__), M/'working_state_20261007.py', M/'current_chain_state_20261007.py', M/'build_long_table.py', M/'measure_event_aware_path_union_20261005.py']): pin(p)
    if stage >= 25:
        application=E/'old_year_remaining_mass_rule_application_20261008/application_receipt.json'
        pin(application)
        assert json.loads(application.read_text())['status']=='applied_native_context_code_own_point_bindings'
    bm=base.metrics(); sm=state.metrics()
    for y in YEARS:
        assert bm[str(y)]['covered_population']==BASELINE[y], (y,bm)
        if stage==7: assert sm[str(y)]['covered_population']==EXPECTED[y], (y,sm)
        if stage==8: assert sm[str(y)]['covered_population']==dict(zip(YEARS,(125900350,123144265,123696246)))[y], (y,sm)
        if stage==9: assert sm[str(y)]['covered_population']==dict(zip(YEARS,(125921075,123161146,123710370)))[y], (y,sm)
        if stage==10: assert sm[str(y)]['covered_population']==dict(zip(YEARS,(125925029,123164827,123713462)))[y], (y,sm)
        if stage==13:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(125948693,123187272,123734052)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(134822,134850,134854)))[y], (y,sm)
        if stage==14:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126150476,123382596,123960048)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(136847,136875,136879)))[y], (y,sm)
        if stage==15:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126153231,123384459,123962647)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(136855,136883,136887)))[y], (y,sm)
        if stage==16:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126165144,123394194,123980432)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(136858,136886,136890)))[y], (y,sm)
        if stage==17:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126184990,123409970,123993409)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137001,137029,137033)))[y], (y,sm)
        if stage==18:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126189027,123416566,124002885)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137016,137044,137048)))[y], (y,sm)
        if stage==19:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126192455,123419108,124005756)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137018,137046,137050)))[y], (y,sm)
        if stage==21:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126260650,123487223,124084966)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137048,137076,137080)))[y], (y,sm)
        if stage==22:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126262285,123488665,124086298)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137049,137077,137081)))[y], (y,sm)
        if stage==23:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126263029,123489307,124086693)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137052,137080,137084)))[y], (y,sm)
        if stage==24:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126291315,123492222,124086693)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137071,137084,137084)))[y], (y,sm)
        if stage==25:
            assert sm[str(y)]['covered_population']==dict(zip(YEARS,(126302080,123502299,124096770)))[y], (y,sm)
            assert sm[str(y)]['covered_rows']==dict(zip(YEARS,(137084,137097,137097)))[y], (y,sm)
        assert sm[str(y)]['denominator_selected_ordinary_population']==DENOM[y]
    expected={y:sm[str(y)]['covered_population'] for y in YEARS}
    obs=state.obs.copy()
    ordinary=obs[obs.is_additive_settlement_record.fillna(False) & ~obs.region_norm.isin(['москва','санкт петербург','севастополь']) & ~((obs.census_year==2021)&obs.region_norm.eq('крым'))].copy()
    point=set(state.point_rows); full={s for s in obs.source_record_id if state.years[state.uf.find(s)]==set(YEARS)}
    linked={s for s in obs.source_record_id if len(state.years[state.uf.find(s)])>=2}
    joint=full & point
    allpointroots={root for root, years in state.years.items() if years==set(YEARS)}
    for sid in full-point: allpointroots.discard(state.uf.find(sid))
    componentpoints={sid for sid in full if state.uf.find(sid) in allpointroots}
    axes={'accepted_point':point,'any_two_or_more_census_identity_link':linked,'full_three_census_identity_link':full,'point_and_full_three_census_identity':joint,'full_three_census_with_all_component_points':componentpoints}
    metrics={}
    for y,d in ordinary.groupby('census_year'):
        metrics[int(y)]={'denominator_population':int(d.population.sum()),'denominator_rows':len(d),'axes':{}}
        for name,ids in axes.items():
            take=d.source_record_id.isin(ids); pop=int(d.loc[take,'population'].sum())
            metrics[int(y)]['axes'][name]={'rows':int(take.sum()),'row_percent':100*take.mean(),'population':pop,'population_percent':100*pop/d.population.sum(),'unknown_population_rows':int(d.loc[take,'population'].isna().sum())}
    basejoint={s for s in base.point_rows if base.years[base.uf.find(s)]==set(YEARS)}
    gains={}
    for y,d in ordinary.groupby('census_year'):
        gained=d[d.source_record_id.isin(joint-basejoint)]; lost=d[d.source_record_id.isin(basejoint-joint)]
        gains[int(y)]={'gained_unique_source_ids':len(gained),'gained_population':int(gained.population.sum()),'lost_unique_source_ids':len(lost),'lost_population':int(lost.population.sum()),'net_population':int(gained.population.sum()-lost.population.sum())}
        assert gains[int(y)]['net_population']==expected[int(y)]-BASELINE[int(y)]
    # Whole-place partition projection has its own coordinate grain.
    pin(PARTITION_MEMBERS);pin(PARTITION_SERIES)
    members=pd.read_csv(PARTITION_MEMBERS); series=pd.read_csv(PARTITION_SERIES)
    assert series.place_id.nunique()==11 and len(series)==33
    extra_partition=E/'additional_complete_partition_application_20261007'
    if (extra_partition/'application_receipt.json').exists():
        receipt_path=extra_partition/'application_receipt.json';pin(receipt_path)
        pr=json.loads(receipt_path.read_text())
        assert pr['status']=='applied_complete_primary_publisher_partition_with_own_physical_point_support'
        outputs=pr.get('outputs',pr.get('output_hashes',{}))
        for filename,h in outputs.items(): assert pin(extra_partition/filename)==h
        extra_members=pd.read_csv(extra_partition/'accepted_exclusive_member_projection.csv')
        extra_series=pd.read_csv(extra_partition/'accepted_three_census_whole_place_series.csv')
        assert len(extra_members)==4 and len(extra_series)==3 and extra_series.place_id.nunique()==1
        support=pd.read_csv(extra_partition/'accepted_whole_place_point_support.csv')
        assert len(support)==1 and not support.external_provider_id_binding_asserted.any()
        assert not support.individual_part_coordinates_admitted.any()
        for row in support.to_dict('records'):
            for path_field,hash_field in [('point_origin_file','point_origin_sha256'),('own_article_file','own_article_sha256'),('own_entity_file','own_entity_sha256')]:
                assert pin(Path(row[path_field]))==row[hash_field]
        for row in extra_series.to_dict('records'):
            assert not row['individual_part_coordinates_admitted'] and not row['population_boundary_comparability_asserted']
            assert int(row['primary_2002_whole_population'])==5288 and int(row['secondary_2002_population_alternative'])==5291
            assert row['secondary_primary_population_disagreement_preserved']
            for source in json.loads(row['member_source_provenance_json']):
                assert pin(Path(source['source_file']))==source['source_sha256']
        members=pd.concat([members,extra_members],ignore_index=True)
        series=pd.concat([series,extra_series],ignore_index=True)
        support.to_csv(OUT/'additional_complete_partition_point_support.csv',index=False)
    members.to_csv(OUT/'complete_publisher_partition_members.csv',index=False)
    series.to_csv(OUT/'complete_publisher_partition_series.csv',index=False)
    assert all(set(g.year)==set(YEARS) for _,g in series.groupby('place_id'))
    assert not members.source_record_id.duplicated().any()
    for r in series.to_dict('records'):
        ids=json.loads(r['member_source_record_ids_json']); vals=json.loads(r['member_populations_json'])
        assert len(ids)==len(vals)==len(set(ids)) and sum(vals)==r['population']
        assert set(members.loc[(members.place_id==r['place_id'])&(members.year==r['year']),'source_record_id'])==set(ids)
        assert r['projection_status'] in {'accepted_complete_publisher_partition','selected_whole_locality_observation'}
        for sid,v in zip(ids,vals): assert int(state.by_id.loc[sid,'population'])==int(v)
        p=Path(r['point_ledger_path']);assert pin(p)==r['point_ledger_sha256']
    partition_ids=set(members.source_record_id)
    assert partition_ids<=set(ordinary.source_record_id)
    overlay=joint|partition_ids
    fedpath=E/'federal_territory_spatial_overlay_20261005/federal_territory_observations.csv';pin(fedpath)
    fed=pd.read_csv(fedpath); fed=fed[fed.territory_key.isin(['RU-FED-MOW','RU-FED-SPE'])]
    # Use exact accepted keys when the file spells St Petersburg differently.
    if len(fed)!=6:
        fed=pd.read_csv(fedpath);fed=fed[fed.region_norm.isin(['москва','санкт петербург'])]
    assert len(fed)==6 and fed.territory_key.nunique()==2
    assert not fed[['territory_key','census_year']].duplicated().any()
    fedp={y:int(fed.loc[fed.census_year==y,'territory_population'].sum()) for y in YEARS}
    assert list(fedp.values())==[15043973,16383067,18612023]
    assert fed.population_source_record_id.nunique()==6
    overlaystats={}
    for y,d in ordinary.groupby('census_year'):
        y=int(y); npop=int(d.loc[d.source_record_id.isin(overlay),'population'].sum()); part=d[d.source_record_id.isin(partition_ids)]
        total=npop+fedp[y]
        overlaystats[y]={'ordinary_joint_population':expected[y],'whole_partition_members_population':int(part.population.sum()),'whole_partition_members_rows':len(part),'partition_net_population_added_by_source_id_union':npop-expected[y],'joint_plus_whole_partition_population':npop,'federal_territory_population':fedp[y],'federal_territory_observations':2,'combined_population':total,'official_national_control':NATIONAL[y],'common_three_census_control':COMMON[y],'percent_of_national_control':100*total/NATIONAL[y],'percent_of_common_control':100*total/COMMON[y],'gap_to_99_percent_common':max(0,math.ceil(.99*COMMON[y])-total),'selected_ordinary_plus_federal_population':DENOM[y]+fedp[y],'control_minus_selected_ordinary_plus_federal':COMMON[y]-DENOM[y]-fedp[y]}
    assert overlaystats[2010]['control_minus_selected_ordinary_plus_federal']==493512
    # Accepted physical three-year sidecars; never ordinary NP chains.
    credit=[]; physical=[]
    def existing(sid,y,pop,label):
        assert sid in state.by_id.index and int(state.by_id.loc[sid,'census_year'])==int(y) and int(state.by_id.loc[sid,'population'])==int(pop)
        credit.append({'scope':label,'source_record_id':sid,'year':int(y),'source_population':int(pop),'already_in_joint_partition_union':sid in overlay})
    def receipt(folder,status,files):
        rp=folder/'application_receipt.json';pin(rp);r=json.loads(rp.read_text());assert r['status']==status
        for name in files: assert pin(folder/name)==r['outputs'][name]
        return r
    dyp=E/'dygulybgey_event_path_20261005';pin(dyp/'accepted_series.csv');pin(dyp/'event_aware_coverage.json')
    dy=pd.read_csv(dyp/'accepted_series.csv').to_dict('records');dr=json.loads((dyp/'event_aware_coverage.json').read_text())
    assert len(dy)==3 and {int(x['year']) for x in dy}==set(YEARS) and dr['approval_status']=='applied_separate_event_aware_existing_selected_village_trajectory'
    approval=ROOT/dr['approval_source'];pin(approval)
    assert json.loads(approval.read_text())['observations']
    for r in dy:
        assert r['event_aware_link_status']=='accepted_event_aware_physical_village_trajectory'
        existing(r['source_record_id'],r['year'],r['population_used'],'dygulybgey_event_aware')
    physical.append({'scope':'dygulybgey_event_aware','series':1,'observations':3,'secondary_population_observations':0,'selected_credit_references':3})
    folder=W/'accepted_secondary_supported_troitsk_shcherbinka_trajectories'
    receipt(folder,'applied_to_separate_immutable_secondary_supported_layer',['scoped_trajectory_observations.parquet','accepted_scoped_physical_continuity_edges.parquet'])
    sec=pq.read_table(folder/'scoped_trajectory_observations.parquet').to_pylist();links=pq.read_table(folder/'accepted_scoped_physical_continuity_edges.parquet').to_pylist()
    assert len(sec)==6 and len(links)==4
    assert {(r['subject_qid'],int(r['observation_year'])) for r in sec}=={(q,y) for q in ['Q196691','Q198388'] for y in YEARS}
    assert all(r['decision_status']=='accepted_scoped_physical_continuity' and not r['population_scope_comparability_asserted'] for r in links)
    by={r['observation_id']:r for r in sec}
    for r in links:
        a,b=by[r['from_observation_id']],by[r['to_observation_id']];assert a['subject_qid']==b['subject_qid'] and (a['observation_year'],b['observation_year']) in {(2002,2010),(2010,2021)}
    for r in sec:
        if r['observation_year']==2021:
            assert r['source_record_id'] is None and not r['national_2021_additive'] and not r['native_2021_binding'] and int(r['P585_precision'])==9
            raw=json.loads(r['P1082_full_raw_statement_json']);assert raw['id']==r['statement_guid'] and int(raw['mainsnak']['datavalue']['value']['amount'])==r['population']
        else:
            existing(r['source_record_id'],r['observation_year'],r['population'],'secondary_supported_troitsk_shcherbinka')
            p=state.point_rows[r['source_record_id']];assert (p['latitude'],p['longitude'])==(r['coordinate_latitude'],r['coordinate_longitude'])
    physical.append({'scope':'secondary_supported_troitsk_shcherbinka','series':2,'observations':6,'secondary_population_observations':2,'selected_credit_references':4,'2021_child_population_added':0})
    for name in ['talnakh','kayerkan']:
        folder=W/f'accepted_{name}_typed_scope';receipt(folder,'materialized_accepted_separate_scoped_layer',['scoped_primary_observations.parquet','scoped_point_uses.parquet','accepted_typed_scope_edges.parquet','loader_schema.json'])
        rows=pq.read_table(folder/'scoped_primary_observations.parquet').to_pylist();uses=pq.read_table(folder/'scoped_point_uses.parquet').to_pylist();links=pq.read_table(folder/'accepted_typed_scope_edges.parquet').to_pylist()
        assert len(rows)==len(uses)==3 and len(links)==2
        byyear={int(r['observation_year']):r for r in rows};assert set(byyear)==set(YEARS)
        assert all(r['source_status']=='official_primary_source_observation' and not r['national_additive'] and not r['ordinary_NP_same_grain_identity'] for r in rows)
        assert all(r['decision_status']=='accepted_scoped_typed_physical_place_relation' and not r['population_comparability_asserted'] and not r['parent_population_transfer'] for r in links)
        assert {(r['from_observation_id'],r['to_observation_id']) for r in links}=={(byyear[a]['observation_id'],byyear[b]['observation_id']) for a,b in [(2002,2010),(2010,2021)]}
        assert {r['target_observation_id'] for r in uses}=={r['observation_id'] for r in rows}
        for r in uses: assert r['point_status']=='accepted_scoped_named_place_point_use' and pin(Path(r['point_origin_file']))==r['point_origin_sha256']
        old=byyear[2002];hook=json.loads((folder/'loader_schema.json').read_text())['old_2002_union_hook']
        assert hook['source_record_id']==old['source_record_id'] and int(hook['old_primary_value'])==old['population']
        existing(old['source_record_id'],2002,old['population'],name+'_typed')
        for y in YEARS:
            parent=ordinary[(ordinary.census_year==y)&ordinary.settlement_name.eq('Норильск')];assert len(parent)==1 and int(parent.iloc[0].population)==byyear[y]['nested_norilsk_city_population'] and parent.iloc[0].source_record_id in overlay
        assert all(byyear[y]['source_record_id'] is None for y in [2010,2021])
        physical.append({'scope':name+'_typed','series':1,'observations':3,'secondary_population_observations':0,'selected_credit_references':1,'later_district_population_added':0})
    folder=W/'accepted_primary2010_auxiliary_temporal16_scope'
    ar=receipt(folder,'applied_scoped_primary_auxiliary_date_trajectories',['accepted_trajectories.json','accepted_existing_primary_credit_references.json'])
    assert not ar['ordinary_graph_modified'] and not ar['source_population_values_modified'] and ar['auxiliary_2010_population_nationally_added']==0
    trajectories=json.loads((folder/'accepted_trajectories.json').read_text())['trajectories'];refs=json.loads((folder/'accepted_existing_primary_credit_references.json').read_text())
    assert len(trajectories)==ar['trajectories']==16 and len(refs)==ar['existing_primary_credit_references']==32
    for t in trajectories:
        assert t['status']=='accepted_scoped_primary_auxiliary_date_trajectory' and not t['ordinary_primary_NP3'] and not t['boundary_comparability_asserted']
        assert len(t['observations'])==3 and {int(r['year']) for r in t['observations']}==set(YEARS)
        aux=next(r for r in t['observations'] if int(r['year'])==2010);assert aux['source_record_id'] not in state.by_id.index and not aux['source_membership_in_selected_observations']
    for r in refs:
        assert int(r['year']) in [2002,2021];existing(r['source_record_id'],r['year'],r['population'],'primary2010_auxiliary16')
        p=r['point_carrier']; active=state.point_rows[r['source_record_id']];assert p['status'] in ACCEPTED_COORDINATE_STATUSES and (p['latitude'],p['longitude'])==(active['latitude'],active['longitude'])
    physical.append({'scope':'primary2010_auxiliary16','series':16,'observations':48,'secondary_population_observations':0,'selected_credit_references':32,'auxiliary2010_population_added':0})
    folder=E/'auxiliary_observed_years_application_20261007'
    ar=receipt(folder,'applied_actual_auxiliary_observations_with_nonadditive_missing_years',['accepted_qualified_physical_observations.csv','held_missing_coordinate_series.csv','accepted_point_use_delta.csv'])
    applied=pd.read_csv(folder/'accepted_qualified_physical_observations.csv')
    assert len(applied)==ar['actual_observations']==27 and applied.trajectory_id.nunique()==ar['physical_three_observed_year_series']==9
    assert ar['held_series_without_accepted_point']==9 and applied.nonadditive_observation.sum()==9
    assert applied.accepted_physical_three_observed_census_year_path.all() and applied.accepted_scoped_representative_point.all()
    assert not applied.ordinary_NP3_asserted.any() and not applied.boundary_comparability_asserted.any()
    for r in applied.to_dict('records'):
        assert pin(Path(r['source_path']))==r['source_sha256']
        if not r['nonadditive_observation']:
            existing(r['source_record_id'],r['year'],r['population_source_value'],r['scope'])
            assert state.by_id.loc[r['source_record_id'],'population_value_quality']==r['population_quality']
        else:
            assert r['source_record_id'] not in state.by_id.index
    physical.append({'scope':'auxiliary_observed_years_20261007','series':9,'observations':27,'secondary_population_observations':1,'selected_credit_references':18,'protected_auxiliary2010_population_added':0,'dated_secondary2002_population_added':0,'held_unpointed_candidates_excluded':9})
    event_folder=E/'recreated_named_locality_event_application_20261007'
    if (event_folder/'application_receipt.json').exists():
        er=receipt(event_folder,'applied_secondary_documented_named_district_recreation_series',['accepted_qualified_physical_observations.csv'])
        event=pd.read_csv(event_folder/'accepted_qualified_physical_observations.csv')
        assert len(event)==6 and event.trajectory_id.nunique()==2 and event.nonadditive_observation.sum()==2
        assert not event.ordinary_NP3_asserted.any() and not event.boundary_comparability_asserted.any()
        assert event.decision_status.eq('qualified_accepted_secondary_event_witness').all()
        for _,g in event.groupby('trajectory_id'): assert set(g.year)==set(YEARS)
        for r in event.to_dict('records'):
            assert pin(Path(r['source_path']))==r['source_sha256']
            assert pin(Path(r['point_origin_file']))==r['point_origin_sha256']
            if r['nonadditive_observation']:
                assert int(r['year'])==2002
            else:
                assert int(r['year']) in [2010,2021]
                existing(r['source_record_id'],r['year'],r['population_source_value'],r['scope'])
                assert state.by_id.loc[r['source_record_id'],'population_value_quality']==r['population_quality']
        assert int(event.loc[event.year.eq(2002),'population_source_value'].sum())==13892+10189
        assert int(event.loc[event.year.eq(2010),'population_source_value'].sum())==24011
        assert int(event.loc[event.year.eq(2021),'population_source_value'].sum())==24041
        physical.append({'scope':'named_district_recreation_2009','series':2,'observations':6,'secondary_population_observations':0,'selected_credit_references':4,'primary2002_quarter_population_nationally_added':0,'ordinary_NP3_asserted':False,'boundary_comparability_asserted':False})
    from secondary_full3 import load as load_secondary_full3
    pin(OUT/'secondary_full3.py')
    secondary_packs=load_secondary_full3(E,state,pin)
    for dirname,secondary_receipt,frame in secondary_packs:
        for r in frame.loc[~frame.nonadditive_observation].to_dict('records'):
            existing(r['source_record_id'],r['year'],r['population_source_value'],r['scope'])
        physical.append({'scope':dirname,'series':len(frame[['scope','trajectory_id']].drop_duplicates()),'observations':len(frame),'secondary_population_observations':int(frame.nonadditive_observation.sum()),'selected_credit_references':int((~frame.nonadditive_observation).sum()),'ordinary_NP3_asserted':False,'boundary_comparability_asserted':False})
    pd.DataFrame(physical).to_csv(OUT/'qualified_physical_series.csv',index=False)
    credits=pd.DataFrame(credit)
    credits['already_in_ordinary_joint']=credits.source_record_id.isin(joint)
    credits['credit_union_first_reference']=~credits.source_record_id.duplicated()
    credits.to_csv(OUT/'qualified_scope_source_id_credit_union.csv',index=False)
    extra=set(credits.source_record_id);scopeunion=overlay|extra
    qualified={}
    for y,d in ordinary.groupby('census_year'):
        y=int(y);pop=int(d.loc[d.source_record_id.isin(scopeunion),'population'].sum())+fedp[y]
        qualified[y]={'qualified_selected_source_id_union_net_population_added':pop-overlaystats[y]['combined_population'],'population_including_federal_territories':pop,'percent_of_common_control':100*pop/COMMON[y],'gap_to_99_percent_common':max(0,math.ceil(.99*COMMON[y])-pop)}
    from physical_observations import build as build_physical
    pin(OUT/'physical_observations.py')
    physical_axis=build_physical(E,W,OUT,joint,overlay,COMMON,[frame for _,_,frame in secondary_packs])
    from national_unions import build as build_national_unions
    pin(OUT/'national_unions.py')
    stronger_national_union=build_national_unions(ordinary,componentpoints,partition_ids,extra,fedp,NATIONAL,COMMON)
    # Top residuals remain relative to strict ordinary point + full-three identity.
    ordinary['accepted_point']=ordinary.source_record_id.isin(point)
    ordinary['full_three_census_identity']=ordinary.source_record_id.isin(full)
    ordinary['all_component_points']=ordinary.source_record_id.isin(componentpoints)
    ordinary['covered_by_complete_partition_scope']=ordinary.source_record_id.isin(partition_ids)
    ordinary['covered_by_qualified_physical_scope']=ordinary.source_record_id.isin(extra)
    columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm','district_raw','population','population_value_quality','accepted_point','full_three_census_identity','all_component_points','covered_by_complete_partition_scope','covered_by_qualified_physical_scope','source_file','source_sha256','source_locator']
    for y,d in ordinary.groupby('census_year'):
        residual=d[~d.source_record_id.isin(joint)].nlargest(100,'population');residual[columns].to_csv(OUT/f'top100_strict_joint_residual_{int(y)}.csv',index=False)
    ordinary['strict_joint_population']=ordinary.population.where(ordinary.source_record_id.isin(joint),0)
    ordinary['scope_union_population']=ordinary.population.where(ordinary.source_record_id.isin(scopeunion),0)
    rg=ordinary.groupby(['census_year','region_norm']).agg(selected_population=('population','sum'),selected_rows=('source_record_id','count'),strict_joint_population=('strict_joint_population','sum'),qualified_union_population=('scope_union_population','sum')).reset_index()
    rg['strict_joint_gap_population']=rg.selected_population-rg.strict_joint_population
    rg['joint_percent_selected']=100*rg.strict_joint_population/rg.selected_population
    rg['gap_rank_within_year']=rg.groupby('census_year').strict_joint_gap_population.rank(method='min',ascending=False).astype(int)
    rg.sort_values(['census_year','gap_rank_within_year']).to_csv(OUT/'regional_joint_gap_rank.csv',index=False)
    # Growth diagnostic: accepted ordinary same-place adjacent census pairs only.
    fullrows=ordinary.loc[ordinary.source_record_id.isin(linked),['root','source_record_id','census_year','population','settlement_name','region_norm','population_value_quality']]
    groups={root:g for root,g in fullrows.groupby('root')};growth=[]
    for root,g in groups.items():
        rows=sorted(g.to_dict('records'),key=lambda r:r['census_year'])
        for a,b in zip(rows,rows[1:]):
            pa,pb=a['population'],b['population'];ratio=None
            if pd.isna(pa) or pd.isna(pb):flag='unknown_population'
            elif pa==0:flag='zero_to_positive' if pb>0 else 'zero_to_zero'
            elif pb==0:flag='positive_to_zero'
            elif pa>0 and pb>0:
                ratio=pb/pa;flag='growth_gt20x_positive' if ratio>20 else ('shrink_gt20x_positive' if ratio<.05 else None)
            else:flag='negative_population'
            if flag:growth.append({'root':root,'from_source_record_id':a['source_record_id'],'to_source_record_id':b['source_record_id'],'from_year':int(a['census_year']),'to_year':int(b['census_year']),'settlement_name_from':a['settlement_name'],'settlement_name_to':b['settlement_name'],'region_norm':b['region_norm'],'from_population':pa,'to_population':pb,'ratio':ratio,'flag':flag,'population_quality_from':a['population_value_quality'],'population_quality_to':b['population_value_quality']})
    growthdf=pd.DataFrame(growth);growthdf.to_csv(OUT/'accepted_growth_and_zero_unknown_flags.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    # Status counts describe accepted ledger inputs, not unique graph edges.
    con=duckdb.connect(config={'threads':1,'memory_limit':'512MB'})
    status={}
    for p in dict.fromkeys(state.inputs):
        if p.suffix=='.parquet' and p in [EDGES,POINTS]:
            fields='decision_status' if p==EDGES else 'coordinate_admission_status'
            status[str(p)]={str(k):int(v) for k,v in con.execute(f'SELECT {fields}, count(*) FROM read_parquet(?) GROUP BY 1',[str(p)]).fetchall()}
        elif '.csv' in p.name:
            f=pd.read_csv(p,keep_default_na=False)
            status[str(p)]={col:f[col].value_counts().to_dict() for col in ['decision_status','coordinate_admission_status','rejection_status'] if col in f}
    active=collections.Counter(r.get('coordinate_admission_status','legacy_accepted') for r in state.point_rows.values())
    # Official 2010 regional control mapping is recorded separately below.
    controls=Path('/workspace/settlements-raw/data/raw/2010_official_controls/rosstat_population2010_by_region.csv');pin(controls)
    from regional_controls import reconcile
    pin(OUT/'regional_controls.py')
    regional_control_receipt=reconcile(ordinary,fed,controls,scopeunion,OUT)
    report={'status':'recomputed_baseline_and_unique_source_id_unions_verified','working_stage':stage,'ordinary_axes_by_year':metrics,'baseline_strict_joint_population':BASELINE,'actual_cumulative_gain_by_unique_source_id_union':gains,'complete_partition_plus_federal_overlay':overlaystats,'qualified_physical_scope_all_grains':{'ordinary_np_three_year_identity_asserted':False,'series':sum(r['series'] for r in physical),'observations':sum(r['observations'] for r in physical),'secondary_population_observations':sum(r['secondary_population_observations'] for r in physical),'scopes':physical,'source_id_credit_reference_rows':len(credits),'unique_selected_credit_source_ids':credits.source_record_id.nunique(),'by_year':qualified},'growth_flags':{'axis':'accepted ordinary adjacent same-place census pairs; positive ratio >20, reverse <1/20 separately, zero/unknown never ratio-imputed','counts':growthdf.flag.value_counts().to_dict() if len(growthdf) else {},'total_flagged_pairs':len(growthdf)},'accepted_status_enums':{'edge':sorted(ACCEPTED_EDGE_STATUSES),'point':sorted(ACCEPTED_COORDINATE_STATUSES)},'input_ledger_status_counts':status,'active_point_status_counts':dict(active),'active_point_target_count':len(point),'same_place_components_all_grains':len(state.years),'full_three_year_components_all_grains':sum(v==set(YEARS) for v in state.years.values()),'point_alternatives':len(state.point_alternatives),'conflicting_point_targets':len(state.conflicting_point_targets),'official_2010_control_minus_selected_ordinary_and_federal':493512,'regional_official_2010_control_mapping':{'status':'not_recalculated_pending_unambiguous_control_region_mapping','national_gap_preserved':493512,'required_parent_folds':'Nenets to Arkhangelsk; Khanty-Mansi and Yamalo-Nenets to Tyumen; inclusive published parent controls'},'limits':['Accepted point use is not a coordinate calibration or census-date measurement claim.','Ordinary denominator excludes Moscow, St Petersburg, Sevastopol and 2021 Crimea. Federal Moscow/St Petersburg territories are separate nonsettlement aggregates.','2021 common control excludes Crimea 1934630 and Sevastopol 547820; national control retains them. Neither 2014-only paths nor absorption-only parent context counts as three observed census years.','Partition points cover whole place, not each individual numbered part. Derived population sums do not add extra population.','Qualified physical series retain grain changes, secondary 2021 values and auxiliary nonadditive observations; they do not assert ordinary NP identity, boundary comparability or unchanged scopes.','2010 protected selected values retain their original quality. All source populations remain unchanged. Candidate-only ledgers never included.']}
    report['regional_official_2010_control_mapping']=regional_control_receipt
    report['all_three_component_points_national_unions']=stronger_national_union
    report['own_row_point_plus_full3_companion_definition']='Companion axis: each counted ordinary row has its own admitted point use and a three-year identity component. Other rows in the same component may lack point uses; this is not the all-three-point axis.'
    report['qualified_physical_actual_observation_axis']=physical_axis
    from point_claims import build as build_point_claims
    pin(OUT/'point_claims.py')
    report['accepted_point_claim_origins_and_quality']=build_point_claims(state,ordinary,POINTS,joint,componentpoints,full,point,OUT)
    review=E/'residual_same_name_5km_batch_20261007'
    for name in ['root_review_receipt.json','root_admission_recommendations.csv','root_review_physical_county_context.csv']: pin(review/name)
    review_receipt=json.loads((review/'root_review_receipt.json').read_text())
    assert review_receipt['held_county_contradictions']==7 and review_receipt['eligible_candidates']==4
    for p,h in review_receipt['cached_physical_source_hashes'].items(): assert pin(Path(p))==h
    report['reviewed_proximity_counterexample']={'original_candidates':11,'held_wrong_county':7,'eligible_later_accepted':4,'example':'Курилово: historical 2002 population 2371 is a Подольский locality; nearby 2021 population 33 belongs to Солнечногорск. The accepted historical point is a wrong namesake; name and proximity do not repair the county contradiction. The candidate edge was held and is not counted.','proof_receipt':str(review/'root_review_receipt.json'),'proof_source_context':str(review/'root_review_physical_county_context.csv')}
    from named_merger_lineage import build as build_named_merger_lineage
    pin(OUT/'named_merger_lineage.py')
    report['named_merger_lineage_extended_population_axis']=build_named_merger_lineage(E,state,ordinary,componentpoints,partition_ids,extra,fedp,NATIONAL,COMMON,OUT,pin)
    from export_full3 import build as export_full3
    pin(OUT/'export_full3.py')
    pin(OUT/'verify_export.py')
    report['ordinary_complete_number_export']=export_full3(state,ordinary,componentpoints,stage,pins,OUT,reuse=reuse_ordinary_export)
    from finite_number_unions import build as build_finite_unions
    pin(OUT/'finite_number_unions.py')
    finite_national_union=build_finite_unions(report,OUT)
    report['finite_three_population_all_three_component_points_national_unions']=finite_national_union
    stronger_national_union=finite_national_union
    from final_mixed_residuals import build as build_final_mixed_residuals
    pin(OUT/'final_mixed_residuals.py')
    lineage=report['named_merger_lineage_extended_population_axis']
    named_ids=set(pd.read_csv(OUT/'named_merger_lineage_constituents.csv').source_record_id) if lineage['status']=='admitted_separate_named_merger_event_lineage' else set()
    report['final_mixed_remaining_native_observation_priority']=build_final_mixed_residuals(state,ordinary,componentpoints,partition_ids,extra,named_ids,OUT)
    report['auxiliary_iteration']=auxiliary_iteration
    report['baseline_snapshot_git_commit']=baseline_snapshot
    report['ordinary_export_reused_without_rewrite']=reuse_ordinary_export
    named_axis=report['named_merger_lineage_extended_population_axis']
    if named_axis['status']=='admitted_separate_named_merger_event_lineage':
        threshold={y:{'population':named_axis['by_year'][y]['extended_named_lineage_population'],'percent_of_common_control':named_axis['by_year'][y]['percent_of_common_control'],'gap_to_99_percent_common':named_axis['by_year'][y]['gap_to_99_percent_common']} for y in YEARS}
    else:
        threshold={y:{'population':stronger_national_union['by_year'][y]['all_three_component_points_plus_partitions_plus_qualified_physical_scopes_plus_federal']['combined_population'],'percent_of_common_control':stronger_national_union['by_year'][y]['all_three_component_points_plus_partitions_plus_qualified_physical_scopes_plus_federal']['percent_of_common_control'],'gap_to_99_percent_common':stronger_national_union['by_year'][y]['all_three_component_points_plus_partitions_plus_qualified_physical_scopes_plus_federal']['gap_to_99_percent_common']} for y in YEARS}
    reached=[y for y in YEARS if threshold[y]['percent_of_common_control']>=99]
    remaining=[y for y in YEARS if y not in reached]
    report['common_control_99_percent_goal_status']={'axis':'Finite ordinary all-three-point populations plus complete whole-place partitions, qualified physical selected source-ID union, Moscow/SPB territories and separate admitted named mergers','years_reaching_99_percent_common_control':reached,'years_still_below_99_percent_common_control':remaining,'all_three_census_years_goal_met':len(reached)==3,'by_year':threshold,'ordinary_only_99_percent_goal_met':False,'2021_national_control_includes_Crimea_and_Sevastopol':True}
    # Detect concurrent ledger edits; pin content exactly as measured.
    for p,m in pins.items(): assert sha(Path(p))==m['sha256'], 'Input changed during measurement: '+p
    report['wall_seconds']=round(time.monotonic()-start,3)
    write_json('coverage_receipt.json',report);write_json('input_hash_manifest.json',pins)
    from verify_export import main as verify_export
    verify_export()
    text=['# Working coverage receipt, 2026-10-07','','Reproduce from repository root:','','```bash',f'python research_rebuild/evidence/working_full_chain_20261007/build_report.py --stage {stage}','```','','Frozen State() baseline and working_state_20261007.load(stage=selected_stage) reproduce their pinned population totals. Population is credited by exclusive source-ID union, never by summing successive receipts.','', 'The leading table requires admitted point uses and finite source populations on all three census rows in every ordinary identity component. The one unknown-2010 component is excluded for every year; the separate all-three-point axis retains it with its unknown flag. Whole partitions and federal territories use their separately admitted representative-point scopes.', '', '| Year | Ordinary full3, all three points and finite numbers | + whole partitions + Moscow/SPB territories | Common control % | + qualified physical scopes | Common control % | Qualified gap to 99% |','|---|---:|---:|---:|---:|---:|---:|']
    for y in YEARS:
        stronger=stronger_national_union['by_year'][y]
        p=stronger['all_three_component_points_plus_whole_partitions_plus_federal']
        q=stronger['all_three_component_points_plus_partitions_plus_qualified_physical_scopes_plus_federal']
        text.append(f"| {y} | {stronger['ordinary_all_three_component_point_uses']['population']:,} | {p['combined_population']:,} | {p['percent_of_common_control']:.5f} | {q['combined_population']:,} | {q['percent_of_common_control']:.5f} | {q['gap_to_99_percent_common']:,} |")
    text+=['','Companion axis: an ordinary row has its own point use and a three-year identity component, while another census row in that component may lack a point use. These totals are not labelled as all-three-point coverage.','', '| Year | Ordinary own-point + full3 identity | + partitions + FED | Common control % | + qualified physical scopes | Common control % |','|---|---:|---:|---:|---:|---:|']
    for y in YEARS:
        text.append(f"| {y} | {expected[y]:,} | {overlaystats[y]['combined_population']:,} | {overlaystats[y]['percent_of_common_control']:.5f} | {qualified[y]['population_including_federal_territories']:,} | {qualified[y]['percent_of_common_control']:.5f} |")
    text+=['','The ordinary point_and_full_three_census_identity axis requires a point on the row being counted and a three-year identity component. The stricter full_three_census_with_all_component_points axis requires an admitted own-point use on each of its three census source rows. The small difference is listed explicitly in own_point_full3_components_missing_other_year_points.csv.','', 'Coordinate origin and claimed quality counts are recorded separately. Seven proximity candidates remain held for physical source county contradictions. For example, Курилово (2,371 in the historical Подольский source) was near a 33-person Солнечногорск namesake because the earlier accepted coordinate itself was wrongly bound; that candidate edge remains excluded. See the pinned root_review_physical_county_context.csv evidence.','', f"The mixed-grain exclusive source-ID union reaches 99% of common control for {', '.join(map(str,reached)) or 'no census year'}; {', '.join(map(str,remaining)) or 'no census year'} remains below 99%. Ordinary settlement full3 coverage and the all-three-census-year goal remain unmet. Official national and common controls are explicit in the JSON; 2021 common excludes Crimea and Sevastopol. The 2010 selected-source population shortfall remains 493,512. Regional rankings include both selected-population gaps and a separate 2010 official-control reconciliation with 83 explicit region mappings folded to 80 disjoint controls. Nenets folds into Arkhangelsk; Khanty-Mansi and Yamalo-Nenets fold into Tyumen. This is a region-level check, not a full municipal audit.",'',f"Qualified physical scopes contain {sum(r['series'] for r in physical)} three-observed-year series, including two secondary-supported 2021 children and one dated secondary 2002 observation. Nine unpointed candidate series are held and excluded. Later Norilsk districts and auxiliary 2010 observations contribute zero additive population. Existing primary source IDs are credited once in the sidecar union.",'','Accepted points are reviewed representative point uses, including retrospective continuity inferences. Coordinate calibration, census-date measurements, boundary equivalence and ordinary NP grain equivalence for physical sidecars are not asserted. Source population values and quality flags are unchanged. Candidate-only paths, 2014-only paths and absorption-only receiving-parent context never count as full3.','','The top100 residual and regional ranking files use strict ordinary full3 + point as the gap axis; sidecar coverage flags remain explicit. Growth flags describe accepted adjacent ordinary census pairs; zero and unknown populations are not imputed.','',f"Wall time: {report['wall_seconds']} seconds. Exact graph, point, delta, sidecar and code hashes are in input_hash_manifest.json."]
    lineage=report['named_merger_lineage_extended_population_axis']
    if lineage['status']=='admitted_separate_named_merger_event_lineage':
        text+=['', f"Separate named merger/event lineage extension: {lineage['groups']} complete named rosters, {lineage['observations']} census-year group observations and {lineage['representative_scope_points']} receiving-parent representative scope points. This different grain retains boundary comparability UNKNOWN and secondary documented event sources; historical constituents are not asserted as ordinary settlements individually observed in all three censuses.", '', '| Year | Finite ordinary + partitions + qualified + FED | Named lineage net exclusive source-ID gain | Extended lineage population | Common control % |', '|---|---:|---:|---:|---:|']
        for y in YEARS:
            row=lineage['by_year'][y]
            text.append(f"| {y} | {row['finite_ordinary_plus_partitions_qualified_federal_population']:,} | {row['named_lineage_net_population_added_by_exclusive_source_ID_union']:,} | {row['extended_named_lineage_population']:,} | {row['percent_of_common_control']:.5f} |")
        text+=['', 'The individual lineage observations, complete constituent source IDs, scope points and event relations are exported separately in named_merger_lineage_*.csv. Ordinary NP3 and the qualified physical register remain separate. No group sum is added on top of constituent credits.']
    quality_unknown=json.loads((OUT/'export_verification_receipt.json').read_text())['unknown_imported_population_quality_rows_by_year']
    text+=['', 'Imported empty population quality values remain unknown, unchanged: '+', '.join(f'{y}: {n} export rows' for y,n in quality_unknown.items())+'.']
    (OUT/'README.md').write_text('\n'.join(text)+'\n')
    outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in OUT.iterdir() if p.is_file() and p.name!='output_hash_manifest.json'}
    write_json('output_hash_manifest.json',outputs)
    print(json.dumps({'all_three_component_points_national_unions':stronger_national_union,'own_row_point_plus_full3_companion':overlaystats,'qualified_own_row_point_companion':qualified,'growth_flag_counts':report['growth_flags']['counts'],'wall_seconds':report['wall_seconds'],'output_bytes':sum(x['bytes'] for x in outputs.values())}))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',type=int,default=7);parser.add_argument('--reuse-ordinary-export',action='store_true',help='Reuse only when graph/point/selected ledger bytes and recomputed ordinary coverage are unchanged')
    parser.add_argument('--auxiliary-iteration');parser.add_argument('--baseline-snapshot');args=parser.parse_args();main(args.stage,args.reuse_ordinary_export,args.auxiliary_iteration,args.baseline_snapshot)
