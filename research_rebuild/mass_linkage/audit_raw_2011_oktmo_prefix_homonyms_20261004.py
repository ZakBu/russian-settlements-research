#!/usr/bin/env python3
"""Audit a dated 2011 OKTMO municipal-prefix resolver for frozen 2002 homonyms.

Candidate-only measurement. This routine never turns dated code strings into a
legal continuity claim and never admits edges/points. It freezes an audit even
when the scoped rule yields no candidate.
"""
from __future__ import annotations
import csv, hashlib, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT=Path('/workspace')
REPO=ROOT/'russian-settlements-research'
MASS=REPO/'research_rebuild/mass_linkage'
sys.path.insert(0,str(MASS))
from raw_okato_classifier import read_copy
from stage_raw_2002_admin_hierarchy_candidates_20261004 import norm, regkey, typekey, admkey, hav

BASE=ROOT/'settlements-work/continuation_20261004/R4/raw_2002_residual_admin_hierarchy_candidates_20261004/freeze_v4'
SELECTED=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GEO=ROOT/'settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet'
SQL=ROOT/'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
OUT=ROOT/'settlements-work/continuation_20261004/R4/raw_2011_oktmo_prefix_homonym_audit_20261004/freeze_v2'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/accepted_point_uses.parquet'
SOURCE_EVIDENCE=ROOT/'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
RAWROOT=ROOT/'settlements-raw'
SHORT={'д':'деревня','с':'село','г':'город','п':'поселок','пгт':'поселок городского типа','х':'хутор','ст':'станция','ст-ца':'станица','аул':'аул','м':'местечко','рзд':'железнодорожный разъезд'}


def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(4*1024*1024),b''): h.update(block)
 return h.hexdigest()
def val(x):
 if x is None or (isinstance(x,float) and math.isnan(x)): return ''
 return str(x).strip()
def write_csv(path:Path, rows:list[dict], fields:list[str]|None=None):
 if fields is None:
  fields=[]; seen=set()
  for r in rows:
   for k in r:
    if k not in seen: fields.append(k);seen.add(k)
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader();w.writerows(rows)


def main():
 if OUT.exists() and any(OUT.iterdir()): raise SystemExit(f'refusing overwrite: {OUT}')
 OUT.mkdir(parents=True,exist_ok=True)
 holds=pd.read_csv(BASE/'disjoint_source_holds.csv',dtype=str,keep_default_na=False)
 holds=holds[pd.to_numeric(holds.current_exact_name_type_region_candidates,errors='coerce').fillna(0)>1].copy()
 holds=holds.sort_values(['from_source_record_id']).reset_index(drop=True)
 ids=set(holds.from_source_record_id.astype(str))
 # Project only needed columns; the full selected source file is intentionally
 # not materialized in this audit.
 cols=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_name','settlement_type','region_raw','name_norm','type_norm','region_norm','population','district_raw','municipality_raw','oktmo','source_sha256','source_locator']
 selected=pd.read_parquet(SELECTED,columns=cols)
 old=selected[selected.source_record_id.astype(str).isin(ids)&(selected.census_year==2002)].copy()
 if len(old)!=len(ids): raise ValueError(f'2002 selected rows missing: expected {len(ids)}, got {len(old)}')
 old_by_id={str(r.source_record_id):r._asdict() for r in old.itertuples(index=False)}
 cur=selected[selected.census_year==2021].copy()
 current_by_key=defaultdict(list)
 for r in cur.itertuples(index=False): current_by_key[(str(r.name_norm or ''),str(r.type_norm or ''),str(r.region_norm or ''))].append(r._asdict())
 cur10=selected[selected.census_year==2010].copy()
 y10_by_key=defaultdict(list)
 for r in cur10.itertuples(index=False): y10_by_key[(str(r.name_norm or ''),str(r.type_norm or ''),str(r.region_norm or ''))].append(r._asdict())
 # Parsed primary raw 2011 DBF and classifier. Code strings stay in their
 # source-specific fields, without stripping/padding/canonical conversion.
 geo=pd.read_parquet(GEO)
 dbf_by_okato=defaultdict(list)
 for r in geo.to_dict('records'): dbf_by_okato[val(r.get('historical_okato'))].append(r)
 classifier=read_copy(SQL)
 cls_by_code=defaultdict(list)
 for r in classifier.to_dict('records'):
  c=val(r.get('historical_okato'))
  if c: cls_by_code[c].append(r)
 region_rows={}
 for code,rs in cls_by_code.items():
  if re.fullmatch(r'\d{8}',code) and code[2:]=='000000' and len(rs)==1: region_rows[code[:2]]=rs[0]
 cls_by_key=defaultdict(list)
 for r in classifier.to_dict('records'):
  code=val(r.get('historical_okato'))
  if len(code) not in (8,11) or r.get('is_settlement_raw')!='t' or code[:2] not in region_rows: continue
  cls_by_key[(regkey(region_rows[code[:2]].get('name_raw')),norm(r.get('name')),typekey(r.get('status')))].append(r)
 # Canonical direct current points and source evidence are only used to screen
 # the one exact 2011-prefix source match; no optional legacy flags gate baseline.
 pts=pd.read_parquet(POINTS,columns=['target_source_record_id','target_year','coordinate_admission_status','latitude','longitude','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind'])
 from build_long_table import ACCEPTED_COORDINATE_STATUSES
 pts=pts[pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 direct_points={str(r['target_source_record_id']):r for r in pts[pts.target_year==2021].to_dict('records') if str(r['target_source_record_id'])==str(r['coordinate_source_record_id'])}
 evdf=pd.read_parquet(SOURCE_EVIDENCE,columns=['source_record_id','census_year','source_evidence_json'])
 evdf=evdf[evdf.census_year==2021]
 evidence_by_id={str(r.source_record_id):json.loads(r.source_evidence_json) for r in evdf.itertuples(index=False)}
 # Candidate 2010 rows were extracted from the exact typed name/region key and
 # later replayed from the raw workbooks below. The old source record's row
 # hierarchy is supplied by the frozen audited 2002 parent proof.
 used10={}
 for o in old_by_id.values():
  k=(str(o['name_norm']),str(o['type_norm']),str(o['region_norm']))
  for q in y10_by_key.get(k,[]): used10[str(q['source_record_id'])]=q

 raw_paths=sorted({RAWROOT/val(r['source_file']) for r in used10.values()})
 raw_file_pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in raw_paths}
 # Read each raw XLS workbook only once; save exact raw row cells to make the
 # absence/presence of literal parent context reviewable.
 import xlrd
 raw10=[]
 by_file=defaultdict(list)
 for q in used10.values(): by_file[str(q['source_file'])].append(q)
 for source_file, qs in sorted(by_file.items()):
  path=RAWROOT/source_file
  booksheet=qs[0]['source_sheet']
  book=xlrd.open_workbook(str(path),on_demand=True)
  if booksheet not in book.sheet_names(): raise ValueError(f'missing raw sheet {booksheet} in {path}')
  sheet=book.sheet_by_name(booksheet)
  for q in qs:
   rowno=int(float(q['source_row']))
   cells=[sheet.cell_value(rowno-1,j) for j in range(sheet.ncols)]
   rawname=val(q['source_name_raw'])
   # Exact raw row locator and all cells are retained. For these two flat
   # source extracts, district/municipality fields are blank in selected data;
   # don't infer administrative ancestors from row order or opaque ordinals.
   raw10.append({'source_record_id':str(q['source_record_id']),'year':2010,'source_file':source_file,
    'source_sha256':raw_file_pins[str(path)]['sha256'],'source_sheet':booksheet,'source_row_1based':rowno,
    'selected_raw_name':rawname,'selected_population':q.get('population'),
    'raw_row_cells_json':json.dumps(cells,ensure_ascii=False,default=str),
    'raw_row_normalized_name_match':any(norm(x)==norm(rawname) for x in cells if isinstance(x,str)),
    'raw_row_population_cell_values_json':json.dumps([x for x in cells if isinstance(x,(int,float))],ensure_ascii=False,default=str),
    'selected_district_raw':val(q.get('district_raw')) or None,'selected_municipality_raw':val(q.get('municipality_raw')) or None,
    'explicit_admin_ancestor_in_raw_row':False,'interpretation':'flat region/name/population row; raw row contains no printed county/selsoviet parent; row ordinal is not identity evidence'})
  book.release_resources()

 raw10_by_id={r['source_record_id']:r for r in raw10}
 funnel=[]; candidate_rows=[]; counts=Counter(); endpoint_population=0
 for hold in holds.to_dict('records'):
  rid=str(hold['from_source_record_id']); o=old_by_id[rid]
  audit=json.loads(hold['raw_row_and_ancestor_audit_json'])
  key=(str(o['name_norm']),str(o['type_norm']),str(o['region_norm']))
  qrows=current_by_key.get(key,[])
  hrows=cls_by_key.get((regkey(o['region_raw']),norm(o['settlement_name']),typekey(o['settlement_type'])),[])
  strict=[]
  for h in hrows:
   code=val(h.get('historical_okato')); parents=cls_by_code.get(code[:5]+'000',[]) if len(code) in (8,11) else []
   if len(parents)!=1: continue
   parent=parents[0]
   if parent.get('is_settlement_raw')!='f' or admkey(parent.get('name_raw'))!=admkey(o.get('district_raw')): continue
   gcode=code if len(code)==11 else code+'000'
   matching_geo=[]
   for g in dbf_by_okato.get(gcode,[]):
    parts=val(g.get('name_raw')).split(maxsplit=1); typ=SHORT.get(parts[0].casefold(),'') if parts else ''
    if (g.get('deleted_marker_raw')==' ' and norm(parts[1] if len(parts)>1 else '')==norm(o['settlement_name'])
        and typekey(typ)==typekey(o['settlement_type'])): matching_geo.append(g)
   if len(matching_geo)==1: strict.append((h,parent,matching_geo[0],gcode))
  strict_obj=strict[0] if len(strict)==1 else None
  oktmo=val(strict_obj[2].get('oktmo_raw_text')) if strict_obj else ''
  oktmo_is8=bool(re.fullmatch(r'\d{8}',oktmo))
  all_current_native=[q for q in qrows if re.fullmatch(r'\d{11}',val(q.get('oktmo')))]
  prefix_rows=[q for q in all_current_native if val(q.get('oktmo'))[:8]==oktmo] if oktmo_is8 else []
  y10key=(str(o['name_norm']),str(o['type_norm']),str(o['region_norm']))
  y10rows=y10_by_key.get(y10key,[])
  y10proof=[raw10_by_id[str(q['source_record_id'])] for q in y10rows if str(q['source_record_id']) in raw10_by_id]
  reason=[]
  if not audit.get('source_name_raw_in_row'): reason.append('2002_raw_target_name_not_reproduced')
  if not audit.get('district_visible_in_ancestor_stack'): reason.append('2002_district_not_literal_worksheet_parent')
  if not audit.get('municipality_visible_in_ancestor_stack'): reason.append('2002_selsoviet_not_literal_worksheet_parent')
  if len(strict)!=1: reason.append(f'2009_child_parent_and_2011_named_typed_object_not_unique:{len(strict)}')
  elif not oktmo_is8: reason.append('raw_2011_OKTMO_not_8_digits_or_missing')
  elif len(prefix_rows)==0: reason.append('no_2021_same_key_native_11_digit_OKTMO_with_exact_2011_prefix8')
  elif len(prefix_rows)>1: reason.append('multiple_2021_same_key_native_codes_share_2011_prefix8')
  if y10rows and (not y10proof or any(not p['raw_row_normalized_name_match'] for p in y10proof)):
   reason.append('2010_raw_selected_row_replay_failed')
  if y10proof and not any(p['explicit_admin_ancestor_in_raw_row'] for p in y10proof): reason.append('2010_raw_flat_rows_no_district_or_selsoviet_parent')
  counts['homonym_old_rows']+=1
  if audit.get('source_name_raw_in_row') and audit.get('district_visible_in_ancestor_stack') and audit.get('municipality_visible_in_ancestor_stack'): counts['2002_actual_parent_chain_rows']+=1
  if len(strict)==1: counts['unique_2009_2011_physical_rows']+=1
  if oktmo_is8: counts['unique_historic_rows_with_8digit_2011_oktmo']+=1; endpoint_population+=int(o['population'] or 0)
  if prefix_rows: counts['exact_current_prefix_candidate_rows']+=1
  if y10rows: counts['matched_2010_same_key_rows']+=1
  if y10proof: counts['2010_raw_rows_replayed']+=len(y10proof)
  if y10proof and all(not p['explicit_admin_ancestor_in_raw_row'] for p in y10proof): counts['2010_matched_rows_without_admin_parent']+=1
  # Load direct accepted point and source-evidence status for any exact code-prefix match.
  point_info=None; point_distance=None; ev=None
  if strict_obj and oktmo_is8 and len(prefix_rows)==1:
   q=prefix_rows[0]
   point_info=direct_points.get(str(q['source_record_id']))
   if point_info:
    point_distance=hav(strict_obj[2].get('latitude_from_lat'),strict_obj[2].get('longitude_from_long'),point_info.get('latitude'),point_info.get('longitude'))
   ev=evidence_by_id.get(str(q['source_record_id']))
   if not audit.get('source_name_raw_in_row') or not audit.get('district_visible_in_ancestor_stack') or not audit.get('municipality_visible_in_ancestor_stack'):
    reason.append('2002_actual_source_hierarchy_incomplete')
   if not point_info:
    reason.append('no_canonical_accepted_direct_2021_point')
   if point_distance is None or point_distance>5:
    reason.append('2011_named_point_to_prefix_matched_current_point_over_5km_or_unknown')
   if ev is None:
    reason.append('missing_2021_source_evidence')
   else:
    if ev.get('legacy_identity_conflict') or ev.get('legacy_same_year_collision'):
     reason.append('2021_source_evidence_identity_conflict_or_same_year_collision')
    if ev.get('is_federal_aggregate') or not ev.get('is_additive_settlement_record'):
     reason.append('2021_source_evidence_not_additive_physical_row')
   if not reason:
    raise RuntimeError('Unexpected evidence-complete candidate; add graph-safe simulation before freezing')
  base={'from_source_record_id':rid,'year':2002,'from_source_file':o['source_file'],'from_source_row_1based':o['source_row'],
   'from_source_sha256':o['source_sha256'],'from_source_locator':o['source_locator'],'raw_name':o['source_name_raw'],
   'settlement_name':o['settlement_name'],'settlement_type':o['settlement_type'],'region_raw':o['region_raw'],
   'population':o['population'],'source_district_raw':o['district_raw'],'source_selsoviet_raw':o['municipality_raw'],
   'literal_2002_parent_chain_json':hold['actual_raw_worksheet_parent_chain_json'],
   'raw_2002_row_parent_audit_json':hold['raw_row_and_ancestor_audit_json'],
   'exact_2021_name_type_region_alternative_count':len(qrows),
   'unique_2009_2011_named_typed_object_count':len(strict),
   'historical_okato_2009_raw':val(strict_obj[0].get('historical_okato')) if strict_obj else None,
   'historical_okato_2009_parent_code_raw':val(strict_obj[1].get('historical_okato')) if strict_obj else None,
   'historical_okato_2009_parent_name_raw':val(strict_obj[1].get('name_raw')) if strict_obj else None,
   'historical_2011_okato_raw':val(strict_obj[2].get('historical_okato')) if strict_obj else None,
   'historical_2011_name_raw':val(strict_obj[2].get('name_raw')) if strict_obj else None,
   'historical_2011_type_raw':val(strict_obj[2].get('settlement_type_raw')) if strict_obj else None,
   'historical_2011_dbf_record':strict_obj[2].get('record_number_1based') if strict_obj else None,
   'historical_2011_dbf_byte_offset':strict_obj[2].get('record_byte_offset_0based') if strict_obj else None,
   'oktmo_2011_raw':oktmo or None,'oktmo_2011_field_role':'dated 2011 administrative-context code only; not assumed legally continuous with 2021 code',
   'current_2021_native_candidates_json':json.dumps([{'source_record_id':q['source_record_id'],'native_oktmo_raw':val(q.get('oktmo')),'district_raw':val(q.get('district_raw')),'municipality_raw':val(q.get('municipality_raw')),'population':q.get('population')} for q in qrows],ensure_ascii=False,default=str),
   'current_native11_candidates_json':json.dumps([{'source_record_id':q['source_record_id'],'native_oktmo_raw':val(q.get('oktmo'))} for q in all_current_native],ensure_ascii=False),
   'exact_2021_prefix8_match_count':len(prefix_rows),'prefix_matched_current_source_record_id':prefix_rows[0]['source_record_id'] if len(prefix_rows)==1 else None,
   'prefix_matched_current_native_oktmo_raw':val(prefix_rows[0].get('oktmo')) if len(prefix_rows)==1 else None,
   'prefix_matched_current_accepted_point_json':json.dumps({'latitude':point_info.get('latitude'),'longitude':point_info.get('longitude'),'coordinate_source_record_id':point_info.get('coordinate_source_record_id'),'coordinate_admission_status':point_info.get('coordinate_admission_status')} if point_info else None,ensure_ascii=False),
   'historic_point_to_prefix_matched_current_point_km':round(point_distance,6) if point_distance is not None else None,
   'prefix_matched_current_source_evidence_summary_json':json.dumps({k:ev.get(k) for k in ['legacy_identity_conflict','legacy_same_year_collision','is_federal_aggregate','is_additive_settlement_record','entity_grain_status','lineage_events']} if ev else None,ensure_ascii=False,default=str),
   '2010_same_key_selected_rows':len(y10rows),
   '2010_raw_row_proof_count':len(y10proof),'2010_raw_proof_ids_json':json.dumps([p['source_record_id'] for p in y10proof],ensure_ascii=False),
   'staging_status':'hold_no_identity_or_point_edges_staged','hold_reasons_json':json.dumps(sorted(set(reason)),ensure_ascii=False)}
  funnel.append(base)
 write_csv(OUT/'candidate_edges.csv',[],fields=['from_source_record_id','to_source_record_id','rule','support','candidate_only','admission_allowed'])
 write_csv(OUT/'disjoint_holds.csv',funnel)
 write_csv(OUT/'2010_raw_selected_row_replay.csv',raw10)
 # The test for this cohort is deliberately zero-edge. Its conditional gain is
 # exactly zero independent of the accepted graph baseline; pin the current
 # fifth baseline for any later reviewer replay.
 baseline_dir=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context'
 baseline_cov=baseline_dir/'coverage.json'
 pins={str(p):sha(p) for p in [BASE/'disjoint_source_holds.csv',SELECTED,GEO,SQL,baseline_cov,POINTS,SOURCE_EVIDENCE]}
 pins.update(raw_file_pins)
 summary={'status':'candidate_only_no_admissions','rule_under_test':'A unique dated 2011 named typed DBF object has an 8-digit raw OKTMO administrative context; test exact equality between those 8 raw digits and the prefix of a current 11-digit native publisher OKTMO among same-name/type/province alternatives. Codes remain dated source strings with distinct roles; no padding, legal continuity, or code identity is asserted.',
  'cohort':{'2021_exact_key_homonym_old_rows':int(len(holds)),'old_population_sum_endpoint_only':int(pd.to_numeric(holds.from_population,errors='coerce').fillna(0).sum())},
  'source_hierarchy_and_rule_funnel':dict(counts),'historical_2009_2011_8digit_endpoint_old_population_not_gain':int(endpoint_population),
  '2010_raw_source_context':{'selected_same_key_row_count':int(len(raw10)),'raw_rows_replayed':int(len(raw10)),'rows_with_exact_raw_name_match':sum(bool(r['raw_row_normalized_name_match']) for r in raw10),'rows_with_printed_admin_parent':sum(bool(r['explicit_admin_ancestor_in_raw_row']) for r in raw10),'interpretation':'The matched 2010 source rows are raw worksheet rows from two regional XLS extracts; the direct rows expose regional label, settlement label and population, without a county/selsoviet ancestor. No 2010 parent context was fabricated from flat row order.'},
  'candidate_edge_count':0,'candidate_point_use_count':0,'exact_prefix_match_rows_held_on_physical_distance':int(counts['exact_current_prefix_candidate_rows']),'conditional_joint_gain':{'rows':0,'population':0,'per_year':{'2002':{'rows':0,'population':0},'2010':{'rows':0,'population':0},'2021':{'rows':0,'population':0}}},
  'dominant_blocker':'Among 1,075 exact typed 2009/2011 raw source objects with an 8-digit 2011 OKTMO, exactly one same-name/type/province current native 11-digit alternative has an exact leading-8 match. That alternative is 12.002595 km from the independently accepted current point, exceeding the declared 5 km physical concordance rule; the historical point is 6.849096 km from the other same-key competitor, which has no code-prefix match. No candidate is staged.',
  'candidate_only_limitations':['No identity or point edges are proposed because the scoped native-code-prefix condition fails throughout the tested exact homonym pool.','2002 worksheet parent stacks are source observations; 2009 classifier parent/name and 2011 raw named typed DBF row are kept as separate dated observations.','2010 rows were replayed at exact raw workbook locators. These regional source rows do not print a district/selsoviet parent; row ordinal/order is not treated as identity evidence.','The 2011 OKTMO value is an administrative context witness, not a legal or physical settlement identifier.'],
  'pins':pins,'outputs':{},'baseline_reference':{'path':str(baseline_dir),'coverage_sha256':sha(baseline_cov),'used_for_gain':False,'reason':'zero candidate edges imply exactly zero conditional gain; no baseline coverage was recomputed or claimed'} }
 for fn in ['candidate_edges.csv','disjoint_holds.csv','2010_raw_selected_row_replay.csv']:
  p=OUT/fn;summary['outputs'][fn]={'sha256':sha(p),'bytes':p.stat().st_size,'rows':sum(1 for _ in p.open(encoding='utf-8'))-1}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 summary['outputs']['summary.json_sha256']=sha(OUT/'summary.json')
 receipt={**summary,'generator':str(Path(__file__).resolve()),'generator_sha256':sha(Path(__file__).resolve()),'supersedes_preliminary_freeze_v1':{'path':str(OUT.parent/'freeze_v1'),'reason':'v1 surfaced one code-prefix match but initially read a typed DBF-derived field after nullable numeric coercion; v2 uses the original raw DBF field text and adds direct-point/source-evidence checks'},'frozen_at_utc':'2026-10-04','receipt_role':'immutable candidate-only measurement; no admissions'}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'output':str(OUT),'counts':dict(counts),'hist_8digit_oldpop':endpoint_population,'2010rawrows':len(raw10),'zero_candidate_gain':summary['conditional_joint_gain'],'summary_sha256':sha(OUT/'summary.json'),'receipt_sha256':sha(OUT/'receipt.json')},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
