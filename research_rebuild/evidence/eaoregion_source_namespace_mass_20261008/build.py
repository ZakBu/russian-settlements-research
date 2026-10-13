"""Source-header-bound EAO interpretation and bounded native identity application."""
import collections
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import xlrd

ROOT = Path(__file__).resolve().parents[3]
E = ROOT / 'research_rebuild/evidence'
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha, normalize, distance_km
from apply_unique_county_name_bridge_20261007 import county_key

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

finite = module('finite_eao', E/'working_full_chain_20261007/replay_additional_native_20261008.py').finite
def nm(value):
    value=normalize(value)
    return re.sub(r'["«»]', '', re.sub(r'^(?:поселок|село|деревня|станица|аул|пгт|рп|п\.|с\.|д\.)\s+', '', value))
def ty(value):
    value=normalize(value)
    return {'поселок':'rural_NP','село':'rural_NP','деревня':'rural_NP','хутор':'rural_NP',
            'рабочий поселок':'пгт','рп':'пгт','поселок городского типа':'пгт'}.get(value,value)

def finite_ids(state):
    bad=~state.obs.source_record_id.isin(state.point_rows)|~np.isfinite(state.obs.population)
    badroots=set(state.obs.loc[bad,'root'])|{state.uf.find(i) for i in state.conflicting_point_targets}
    roots={r for r in state.obs.root.unique() if state.years[r]=={2002,2010,2021} and r not in badroots}
    return set(state.obs.loc[state.obs.root.isin(roots),'source_record_id'])

def main():
    pins={}
    def pin(path, expected=None):
        path=Path(path); actual=sha(path)
        if expected: assert actual==expected, str(path)
        pins[str(path)]=actual
        return actual
    raw=Path('/workspace/settlements-raw/data/raw/2002/086_3c3b73a0d2_EvrejskajaAO.xls')
    manifest_path=E/'working_full_chain_20261007/input_hash_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    frozen_manifest=OUT/'frozen_source_manifest_context.json'
    frozen_manifest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');pin(frozen_manifest)
    pin(raw,manifest[str(raw)]['sha256'])
    selected=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');pin(selected)
    book=xlrd.open_workbook(str(raw),on_demand=True);sheet=book.sheet_by_name('Sheet1')
    assert sheet.cell_value(0,0)=='Еврейская АО' and float(sheet.cell_value(1,1))==62556
    c=duckdb.connect();native=c.execute("SELECT source_record_id,region_raw,region_norm,source_row,source_name_raw FROM read_parquet(?) WHERE census_year=2002 AND source_file='data/raw/2002/086_3c3b73a0d2_EvrejskajaAO.xls'",[str(selected)]).fetchdf();c.close()
    state=load(49)
    fifty=E/'native2010_remaining_county_rule_mass_20261008';r50=json.loads((fifty/'application_receipt.json').read_text());pin(fifty/'application_receipt.json')
    for filename,expected in r50['output_pins'].items():pin(fifty/filename,expected)
    state.add_deltas([fifty/'accepted_identity_edge_delta.csv.gz'],[fifty/'accepted_point_use_delta.csv.gz'])
    assert finite(state)==r50['after_finite_all3_all_points']
    for path in state.inputs:pin(path)
    protected=state.obs[['source_record_id','population','population_value_quality','settlement_name','settlement_type','source_file','source_path','source_sha256','source_locator']].copy()
    before=finite(state);before_metrics=state.metrics()
    previous_finite_ids=finite_ids(state)
    scope_sets={'original_mixed':set(),'direct_lifecycle':set(),'direct_plus_formation':set()}
    for filename in ['complete_publisher_partition_members.csv','qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv']:
        path=fifty/('baseline49_union_'+filename+'.gz');pin(path)
        frame=pd.read_csv(path,keep_default_na=False)
        scope_sets['original_mixed'].update(frame.source_record_id.astype(str))
    scope_sets['direct_lifecycle']=set(scope_sets['original_mixed'])
    path=fifty/'baseline49_union_direct_inclusion_transformation_path_native_credit_union.csv.gz';pin(path)
    scope_sets['direct_lifecycle'].update(pd.read_csv(path,keep_default_na=False).source_record_id.astype(str))
    scope_sets['direct_plus_formation']=set(scope_sets['direct_lifecycle'])
    path=fifty/'baseline49_union_formation_path_native_credit_union.csv.gz';pin(path)
    scope_sets['direct_plus_formation'].update(pd.read_csv(path,keep_default_na=False).source_record_id.astype(str))
    assert len(native)==98
    oldids=set(native.source_record_id);old=state.obs[state.obs.source_record_id.isin(oldids)]
    assert old.population.sum()==62556
    canonical=state.obs[state.obs.census_year.eq(2002)&state.obs.region_norm.eq('еврейская')]
    assert canonical.population.sum()==128359 and canonical.population.sum()+old.population.sum()==190915
    corrections=[];raw_checks=[]
    for row in native.itertuples():
        obs=state.by_id.loc[row.source_record_id];values=sheet.row_values(int(row.source_row)-1)
        assert row.region_norm=='086_3c3b73a0d2_evrejskajaao'
        assert normalize(values[0])==normalize(row.source_name_raw) and float(values[1])==obs.population
        corrections.append(dict(source_record_id=row.source_record_id,census_year=2002,region_norm_original_import=row.region_norm,
            region_raw_original_import=row.region_raw,effective_region_norm='еврейская',source_file_original_import=obs.source_file,
            interpretation_status='checked_source_header_interpretation_accepted',interpretation_rule='Exact raw Sheet1!A1 Еврейская АО; source-specific filename namespace only',
            source_namespace_witness_file=str(raw),source_namespace_witness_sha256=pins[str(raw)],source_namespace_witness_locator='Sheet1!A1',
            source_population_modified=False,raw_source_metadata_overwritten=False))
        raw_checks.append(dict(source_record_id=row.source_record_id,settlement_name=obs.settlement_name,settlement_type=obs.settlement_type,
            native_population=obs.population,native_population_quality=obs.population_value_quality,county_raw=obs.district_raw,
            raw_locator=f'Sheet1!row_1based={row.source_row}',raw_row_json=json.dumps(values,ensure_ascii=False),
            source_file=str(raw),source_sha256=pins[str(raw)]))
    pd.DataFrame(corrections).to_csv(OUT/'source_namespace_interpretation_delta.csv',index=False)
    pd.DataFrame(raw_checks).to_csv(OUT/'actual98_native_raw_source_checks.csv',index=False)
    state.obs['region_norm_original_import']=state.obs.region_norm
    state.by_id['region_norm_original_import']=state.by_id.region_norm
    state.obs.loc[state.obs.source_record_id.isin(oldids),'region_norm']='еврейская'
    state.by_id.loc[list(oldids),'region_norm']='еврейская'
    assert state.obs.region_norm.eq('086_3c3b73a0d2_evrejskajaao').sum()==0
    assert finite(state)==before and state.metrics()==before_metrics
    members=collections.defaultdict(list)
    for row in state.obs.itertuples():members[state.uf.find(row.source_record_id)].append(row.source_record_id)
    regional=state.obs[state.obs.region_norm.eq('еврейская')]
    index=collections.defaultdict(list)
    for row in regional.itertuples():index[(int(row.census_year),nm(row.settlement_name))].append(row.source_record_id)
    rivals=[];edges=[];points=[];positives=[];holds=[];retained=[]
    for row in old.sort_values('population',ascending=False).itertuples():
        sid=row.source_record_id;name=nm(row.settlement_name);county=county_key(row.district_raw)
        all02=index[(2002,name)];all10=index[(2010,name)];all21=index[(2021,name)]
        for rid in all02+all10+all21:
            rr=state.by_id.loc[rid]
            rivals.append(dict(target2002_source_record_id=sid,rival_source_record_id=rid,census_year=int(rr.census_year),
                name=rr.settlement_name,type=rr.settlement_type,county_raw=rr.district_raw,county_key=county_key(rr.district_raw),
                original_region_norm=rr.region_norm_original_import,effective_region_norm=rr.region_norm,point_present=rid in state.point_rows))
        if state.years[state.uf.find(sid)]=={2002,2010,2021}:
            holds.append(dict(source_record_id=sid,reason='already_native_complete_component'));continue
        def choose(ids):
            typed=[i for i in ids if ty(state.by_id.loc[i,'settlement_type'])==ty(row.settlement_type)]
            in_county=[i for i in typed if county and county_key(state.by_id.loc[i,'district_raw'])==county]
            if len(in_county)==1:return in_county
            if len(typed)==1 and (not county_key(state.by_id.loc[typed[0],'district_raw']) or not county):return typed
            return []
        current=choose(all21);oldrivals=choose(all02)
        if current and oldrivals==[sid]:
            cid=current[0];currentroot=state.uf.find(cid)
            twin=[i for i in members[currentroot] if int(state.by_id.loc[i,'census_year'])==2010]
            ten=twin or choose(all10)
            if len(ten)==1 and len(choose(all10))<=1:
                tid=ten[0];ids=[sid,tid,cid];roots={state.uf.find(i) for i in ids}
                union_years=set();collision=False
                for root in roots:
                    if union_years & state.years[root]:collision=True
                    union_years |= state.years[root]
                carrier=state.point_rows.get(cid)
                if not collision and union_years=={2002,2010,2021} and carrier and not any(i in state.conflicting_point_targets for root in roots for i in members[root]):
                    existing=[state.point_rows[i] for root in roots for i in members[root] if i in state.point_rows]
                    if all(distance_km((p['latitude'],p['longitude']),(carrier['latitude'],carrier['longitude']))<=5 for p in existing):
                        rule='Raw source-header region interpretation; exact ownNP name, compatible printed rural class or exact other class and explicit historical county; all class/county competitors before component filtering; accepted own current point'
                        for a,b in [(sid,tid),(tid,cid)]:
                            if state.uf.find(a)!=state.uf.find(b):
                                edges.append(dict(from_source_record_id=a,to_source_record_id=b,relation='same_place',decision_status='checked_rule_accepted',admission_rule=rule,boundary_comparability_asserted=False))
                                state.union(a,b)
                        for target in ids:
                            if target in state.point_rows:
                                retained.append(dict(source_record_id=target,decision='existing_admitted_point_retained'));continue
                            p=dict(carrier);p.update(target_source_record_id=target,coordinate_source_record_id=cid,coordinate_admission_status='reviewed_extension_rule_accepted',
                                admission_allowed=True,admission_rule=rule,point_temporal_interpretation='Accepted current ownNP point retrospectively reused by source-bound physical continuity; no census-day measurement',
                                municipal_P625_projected_to_NP=False,boundary_comparability_asserted=False)
                            points.append(p);state.point_rows[target]=p
                        positives.append(dict(native2002_source_record_id=sid,native2010_source_record_id=tid,native2021_source_record_id=cid,
                            name=row.settlement_name,type=row.settlement_type,county_key=county,source_region_header='Еврейская АО',
                            imported_old_namespace_retained=row.region_norm,population2002=row.population,population2010=state.by_id.loc[tid,'population'],population2021=state.by_id.loc[cid,'population'],
                            existing2010_2021_component=twin!=[],current_own_point_origin_file=carrier.get('point_origin_file',''),current_own_point_origin_sha256=carrier.get('point_origin_sha256','')))
                        continue
        holds.append(dict(source_record_id=sid,name=row.settlement_name,type=row.settlement_type,county_raw=row.district_raw,
            old_name_rivals=len(all02),native2010_name_rivals=len(all10),current_name_rivals=len(all21),reason='native_name_type_county_or_component_or_ownpoint_rule_not_met'))
    state.obs['root']=state.obs.source_record_id.map(state.uf.find)
    after=finite(state);after_metrics=state.metrics();assert protected.equals(state.obs[protected.columns])
    new_finite_ids=finite_ids(state);union_rows=[];union_receipt={}
    ordinary=state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~(state.obs.census_year.eq(2021)&state.obs.region_norm.eq('крым'))]
    for axis,scope in scope_sets.items():
        beforeids=scope|previous_finite_ids;afterids=scope|new_finite_ids
        bv={str(int(y)):int(g[g.source_record_id.isin(beforeids)].population.sum()) for y,g in ordinary.groupby('census_year')}
        av={str(int(y)):int(g[g.source_record_id.isin(afterids)].population.sum()) for y,g in ordinary.groupby('census_year')}
        union_receipt[axis]={'before_native_population':bv,'after_native_population':av,'net_native_population':{y:av[y]-bv[y] for y in bv}}
        for row in ordinary[ordinary.source_record_id.isin(afterids-beforeids)].itertuples():
            union_rows.append(dict(axis=axis,source_record_id=row.source_record_id,census_year=int(row.census_year),native_population=row.population,native_population_quality=row.population_value_quality))
    pd.DataFrame(union_rows).to_csv(OUT/'exact_net_native_source_ID_union_gain.csv',index=False)
    for filename,rows,cols in [
        ('accepted_identity_edge_delta.csv',edges,['from_source_record_id','to_source_record_id','relation','decision_status','admission_rule','boundary_comparability_asserted']),
        ('accepted_point_use_delta.csv',points,None),('accepted_native_binding_witnesses.csv',positives,None),
        ('all_name_type_county_competitors.csv',rivals,None),('held_rows.csv',holds,None),('retained_existing_points.csv',retained,None)]:
        pd.DataFrame(rows,columns=cols).to_csv(OUT/filename,index=False)
    for row in points:
        if row.get('point_origin_file'):pin(row['point_origin_file'],row.get('point_origin_sha256'))
    outputs={p.name:sha(p) for p in OUT.glob('*.csv')}
    result=dict(status='accepted_actual50_source_specific_header_interpretation_and_bounded_native_application',baseline_stage=50,
        interpretation_rows=98,original_native_population=62556,canonical_other2002_population=128359,combined2002_EAO_population=190915,
        source_header='Еврейская АО',raw_source_populations_quality_metadata_unchanged=True,interpretation_effective_region_only=True,
        accepted_cases=len(positives),accepted_edges=len(edges),accepted_point_uses=len(points),held_rows=len(holds),
        before=before_metrics,after=after_metrics,before_finite_all3_all_points=before,after_finite_all3_all_points=after,
        net_finite_all3_all_points={'histories':after['histories']-before['histories'],'population_by_year':{y:after['populations_by_year'][y]-before['populations_by_year'][y] for y in before['populations_by_year']}},
        all_competitors_enumerated_before_component_filter=True,ordinary_population_source_values_unchanged=True,
        inferred_historical_point_measurement=False,municipal_point_projection=False,network_requests=0,input_pins=pins,output_pins=outputs,code_sha256=sha(Path(__file__)),
        native_source_ID_union_axes=union_receipt,source_manifest_context_original_path=str(manifest_path),source_manifest_context_read_sha256=sha(manifest_path))
    (OUT/'application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','interpretation_rows','accepted_cases','accepted_edges','accepted_point_uses','held_rows','net_finite_all3_all_points']},ensure_ascii=False))

if __name__=='__main__':main()
