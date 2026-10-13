"""Admit real missing-year observations in explicitly nonadditive physical series."""
import json
from pathlib import Path
import pandas as pd
import xlrd
from current_chain_state_20261007 import sha, normalize, distance_km
from working_state_20261007 import load,E
from apply_unique_county_name_bridge_20261007 import county_key

RAW_REVIEW=E/'large_residual_temporal_batch_20261007/raw_untyped_2010_reserve'
WIKI_REVIEW=E/'top_large_missing_year_sources_20261007'
POINT_REVIEW=E/'partial_full3_point_completion_20261007'
OUT=E/'auxiliary_observed_years_application_20261007'

def main():
    state=load(stage=10)
    before=state.metrics()
    hashes={str(p):sha(p) for p in state.inputs}
    def pin(path):
        path=Path(path)
        if str(path) not in hashes:hashes[str(path)]=sha(path)
        return hashes[str(path)]
    # The point is an existing full3 physical identity, supported by printed region.
    point_path=POINT_REVIEW/'candidate_point_use_delta.csv'
    pin(point_path)
    points=pd.read_csv(point_path,keep_default_na=False)
    for p in points.to_dict('records'):
        sid,donor=p['target_source_record_id'],p['coordinate_source_record_id']
        if sid in state.point_rows or state.uf.find(sid)!=state.uf.find(donor) or state.years[state.uf.find(sid)]!={2002,2010,2021}:raise ValueError('Point identity changed')
        if pin(p['coordinate_origin_ledger'])!=p['coordinate_origin_ledger_sha256']:raise ValueError('Point donor changed')
        a=state.point_rows[donor]
        if distance_km((float(p['latitude']),float(p['longitude'])),(a['latitude'],a['longitude']))>0.00001:raise ValueError('Point differs')
    regionproof=POINT_REVIEW/'physical_region_context_resolution.csv'
    pin(regionproof)
    points['coordinate_admission_status']='reviewed_extension_rule_accepted'
    OUT.mkdir(parents=True,exist_ok=True)
    points.to_csv(OUT/'accepted_point_use_delta.csv',index=False)
    state.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv'])
    records=[]
    held=[]
    def add(series,year,pop,sid,name,region,county,point,quality,grain,nonadditive,path,locator,rule):
        records.append({'scope':'auxiliary_observed_years_20261007','trajectory_id':series,'year':int(year),'population_source_value':int(pop),'source_record_id':sid,'settlement_name':name,'region_norm':region,'county_context':county,'latitude':point[0],'longitude':point[1],'population_quality':quality,'grain':grain,'nonadditive_observation':nonadditive,'decision_status':'case_specific_independent_review_accepted','accepted_physical_three_observed_census_year_path':True,'accepted_scoped_representative_point':True,'ordinary_NP3_asserted':False,'native_provider_binding_asserted':False,'boundary_comparability_asserted':False,'source_path':str(path),'source_sha256':pin(path),'source_locator':locator,'admission_rule':rule})
    def native(series,sid,point,rule):
        row=state.by_id.loc[sid]
        if pd.isna(row.population):raise ValueError('Unknown population cannot be a complete observed series')
        source=Path('/workspace/settlements-raw')/row.source_file
        add(series,row.census_year,row.population,sid,row.settlement_name,row.region_norm,row.district_raw,point,row.population_value_quality,'existing selected settlement row',False,source,str(row.source_locator or sid),rule)
    books={}
    for filename in ['eligible_auxiliary_observation_candidates.csv','boundary_context_auxiliary_candidates.csv']:
        path=RAW_REVIEW/filename;pin(path)
        for r in pd.read_csv(path,keep_default_na=False).to_dict('records'):
            old,cur=r['old_id'],r['current_id']
            if cur not in state.point_rows:
                held.append({'old_id':old,'current_id':cur,'raw_source_record_id':r['raw_source_record_id'],'reason':'no_accepted_current_representative_point','population_2002':r['population_2002'],'population_2010':r['population_2010_as_printed'],'population_2021':r['population_2021']})
                continue
            if state.uf.find(old)!=state.uf.find(cur) or state.years[state.uf.find(cur)]!={2002,2021}:raise ValueError('Auxiliary series is not a missing2010 pair')
            if r['selected_same_physical_row_id'] or json.loads(r['all_selected_2010_exact_name_region_alias_ids']):raise ValueError('Selected2010 alias requires migration')
            source=Path(r['raw_file'])
            if pin(source)!=r['source_sha256']:raise ValueError('Raw workbook changed')
            if source not in books:books[source]=xlrd.open_workbook(str(source),on_demand=True)
            sheet=books[source].sheet_by_name(r['raw_sheet'])
            name=sheet.cell_value(int(r['row_1based'])-1,int(r['name_column_1based'])-1)
            pop=sheet.cell_value(int(r['row_1based'])-1,int(r['population_column_1based'])-1)
            if normalize(name)!=normalize(r['raw_name']) or not isinstance(pop,(float,int)) or float(pop)!=float(r['population_2010_as_printed']):raise ValueError('Actual source cell differs')
            boundary=filename.startswith('boundary')
            anchors=json.loads(r['following_anchor_evidence_json'])[:2] if boundary else [json.loads(r['lower_anchor']),json.loads(r['upper_anchor'])]
            if len(anchors)!=2 or len({normalize(a['name']) for a in anchors})!=2:raise ValueError('Need distinct source context')
            for anchor in anchors:
                aa,cc=anchor['id'],anchor['current_id']
                if state.uf.find(aa)!=state.uf.find(cc) or county_key(state.by_id.loc[cc].district_raw)!=r['county']:raise ValueError('Source county anchor changed')
                if not 0<abs(int(anchor['n'])-int(r['row_1based']))<=20:raise ValueError('Source context too far')
            if boundary:
                oldsource=Path('/workspace/settlements-raw')/state.by_id.loc[old].source_file;pin(oldsource)
                oldsheet=xlrd.open_workbook(str(oldsource)).sheet_by_name('Sheet1')
                if 'малгобекск' not in normalize(' '.join(map(str,oldsheet.row_values(20)))):raise ValueError('Printed historical county not found')
                if any(int(a['n'])<=int(r['row_1based']) for a in anchors):raise ValueError('Boundary case needs two following anchors')
            donor=state.point_rows[cur];point=(donor['latitude'],donor['longitude'])
            if distance_km(point,(float(r['current_accepted_point_latitude']),float(r['current_accepted_point_longitude'])))>0.00001:raise ValueError('Current representative changed')
            pin(donor['point_ledger_path'])
            series='raw2010:'+r['raw_source_record_id']
            rule='printed_historical_county_and_two_following_accepted_source_anchors_boundary_case' if boundary else 'two_sided_accepted_source_county_context_for_untyped_auxiliary_locality'
            native(series,old,point,rule)
            add(series,2010,pop,r['raw_source_record_id'],r['name'],r['region'],r['county'],point,'protected_secondary_source_value','auxiliary untyped named locality row; type inferred from dated endpoints',True,source,f"{r['raw_sheet']}!row={r['row_1based']}; name_col={r['name_column_1based']}; population_col={r['population_column_1based']}",rule)
            native(series,cur,point,rule)
    path=WIKI_REVIEW/'missing_year_observation_candidates.csv';pin(path)
    wiki=pd.read_csv(path,keep_default_na=False)
    wiki=wiki[wiki.wikidata_qid.eq('Q1009953') & wiki.observation_year.eq(2002)]
    if len(wiki)!=1:raise ValueError('Vlasikha ownyear statement not unique')
    r=wiki.iloc[0].to_dict()
    if pin(r['source_path'])!=r['source_sha256'] or pin(r['additional_dated_secondary_source_path'])!=r['additional_dated_secondary_source_sha256']:raise ValueError('Secondary source changed')
    ids=json.loads(r['existing_component_source_ids'])
    if len(ids)!=2 or len({state.uf.find(sid) for sid in ids})!=1 or state.years[state.uf.find(ids[0])]!= {2010,2021}:raise ValueError('Vlasikha native series differs')
    point=(float(r['representative_latitude']),float(r['representative_longitude']))
    if pin(r['point_origin_file'])!=r['point_origin_sha256']:raise ValueError('Vlasikha representative source changed')
    for sid in ids:
        p=state.point_rows[sid]
        if distance_km(point,(p['latitude'],p['longitude']))>5:raise ValueError('Vlasikha points disagree')
    rule='dated_secondary_own_entity_2002_statement_supported_by_2012_publication'
    add('Q1009953',2002,r['population_as_printed'],'WD:'+r['statement_id'],'Власиха','московская','historical military town before ZATO formation',point,'dated_secondary_census_value_original_publication_unverified','auxiliary military-town physical scope; no selected2002 additive credit',True,r['source_path'],r['source_locator'],rule)
    for sid in ids:native('Q1009953',sid,point,rule)
    frame=pd.DataFrame(records)
    if len(frame)!=3*frame.trajectory_id.nunique() or frame[['trajectory_id','year']].duplicated().any():raise ValueError('Incomplete auxiliary rows')
    for _,group in frame.groupby('trajectory_id'):
        if set(group.year)!={2002,2010,2021}:raise ValueError('Not three actual observed years')
    frame.to_csv(OUT/'accepted_qualified_physical_observations.csv',index=False)
    pd.DataFrame(held).to_csv(OUT/'held_missing_coordinate_series.csv',index=False)
    after=state.metrics()
    result={'status':'applied_actual_auxiliary_observations_with_nonadditive_missing_years','stage_before':10,'new_identity_edges':0,'new_point_uses':len(points),'physical_three_observed_year_series':int(frame.trajectory_id.nunique()),'actual_observations':len(frame),'auxiliary_nonadditive_observations':int(frame.nonadditive_observation.sum()),'protected_auxiliary2010_observations':int(((frame.year==2010)&frame.nonadditive_observation).sum()),'dated_secondary_auxiliary2002_observations':1,'held_series_without_accepted_point':len(held),'selected_population_values_modified':False,'selected_denominators_modified':False,'official_population_controls_modified':False,'boundary_comparability_asserted':False,'ordinary_NP3_for_auxiliary_series_asserted':False,'ordinary_before':before,'ordinary_after':after,'inputs':hashes,'selected_source_id_references_potential_not_summed_with_previous_credits':{str(y):int(g.loc[~g.nonadditive_observation,'population_source_value'].sum()) for y,g in frame.groupby('year')},'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['physical_three_observed_year_series','actual_observations','new_point_uses','selected_source_id_references_potential_not_summed_with_previous_credits','ordinary_after']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
