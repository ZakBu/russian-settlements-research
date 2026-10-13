"""Stage old-census historical point candidates under the typed 8-to-11 code bridge.

This is a point-use proposal generator only. It reopens the pinned 2009 SQL COPY
rows and 2011 DBF records, preserves raw code blocks and does not assert identity,
point-date measurement, population comparability, or admission.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import pandas as pd
from verify_geokladr_snapshot import parse_dbf_header

W=Path('/workspace')
F=W/'settlements-delivery/continuation-consolidated-20261003'
C=W/'settlements-work/continuation_20261003'
H=W/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
SQL=W/'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
DBF=W/'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
EVENTS=W/'settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json'
BLOCKED=C/'blocked_point_reuse_targets_v1.json'


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def raw_sql_row(lines,n):
    if not n or int(n)<1: raise ValueError('bad classifier line locator')
    vals=lines[int(n)-1].rstrip('\r\n').split('\t')
    if len(vals)!=6: raise ValueError(f'bad SQL COPY row at line {n}: {len(vals)} fields')
    return dict(zip(['code','name_raw','name','status','name_full','is_settlement'],vals))

def raw_dbf_rows(path, targets):
    result={}
    with path.open('rb') as f:
        pre=f.read(32); hl=int.from_bytes(pre[8:10],'little'); f.seek(0); header=f.read(hl)
        n,hl,rl,fields=parse_dbf_header(header)
        byname={x['name']:x for x in fields}
        if (n,hl,rl)!=(151875,705,395): raise ValueError('raw DBF layout is not the pinned GeoKLADR snapshot')
        for r in targets.itertuples(index=False):
            no=int(r.record_number_1based); off=int(r.record_byte_offset_0based)
            if not (1<=no<=n and off==hl+(no-1)*rl): raise ValueError('DBF locator mismatch')
            f.seek(off); raw=f.read(rl)
            if len(raw)!=rl: raise ValueError('truncated DBF record')
            def field(name):
                spec=byname[name]; a=spec['offset']; b=a+spec['width']; return raw[a:b].decode('cp1251')
            parts=[field(x).strip() for x in ('TER','KOD1','KOD2','KOD3')]
            result[no]={'record_no':no,'offset':off,'deleted':raw[0:1].decode('ascii'),
                'code':''.join(parts),'ter':parts[0],'kod1':parts[1],'kod2':parts[2],'kod3':parts[3],
                'name_raw':field('NAME1').strip(),'type_raw':field('SCOKATO').strip(),
                'long_raw':field('LONG').strip(),'lat_raw':field('LAT').strip(),
                'updated_raw':field('DATA_UPD').strip()}
    return result

def main(out):
    if out.exists(): raise FileExistsError('choose a new immutable output directory')
    paths={'selected':F/'selected_observations.parquet','points':F/'accepted_point_uses.parquet',
           'graph':F/'accepted_identity_edges.parquet','source_evidence':F/'source_evidence.parquet',
           'manifest':F/'input_manifest.parquet','historical_candidate_context':H,
           'raw_classifier_sql':SQL,'raw_geokladr_dbf':DBF,'lineage_events':EVENTS,'hard_quarantine_ids':BLOCKED}
    pin={k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()}
    selected=pd.read_parquet(paths['selected'])
    nativeid=dict(zip(selected.source_record_id.astype(str),selected.source_native_id))
    points=pd.read_parquet(paths['points'])
    ev=pd.read_parquet(paths['source_evidence'],columns=['source_record_id','source_evidence_json'])
    evmap={str(r.source_record_id):json.loads(r.source_evidence_json) for r in ev.itertuples(index=False)}
    manifest=pd.read_parquet(paths['manifest'],columns=['path','sha256'])
    maphash=dict(zip(manifest.path.astype(str),manifest.sha256.astype(str)))
    allh=pd.read_parquet(H)
    accepted=set(points.target_source_record_id.astype(str))
    selected_missing=set(selected.loc[selected.latitude.isna() & selected.longitude.isna(), 'source_record_id'].astype(str))
    # Code-bridge cohort consists only of missing-point selected 2002/2010 records.
    c=allh[allh.census_year.isin([2002,2010]) & allh.historical_named_point_candidate.eq(True) &
           allh.code_join_basis.eq('typed_urban_8digit_plus_zero_third_geo_group') &
           ~allh.source_record_id.astype(str).isin(accepted) &
           allh.source_record_id.astype(str).isin(selected_missing)].copy()
    # One row per selected source record is required.
    if c.source_record_id.duplicated().any(): raise ValueError('duplicate selected target in candidate bridge pool')
    # Independently reopen literal SQL source lines and DBF records.
    with SQL.open('r',encoding='utf-8',newline='') as f: sql_lines=f.readlines()
    crows={int(n):raw_sql_row(sql_lines,n) for n in c.source_line_1based.dropna().unique()}
    dbrows=raw_dbf_rows(DBF,c.drop_duplicates('record_number_1based'))
    # Collision status is based on distinct raw historical point objects, not duplicate selected rows.
    # A collision is a same-year shared point among the audited missing-point
    # cohort, and must involve distinct literal raw 2011 OKATO objects.
    loc=allh[allh.source_record_id.astype(str).isin(selected_missing) &
             allh.historical_named_point_candidate.eq(True) & allh.historical_name_exact.eq(True) &
             allh.historical_type_exact.eq(True) & allh.is_additive_settlement_record.eq(True) &
             allh.latitude_from_lat.notna() & allh.longitude_from_long.notna()].copy()
    loc['_lat']=pd.to_numeric(loc.latitude_from_lat,errors='coerce'); loc['_lon']=pd.to_numeric(loc.longitude_from_long,errors='coerce')
    col=loc.groupby(['census_year','_lat','_lon']).historical_okato_2011_raw.nunique()
    collision=set(col[col.gt(1)].index)
    hard=set(json.loads(BLOCKED.read_text()).get('blocked_target_source_record_ids',[]))
    existing_quarantine=set()
    for name in ('mezhgorye_quarantine_decision.json','podlipkovsky_point_hold_decision_v1.json','rural_shared_point_quarantine_decision.json'):
        p=C/name
        if p.exists():
            obj=json.loads(p.read_text()); existing_quarantine.update(obj.get('quarantine_target_source_record_ids',[]))
    hard |= existing_quarantine
    # Verify exact local source assets against release manifest, once per distinct selected file.
    rawroot=W/'settlements-raw'; asset_hashes={};
    for sf in sorted(set(c.source_file.dropna().astype(str))):
        expected=maphash.get(sf); p=rawroot/sf
        actual=sha(p) if p.is_file() else None
        asset_hashes[sf]=(expected,actual,str(p),p.is_file())
    # Candidate frame has exact source-row data. Never infer source codes from classifier/GeoKLADR.
    rows=[]; staged=[]; modern_points=points[points.target_year.eq(2021)].set_index('target_source_record_id')
    prpath=C/'audit_99_20261003/older_years/current_candidate_priorities.csv'
    priority=pd.read_csv(prpath,low_memory=False)
    priority=priority.set_index('source_record_id')
    # Strongest separately measured residual route: exact accepted 2021 graph
    # carrier already exists, but retrospective point continuity still needs
    # event, point-origin, and temporal review. Keep this queue separate.
    carrier_rows=priority[pd.to_numeric(priority.accepted_2021_carrier_count,errors='coerce').eq(1)].copy()
    carrier_rows=carrier_rows[carrier_rows.census_year.isin([2002,2010])].copy()
    carrier_rows['modern_carrier_point_origin_file']=carrier_rows.accepted_2021_carrier_id.map(
        lambda x: str(points.loc[points.target_source_record_id.eq(x),'point_origin_file'].iloc[0])
        if (points.target_source_record_id.eq(x)).any() else '')
    carrier_rows['modern_carrier_point_origin_locator']=carrier_rows.accepted_2021_carrier_id.map(
        lambda x: str(points.loc[points.target_source_record_id.eq(x),'point_origin_locator'].iloc[0])
        if (points.target_source_record_id.eq(x)).any() else '')
    carrier_rows['route_decision']='retrospective modern-point continuity candidate; event/point-origin review required; no admission'
    for r in c.itertuples(index=False):
        rid=str(r.source_record_id); e=evmap.get(rid,{})
        sr=crows[int(r.source_line_1based)]; dr=dbrows[int(r.record_number_1based)]
        reasons=[]
        if not (len(str(r.historical_okato_2009_raw))==8 and str(r.historical_okato_2009_raw).isdigit()): reasons.append('2009_raw_city_code_not_exact_8_digits')
        if str(r.historical_okato_2011_raw)!=str(r.historical_okato_2009_raw)+'000': reasons.append('historical_code_bridge_not_exact_8_plus_000')
        if sr['code']!=str(r.historical_okato_2009_raw) or sr['is_settlement']!='t': reasons.append('raw_sql_row_does_not_verify_literal_2009_code_and_settlement_flag')
        if sr['status'] not in ('город','поселок городского типа'): reasons.append('raw_sql_type_outside_typed_urban_bridge')
        if dr['deleted']!=' ' or dr['code']!=str(r.historical_okato_2011_raw) or dr['kod3']!='000': reasons.append('raw_dbf_record_does_not_verify_11_digit_code_or_literal_kod3_000')
        if dr['type_raw'] not in ('г','пгт'): reasons.append('raw_dbf_type_outside_typed_urban_bridge')
        if not bool(r.historical_name_exact) or not bool(r.historical_type_exact): reasons.append('historical_name_or_type_not_exact')
        if str(r.name_raw_2009)!=sr['name_raw'] or str(r.name_raw_2011)!=dr['name_raw'] or str(r.settlement_type_raw)!=dr['type_raw']: reasons.append('parsed_candidate_fields_do_not_match_raw_sql_dbf')
        if int(r.source_region_name_type_count)!=1: reasons.append('selected_source_region_name_type_not_unique')
        if int(r.historical_key_region_name_type_count)!=1: reasons.append('historical_point_region_name_type_not_unique')
        if str(r.historical_point_modern_region)!=str(r.region_norm): reasons.append('historical_point_modern_region_disagrees_with_selected_region')
        if not bool(r.is_additive_settlement_record): reasons.append('source_row_not_additive_settlement_record')
        grain=str(r.entity_grain_status or '').lower()
        if any(x in grain for x in ('aggregate','federal_city','parent','derived_sum')): reasons.append('source_grain_explicit_aggregate_or_parent')
        if e.get('legacy_identity_conflict') or e.get('legacy_same_year_collision') or e.get('is_federal_aggregate') or not e.get('is_additive_settlement_record',False): reasons.append('source_evidence_hard_identity_collision_or_aggregate_hold')
        if rid in hard: reasons.append('prior_target_specific_hard_quarantine')
        key=(int(r.census_year),float(r.latitude_from_lat),float(r.longitude_from_long))
        shared=key in collision
        if shared: reasons.append('same_year_exact_point_shared_by_distinct_raw_historical_objects')
        if pd.isna(r.latitude_from_lat) or pd.isna(r.longitude_from_long) or not (-90<=float(r.latitude_from_lat)<=90 and -180<=float(r.longitude_from_long)<=180): reasons.append('historical_point_invalid')
        sf=str(r.source_file); expected,actual,asset_path,exists=asset_hashes.get(sf,(None,None,str(rawroot/sf),False))
        manifest_ok=bool(expected and exists and actual==expected)
        if not manifest_ok: reasons.append('selected_source_asset_not_locally_verified_against_frozen_manifest')
        loc=f'selected_source_file={sf};sheet={r.source_sheet};row={r.source_row};source_native_id={nativeid.get(rid, '')}'
        if pd.isna(r.source_sheet) or pd.isna(r.source_row): reasons.append('selected_source_sheet_or_row_locator_missing')
        # Native OKTMO is absent for nearly all frozen older residual rows; this remains explicit.
        native_code='' if pd.isna(r.oktmo) else str(r.oktmo)
        # Identity-graph carrier is context only; it never substitutes for the historic point rule.
        pinfo=priority.loc[rid].to_dict() if rid in priority.index else {}
        carrier=str(pinfo.get('accepted_2021_carrier_id') or '') if pd.notna(pinfo.get('accepted_2021_carrier_id')) else ''
        dist=None
        if carrier and carrier in modern_points.index:
            cr=modern_points.loc[carrier]
            if pd.notna(cr.latitude) and pd.notna(cr.longitude):
                lat1,lon1,lat2,lon2=map(math.radians,[float(r.latitude_from_lat),float(r.longitude_from_long),float(cr.latitude),float(cr.longitude)])
                a=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
                dist=6371*2*math.asin(math.sqrt(a))
        item={'target_source_record_id':rid,'target_year':int(r.census_year),'population':int(r.population) if pd.notna(r.population) else None,
            'settlement_name':r.settlement_name,'settlement_type':r.settlement_type,'region_norm':r.region_norm,
            'selected_source_file':sf,'selected_source_file_sha256_manifest':expected,'selected_source_file_sha256_local':actual,
            'selected_source_asset_verified':manifest_ok,'selected_source_locator':loc,'source_sheet':r.source_sheet,'source_row':r.source_row,
            'source_native_id':nativeid.get(rid),'native_oktmo_raw':r.oktmo,'native_okato_raw':r.okato,
            'classifier_sql_file':str(SQL),'classifier_sql_sha256':pin['raw_classifier_sql']['sha256'],
            'classifier_sql_line_1based':int(r.source_line_1based),'classifier_okato2009_raw':str(sr['code']),
            'classifier_raw_name':sr['name_raw'],'classifier_raw_status':sr['status'],'classifier_raw_settlement_flag':sr['is_settlement'],
            'geokladr_dbf_file':str(DBF),'geokladr_dbf_sha256':pin['raw_geokladr_dbf']['sha256'],
            'geokladr_record_1based':int(dr['record_no']),'geokladr_byte_offset_0based':int(dr['offset']),
            'geokladr_okato2011_raw':dr['code'],'geokladr_kod3_raw':dr['kod3'],'geokladr_name_raw':dr['name_raw'],
            'geokladr_type_raw':dr['type_raw'],'geokladr_long_raw':dr['long_raw'],'geokladr_lat_raw':dr['lat_raw'],
            'geokladr_update_date_raw':dr['updated_raw'],'latitude':float(r.latitude_from_lat),'longitude':float(r.longitude_from_long),
            'code_bridge_basis':'typed urban 2009 raw 8-digit OKATO + exact DBF KOD3=000 => 2011 raw 11-digit GeoKLADR point association; no census identifier rewrite',
            'same_year_distinct_object_point_collision':shared,'modern_point_continuity_candidate_source_record_id':carrier or None,
            'modern_point_distance_km_diagnostic_only':dist,'modern_spatial_continuity_admitted':False,
            'population_boundary_comparability_admitted':False,'point_measurement_date_interpreted_as_census_date':False,
            'point_date_interpretation':'GeoKLADR DATA_UPD raw date is a 2011 source update, not a census-date coordinate measurement',
            'exact_native_oktmo_event_check_available':bool(native_code),'event_scope_note':'No new identity or event inference; exact event lookup not possible where native census OKTMO is blank; target-specific quarantines and source-evidence hard holds preserved.',
            'decision_status':'staged_candidate_pending_independent_review' if not reasons else 'held_candidate',
            'hold_reasons_json':json.dumps(reasons,ensure_ascii=False)}
        rows.append(item)
        if not reasons:
            staged.append({'target_source_record_id':rid,'target_year':int(r.census_year),'latitude':float(r.latitude_from_lat),'longitude':float(r.longitude_from_long),
                'coordinate_quality':'2011_named_typed_historical_point_candidate_pending_review','coordinate_source':'Raw named typed GeoKLADR 2011 point under explicit typed-city/PGT OKATO code-width bridge; retrospective point-use assumption only',
                'coordinate_source_record_id':'GEOKLADR2011:'+str(dr['code']),'coordinate_provider':'GeoKLADR 2011 raw DBF','coordinate_provider_id':'',
                'source_name':dr['name_raw'],'source_type':dr['type_raw'],'source_region':str(r.region_norm),'source_file':str(DBF),'source_row':int(dr['record_no']),
                'source_sha256':pin['raw_geokladr_dbf']['sha256'],'source_locator':f'DBF_record_1based={dr["record_no"]};DBF_byte_offset_0based={dr["offset"]};OKATO2011_raw={dr["code"]};KOD3_raw={dr["kod3"]}',
                'coordinate_provenance':'2011 named typed GeoKLADR representative point; explicit retrospective use assumption; no exact census-date point or boundary equivalence claimed',
                'admission_rule':'old_census_typed_urban_8digit_2009_to_11digit_geokladr_2011_code_bridge_candidate_v1',
                'coordinate_admission_status':'staged_candidate_pending_independent_review','coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,
                'point_origin_file':str(DBF),'point_origin_sha256':pin['raw_geokladr_dbf']['sha256'],'point_origin_locator':f'DBF_record_1based={dr["record_no"]};DBF_byte_offset_0based={dr["offset"]};OKATO2011_raw={dr["code"]}',
                'point_origin_kind':'raw_named_typed_geo2011_object','historical_classifier2009_file':str(SQL),'historical_classifier2009_sha256':pin['raw_classifier_sql']['sha256'],
                'historical_classifier2009_locator':f'line_1based={int(r.source_line_1based)};OKATO2009_raw={sr["code"]}',
                'source_record_lineage_json':json.dumps({'source_record_id':rid,'source_file':sf,'source_manifest_sha256':expected,'sheet':str(r.source_sheet),'row':r.source_row,'source_native_id':nativeid.get(rid)},ensure_ascii=False),
                'inference_modern_point_use_target_source_record_id':carrier or None,'corroborating_modern_point_distance_km':dist,
                'modern_point_spatial_continuity_admitted':False,'population_scope_comparability_asserted':False,'admission_allowed':False})
    ledger=pd.DataFrame(rows); stage=pd.DataFrame(staged)
    out.mkdir(parents=True)
    ledger.to_parquet(out/'historical_bridge_gate_ledger.parquet',index=False)
    stage.to_parquet(out/'staged_point_uses.parquet',index=False)
    carrier_rows.reset_index()[['source_record_id','census_year','settlement_name','settlement_type','region_raw','population',
        'accepted_2021_carrier_id','historical_named_point_candidate','legacy_point_available','modern_carrier_point_origin_file',
        'modern_carrier_point_origin_locator','route_decision']].sort_values('population',ascending=False).to_csv(out/'other_route_carrier_context.csv',index=False)
    ledger.sort_values(['population','target_source_record_id'],ascending=[False,True]).head(100).to_csv(out/'fixed_top100_sample.csv',index=False)
    # A reproducible, mass-oriented sample frame with hold reason visible.
    ledger.sort_values(['target_year','population','target_source_record_id'],ascending=[True,False,True]).groupby('target_year',group_keys=False).head(50).to_csv(out/'year_top50_sample.csv',index=False)
    reason_counts={}
    for s in ledger.hold_reasons_json:
        for x in json.loads(s): reason_counts[x]=reason_counts.get(x,0)+1
    summary={'status':'candidate_stage_only_no_admissions','rule':'Raw SQL/DBF typed urban 8-digit 2009 classifier code bridged to matching 11-digit 2011 DBF code only when literal DBF KOD3=000; source name/type/region keys unique; selected source and point evidence pinned.',
       'inputs':pin,'builder_sha256':sha(Path(__file__)),'bridge_candidates':len(ledger),'bridge_candidate_population':int(ledger.population.fillna(0).sum()),
       'staged_pending_review':len(stage),'staged_population_pending_review':int(stage.target_source_record_id.map(ledger.set_index('target_source_record_id').population).sum()) if len(stage) else 0,
       'held':int(ledger.decision_status.eq('held_candidate').sum()),'hold_reason_marginals_overlap':reason_counts,
       'by_year':ledger.groupby('target_year').agg(rows=('target_source_record_id','size'),population=('population','sum'),staged=('decision_status',lambda x:int(x.eq('staged_candidate_pending_independent_review').sum()))).reset_index().to_dict('records'),
       'collision_bridge_rows':int(ledger.same_year_distinct_object_point_collision.sum()),
       'modern_carrier_context_rows':int(ledger.modern_point_continuity_candidate_source_record_id.notna().sum()),
       'other_route_unique_modern_carriers':len(carrier_rows),'other_route_carrier_population_context':int(carrier_rows.population.fillna(0).sum()),
       'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()},
       'interpretation':['The bridge aligns documented raw code grains for point association; it does not rewrite native census OKATO/OKTMO and does not imply legal identifier equivalence.','All points are GeoKLADR 2011 source points and are not census-date measurements.','Modern accepted-point distances and carriers are diagnostic context only; no identity edge, temporal continuity, or boundary/population comparability is admitted.','Same-year shared exact points remain held pending evidence about source coordinate precision/object granularity; shared groups are not blanket-rejected or treated as place identity.','No native OKTMO event binding is inferred where source OKTMO is absent; hard quarantines and source-evidence conflict/aggregate holds remain blocking.']}
    (out/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('inputs','outputs','interpretation','hold_reason_marginals_overlap')},ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=W/'settlements-work/continuation_20261004/historical_points');main(ap.parse_args().output)
