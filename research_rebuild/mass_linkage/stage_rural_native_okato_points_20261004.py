"""Stage rural historical direct-point candidates from exact 11-digit OKATO rows.

This generator only proposes point uses for selected old census records. It
reopens raw classifier SQL and live GeoKLADR DBF bytes, independently checks the
published source row where locally parseable, and never creates temporal
identity edges or admits coordinates. The code is an 11-digit raw 2009/2011
object key; source_native_id remains an opaque published row identifier.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import xlrd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from verify_geokladr_snapshot import parse_dbf_header

W=Path('/workspace')
F=W/'settlements-delivery/continuation-consolidated-20261003'
C=W/'settlements-work/continuation_20261004'
H=W/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
SQL=W/'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
DBF=W/'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
BLOCKED=W/'settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json'
QUARANTINES=[W/'settlements-work/continuation_20261003'/n for n in (
 'mezhgorye_quarantine_decision.json','podlipkovsky_point_hold_decision_v1.json','rural_shared_point_quarantine_decision.json')]
OLD_REVIEW=C/'independent_review'
APPROVED_POINT_IDS=[OLD_REVIEW/'historical_point_recovery_eligible_123.csv',OLD_REVIEW/'historical_name_key_extension_eligible_10.csv']
PHYSICAL_STATUSES={'деревня','село','поселок','посёлок','станица','хутор','аул','кишлак','слобода'}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()

def norm(v):
    if v is None or pd.isna(v): return ''
    s=str(v).lower().replace('ё','е').replace('\xa0',' ').strip()
    return re.sub(r'\s+',' ',s)
def regionnorm(v):
    return re.sub(r'\s+(область|край|республика|автономный округ|автономная область)$','',norm(v))
def adminnorm(v):
    s=norm(v)
    s=re.sub(r'^(городской округ|муниципальный округ|муниципальный район|городской район|район|г\.?\s*)','',s)
    s=re.sub(r'\s+(район|округ)$','',s)
    return s.strip()
def raw_sql_row(lines,n):
    if int(n)<1 or int(n)>len(lines): raise ValueError(f'bad SQL COPY line {n}')
    cells=lines[int(n)-1].rstrip('\r\n').split('\t')
    if len(cells)!=6: raise ValueError(f'bad SQL COPY row at {n}: {len(cells)} columns')
    return dict(zip(('code','name_raw','name','status','name_full','is_settlement'),cells))
def raw_dbf_rows(path, targets):
    out={}
    with path.open('rb') as f:
        prefix=f.read(32); header_len=int.from_bytes(prefix[8:10],'little'); f.seek(0)
        header=f.read(header_len); n,hl,rl,fields=parse_dbf_header(header)
        if (n,hl,rl)!=(151875,705,395): raise ValueError('GeoKLADR DBF snapshot layout mismatch')
        byname={x['name']:x for x in fields}
        for row in targets.itertuples(index=False):
            no=int(row.record_number_1based); off=int(row.record_byte_offset_0based)
            if not 1<=no<=n or off!=hl+(no-1)*rl: raise ValueError('DBF locator mismatch')
            f.seek(off); raw=f.read(rl)
            if len(raw)!=rl: raise ValueError('truncated DBF record')
            def field(name):
                spec=byname[name]; a=spec['offset']; return raw[a:a+spec['width']].decode('cp1251').strip()
            ter,k1,k2,k3=(field(x) for x in ('TER','KOD1','KOD2','KOD3'))
            out[no]={'record_no':no,'byte_offset':off,'deleted_marker':raw[0:1].decode('ascii'),
              'ter':ter,'kod1':k1,'kod2':k2,'kod3':k3,'code':ter+k1+k2+k3,
              'name_raw':field('NAME1'),'type_raw':field('SCOKATO'),'lat_raw':field('LAT'),
              'lon_raw':field('LONG'),'data_upd_raw':field('DATA_UPD'),'oktmo_raw':field('OKTMO'),
              'is_settlement_raw':field('STATUS')}
    return out

def numeric_cell(v):
    if isinstance(v,(int,float)) and not isinstance(v,bool): return float(v)
    s=str(v).strip().replace('\xa0','').replace(' ','').replace(',','.')
    try:return float(s)
    except:return None

def verify_workbook_row(path, sheet, rownum, source_name_raw, source_name, population,
                        source_region_raw, source_region_norm, source_district_raw):
    suffix=path.suffix.lower()
    if suffix not in ('.xls','.xlsx','.xlsm'):
        return {'status':'unsupported_source_format','cells':[],'name_exact':False,'population_exact':False,'region_in_row':False,'district_in_row':False,'row_locator_exact':False}
    if not path.is_file():
        return {'status':'source_asset_missing_locally','cells':[],'name_exact':False,'population_exact':False,'region_in_row':False,'district_in_row':False,'row_locator_exact':False}
    if suffix=='.xls':
        key=('xls',str(path.resolve()))
        book=WORKBOOK_CACHE.get(key)
        if book is None:
            book=xlrd.open_workbook(str(path),on_demand=True);WORKBOOK_CACHE[key]=book
        if sheet not in book.sheet_names(): return {'status':'sheet_missing','cells':[],'name_exact':False,'population_exact':False,'region_in_row':False,'district_in_row':False,'row_locator_exact':False}
        sh=book.sheet_by_name(sheet); idx=int(rownum)-1
        if idx<0 or idx>=sh.nrows:return {'status':'row_out_of_range','cells':[],'name_exact':False,'population_exact':False,'region_in_row':False,'district_in_row':False,'row_locator_exact':False}
        cells=sh.row_values(idx)
    else:
        import openpyxl
        key=('xlsx',str(path.resolve()))
        book=WORKBOOK_CACHE.get(key)
        if book is None:
            book=openpyxl.load_workbook(path,read_only=True,data_only=True);WORKBOOK_CACHE[key]=book
        if sheet not in book.sheetnames:return {'status':'sheet_missing','cells':[],'name_exact':False,'population_exact':False,'region_in_row':False,'district_in_row':False,'row_locator_exact':False}
        sh=book[sheet]; cells=[x.value for x in sh[int(rownum)]]
    raw=[x for x in cells if x is not None and str(x).strip()]
    texts=[norm(x) for x in raw if isinstance(x,str)]
    label=norm(source_name_raw)
    target=norm(source_name)
    label_ok=bool(label and label in texts) or bool(target and target in texts)
    population=float(population)
    pop_ok=any((n is not None and abs(n-population)<1e-7) for n in (numeric_cell(x) for x in raw))
    rn=regionnorm(source_region_raw) or regionnorm(source_region_norm)
    region_ok=bool(rn and any(rn in t or t in rn for t in texts))
    dn=adminnorm(source_district_raw)
    district_ok=bool(dn and any(dn==adminnorm(t) or (len(dn)>3 and dn in adminnorm(t)) for t in texts))
    return {'status':'raw_source_row_reopened','cells':[str(x) for x in cells],
      'name_exact':label_ok,'population_exact':pop_ok,'region_in_row':region_ok,
      'district_in_row':district_ok,'row_locator_exact':True,'source_name_raw_expected':str(source_name_raw),
      'source_region_raw_expected':str(source_region_raw),'source_district_raw_expected':str(source_district_raw)}

def quarantine_ids():
    hard=set(json.loads(BLOCKED.read_text()).get('blocked_target_source_record_ids',[]))
    for p in QUARANTINES:
        if p.is_file(): hard.update(json.loads(p.read_text()).get('quarantine_target_source_record_ids',[]))
    return hard

WORKBOOK_CACHE={}

def main(output:Path, max_candidates:int):
    if output.exists(): raise FileExistsError(f'new output path required: {output}')
    files={'selected':F/'selected_observations.parquet','accepted_points':C/'accepted_mass_batch/accepted_point_uses.parquet',
      'source_evidence':F/'source_evidence.parquet','input_manifest':F/'input_manifest.parquet',
      'historical_named_candidates':H,'classifier_2009_sql':SQL,'geokladr_2011_dbf':DBF,
      'blocked_targets':BLOCKED}
    for p in QUARANTINES:
        if p.exists(): files['quarantine_'+p.stem]=p
    for p in APPROVED_POINT_IDS:
        if p.exists(): files['prior_reviewed_point_ids_'+p.stem]=p
    pins={k:{'path':str(p),'sha256':sha(p)} for k,p in files.items()}
    selected=pd.read_parquet(files['selected'])
    points=pd.read_parquet(files['accepted_points'],columns=['target_source_record_id'])
    accepted=set(points.target_source_record_id.astype(str))
    selected_ids=set(selected.source_record_id.astype(str))
    # Directly reviewed point rows in this simultaneous root batch take precedence.
    pre_reviewed=set()
    for p in APPROVED_POINT_IDS:
        if p.exists():
            pre_reviewed.update(pd.read_csv(p,dtype=str,keep_default_na=False,engine='python').target_source_record_id.astype(str))
    sel=selected.set_index('source_record_id',drop=False)
    allh=pd.read_parquet(H)
    c=allh.loc[allh.census_year.isin([2002,2010]) & allh.code_join_basis.eq('exact_raw_code') &
                allh.source_record_id.astype(str).isin(selected_ids) &
                ~allh.source_record_id.astype(str).isin(accepted|pre_reviewed)].copy()
    c['population_numeric']=pd.to_numeric(c.population,errors='coerce')
    c=c.sort_values(['population_numeric','source_record_id'],ascending=[False,True]).head(max_candidates).copy()
    if c.source_record_id.astype(str).duplicated().any():raise ValueError('duplicate candidate source IDs')
    with SQL.open('r',encoding='utf-8',newline='') as f: sql_lines=f.readlines()
    dbrows=raw_dbf_rows(DBF,c.drop_duplicates('record_number_1based'))
    # Check exact-coordinate collisions among all matching raw classifier/DBF objects,
    # not only the top-mass subset selected for detailed source-row reopening.
    all_exact=allh.loc[allh.census_year.isin([2002,2010]) & allh.code_join_basis.eq('exact_raw_code') &
       allh.historical_name_exact.eq(True) & allh.historical_type_exact.eq(True) & allh.is_additive_settlement_record.eq(True) &
       allh.latitude_from_lat.notna() & allh.longitude_from_long.notna(),
       ['census_year','latitude_from_lat','longitude_from_long','historical_okato_2011_raw']].copy()
    coords=all_exact.groupby(['census_year','latitude_from_lat','longitude_from_long']).historical_okato_2011_raw.nunique()
    collision=set(coords[coords>1].index)
    # Source-name/type uniqueness recomputed from frozen selected census grain.
    selcounts=selected.groupby(['census_year','region_norm','name_norm','type_norm'],dropna=False).source_record_id.nunique().to_dict()
    evid_df=pd.read_parquet(files['source_evidence'],columns=['source_record_id','source_evidence_json'])
    evid={str(x.source_record_id):json.loads(x.source_evidence_json) for x in evid_df.itertuples(index=False)}
    manifest=pd.read_parquet(files['input_manifest'],columns=['path','sha256'])
    manifest_sha=dict(zip(manifest.path.astype(str),manifest.sha256.astype(str)))
    rawroot=W/'settlements-raw'; asset_cache={}; workbook_cache={}
    hard=quarantine_ids()
    # Include 31 confirmed blocked IDs in exact exclusion review even if no selected row is present.
    rows=[]; uses=[]; rawchecks=[]
    for r in c.itertuples(index=False):
        sid=str(r.source_record_id); source=sel.loc[sid]; ev=evid.get(sid,{})
        raw_sql=raw_sql_row(sql_lines,int(r.source_line_1based)); raw_dbf=dbrows[int(r.record_number_1based)]
        reasons=[]
        code=str(r.historical_okato_2009_raw or '')
        if not (len(code)==11 and code.isdigit()):reasons.append('raw_2009_classifier_code_not_exact_11_digit_OKATO')
        if str(raw_sql['code'])!=code or raw_sql['is_settlement']!='t':reasons.append('raw_SQL_line_does_not_match_exact_code_or_settlement_flag')
        if raw_dbf['code']!=code or raw_dbf['deleted_marker']!=' ' or raw_dbf['kod3']=='000':reasons.append('live_DBf_record_not_exact_active_nonurban_11_digit_object')
        if raw_dbf['ter']!=code[:2]:reasons.append('region_TЕR_does_not_match_literal_2009_code_prefix')
        if norm(raw_sql['name_raw'])!=norm(str(r.name_raw_2009)) or norm(raw_dbf['name_raw'])!=norm(str(r.name_raw_2011)):
            reasons.append('raw_classifier_or_DBf_name_differs_from_reviewed_candidate')
        if raw_dbf['type_raw']!=str(r.scokato_raw_text).strip():reasons.append('raw_DBf_type_differs_from_candidate')
        if norm(raw_sql['status']) not in PHYSICAL_STATUSES:reasons.append('2009_classifier_status_not_rural_physical_settlement')
        if not bool(r.historical_name_exact) or not bool(r.historical_type_exact):reasons.append('candidate_name_or_type_not_exact')
        if int(r.source_region_name_type_count)!=1:reasons.append('selected_region_name_type_key_not_unique')
        if int(r.historical_key_region_name_type_count)!=1:reasons.append('historical_region_name_type_key_not_unique')
        if regionnorm(str(r.historical_point_modern_region))!=regionnorm(str(source.region_norm)):reasons.append('historical_object_region_disagrees_with_selected_region')
        selected_key=(int(source.census_year),source.region_norm,source.name_norm,source.type_norm)
        if selcounts.get(selected_key,0)!=1:reasons.append('frozen_selected_year_region_name_type_not_unique')
        grain=str(source.entity_grain_status or '').lower()
        if any(x in grain for x in ('aggregate','federal_city','parent','derived_sum')):reasons.append('selected_entity_grain_explicit_aggregate_or_parent')
        if not bool(source.is_additive_settlement_record):reasons.append('selected_source_not_additive_settlement_row')
        if ev.get('is_federal_aggregate') or ev.get('legacy_verified_successor_settlement_id') or ev.get('legacy_same_year_collision'):
            reasons.append('frozen_evidence_federal_event_or_same_year_collision_hold')
        if sid in hard:reasons.append('prior_target_specific_hard_quarantine_preserved')
        if sid in pre_reviewed:reasons.append('separately_reviewed_mass_batch_point_candidate_excluded_from_rural_batch')
        ckey=(int(r.census_year),float(r.latitude_from_lat),float(r.longitude_from_long))
        shared=ckey in collision
        if shared:reasons.append('same_year_coordinate_shared_by_distinct_raw_11_digit_objects')
        try:lat=float(raw_dbf['lat_raw']);lon=float(raw_dbf['lon_raw'])
        except:lat=lon=float('nan')
        if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat)>90 or abs(lon)>180:reasons.append('raw_DBf_coordinate_invalid')
        sf=str(source.source_file)
        local=(rawroot/sf).resolve()
        expected=manifest_sha.get(sf)
        if sf not in asset_cache:
            actual=sha(local) if local.is_file() else None
            asset_cache[sf]=(expected,actual,local)
        expected,actual,local=asset_cache[sf]
        if not expected or not actual or expected!=actual:reasons.append('source_file_not_locally_byte_verified_against_frozen_manifest')
        sheet=str(source.source_sheet) if pd.notna(source.source_sheet) else ''
        source_row=int(source.source_row) if pd.notna(source.source_row) else 0
        rawproof=verify_workbook_row(local,sheet,source_row,source.source_name_raw,source.settlement_name,
            source.population,source.region_raw,source.region_norm,source.district_raw)
        name_ok=rawproof.get('name_exact',False);pop_ok=rawproof.get('population_exact',False)
        if not name_ok:reasons.append('published_raw_source_row_label_not_reopened_exact')
        if not pop_ok:reasons.append('published_raw_source_row_population_not_reopened_exact')
        # Require row-level region and district wherever they are actually printed;
        # blank source cells remain explicit and are never filled from adjacent context.
        rawtexts=[norm(x) for x in rawproof.get('cells',[]) if isinstance(x,str)]
        region_literal=regionnorm(source.region_raw) or regionnorm(source.region_norm)
        region_in=rawproof.get('region_in_row',False)
        district_in=rawproof.get('district_in_row',False)
        rawtexts=[norm(x) for x in rawproof.get('cells',[]) if isinstance(x,str)]
        explicit_region_cells=[t for t in rawtexts if re.search(r'\b(область|край|республика|автономный округ|автономная область)\b',t)]
        explicit_district_cells=[t for t in rawtexts if 'район' in t]
        if explicit_region_cells and not region_in:reasons.append('direct_raw_source_region_cell_disagrees')
        if explicit_district_cells and norm(source.district_raw) and not district_in:reasons.append('direct_raw_source_district_cell_disagrees')
        # Some frozen 2002 source rows print only label and population. For
        # those, require row-bound frozen source_evidence agreement and leave
        # the blank row cells explicit; never claim a carried context was printed.
        source_evidence_matches=bool(ev) and norm(ev.get('source_file'))==norm(sf) and \
            numeric_cell(ev.get('source_row')) is not None and int(numeric_cell(ev.get('source_row')))==source_row and \
            regionnorm(ev.get('region_norm'))==regionnorm(source.region_norm) and \
            norm(ev.get('source_name_raw'))==norm(source.source_name_raw) and \
            numeric_cell(ev.get('population')) is not None and int(numeric_cell(ev.get('population')))==int(source.population)
        if norm(ev.get('district_raw'))!=norm(source.district_raw):source_evidence_matches=False
        if not source_evidence_matches:reasons.append('frozen_source_evidence_not_exact_on_source_locator_name_population_region_admin')
        key=(int(source.census_year),str(source.region_norm),str(source.name_norm),str(source.type_norm))
        item={'target_source_record_id':sid,'target_year':int(source.census_year),'population':int(source.population),
          'settlement_name':str(source.settlement_name),'settlement_type':str(source.settlement_type),
          'source_region_raw':norm(source.region_raw),'source_region_norm':norm(source.region_norm),
          'source_district_raw':norm(source.district_raw),'source_municipality_raw':norm(source.municipality_raw),
          'selected_source_file':sf,'selected_source_file_sha256_manifest':expected,'selected_source_file_sha256_local':actual,
          'selected_source_sheet':sheet,'selected_source_row_1based':source_row,'source_native_id_opaque_not_code':str(source.source_native_id),
          'source_raw_name_selected':norm(source.source_name_raw),'source_raw_row_check_json':json.dumps(rawproof,ensure_ascii=False),
          'direct_source_row_region_cell_witness':region_in,'direct_source_row_district_cell_witness':district_in,
          'frozen_source_evidence_region_admin_matches_selected':source_evidence_matches,
          'admin_context_interpretation':'direct raw cells retained as observed; blank source-row region/district remains blank; selected admin context cross-checked against exact frozen source-evidence locator and is not claimed as a printed row cell',
          'historical_classifier_sql_file':str(SQL),'historical_classifier_sql_sha256':pins['classifier_2009_sql']['sha256'],
          'historical_classifier_sql_line_1based':int(r.source_line_1based),'historical_okato2009_raw':code,
          'classifier_raw_name':raw_sql['name_raw'],'classifier_raw_status':raw_sql['status'],'classifier_raw_is_settlement':raw_sql['is_settlement'],
          'geokladr_dbf_file':str(DBF),'geokladr_dbf_sha256':pins['geokladr_2011_dbf']['sha256'],
          'geokladr_record_1based':int(raw_dbf['record_no']),'geokladr_byte_offset_0based':int(raw_dbf['byte_offset']),
          'geokladr_okato2011_raw':raw_dbf['code'],'geokladr_ter_raw':raw_dbf['ter'],'geokladr_kod1_raw':raw_dbf['kod1'],
          'geokladr_kod2_raw':raw_dbf['kod2'],'geokladr_kod3_raw':raw_dbf['kod3'],'geokladr_name_raw':raw_dbf['name_raw'],
          'geokladr_type_raw':raw_dbf['type_raw'],'geokladr_lat_raw':raw_dbf['lat_raw'],'geokladr_lon_raw':raw_dbf['lon_raw'],
          'geokladr_data_upd_raw':raw_dbf['data_upd_raw'],'latitude':lat,'longitude':lon,
          'join_rule':'exact 11-digit raw 2009 classifier OKATO == live raw 2011 GeoKLADR TER+KOD1+KOD2+KOD3; rural typed physical object',
          'shared_same_year_point_hold':shared,'prior_quarantine':sid in hard,
          'legacy_identity_conflict_preserved_not_decided_by_point':bool(ev.get('legacy_identity_conflict',False)),
          'temporal_identity_admitted':False,'modern_point_continuity_admitted':False,
          'population_boundary_comparability_asserted':False,'census_date_coordinate_claimed':False,
          'decision_status':'point_only_candidate_pending_independent_review' if not reasons else 'held_candidate',
          'hold_reasons_json':json.dumps(reasons,ensure_ascii=False)}
        rows.append(item)
        rawchecks.append({'source_record_id':sid,'source_row_name_exact':name_ok,'source_row_population_exact':pop_ok,
          'source_row_region_in_row':region_in,'source_row_district_in_row':district_in,'source_row_format_status':rawproof.get('status'),
          'source_file_manifest_sha256':expected,'source_file_local_sha256':actual,'source_file_hash_ok':bool(expected and actual and expected==actual),
          'sql_literal_code_ok':raw_sql['code']==code,'dbf_literal_code_ok':raw_dbf['code']==code,'dbf_literal_name_type_ok':norm(raw_dbf['name_raw'])==norm(str(r.name_raw_2011)) and raw_dbf['type_raw']==str(r.scokato_raw_text).strip()})
        if not reasons:
            locator=f"{sf};sheet={sheet};row_1based={source_row};source_native_id={source.source_native_id}"
            uses.append({'target_source_record_id':sid,'target_year':int(source.census_year),'latitude':lat,'longitude':lon,
              'coordinate_quality':'2011_named_typed_rural_object_point_candidate_pending_review',
              'coordinate_source':'Exact 11-digit 2009 OKATO classifier row and live 2011 GeoKLADR rural typed object; point-only retrospective use assumption',
              'coordinate_source_record_id':'GEOKLADR2011:'+code,'coordinate_provider':'GeoKLADR 2011 raw DBF',
              'coordinate_provider_id':'','source_name':raw_dbf['name_raw'],'source_type':raw_dbf['type_raw'],
              'source_region':str(source.region_norm),'source_file':str(DBF),'source_row':int(raw_dbf['record_no']),
              'source_sha256':pins['geokladr_2011_dbf']['sha256'],
              'source_locator':f"DBF_record_1based={raw_dbf['record_no']};DBF_byte_offset_0based={raw_dbf['byte_offset']};OKATO2011_raw={code};KOD3_raw={raw_dbf['kod3']}",
              'coordinate_provenance':'2011 named typed rural point; census-date measurement and population-boundary equivalence are not asserted',
              'admission_rule':'rural_exact_native_11_digit_OKATO_2009_to_live_GeoKLADR_2011_point_only_v1',
              'coordinate_admission_status':'staged_candidate_pending_independent_review','coordinate_measurement_date_unknown':True,
              'boundary_comparability_asserted':False,'admission_allowed':False,
              'point_origin_file':str(DBF),'point_origin_sha256':pins['geokladr_2011_dbf']['sha256'],
              'point_origin_locator':f"DBF_record_1based={raw_dbf['record_no']};DBF_byte_offset_0based={raw_dbf['byte_offset']};OKATO2011_raw={code}",
              'point_origin_kind':'raw_named_typed_2011_rural_geo_object','historical_classifier2009_file':str(SQL),
              'historical_classifier2009_sha256':pins['classifier_2009_sql']['sha256'],
              'historical_classifier2009_locator':f"line_1based={int(r.source_line_1based)};OKATO2009_raw={code}",
              'source_record_lineage_json':json.dumps({'source_record_id':sid,'source_file':sf,'source_sha256':expected,
                'source_locator':locator,'source_name_raw':norm(source.source_name_raw),'settlement_type':norm(source.settlement_type),
                'region_raw':norm(source.region_raw),'district_raw':norm(source.district_raw),'population':int(source.population),
                'source_native_id':str(source.source_native_id),'native_id_is_not_OKATO':True,
                'reopened_source_row_cells':rawproof['cells']},ensure_ascii=False),
              'coordinate_use_interpretation':'direct point-only association to the same-year selected typed source row; no temporal same-place or provider identifier binding',
              'modern_point_continuity_admitted':False,'temporal_identity_admitted':False,
              'population_scope_comparability_asserted':False})
    output.mkdir(parents=True)
    ledger=pd.DataFrame(rows); point_uses=pd.DataFrame(uses); checks=pd.DataFrame(rawchecks)
    ledger.to_parquet(output/'rural_native_candidate_ledger.parquet',index=False)
    point_uses.to_parquet(output/'rural_native_staged_point_uses.parquet',index=False)
    checks.to_csv(output/'raw_source_checks.csv',index=False)
    ledger.sort_values(['population','target_source_record_id'],ascending=[False,True]).head(100).to_csv(output/'review_top100.csv',index=False)
    counts={}
    for value in ledger.hold_reasons_json:
        for reason in json.loads(value):counts[reason]=counts.get(reason,0)+1
    receipt={'status':'rural_exact_11_digit_okato_point_candidates_only_no_admissions',
      'max_candidates_by_population':max_candidates,'candidate_rows':len(ledger),'candidate_population':int(ledger.population.sum()),
      'point_only_candidates_pending_review':len(point_uses),'pending_review_population':int(ledger.loc[ledger.decision_status.eq('point_only_candidate_pending_independent_review'),'population'].sum()),
      'target_year_counts':ledger.groupby('target_year').size().to_dict(),
      'pending_by_year':ledger.loc[ledger.decision_status.eq('point_only_candidate_pending_independent_review')].groupby('target_year').agg(rows=('target_source_record_id','size'),population=('population','sum')).reset_index().to_dict('records'),
      'hold_reason_marginals_overlap':counts,'review_sample':'review_top100.csv',
      'inputs':pins,'script_sha256':sha(Path(__file__)),
      'rule_summary':'Exact 11-digit raw classifier OKATO==live 2011 GeoKLADR code; matching region; rural physical SQL status; exact candidate raw name/type; unique selected and historical region/name/type keys; frozen source-evidence locator/admin agreement; published source file byte hash and exact raw row name/population. Direct region/admin cells are recorded when printed; blank cells remain blank and are not filled from adjacent rows. Reject same-year shared-coordinate collisions and prior hard quarantines.',
      'interpretation':'Point-only retrospective spatial association for an exact typed selected old-census row; exact native 11-digit code is the classifier/GeoKLADR object key and source_native_id remains opaque, never an OKATO code. No census-date point, temporal identity, modern identifier binding, population-boundary comparability, or continuity is claimed.',
      'outputs':{p.name:sha(p) for p in output.iterdir() if p.is_file()}}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('inputs','outputs','hold_reason_marginals_overlap')},ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=C/'root/R4/historical_points/rural_native_extension/source_evidence_verified_final')
    ap.add_argument('--max-candidates',type=int,default=2000)
    a=ap.parse_args();main(a.output,a.max_candidates)
