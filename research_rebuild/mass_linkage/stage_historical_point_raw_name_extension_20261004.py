"""Stage strict punctuation-preserving old-year point candidates missed by name normalization.

The rule is point-only: exact census source name/type/region and raw source-row
population, joined to one exact typed 2009 SQL/2011 DBF object in the same region.
It makes no temporal identity or modern-provider claim.
"""
from __future__ import annotations
import argparse,hashlib,json,re,sys,unicodedata
from pathlib import Path
import pandas as pd
import fitz
W=Path('/workspace');sys.path.insert(0,str(W/'russian-settlements-research/research_rebuild/mass_linkage'))
from stage_historical_bridge_20261004 import raw_sql_row,raw_dbf_rows,sha,SQL,DBF
F=W/'settlements-delivery/continuation-consolidated-20261003'
RESIDUAL=W/'settlements-work/continuation_20261004/root/mass_union_joint_residual.parquet'
HOBJ=W/'settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet'
CLASS=W/'settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet'
REGION_RAW={
 'хабаровский':'Хабаровский край','красноярский':'Красноярский край','краснодарский':'Краснодарский край',
 'приморский':'Приморский край','алтайский':'Алтайский край'}
TARGET_NAMES={'Комсомольск-на-Амуре','Зеленогорск','Славянск-на-Кубани','Спасск-Дальний','Камень-на-Оби'}

def rawkey(v):
 if v is None or pd.isna(v):return ''
 return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').split())
def main(out):
 if out.exists():raise FileExistsError('new immutable output directory required')
 pinpaths=[F/'selected_observations.parquet',F/'source_evidence.parquet',F/'input_manifest.parquet',
  W/'settlements-baseline/output/input_manifest.parquet',RESIDUAL,HOBJ,CLASS,SQL,DBF,
  W/'settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls',
  W/'settlements-raw/data/raw/2010_official_tom11/pub-11-1-4.pdf']
 pins={str(p):sha(p) for p in pinpaths}
 selected=pd.read_parquet(F/'selected_observations.parquet')
 residual=pd.read_parquet(RESIDUAL)
 ids=set(residual.loc[residual.census_year.isin([2002,2010])&
     residual.settlement_name.isin(TARGET_NAMES),'source_record_id'].astype(str))
 src=selected[selected.source_record_id.astype(str).isin(ids)].copy()
 src=src[src.latitude.isna()&src.longitude.isna()].copy()
 if len(src)!=10:raise ValueError(f'expected ten specified missing-point source records; got {len(src)}')
 h=pd.read_parquet(HOBJ)
 classifier=pd.read_parquet(CLASS)
 ev=pd.read_parquet(F/'source_evidence.parquet',columns=['source_record_id','source_evidence_json'])
 evmap={str(r.source_record_id):json.loads(r.source_evidence_json) for r in ev.itertuples(index=False)}
 fm=pd.read_parquet(F/'input_manifest.parquet',columns=['path','sha256']);fmap=dict(zip(fm.path.astype(str),fm.sha256.astype(str)))
 bm=pd.read_parquet('/workspace/settlements-baseline/output/input_manifest.parquet',columns=['path','sha256']);bmap=dict(zip(bm.path.astype(str),bm.sha256.astype(str)))
 # 2009 SQL parent records explicitly decode OKATO territory prefixes.
 with SQL.open('r',encoding='utf-8',newline='') as f: sql_lines=f.readlines()
 candidates=[]; outputs=[]
 dbf_needs=[]
 for r in src.itertuples(index=False):
  objs=h[h.name_raw_2009.map(rawkey).eq(rawkey(r.settlement_name)) &
         h.name_raw_2011.map(rawkey).eq(rawkey(r.settlement_name)) &
         h.status.eq('город') & h.settlement_type_raw.eq('г') &
         h.historical_point_modern_region.eq(r.region_norm) &
         h.historical_name_exact.eq(True) & h.historical_type_exact.eq(True)].copy()
  if len(objs)!=1: raise ValueError(f'{r.source_record_id}: expected unique exact same-region typed historical object, got {len(objs)}')
  o=objs.iloc[0];dbf_needs.append(o)
 # Read exact DBF row bytes selected by raw historical object locators.
 class_targets=pd.DataFrame([{'record_number_1based':o.record_number_1based,'record_byte_offset_0based':o.record_byte_offset_0based} for o in dbf_needs])
 rawgeo=raw_dbf_rows(DBF,class_targets)
 workbooks={};pdfdoc=fitz.open(W/'settlements-raw/data/raw/2010_official_tom11/pub-11-1-4.pdf')
 xls_path=W/'settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls'
 xls=pd.read_excel(xls_path,sheet_name=0,header=None)
 for r,o in zip(src.itertuples(index=False),dbf_needs):
  reasons=[];rid=str(r.source_record_id);e=evmap[rid]
  # Source row grain and exact same-year source key.
  peer=selected[selected.census_year.eq(r.census_year)&selected.region_norm.eq(r.region_norm)&
    selected.name_norm.eq(r.name_norm)&selected.type_norm.eq(r.type_norm)&selected.is_additive_settlement_record.eq(True)]
  if len(peer)!=1:reasons.append('same_year_selected_region_name_type_not_unique')
  if not bool(r.is_additive_settlement_record):reasons.append('source_row_not_additive')
  if r.settlement_type!='город' or o['status']!='город' or o['settlement_type_raw']!='г':reasons.append('exact_city_type_chain_failed')
  if rawkey(r.settlement_name)!=rawkey(o['name_raw_2009']) or rawkey(r.settlement_name)!=rawkey(o['name_raw_2011']):reasons.append('punctuation_preserving_name_equality_failed')
  if not (str(o['historical_okato_2009_raw']).isdigit() and len(str(o['historical_okato_2009_raw']))==8 and
          str(o['historical_okato_2011_raw'])==str(o['historical_okato_2009_raw'])+'000' and str(o['kod3_raw_text']).strip()=='000'):
   reasons.append('typed_8_digit_to_11_digit_raw_code_bridge_failed')
  region_code=str(o['historical_okato_2009_raw'])[:2]+'000000'
  parent=classifier[classifier.historical_okato.astype(str).eq(region_code)]
  if len(parent)!=1:reasons.append('territory_prefix_parent_code_not_unique')
  parent_row=parent.iloc[0] if len(parent) else None
  region_label=REGION_RAW.get(str(r.region_norm))
  if not region_label or parent_row is None or rawkey(parent_row.name_raw)!=rawkey(region_label):reasons.append('raw_okato_territory_prefix_not_equal_expected_region')
  if str(o['historical_point_modern_region'])!=str(r.region_norm):reasons.append('historical_point_region_disagrees_with_census_source_region')
  if int(o['historical_key_region_name_type_count'])!=1:reasons.append('historical_same_region_name_type_not_unique')
  # Any exact same-name/type classifier competitor must map by its literal OKATO TER prefix.
  rivals=classifier[classifier.name_raw.map(rawkey).eq(rawkey(r.settlement_name))&classifier.status.eq('город')&classifier.is_settlement_raw.eq('t')].copy()
  rival_evidence=[]
  for q in rivals.itertuples(index=False):
   code=str(q.historical_okato);pc=code[:2]+'000000';pr=classifier[classifier.historical_okato.astype(str).eq(pc)]
   if len(pr)!=1: rival_evidence.append({'code_raw':code,'status':'unresolved_parent_region'});continue
   prow=pr.iloc[0]
   qsql=raw_sql_row(sql_lines,q.source_line_1based)
   rival_evidence.append({'okato2009_raw':code,'sql_line_1based':int(q.source_line_1based),'raw_name':qsql['name_raw'],
       'raw_type':qsql['status'],'ter_prefix_raw':code[:2],'parent_okato_raw':pc,'parent_region_raw':prow.name_raw,
       'same_expected_region':rawkey(prow.name_raw)==rawkey(region_label)})
  same_region=[v for v in rival_evidence if v.get('same_expected_region') is True]
  if len(same_region)!=1:reasons.append('same_region_classifier_name_type_competitor_not_resolved')
  # Exact point collision checks among typed historical objects.
  samepoint=h[(pd.to_numeric(h.latitude_from_lat,errors='coerce').eq(float(o.latitude_from_lat)))&
      (pd.to_numeric(h.longitude_from_long,errors='coerce').eq(float(o.longitude_from_long)))]
  point_codes=sorted(set(samepoint.historical_okato_2011_raw.astype(str)))
  if len(point_codes)!=1:reasons.append('exact_2011_point_shared_by_multiple_raw_historical_objects')
  # Validate source raw row and population directly in the pinned census publication.
  sf=str(r.source_file);local=W/'settlements-raw'/sf;actual=sha(local) if local.is_file() else ''
  expected=fmap.get(sf);base_expected=bmap.get(sf)
  if not (actual and expected==actual):reasons.append('census_asset_hash_not_verified_against_frozen_selection_manifest')
  rawname='';raw_population=None;raw_region_context='';source_locator=''
  if int(r.census_year)==2002:
   # Workbook row is a one-based Excel row. Verify label, published count and closest subject heading.
   ix=int(r.source_row)-1;rawname=str(xls.iloc[ix,0]).strip();raw_population=int(xls.iloc[ix,1])
   if rawname!=str(r.source_name_raw).strip():reasons.append('raw_2002_workbook_label_differs_from_selected_source_name')
   if raw_population!=int(r.population):reasons.append('raw_2002_workbook_population_differs_from_selected_value')
   labels=xls.iloc[:ix+1,0].fillna('').astype(str).tolist();expected_region=region_label
   hits=[i for i,v in enumerate(labels) if rawkey(v.strip())==rawkey(expected_region)]
   raw_region_context=xls.iloc[hits[-1],0].strip() if hits else ''
   if not hits:reasons.append('raw_2002_workbook_region_heading_not_found_before_source_row')
   source_locator=f'Excel_sheet=0;Excel_row_1based={int(r.source_row)};source_native_id={r.source_native_id}'
  else:
   page=int(str(r.source_sheet).split('_')[-1])-1
   lines=pdfdoc[page].get_text('text').splitlines();name_line=next((i for i,v in enumerate(lines) if rawkey(v)==rawkey(r.settlement_name)),None)
   if name_line is None or name_line+4>=len(lines):reasons.append('raw_2010_pdf_table_row_context_not_found')
   else:
    rawname=lines[name_line].strip();raw_region_context=lines[name_line+1].strip()
    try: prior_pop=int(lines[name_line+2].strip().replace(' ',''));raw_population=int(lines[name_line+3].strip().replace(' ',''))
    except Exception: prior_pop=None;raw_population=None;reasons.append('raw_2010_pdf_population_cells_not_parseable')
    if rawkey(raw_region_context)!=rawkey(region_label):reasons.append('raw_2010_pdf_region_label_differs_from_selected_region')
    if raw_population!=int(r.population):reasons.append('raw_2010_pdf_population_differs_from_selected_value')
    rawline=str(r.source_name_raw)
    if rawkey(r.settlement_name) not in rawkey(rawline) or str(raw_population) not in rawline:reasons.append('selected_source_evidence_line_does_not_restate_pdf_count')
   source_locator=f'PDF_page_1based={page+1};published_table_row={int(r.source_row)};source_native_id={r.source_native_id}'
  source_evidence_hash=str(e.get('source_sha256') or '')
  # Source evidence absence of an optional sheet/row locator does not affect the raw verified source locator above.
  if e.get('legacy_identity_conflict') or e.get('legacy_same_year_collision') or e.get('is_federal_aggregate') or not e.get('is_additive_settlement_record'):
   reasons.append('source_evidence_identity_collision_aggregate_or_nonadditive_hold')
  lat=float(o.latitude_from_lat);lon=float(o.longitude_from_long)
  # Verify DBF raw record agrees with normalized historical-object payload.
  db=rawgeo[int(o.record_number_1based)]
  if db['code']!=str(o.historical_okato_2011_raw) or db['kod3']!='000' or db['deleted']!=' ':
   reasons.append('raw_dbf_record_code_or_live_marker_mismatch')
  if rawkey(db['name_raw'])!=rawkey(r.settlement_name) or db['type_raw']!='г':reasons.append('raw_dbf_name_or_type_mismatch')
  candidate_row={'source_record_id':rid,'census_year':int(r.census_year),'settlement_name':r.settlement_name,'settlement_type':r.settlement_type,
   'region_norm':r.region_norm,'population':int(r.population),'source_raw_name':r.source_name_raw,'source_raw_row_label':rawname,
   'source_raw_region_context':raw_region_context,'source_raw_population_verified':raw_population,
   'source_file':sf,'source_file_sha256_manifest':expected,'source_file_sha256_baseline_manifest':base_expected,
   'source_file_sha256_local':actual,'source_file_sha256_verified':bool(actual and expected==actual),'source_locator_verified':source_locator,
   'source_sheet_field_used':False,'source_native_id':r.source_native_id,'source_evidence_json_source_path':e.get('source_path'),
   'source_evidence_json_sha256':source_evidence_hash or None,
   'historical_classifier_file':str(SQL),'historical_classifier_sha256':pins[str(SQL)],
   'historical_classifier_locator':f'line_1based={int(o.source_line_1based)};OKATO2009_raw={o.historical_okato_2009_raw}',
   'historical_classifier_code_raw':str(o.historical_okato_2009_raw),'historical_classifier_raw_name':o.name_raw_2009,
   'historical_classifier_raw_type':o.status,'historical_classifier_region_parent_code_raw':region_code,
   'historical_classifier_region_parent_name_raw':parent_row.name_raw if parent_row is not None else None,
   'historical_classifier_region_parent_line_1based':int(parent_row.source_line_1based) if parent_row is not None else None,
   'historical_competing_name_type_codes_by_region_json':json.dumps(rival_evidence,ensure_ascii=False),
   'different_region_competitor_scoped_out':len(rival_evidence)>1 and len(same_region)==1,
   'historical_geo_file':str(DBF),'historical_geo_sha256':pins[str(DBF)],'historical_geo_record_1based':int(o.record_number_1based),
   'historical_geo_byte_offset_0based':int(o.record_byte_offset_0based),'historical_okato2011_raw':db['code'],
   'historical_geo_kod3_raw':db['kod3'],'historical_geo_raw_name':db['name_raw'],'historical_geo_raw_type':db['type_raw'],
   'historical_geo_date_raw':db['updated_raw'],'latitude':lat,'longitude':lon,'historical_point_region':o.historical_point_modern_region,
   'exact_point_collision_objects':json.dumps(point_codes,ensure_ascii=False),
   'name_match_basis':'Unicode NFKC/casefold/ё→е and whitespace collapse; punctuation retained; avoids lossy source name_norm that turns hyphens into spaces',
   'point_only_rule':'unique additive same-year source row by exact region/name/type + raw published population; exact raw 2009 typed city code and live 2011 DBF object; literal code TER parent and point locate to same selected region; no temporal identity inference',
   'candidate_status':'point_only_candidate_pending_independent_review' if not reasons else 'held',
   'hold_reasons_json':json.dumps(reasons,ensure_ascii=False),'temporal_identity_admitted':False,'modern_provider_binding_claimed':False,
   'modern_point_continuity_admitted':False,'population_boundary_comparability_admitted':False,'admission_allowed':False}
  candidates.append(candidate_row)
  if not reasons:
   outputs.append({'target_source_record_id':rid,'target_year':int(r.census_year),'latitude':lat,'longitude':lon,
     'coordinate_quality':'2011_named_typed_point_candidate_pending_review','coordinate_source':'Raw named typed GeoKLADR 2011 point; exact historical code and scoped regional source-name recovery; point-only retrospective use',
     'coordinate_source_record_id':'GEOKLADR2011:'+db['code'],'coordinate_provider':'GeoKLADR 2011 raw DBF','coordinate_provider_id':'',
     'source_name':db['name_raw'],'source_type':db['type_raw'],'source_region':str(r.region_norm),'source_file':str(DBF),
     'source_row':int(db['record_no']),'source_sha256':pins[str(DBF)],
     'source_locator':f'DBF_record_1based={db["record_no"]};DBF_byte_offset_0based={db["offset"]};OKATO2011_raw={db["code"]};KOD3_raw={db["kod3"]}',
     'coordinate_provenance':'2011 named typed point; no census-date coordinate or population boundary equivalence asserted',
     'admission_rule':'old_census_raw_punctuation_preserving_exact_name_scoped_region_point_only_candidate_v1',
     'coordinate_admission_status':'staged_candidate_pending_independent_review','coordinate_measurement_date_unknown':True,
     'boundary_comparability_asserted':False,'admission_allowed':False,'point_origin_file':str(DBF),
     'point_origin_sha256':pins[str(DBF)],'point_origin_locator':f'DBF_record_1based={db["record_no"]};DBF_byte_offset_0based={db["offset"]};OKATO2011_raw={db["code"]}',
     'point_origin_kind':'raw_named_typed_geo2011_object','historical_classifier2009_file':str(SQL),'historical_classifier2009_sha256':pins[str(SQL)],
     'historical_classifier2009_locator':f'line_1based={int(o.source_line_1based)};OKATO2009_raw={o.historical_okato_2009_raw}',
     'target_source_locator_verified':source_locator,'target_source_file_sha256':actual,'target_population_raw_verified':raw_population,
     'point_only_assumption':'same-year exact typed coded object association only; no cross-year identity, modern identifier binding, or population boundary claim',
     'temporal_identity_admitted':False,'modern_provider_binding_claimed':False})
 out.mkdir(parents=True)
 cand=pd.DataFrame(candidates);use=pd.DataFrame(outputs)
 cand.to_parquet(out/'raw_name_key_extension_candidates.parquet',index=False)
 use.to_parquet(out/'additional_point_only_staged_uses.parquet',index=False)
 cand.sort_values(['population','source_record_id'],ascending=[False,True]).to_csv(out/'fixed_10_source_review.csv',index=False)
 summary={'status':'separate_point_only_candidate_extension_no_admissions','inputs':pins,'candidate_rows':len(cand),
  'candidate_population':int(cand.population.sum()),'point_only_pending_review_rows':len(use),
  'point_only_pending_review_population':int(use.target_source_record_id.map(cand.set_index('source_record_id').population).sum()) if len(use) else 0,
  'same_name_competitor_scoped_resolution_rows':int(cand.different_region_competitor_scoped_out.sum()),
  'source_rows_reopened_and_population_verified':int(cand.source_raw_population_verified.notna().sum()),
  'all_source_hashes_match_frozen_manifest':bool(cand.source_file_sha256_verified.all()),
  'by_year':cand.groupby('census_year').agg(rows=('source_record_id','size'),population=('population','sum'),staged=('candidate_status',lambda s:int(s.eq('point_only_candidate_pending_independent_review').sum()))).reset_index().to_dict('records'),
  'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()},
  'limitations':['Candidate generation only; no temporal identity or modern provider identifier claim.','Historical point source update is 2011, not a census-date measurement.','Population boundary comparability is not asserted.','The same-name Zelenogorsk object in Saint Petersburg is scoped out only by raw OKATO territory prefix parent plus the unique Krasnoyarsk source key and point-region concordance; do not generalize this resolution without equivalent evidence.']}
 (out/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in ('inputs','outputs','limitations')},ensure_ascii=False))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=W/'settlements-work/continuation_20261004/historical_points/recovery/name_key_extension');main(ap.parse_args().output)
