"""Recover selected-source provenance and point-only candidates for old bridge holds.

This recovery layer does not alter the reviewed v1 stage or admit temporal identity.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import pandas as pd
W=Path('/workspace')
F=W/'settlements-delivery/continuation-consolidated-20261003'
BASE=W/'settlements-baseline/output/input_manifest.parquet'
OLD=W/'settlements-work/continuation_20261004/historical_points'
EVID=F/'source_evidence.parquet'
ALIASES={
 'research_rebuild/evidence/ingestion/arkhangelsk_2010_archived_page_audit_r2_region_join/arkhangelsk_2010_archived_original.html':W/'settlements-work/sources/r2-missing/arkhangelsk_2010_archived_original.html',
 'research_rebuild/evidence/ingestion/sources/kaliningrad_2010_official/kaliningrad_2010_tom1.xlsx':W/'settlements-work/sources/r2-missing/kaliningrad_tom1.xlsx',
 'research_rebuild/evidence/ingestion/sources/murmansk_2010_official/murmansk_population_by_sex_municipalities.doc':W/'settlements-work/sources/r2-missing/murmansk_population.doc',
}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def decode_reason_list(value):
 if isinstance(value,list):return value
 if isinstance(value,str):
  try:
   x=json.loads(value)
   return x if isinstance(x,list) else []
  except Exception:return []
 return []
def main(out):
 if out.exists():raise FileExistsError('new immutable recovery directory required')
 ledger=pd.read_parquet(OLD/'historical_bridge_gate_ledger.parquet')
 staged_old=pd.read_parquet(OLD/'staged_point_uses.parquet')
 source=pd.read_parquet(EVID,columns=['source_record_id','source_evidence_json'])
 emap={str(r.source_record_id):json.loads(r.source_evidence_json) for r in source.itertuples(index=False)}
 bmf=pd.read_parquet(BASE,columns=['path','sha256'])
 bmap=dict(zip(bmf.path.astype(str),bmf.sha256.astype(str)))
 dmf=pd.read_parquet(F/'input_manifest.parquet',columns=['path','sha256'])
 dmap=dict(zip(dmf.path.astype(str),dmf.sha256.astype(str)))
 candidates=ledger[ledger.decision_status.eq('held_candidate')].copy()
 additional=[];assetrows=[];outrows=[]
 for r in candidates.itertuples(index=False):
  rid=str(r.target_source_record_id);e=emap.get(rid,{})
  oldreasons=json.loads(r.hold_reasons_json);reasons=list(oldreasons)
  source_path=str(e.get('source_path') or e.get('source_file') or '')
  expected=str(e.get('source_sha256') or '')
  raw_locator=str(e.get('source_locator') or '')
  sf=str(r.selected_source_file)
  local=ALIASES.get(sf)
  if local is None:
   q=Path(sf)
   local=q if q.is_absolute() else W/'settlements-raw'/sf
  exists=local.is_file();actual=sha(local) if exists else ''
  ev_asset_ok=bool(expected and actual and expected==actual)
  delivery_sha=dmap.get(sf);baseline_sha=bmap.get(sf)
  manifest_match=(delivery_sha==expected and bool(expected)) or (baseline_sha==expected and bool(expected))
  provenance_verified=bool(ev_asset_ok and source_path and expected and raw_locator)
  # Exact source_evidence raw hash and locator repair the prior null join to
  # the selected-file-only manifest. A printed workbook/PDF sheet is optional
  # when the frozen source-evidence locator names the exact row/page.
  if 'selected_source_asset_not_locally_verified_against_frozen_manifest' in reasons and provenance_verified:
   reasons.remove('selected_source_asset_not_locally_verified_against_frozen_manifest')
  if 'selected_source_sheet_or_row_locator_missing' in reasons and provenance_verified:
   reasons.remove('selected_source_sheet_or_row_locator_missing')
  identity_reasons=decode_reason_list(e.get('legacy_identity_reasons'))
  transition_only=(e.get('legacy_identity_conflict') is True and identity_reasons==['undocumented_type_transition'] and
                   e.get('legacy_same_year_collision') is False and e.get('is_federal_aggregate') is False and
                   e.get('is_additive_settlement_record') is True)
  if transition_only and 'source_evidence_hard_identity_collision_or_aggregate_hold' in reasons:
   reasons.remove('source_evidence_hard_identity_collision_or_aggregate_hold')
  # Preserve every other hard conflict, aggregate flag, point collision and prior quarantine.
  status='point_only_candidate_pending_independent_review' if not reasons else 'held_after_recovery'
  x={'source_record_id':rid,'target_year':int(r.target_year),'population':int(r.population),
     'settlement_name':r.settlement_name,'settlement_type':r.settlement_type,'region_norm':r.region_norm,
     'original_hold_reasons_json':r.hold_reasons_json,'remaining_hold_reasons_json':json.dumps(reasons,ensure_ascii=False),
     'legacy_identity_reasons_json':json.dumps(identity_reasons,ensure_ascii=False) if identity_reasons is not None else None,
     'legacy_identity_conflict':bool(e.get('legacy_identity_conflict',False)),
     'legacy_type_transition_only':bool(transition_only),
     'point_only_rule':'exact raw SQL/DBF code bridge + exact selected/historical name/type + unique selected/historical region-name-type + source evidence; does not decide temporal same-place identity',
     'selected_source_file_frozen':sf,'source_evidence_source_path_raw':source_path,'source_evidence_source_sha256_raw':expected or None,
     'source_evidence_locator_raw':raw_locator or None,'local_asset_resolved_path':str(local),'local_asset_exists':exists,
     'local_asset_sha256':actual or None,'source_evidence_hash_matches_local_asset':ev_asset_ok,
     'delivery_manifest_exact_path_sha256':delivery_sha,'baseline_manifest_exact_path_sha256':baseline_sha,
     'source_evidence_hash_matches_either_manifest':bool(manifest_match),
     'source_provenance_recovered':provenance_verified,
     'source_sheet_field_optional_for_point_rule':True,
     'point_collision_hold_preserved':bool(r.same_year_distinct_object_point_collision),
     'prior_target_specific_quarantine_preserved':'prior_target_specific_hard_quarantine' in oldreasons,
     'modern_point_continuity_admitted':False,'temporal_identity_admitted':False,'population_boundary_comparability_admitted':False,
     'recovery_status':status}
  outrows.append(x)
  assetrows.append({'source_record_id':rid,'selected_source_file_frozen':sf,'source_path_from_evidence':source_path,
    'source_sha256_from_evidence':expected,'source_locator_from_evidence':raw_locator,'local_asset_path':str(local),
    'local_asset_exists':exists,'local_asset_sha256':actual,'hash_verified':ev_asset_ok,
    'delivery_manifest_exact_path_sha256':delivery_sha,'baseline_manifest_exact_path_sha256':baseline_sha,
    'manifest_exact_path_match':bool(manifest_match),'source_provenance_recovered':provenance_verified})
  if not reasons:
   use={'target_source_record_id':rid,'target_year':int(r.target_year),'latitude':float(r.latitude),'longitude':float(r.longitude),
    'coordinate_quality':'2011_named_typed_historical_point_candidate_pending_review','coordinate_source':'Raw named typed GeoKLADR 2011 point under scoped exact code bridge; point-only retrospective use assumption',
    'coordinate_source_record_id':'GEOKLADR2011:'+str(r.geokladr_okato2011_raw),'coordinate_provider':'GeoKLADR 2011 raw DBF','coordinate_provider_id':'',
    'source_name':r.geokladr_name_raw,'source_type':r.geokladr_type_raw,'source_region':r.region_norm,'source_file':r.geokladr_dbf_file,
    'source_row':int(r.geokladr_record_1based),'source_sha256':r.geokladr_dbf_sha256,
    'source_locator':f'DBF_record_1based={int(r.geokladr_record_1based)};DBF_byte_offset_0based={int(r.geokladr_byte_offset_0based)};OKATO2011_raw={r.geokladr_okato2011_raw};KOD3_raw={r.geokladr_kod3_raw}',
    'coordinate_provenance':'2011 named typed point; no census-date measurement or population boundary equivalence asserted',
    'admission_rule':'old_census_typed_urban_code_bridge_point_only_recovery_candidate_v1','coordinate_admission_status':'staged_candidate_pending_independent_review',
    'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,'admission_allowed':False,
    'point_origin_file':r.geokladr_dbf_file,'point_origin_sha256':r.geokladr_dbf_sha256,'point_origin_locator':f'DBF_record_1based={int(r.geokladr_record_1based)};DBF_byte_offset_0based={int(r.geokladr_byte_offset_0based)};OKATO2011_raw={r.geokladr_okato2011_raw}',
    'point_origin_kind':'raw_named_typed_geo2011_object','historical_classifier2009_file':r.classifier_sql_file,'historical_classifier2009_sha256':r.classifier_sql_sha256,
    'historical_classifier2009_locator':f'line_1based={int(r.classifier_sql_line_1based)};OKATO2009_raw={r.classifier_okato2009_raw}',
    'source_record_lineage_json':json.dumps({'source_record_id':rid,'source_file':sf,'source_path':source_path,'source_sha256':expected,
       'source_locator':raw_locator,'local_verified_path':str(local),'local_sha256':actual},ensure_ascii=False),
    'coordinate_use_interpretation':'point association under exact same-year row/name/type/source-code structure only; no temporal same-place decision',
    'legacy_identity_hold_reason':json.dumps(identity_reasons,ensure_ascii=False) if identity_reasons is not None else None,
    'legacy_type_transition_does_not_decide_point_only_use':bool(transition_only),
    'modern_point_continuity_admitted':False,'population_scope_comparability_asserted':False}
   additional.append(use)
  assetrows[-1]['recovery_status']=status
 # Immutable hashes show the original stage is unchanged.
 out.mkdir(parents=True)
 df=pd.DataFrame(outrows); uses=pd.DataFrame(additional); assets=pd.DataFrame(assetrows)
 df.to_parquet(out/'recovery_hold_ledger.parquet',index=False)
 uses.to_parquet(out/'additional_point_only_staged_uses.parquet',index=False)
 assets.to_csv(out/'recovered_source_provenance.csv',index=False)
 df.sort_values(['population','source_record_id'],ascending=[False,True]).to_csv(out/'recovery_fixed_top100_sample.csv',index=False)
 reasons={}
 for v in df.remaining_hold_reasons_json:
  for reason in json.loads(v):reasons[reason]=reasons.get(reason,0)+1
 receipt={'status':'separate_point_only_recovery_candidates_no_admissions',
  'inputs':{str(p):sha(p) for p in [OLD/'historical_bridge_gate_ledger.parquet',OLD/'staged_point_uses.parquet',EVID,F/'input_manifest.parquet',BASE]},
  'prior_reviewed_stage_sha256_unchanged':sha(OLD/'staged_point_uses.parquet'),'recovery_candidates':len(df),
  'source_provenance_recovered_rows':int(df.source_provenance_recovered.sum()),
  'source_asset_local_hash_verified_rows':int(df.source_evidence_hash_matches_local_asset.sum()),
  'baseline_manifest_exact_path_matches':int(df.source_evidence_hash_matches_either_manifest.sum()),
  'point_only_pending_review_rows':len(uses),'point_only_pending_review_population':int(df.loc[df.recovery_status.eq('point_only_candidate_pending_independent_review'),'population'].sum()),
  'legacy_transition_only_rows':int(df.legacy_type_transition_only.sum()),
  'transition_only_point_candidates_pending_review':int((df.legacy_type_transition_only & df.recovery_status.eq('point_only_candidate_pending_independent_review')).sum()),
  'remaining_hold_reason_marginals_overlap':reasons,
  'by_year':df.groupby('target_year').agg(rows=('source_record_id','size'),point_only_pending_review=('recovery_status',lambda x:int(x.eq('point_only_candidate_pending_independent_review').sum())),population=('population','sum')).reset_index().to_dict('records'),
  'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()},
  'limitations':['This is a point-only association candidate layer; no temporal identity edge or modern-point continuity is proposed as admitted.','The 2011 point is not an exact census-date measurement and does not establish population boundary comparability.','Same-year shared-point collisions, explicit quarantines, dependency holds, administrative conflicts and unaccepted legacy associations remain blocked.','Source evidence SHA256 and row/page locator are retained as raw evidence; exact path presence in the prior baseline manifest is reported separately.']}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in receipt.items() if k not in ('inputs','outputs','limitations','remaining_hold_reason_marginals_overlap')},ensure_ascii=False))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=OLD/'recovery');main(ap.parse_args().output)
