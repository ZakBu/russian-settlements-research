"""Stage reviewed-rule current-provider points for 2021 noncity census rows.

The application verifies the entire frozen candidate set against the raw source,
selected R2 observations, historical code rows, and whole-set exception evidence.
It creates candidate/staging artifacts only; it does not mutate accepted ledgers.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import pandas as pd
from research_rebuild.mass_linkage.coordinate_ledger import norm, typekey
from research_rebuild.mass_linkage.modern_historical_point_candidates import compatible_type

W=Path('/workspace')
CAND=W/'settlements-work/coordinates/modern_historical_noncity_v1/new_point_candidates.parquet'
REVIEW=W/'settlements-work/coordinates/modern_noncity_review_v1/review.json'
ADDENDUM=W/'settlements-work/coordinates/modern_noncity_review_v1/audit_addendum_20261003.md'
RAW=W/'settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
SELECTED=W/'settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet'
R2_MANIFEST=SELECTED.parent/'release_manifest.json'
EVIDENCE=W/'settlements-work/candidates/optimized_run/source_evidence.parquet'
REGION=W/'settlements-work/coordinates/region_screen_v1/region_point_screen.parquet'
EVENTS=W/'settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json'
RAW09=W/'settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet'
RAW11=W/'settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet'
OUT=W/'settlements-work/coordinates/modern_noncity_application_v2'
RAW_SHA='86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'
R2_SHA='524e706daa32a69cac9b3e67b3bb8f9113fe2d851f10cdf42e93ba4efa5d72bf'
GEO09_SHA='343c0f5af1f52b9276699d9fe8d883b58def5aeabdd904063389606d29bc2b81'
GEO11_SHA='c778b841d22a65ac01a8658957044b66390bc32fe7f095cb2ca38489858ce17f'
HOLD_IDS={
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46749':'provider_settlement_fias_value_duplicate',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:8403':'provider_settlement_fias_value_duplicate',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:88635':'provider_settlement_fias_value_duplicate',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:162104':'source_grain_settlement_shared_okato_review',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46570':'border_near_or_simplification_uncertain',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:108423':'native_oktmo_linked_lineage_coverage_event',
}
POINT_COLS=['target_source_record_id','target_year','latitude','longitude','coordinate_quality','coordinate_source',
'coordinate_source_record_id','coordinate_provider','coordinate_provider_id','source_name','source_type','source_region',
'source_file','source_row','source_sha256','source_locator','coordinate_provenance','admission_rule','provider_binding_status',
'provider_fias_binding_status','coordinate_admission_status','coordinate_measurement_date_unknown','boundary_comparability_asserted',
'coordinate_provider_family','source_oktmo_raw','source_okato_raw','provider_query_receipt_missing','coordinate_uncertainty_flags_json',
'admission_allowed',
'point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_claim_artifact_file','point_claim_artifact_sha256']


def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def txt(v:Any)->str:
 if v is None or pd.isna(v):return ''
 return str(v).strip()
def norm_text(v:Any)->str:
 return norm(v)
def num(v:Any):
 try:
  x=float(v); return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None
def same_num(a,b):
 x,y=num(a),num(b);return x is not None and y is not None and x==y
def valid_pt(a,b):
 x,y=num(a),num(b);return x is not None and y is not None and -90<=x<=90 and -180<=y<=180
def code_match(provider, historical, numeric_allowed):
 p,h=txt(provider),txt(historical)
 if not p or not h:return False
 if p==h:return True
 if not numeric_allowed or not re.fullmatch(r'\d+\.0+',p) or not re.fullmatch(r'\d+',h):return False
 return int(p.split('.')[0])==int(h)
def source_evidence_conflicts(ev):
 if ev is None:return ['missing_2021_source_evidence']
 out=[]
 if ev.get('legacy_identity_conflict') or ev.get('legacy_same_year_collision'):out.append('source_evidence_identity_conflict_or_collision')
 if ev.get('is_federal_aggregate') or not ev.get('is_additive_settlement_record'):out.append('source_evidence_not_additive_physical_row')
 return out
def raw_object_level_conflicts(level):
 return [] if txt(level)=='Населенный пункт' else ['raw_2021_wrong_object_level']
def parse_event_codes(events):
 by_code=defaultdict(list)
 for e in events:
  for key,val in e.items():
   if 'settlement_id' not in key or not val:continue
   m=re.fullmatch(r'RU-OKTMO-(\d+)',str(val))
   if m:by_code[m.group(1)].append(str(e.get('event_id') or 'event_without_id'))
 return by_code

def apply(out:Path=OUT)->dict[str,Any]:
 out=Path(out)
 if out.exists() and any(out.iterdir()):raise FileExistsError(f'output directory not empty: {out}')
 review=json.loads(REVIEW.read_text())
 expected=review['evidence_checksums']
 paths={'candidate':CAND,'raw2021':RAW,'raw2009':RAW09,'raw2011':RAW11,'region':REGION,'events':EVENTS,'source_evidence':EVIDENCE}
 for key,path in paths.items():
  pin_key={'candidate':'new_point_candidates','raw2021':'raw_2021_source','raw2009':'raw_2009_classifier','raw2011':'raw_2011_geokladr','region':'region_screen','events':'lineage_events','source_evidence':'legacy_source_evidence'}[key]
  got=sha(path)
  if got!=expected[pin_key]['sha256']:raise ValueError(f'{pin_key} SHA mismatch: {got}')
 raw_sha=sha(RAW)
 if raw_sha!=RAW_SHA:raise ValueError(f'2021 raw source SHA mismatch {raw_sha}')
 selected_sha=sha(SELECTED)
 if selected_sha!=R2_SHA:raise ValueError(f'R2 selected observations SHA mismatch {selected_sha}')
 rm=json.loads(R2_MANIFEST.read_text())
 if rm.get('outputs',{}).get('selected_observations.parquet',{}).get('sha256')!=selected_sha:raise ValueError('R2 manifest selected file hash mismatch')
 cand=pd.read_parquet(CAND)
 if len(cand)!=13772 or cand.source_record_id.astype(str).duplicated().any():raise ValueError('candidate set row count/key uniqueness differs from frozen rule')
 # Pin the exact supporting artifacts. Load only the fields needed for checks.
 selected=pd.read_parquet(SELECTED)
 selected_by={str(r.source_record_id):r for r in selected[selected.census_year.eq(2021)].itertuples(index=False)}
 evid=pd.read_parquet(EVIDENCE,columns=['source_record_id','census_year','source_evidence_json'])
 evid=evid[evid.census_year.eq(2021)]; evid_by={str(r.source_record_id):json.loads(r.source_evidence_json) for r in evid.itertuples(index=False)}
 reg=pd.read_parquet(REGION); reg=reg[reg.source_record_id.isin(cand.source_record_id)];reg_by={str(r.source_record_id):r for r in reg.itertuples(index=False)}
 # Raw frame verification: exact row IDs and all claimed source/provider fields.
 raw=pd.read_parquet(RAW,columns=['object_level','object_name','oktmo','population','settlement_fias_id_dadata','fias_level_dadata',
 'settlement_dadata','settlement_type_full_dadata','latitude_dadata','longitude_dadata','okato_dadata'])
 fias_counts=raw.settlement_fias_id_dadata.dropna().astype(str).value_counts().to_dict()
 point_counts=raw.dropna(subset=['latitude_dadata','longitude_dadata']).groupby(['latitude_dadata','longitude_dadata'],dropna=False).size().to_dict()
 d09=pd.read_parquet(RAW09,columns=['historical_okato','source_line_1based'])
 d09_by={int(r.source_line_1based):txt(r.historical_okato) for r in d09.itertuples(index=False)}
 d11=pd.read_parquet(RAW11,columns=['historical_okato','record_number_1based','record_byte_offset_0based'])
 d11_by={int(r.record_number_1based):(int(r.record_byte_offset_0based),txt(r.historical_okato)) for r in d11.itertuples(index=False)}
 events=json.loads(EVENTS.read_text()); event_by_code=parse_event_codes(events)
 hold_reasons={rid:[reason] for rid,reason in HOLD_IDS.items()}
 ledger=[]; staged=[]
 for r in cand.itertuples(index=False):
  rid=txt(r.source_record_id); reasons=list(hold_reasons.get(rid,[]))
  try: n=int(rid.rsplit(':',1)[1])
  except Exception: n=-1; reasons.append('source_record_id_row_locator_malformed')
  if n<1 or n>len(raw): reasons.append('raw_2021_source_row_out_of_range'); rr=None
  else: rr=raw.iloc[n-1]
  if rr is not None:
   if int(num(r.source_row) or -1)!=n: reasons.append('candidate_source_row_disagrees_with_record_id')
   if not same_num(r.population,rr.population): reasons.append('raw_2021_population_mismatch')
   if txt(r.oktmo)!=txt(rr.oktmo): reasons.append('raw_2021_native_oktmo_mismatch')
   reasons.extend(raw_object_level_conflicts(rr.object_level))
   if not bool(r.source_object_is_naselenniy_punkt): reasons.append('candidate_object_level_flag_disagrees')
   if not txt(rr.object_name).lower().startswith(('село ','деревня ','станица ','хутор ','рабочий поселок ','поселок ','посёлок ','аул ','улус ','разъезд ','станция ','починок ','слобода ','пгт ')):
    # Explicit object_level and provider type remain primary; retain evidence if
    # the source name uses an uncommon but valid physical-settlement prefix.
    if not txt(rr.object_name): reasons.append('raw_2021_source_object_name_missing')
   if not same_num(r.provider_latitude,rr.latitude_dadata) or not same_num(r.provider_longitude,rr.longitude_dadata): reasons.append('raw_current_provider_point_mismatch')
   if not valid_pt(rr.latitude_dadata,rr.longitude_dadata): reasons.append('current_provider_point_invalid')
   if txt(r.provider_general_fias_id)!=txt(rr.settlement_fias_id_dadata): reasons.append('provider_settlement_fias_id_raw_mismatch')
   if txt(rr.fias_level_dadata)!='6' or txt(r.provider_fias_level)!='6': reasons.append('provider_fias_level_not_6')
   if txt(rr.settlement_dadata)!=txt(r.provider_settlement_name) or norm_text(r.provider_settlement_name)!=norm_text(r.settlement_name): reasons.append('provider_own_name_mismatch')
   if txt(rr.settlement_type_full_dadata)!=txt(r.provider_settlement_type_full): reasons.append('raw_provider_type_mismatch')
   if not compatible_type(r.settlement_type,rr.settlement_type_full_dadata): reasons.append('source_provider_type_disagreement')
   fid=txt(rr.settlement_fias_id_dadata)
   if not fid or int(fias_counts.get(fid,0))!=1: reasons.append('provider_settlement_fias_identifier_not_unique_in_raw_frame')
   coord=(num(rr.latitude_dadata),num(rr.longitude_dadata))
   if not coord[0] is None and int(point_counts.get(coord,0))!=1: reasons.append('provider_point_not_unique_in_raw_frame')
   if not code_match(rr.okato_dadata,r.historical_okato_2011_raw,bool(r.modern_numeric_provider_code_agrees_historical_code)):
    reasons.append('provider_okato_not_exact_or_reviewed_numeric_serialization_match')
   if txt(r.historical_okato)!=txt(r.historical_okato_2011_raw): reasons.append('canonical_historical_code_differs_from_2011_object_code')
  line09=int(num(r.source_line_1based) or -1)
  if d09_by.get(line09)!=txt(r.historical_okato_2009_raw): reasons.append('raw_2009_classifier_code_or_locator_mismatch')
  rec11=int(num(r.record_number_1based) or -1)
  geo11=d11_by.get(rec11)
  if geo11 is None or geo11[0]!=int(num(r.record_byte_offset_0based) or -1) or geo11[1]!=txt(r.historical_okato_2011_raw):
   reasons.append('raw_2011_geokladr_code_or_locator_mismatch')
  sel=selected_by.get(rid)
  if sel is None: reasons.append('missing_selected_r2_2021_observation')
  else:
   for col,rv in [('settlement_name',r.settlement_name),('settlement_type',r.settlement_type),('oktmo',r.oktmo),('okato',r.okato)]:
    if txt(getattr(sel,col))!=txt(rv):reasons.append('selected_r2_'+col+'_mismatch');break
   if not same_num(sel.population,r.population):reasons.append('selected_r2_population_mismatch')
   if int(num(sel.source_row) or -1)!=n:reasons.append('selected_r2_source_row_mismatch')
  ev=evid_by.get(rid)
  reasons.extend(source_evidence_conflicts(ev))
  if ev is not None:
   if txt(ev.get('source_record_id'))!=rid or int(ev.get('census_year') or 0)!=2021: reasons.append('source_evidence_record_key_mismatch')
   if txt(ev.get('legacy_verified_successor_settlement_id')) and rid not in HOLD_IDS:
    successor=txt(ev.get('legacy_verified_successor_settlement_id')).removeprefix('RU-OKTMO-')
    if successor in event_by_code: reasons.append('source_successor_has_lineage_event')
   grain=txt(ev.get('entity_grain_status'))
   if grain and ('shared' in grain.lower() or 'aggregate' in grain.lower() or 'parent' in grain.lower()): reasons.append('source_evidence_grain_exception')
  grain=txt(r.entity_grain_status)
  if grain and ('shared' in grain.lower() or 'aggregate' in grain.lower() or 'parent' in grain.lower()): reasons.append('source_grain_exception')
  if not bool(r.is_additive_settlement_record) or bool(r.source_is_aggregate_scope): reasons.append('source_not_explicit_physical_additive_record')
  if not bool(r.proposed_rule_pass) or not bool(r.provider_own_name_matches_source) or not bool(r.provider_type_compatible_with_source): reasons.append('frozen_rule_predicates_failed')
  if not bool(r.historical_name_exact) or not bool(r.historical_type_exact) or int(num(r.historical_key_region_name_type_count) or 0)!=1 or bool(r.possible_unlocated_historical_competitor): reasons.append('historical_named_code_object_not_unique')
  if txt(r.historical_point_modern_region)!=txt(r.region_norm): reasons.append('historical_point_not_in_expected_modern_region')
  if txt(r.provider_settlement_fias_duplicate_count) not in ('1','1.0') or txt(r.provider_general_fias_duplicate_count) not in ('1','1.0'): reasons.append('provider_identifier_collision_flag')
  if not bool(r.provider_coordinate_duplicate_count==1): reasons.append('provider_point_duplicate_flag')
  rs=reg_by.get(rid)
  if rs is None: reasons.append('missing_region_point_screen')
  elif txt(rs.region_screen_status)!='inside_expected_modern_region' or not bool(rs.point_valid_wgs84): reasons.append('region_point_exception')
  # Native current OKTMO is compared as a complete exact string; no padding or
  # transformation is used to connect it to historical OKATO.
  native=txt(r.oktmo)
  if native in event_by_code and rid not in HOLD_IDS: reasons.append('native_oktmo_linked_lineage_event')
  reasons=list(dict.fromkeys(reasons))
  item={'source_record_id':rid,'candidate_rule':'reviewed_modern_noncity_current_provider_point_v1',
        'candidate_status':'held' if reasons else 'eligible_staged_pending_root_review',
        'hold_reasons_json':json.dumps(reasons,ensure_ascii=False), 'admission_allowed':False,
        'point_origin_file':str(RAW),'point_origin_sha256':raw_sha,
        'point_origin_locator':f'parquet_row_1based={n};latitude_dadata,longitude_dadata',
        'point_origin_kind':'tochno_2021_dadata_raw_parquet_point',
        'historical_code_2009':txt(r.historical_okato_2009_raw),'historical_code_2011':txt(r.historical_okato_2011_raw),
        'native_2021_oktmo':native,'provider_okato_raw':txt(r.raw_okato_dadata),
        'region_screen_status':txt(rs.region_screen_status) if rs is not None else '',
        'source_evidence_identity_conflict':bool(ev.get('legacy_identity_conflict')) if ev else None}
  ledger.append(item)
  if reasons:continue
  srcfile=txt(r.source_file)
  point={
   'target_source_record_id':rid,'target_year':2021,'latitude':float(r.provider_latitude),'longitude':float(r.provider_longitude),
   'coordinate_quality':'reviewed modern representative point; staged application',
   'coordinate_source':'tochno_dadata','coordinate_source_record_id':rid,'coordinate_provider':'tochno_dadata',
   'coordinate_provider_id':txt(r.provider_general_fias_id),
   'source_name':txt(r.provider_settlement_name),'source_type':txt(r.provider_settlement_type_full),
   'source_region':txt(sel.region_raw),'source_file':srcfile,'source_row':float(n),'source_sha256':raw_sha,
   'source_locator':f'{srcfile}#:row_1based={n}',
   'coordinate_provenance':'Current DaData/Tochno 2021 source-row point; exact raw row, native source code, own name/type, unique provider ID/point, and reviewed historical corroboration checked; source query/measurement date unavailable.',
   'admission_rule':'modern_noncity_review_v1_addendum_automatic_2021_source_row_to_current_point',
   'provider_binding_status':'reviewed noncity point rule staged; current provider point association only',
   'provider_fias_binding_status':'provider-reported FIAS identifier preserved; official FIAS identity binding not asserted',
   'coordinate_admission_status':'staged_candidate_pending_root_review','coordinate_measurement_date_unknown':True,
   'boundary_comparability_asserted':False,'coordinate_provider_family':'tochno_dadata',
   'source_oktmo_raw':txt(r.oktmo),'source_okato_raw':txt(r.raw_okato_dadata),'provider_query_receipt_missing':True,
   'coordinate_uncertainty_flags_json':json.dumps(['provider_query_receipt_and_measurement_date_missing_soft_provenance'],ensure_ascii=False),
   'admission_allowed':False,
   'point_origin_file':str(RAW),'point_origin_sha256':raw_sha,
   'point_origin_locator':f'parquet_row_1based={n};latitude_dadata,longitude_dadata',
   'point_origin_kind':'tochno_2021_dadata_raw_parquet_point',
   'point_claim_artifact_file':str(RAW),'point_claim_artifact_sha256':raw_sha,
  }
  staged.append(point)
 # Preserve identical accepted-modern schema and canonical origin extension.
 pointdf=pd.DataFrame(staged,columns=POINT_COLS)
 ledgerdf=pd.DataFrame(ledger)
 out.mkdir(parents=True,exist_ok=True)
 ppoint=out/'staged_point_uses.parquet'; pledger=out/'candidate_ledger.parquet'
 pointdf.to_parquet(ppoint,index=False); ledgerdf.to_parquet(pledger,index=False)
 receipt={'status':'reviewed_modern_noncity_points_staged_pending_root_review','review_id':review['review_id'],
  'rule_scope':'2021 census source row to current provider point only; no historical continuity, official FIAS identity, point accuracy, or population/boundary claim',
  'inputs':{str(k):{'path':str(p),'sha256':sha(p)} for k,p in {'review':REVIEW,'addendum':ADDENDUM,'candidates':CAND,'raw_2021':RAW,'selected_r2':SELECTED,'source_evidence':EVIDENCE,'region_screen':REGION,'lineage_events':EVENTS,'raw_2009':RAW09,'raw_2011':RAW11}.items()},
  'candidate_count':len(cand),'eligible_staged_count':len(pointdf),'held_count':len(ledgerdf)-len(pointdf),
  'hold_reasons':dict(Counter(reason for s in ledgerdf.hold_reasons_json for reason in json.loads(s) if reason in set(HOLD_IDS.values()) or reason not in {'source_record_id_row_locator_malformed'})),
  'six_frozen_review_holds':HOLD_IDS,'checks':{'raw_2021_source_row_point_population_native_oktmo_provider_fields_exact':True,
   'selected_r2_2021_observation_exact':True,'raw_2009_and_2011_historical_code_rows_checked':True,
   'provider_fias_id_and_point_uniqueness_checked_against_raw_frame':True,'source_evidence_region_events_scanned':True,
   'all_staged_rows_admission_allowed_false':bool(not pointdf.admission_allowed.any())},
  'by_family':{'reviewed_modern_noncity_current_provider_point_v1':int(len(pointdf))},
  'artifacts':{'staged_point_uses':{'path':str(ppoint),'sha256':sha(ppoint),'rows':len(pointdf)},
   'candidate_ledger':{'path':str(pledger),'sha256':sha(pledger),'rows':len(ledgerdf)}},
  'limits':['The current provider point is assigned to the 2021 source locality row under the reviewed rule only.',
   'Historical OKATO/name/type and 2011 point are corroborating evidence, not the assigned coordinate.',
   'Native 2021 OKTMO is retained exactly and never padded or translated.',
   'Provider-reported FIAS identifier is retained, but official FIAS identity binding is unknown.',
   'No historical point continuity, boundary comparability, population comparability, or coordinate accuracy claim is made.',
   'Missing provider query receipt and measurement date are provenance limitations, not standalone vetoes.']}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 return receipt

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=OUT);a=ap.parse_args();print(json.dumps(apply(a.out),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
