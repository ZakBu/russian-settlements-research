#!/usr/bin/env python3
"""Explain current old-year exact historical-point candidate holds from v2 checks."""
from pathlib import Path
import hashlib,json
import pandas as pd
OUT=Path('/workspace/settlements-work/continuation_20261003/audit_99_20261003/older_years')
PR=OUT/'current_candidate_priorities.csv'
CHECK=Path('/workspace/settlements-work/coordinates/extension_application_v2/coordinate_extension_application_checks.parquet')

def main():
    q=pd.read_csv(PR,low_memory=False)
    mask=q.historical_named_point_candidate.astype(str).str.lower().eq('true')
    ids=set(q.loc[mask,'source_record_id'].astype(str))
    d=pd.read_parquet(CHECK)
    d=d[d.target_source_record_id.astype(str).isin(ids)&d.candidate_family.eq('F_generic_2002_2010_geokladr2011_point')].copy()
    rows=[]
    for z in d.itertuples(index=False):
        s=json.loads(z.candidate_source_row_json or '{}');e=json.loads(z.evidence_checks_json or '{}');reasons=json.loads(z.held_reasons_json or '[]')
        rows.append({'target_source_record_id':str(z.target_source_record_id),'year':int(z.target_year),'name':s.get('settlement_name'),'type':s.get('settlement_type'),'region':s.get('region_norm'),'population':s.get('population'),'reason':'|'.join(reasons) if reasons else 'pending_root_review','code_join_basis':s.get('code_join_basis'),'historical_okato_2009_raw':s.get('historical_okato_2009_raw'),'historical_okato_2011_raw':s.get('historical_okato_2011_raw'),'oktmo_2011_raw':s.get('oktmo_2011_raw'),'kod3_raw_text':s.get('kod3_raw_text'),'geokladr_point_lat':s.get('latitude_from_lat'),'geokladr_point_lon':s.get('longitude_from_long'),'point_date':s.get('source_updated_at'),'source_file':e.get('selected_source_exact_file'),'source_file_present':e.get('selected_source_file_resolved_locally'),'selected_source_hash_present':e.get('source_sha256_present'),'selected_source_locator_present':e.get('source_locator_present'),'selected_source_hash_matches':e.get('selected_source_file_hash_matches'),'raw_source_reopened_and_rehashed':e.get('raw_source_reopened_and_rehashed'),'exact_event_ids':json.dumps(e.get('exact_event_ids') or [],ensure_ascii=False),'within_year_shared_point':e.get('duplicate_point_group')})
    out=pd.DataFrame(rows)
    # Reconstruct the exact coordinate collision key used by the existing
    # generic historical-point gate, across the complete v4 candidate pool.
    hist=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet')
    allh=pd.read_parquet(hist)
    loc=allh[allh.historical_named_point_candidate.fillna(False)].copy()
    loc['_lat']=pd.to_numeric(loc.latitude_from_lat,errors='coerce');loc['_lon']=pd.to_numeric(loc.longitude_from_long,errors='coerce')
    coll=loc.groupby(['census_year','_lat','_lon']).agg(v4_candidate_rows=('source_record_id','size'),distinct_raw_okato11=('historical_okato_2011_raw','nunique'),candidate_names=('settlement_name',lambda x:';'.join(sorted(set(map(str,x))))),candidate_raw_okato11=('historical_okato_2011_raw',lambda x:';'.join(sorted(set(map(str,x)))))).reset_index()
    out=out.merge(loc[['source_record_id','latitude_from_lat','longitude_from_long','historical_okato_2011_raw']],left_on='target_source_record_id',right_on='source_record_id',how='left')
    out=out.merge(coll,left_on=['year','latitude_from_lat','longitude_from_long'],right_on=['census_year','_lat','_lon'],how='left')
    shared=out[out.reason.str.contains('within_year_shared_geokladr_point_group',na=False)]
    shared.groupby(['year','distinct_raw_okato11'],dropna=False).agg(residual_rows=('target_source_record_id','size'),recorded_population=('population','sum'),distinct_exact_point_groups=('latitude_from_lat',lambda x:len(set(zip(x,shared.loc[x.index,'longitude_from_long']))))).reset_index().to_csv(OUT/'shared_point_collision_profile.csv',index=False)
    # Compare the 2011 candidate with the already accepted unique 2021 carrier.
    carriers=q[q.historical_named_point_candidate.astype(str).str.lower().eq('true')&pd.to_numeric(q.accepted_2021_carrier_count,errors='coerce').eq(1)].copy()
    if not carriers.empty:
        pts=pd.read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/accepted_point_uses.parquet')
        sr=pd.read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',columns=['source_record_id','settlement_name','settlement_type','region_raw'])
        hp=allh[['source_record_id','latitude_from_lat','longitude_from_long','source_updated_at']]
        carriers=carriers.merge(hp,on='source_record_id',how='left').merge(pts[['target_source_record_id','latitude','longitude','admission_rule','point_origin_kind']],left_on='accepted_2021_carrier_id',right_on='target_source_record_id',how='left').merge(sr.rename(columns={'source_record_id':'accepted_2021_carrier_id','settlement_name':'carrier_name','settlement_type':'carrier_type','region_raw':'carrier_region'}),on='accepted_2021_carrier_id',how='left')
        from math import radians,sin,cos,asin,sqrt
        def km(z):
            if pd.isna(z.latitude) or pd.isna(z.longitude) or pd.isna(z.latitude_from_lat) or pd.isna(z.longitude_from_long):return None
            a,b=radians(float(z.latitude_from_lat)),radians(float(z.longitude_from_long));c,d=radians(float(z.latitude)),radians(float(z.longitude));v=sin((c-a)/2)**2+cos(a)*cos(c)*sin((d-b)/2)**2
            return 6371*2*asin(sqrt(v))
        carriers['distance_km']=carriers.apply(km,axis=1)
        carriers[['source_record_id','census_year','settlement_name','settlement_type','region_raw','population','accepted_2021_carrier_id','carrier_name','carrier_type','carrier_region','distance_km','admission_rule','point_origin_kind','source_updated_at']].to_csv(OUT/'unique_carrier_concordance.csv',index=False)
    # Current rule failure buckets are disjoint by full JSON hold combination.
    out.groupby(['year','reason','code_join_basis'],dropna=False).agg(rows=('target_source_record_id','size'),recorded_population=('population','sum')).reset_index().sort_values(['year','rows'],ascending=[True,False]).to_csv(OUT/'historical_candidate_rule_failure_partition.csv',index=False)
    out.sort_values('population',ascending=False).head(20).to_csv(OUT/'historical_candidate_top20.csv',index=False)
    # Gate reason marginals overlap; disclose as such.
    reason_counts={}
    for val in out.reason:
        for reason in ([] if val=='pending_root_review' else val.split('|')): reason_counts[reason]=reason_counts.get(reason,0)+1
    delivery=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
    manifest=pd.read_parquet(delivery/'input_manifest.parquet')
    selected=pd.read_parquet(delivery/'selected_observations.parquet')
    selected=selected[selected.source_record_id.astype(str).isin(ids)].copy()
    manifest_map=dict(zip(manifest.path.astype(str),manifest.sha256.astype(str)))
    selected['input_manifest_sha256']=selected.source_file.astype(str).map(manifest_map)
    asset_rows=[]
    raw_root=Path('/workspace/settlements-raw')
    for path in sorted(set(selected.loc[selected.input_manifest_sha256.notna(),'source_file'].astype(str))):
        expected_sha=manifest_map[path];asset=raw_root/path
        actual_sha=None
        if asset.is_file():
            hsh=hashlib.sha256()
            with asset.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):hsh.update(block)
            actual_sha=hsh.hexdigest()
        asset_rows.append({'path':path,'input_manifest_sha256':expected_sha,'local_asset_exists':asset.is_file(),'local_sha256':actual_sha,'local_sha256_matches_manifest':actual_sha==expected_sha})
    assets=pd.DataFrame(asset_rows)
    assets.to_csv(OUT/'selected_source_manifest_assets.csv',index=False)
    selected['source_provenance_route']=selected.apply(lambda z:'exact_input_manifest_path_and_file_hash' if pd.notna(z.input_manifest_sha256) else ('selected_row_has_sha256_and_locator' if pd.notna(z.source_sha256) and pd.notna(z.source_locator) else 'source_provenance_needs_resolution'),axis=1)
    selected[['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_sha256','source_locator','input_manifest_sha256','source_provenance_route']].to_csv(OUT/'selected_source_lineage_reconciliation.csv',index=False)
    source_lineage={'selected_row_lineage_routes':selected.source_provenance_route.value_counts().to_dict(),'manifest_paths_resolved':int(selected.input_manifest_sha256.notna().sum()),'manifest_hash_equals_selected_row_hash_when_both_present':int((selected.input_manifest_sha256.notna()&selected.source_sha256.notna()&selected.input_manifest_sha256.eq(selected.source_sha256)).sum()),'unique_manifest_assets_checked':int(len(assets)),'unique_manifest_assets_locally_present':int(assets.local_asset_exists.sum()),'unique_manifest_assets_local_hash_matches':int(assets.local_sha256_matches_manifest.sum()),'row_id_and_locator_note':'The release source_record_id retains source file plus sheet/row or PDF page/row; input_manifest pins the source file bytes. Nulls in selected source_sha256/source_locator do not mean the source asset is unpinned when an exact input_manifest path join exists.'}
    summary={'status':'read_only_current_residual_gate_diagnostic','current_physical_exact_historical_point_candidates':len(out),'by_year':{},'gate_reason_marginals_overlapping':reason_counts,'code_join_basis':out.groupby(['year','code_join_basis'],dropna=False).agg(rows=('target_source_record_id','size'),population=('population','sum')).reset_index().to_dict('records'),'shared_coordinate_candidates':{'rows':int(len(shared)),'distinct_exact_point_groups':int(shared.groupby(['year','latitude_from_lat','longitude_from_long']).ngroups),'all_grouped_objects_have_distinct_historical_raw_okato':bool((shared.distinct_raw_okato11>1).all())},'selected_row_source_lineage':source_lineage,'source_provenance':{'selected_source_hash_missing_in_extension_check_rows':int((~out.selected_source_hash_present.fillna(False)).sum()),'selected_source_locator_missing_in_extension_check_rows':int((~out.selected_source_locator_present.fillna(False)).sum()),'local_source_file_resolved_rows':int(out.source_file_present.fillna(False).sum()),'local_source_hash_matches_rows':int(out.selected_source_hash_matches.fillna(False).sum()),'raw_source_reopened_and_rehashed_rows':int(out.raw_source_reopened_and_rehashed.fillna(False).sum()),'exact_current_event_ids_rows':int(out.exact_event_ids.map(lambda x:x!='[]').sum()),'dated_point_source_values':out.point_date.value_counts(dropna=False).to_dict()},'interpretation':['Historical raw OKATO code joins are classifier/GeoKLADR code witnesses, not native census-source official identifiers. Census-source OKATO/OKTMO values remain literal and are not widened or repaired by this diagnostic.','The verified typed-city schema bridge is 2009 raw 8-digit code to the 2011 raw 11-digit GeoKLADR code only when the raw KOD3 block is literally 000. Treat it as a scoped point-candidate association, never a legal-code identity or a leading-zero repair.','Generic 2002/2010 points are GeoKLADR records updated 2011-06-20, not census-date measurements. No exact event IDs were attached to these generic candidates; separate modern-point reuse candidate holds have event-specific restrictions.','The historical name/type/region candidate is not proof of same-place continuity, coordinate identity, population scope, or polygon comparability. Shared points are exact-coordinate collisions across distinct raw historical objects and remain blocked pending scoped resolution.']}
    for y,g in out.groupby('year'):
        summary['by_year'][str(y)]={'rows':len(g),'population':int(g.population.sum()),'pending_root_review':int(g.reason.eq('pending_root_review').sum()),'held':int(g.reason.ne('pending_root_review').sum()),'population_pending_root_review':int(g.loc[g.reason.eq('pending_root_review'),'population'].sum())}
    (OUT/'historical_candidate_gate_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
