"""Candidate-only native 2011 named-point recovery for already accepted census chains.

This does not add identity links or admit point uses. It stages direct source
points only where the accepted graph already contains an unambiguous 2002/2010/
2021 component, and where the existing raw historical named-point table has an
exact region/name/type match. The modern publisher row and native OKTMO are
retained as corroboration; Dadata/other-provider metadata is not used as a code.
"""
from __future__ import annotations
import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path
import pandas as pd
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_COORDINATE_STATUSES

ROOT=Path('/workspace')
SELECTED=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/accepted_identity_edges.parquet'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/accepted_point_uses.parquet'
HIST=ROOT/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
COVERAGE=ROOT/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/coverage.json'
CONFIG=ROOT/'russian-settlements-research/config/mass_joint_20261004.json'
BUILDER=ROOT/'russian-settlements-research/research_rebuild/mass_linkage/stage_named_native_point_full_chain_recovery_20261004.py'
QUARANTINE=ROOT/'settlements-work/continuation_20261004/R4/point_quarantine_scope_recovery_20261004/scoped_quarantine_dispositions.jsonl'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def is_true(value):
 return pd.notna(value) and bool(value)

def is_false(value):
 return pd.notna(value) and not bool(value)

def valid_point(lat,lon):
 try: return pd.notna(lat) and pd.notna(lon) and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
 except (TypeError,ValueError): return False

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--output',required=True,type=Path); a=ap.parse_args()
 if a.output.exists(): raise FileExistsError(f'Use a new immutable output path: {a.output}')
 a.output.mkdir(parents=True)
 s=pd.read_parquet(SELECTED,columns=['source_record_id','census_year','population','latitude','longitude','settlement_name','settlement_type','name_norm','type_norm','region_norm','population_scope','is_additive_settlement_record','entity_grain_status','oktmo','okato','source_native_id','source_file','source_sheet','source_row','source_sha256','source_locator','source_selection_component','population_value_quality'])
 if s.source_record_id.isna().any() or s.source_record_id.duplicated().any(): raise ValueError('Selected IDs must be unique/non-null')
 years=s.set_index('source_record_id').census_year.to_dict(); byid=s.set_index('source_record_id',drop=False)
 g=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','decision_status'])
 if not g.decision_status.isin(ACCEPTED_EDGE_STATUSES).all(): raise ValueError('Nonaccepted canonical identity decision status in baseline')
 # Union-find keeps only the current accepted graph; no candidate edge is ever added.
 parent={x:x for x in years}; rank={x:0 for x in years}
 def find(x):
  while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
  return x
 def union(x,y):
  x,y=find(x),find(y)
  if x==y:return
  if rank[x]<rank[y]:x,y=y,x
  parent[y]=x
  if rank[x]==rank[y]:rank[x]+=1
 for x,y in g[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
  if x not in parent or y not in parent: raise ValueError('Baseline graph endpoint outside selected layer')
  if years[x]==years[y]: raise ValueError('Baseline same-year edge')
  union(x,y)
 comps=defaultdict(list)
 for sid in years: comps[find(sid)].append(sid)
 for members in comps.values():
  component_years=[int(years[x]) for x in members]
  if len(component_years)!=len(set(component_years)): raise ValueError('Accepted graph component has duplicate census year')
 full={sid for members in comps.values() if {2002,2010,2021}.issubset({int(years[x]) for x in members}) for sid in members}
 full_components={sid:members for members in comps.values() if {2002,2010,2021}.issubset({int(years[x]) for x in members}) for sid in members}
 pts=pd.read_parquet(POINTS,columns=['target_source_record_id','coordinate_admission_status','latitude','longitude','coordinate_source','point_origin_file','point_origin_sha256','point_origin_locator'])
 if not pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all(): raise ValueError('Nonaccepted canonical coordinate status in baseline')
 if pts.target_source_record_id.duplicated().any(): raise ValueError('More than one current admitted point per source row')
 point_ids=set(pts.target_source_record_id); missing=full-point_ids
 h=pd.read_parquet(HIST,columns=['source_record_id','historical_named_point_candidate','historical_name_exact','historical_type_exact','historical_key_region_name_type_count','possible_unlocated_historical_competitor','historical_code_structure_compatible','historical_point_modern_region','historical_okato_2009_raw','historical_okato_2011_raw','name_raw_2009','name_raw_2011','name_key','geo_name_key','type_key_2009','type_key_2011','settlement_type_raw','latitude_from_lat','longitude_from_long','source_sha256_2009','source_sha256_2011','record_number_1based','record_byte_offset_0based','historical_okato','code_join_basis'])
 h=h[h.source_record_id.isin(missing)].copy()
 if h.source_record_id.duplicated().any(): raise ValueError('Historical named candidate table has duplicate selected IDs')
 # Count literal native OKTMO keys on all currently selected 2021 rows. Do not
 # substitute provider OKATO, Dadata, or inherited legacy identifiers.
 cur=s[s.census_year.eq(2021)].copy()
 cur['native_oktmo_count']=cur.groupby('oktmo',dropna=False).source_record_id.transform('size')
 current_by_component={}
 for root,members in comps.items():
  modern=[sid for sid in members if years[sid]==2021]
  if len(modern)==1: current_by_component[root]=modern[0]
 # Preserve any old point quarantine disposition; the new historical point is a
 # distinct origin and no provider identifier binding is asserted.
 quarantine={}
 if QUARANTINE.exists():
  for line in QUARANTINE.open():
   d=json.loads(line); sid=d.get('source_record_id')
   if sid: quarantine[sid]=d
 hmap=h.set_index('source_record_id',drop=False)
 curmap=cur.set_index('source_record_id',drop=False)
 proposals=[]; holds=[]
 aggregates={'full_chain_missing_point_rows':len(missing),'full_chain_missing_population_by_year':{}}
 for y in (2002,2010,2021):
  ids_y=[sid for sid in missing if years[sid]==y]
  aggregates['full_chain_missing_population_by_year'][str(y)]=int(byid.loc[ids_y,'population'].fillna(0).sum())
 for sid in sorted(missing):
  row=byid.loc[sid]; reasons=[]; root=find(sid); comp=full_components[sid]
  if sid not in hmap.index: reasons.append('no_existing_historical_named_point_row')
  else:
   hr=hmap.loc[sid]
   if not is_true(hr.historical_named_point_candidate): reasons.append('historical_named_point_candidate_flag_not_true')
   if not is_true(hr.historical_name_exact): reasons.append('historical_name_not_exact')
   if not is_true(hr.historical_type_exact): reasons.append('historical_type_or_code_structure_not_exact')
   if (pd.isna(hr.historical_key_region_name_type_count) or int(hr.historical_key_region_name_type_count)!=1): reasons.append('historical_whole_region_name_type_key_not_unique')
   if not is_false(hr.possible_unlocated_historical_competitor): reasons.append('unlocated_historical_competitor_possible')
   if not is_true(hr.historical_code_structure_compatible): reasons.append('historical_native_code_structure_unresolved')
   if not valid_point(hr.latitude_from_lat,hr.longitude_from_long): reasons.append('historical_raw_point_invalid_or_missing')
   if str(row.region_norm)!=str(hr.historical_point_modern_region): reasons.append('selected_region_differs_from_historical_point_region')
   if str(row.name_norm)!=str(hr.name_key) or str(row.type_norm)!=str(hr.type_key_2009): reasons.append('target_source_name_or_type_differs_from_historical_key')
  modern_id=current_by_component.get(root)
  if not modern_id: reasons.append('component_does_not_have_exactly_one_2021_row')
  else:
   mr=curmap.loc[modern_id]
   if not is_true(mr.is_additive_settlement_record): reasons.append('current_publisher_row_not_additive')
   if mr.population_scope not in ('settlement','populated_place','naselenniy_punkt'): reasons.append('current_publisher_scope_not_proper_settlement')
   if pd.isna(mr.oktmo) or str(mr.oktmo).strip()=='' or int(mr.native_oktmo_count)!=1: reasons.append('current_publisher_native_oktmo_missing_or_nonunique')
   if str(mr.region_norm)!=str(row.region_norm): reasons.append('current_full_chain_province_mismatch')
   if str(mr.name_norm)!=str(row.name_norm) or str(mr.type_norm)!=str(row.type_norm): reasons.append('current_modern_name_or_type_differs_from_point_target')
  if reasons:
   # Keep bounded holds for high-population records and every historical point row.
   if row.population is not None and float(row.population)>=5000: holds.append({'source_record_id':sid,'year':int(row.census_year),'population':int(row.population),'name':row.settlement_name,'type':row.settlement_type,'reasons':';'.join(reasons)})
   continue
  hr=hmap.loc[sid]; mr=curmap.loc[modern_id]
  q=quarantine.get(sid) or quarantine.get(modern_id) or {}
  hold_scope=q.get('hold_scope')
  proposals.append({
   'point_use_candidate_id':f'native2011-fullchain:{sid}', 'target_source_record_id':sid,
   'census_year':int(row.census_year),'population':int(row.population) if pd.notna(row.population) else None,
   'settlement_name':row.settlement_name,'settlement_type':row.settlement_type,'region_norm':row.region_norm,
   'latitude':float(hr.latitude_from_lat),'longitude':float(hr.longitude_from_long),
   'point_origin_file':'geokladr_okato_2011_raw_parsed.parquet; raw asset geokladr_okato_2011/okato.dbf',
   'point_origin_sha256':str(hr.source_sha256_2011),'point_origin_locator':f"DBF record {int(hr.record_number_1based)}; byte offset {int(hr.record_byte_offset_0based)}",
   'raw_historical_OKATO_2009':str(hr.historical_okato_2009_raw),'raw_historical_OKATO_2011':str(hr.historical_okato_2011_raw),
   'raw_historical_name_2009':hr.name_raw_2009,'raw_historical_name_2011':hr.name_raw_2011,
   'raw_historical_type_2011':hr.settlement_type_raw,'raw_historical_point_region':hr.historical_point_modern_region,
   'historical_name_exact':bool(hr.historical_name_exact),'historical_type_exact':bool(hr.historical_type_exact),
   'historical_whole_region_name_type_count':int(hr.historical_key_region_name_type_count),
   'historical_code_join_basis':str(hr.code_join_basis),
   'modern_current_source_record_id':modern_id,'modern_current_name':mr.settlement_name,'modern_current_type':mr.settlement_type,
   'modern_current_region':mr.region_norm,'modern_current_OKTMO_literal':str(mr.oktmo),
   'modern_source_file':mr.source_file,'modern_source_sheet':mr.source_sheet,'modern_source_row':mr.source_row,
   'modern_source_locator':mr.source_locator,'modern_source_native_id':mr.source_native_id,
   'modern_source_sha256':mr.source_sha256,'modern_code_is_source_native_OKTMO':True,'modern_OKTMO_unique_in_2021_selected':True,
   'existing_identity_support':'current accepted graph component already contains exactly one row in each of 2002, 2010, 2021; no new identity edge proposed',
   'same_place_inference':'native 2011 named typed physical point attached by exact source region/name/type key; point use across census row is a continuity inference, not an exact census-date measurement',
   'boundary_population_comparability_asserted':False,'provider_identifier_binding_asserted':False,
   'existing_point_quarantine_hold_scope_preserved':hold_scope,
   'quarantine_resolution_basis':'independent raw named typed 2011 GeoKLADR point; no external provider ID binding claimed' if hold_scope else None,
   'decision_status':'candidate_requires_independent_review','coordinate_admission_status':None,
   'candidate_only':True})
 out=pd.DataFrame(proposals)
 out.to_csv(a.output/'staged_point_use_candidates.csv',index=False)
 pd.DataFrame(holds).to_csv(a.output/'large_holds.csv',index=False)
 # Per-year conditional increment is point-only: every target is already in an
 # accepted full graph component. It is not an admission or a post-review claim.
 yr=[]
 for y in (2002,2010,2021):
  z=out[out.census_year.eq(y)] if len(out) else out
  yr.append({'year':y,'candidate_rows':len(z),'conditional_joint_population_gain':int(z.population.fillna(0).sum()),'population_is_recorded_observation_not_boundary_harmonized':True})
 receipt={'status':'candidate_only_no_admissions','rule':'exact existing historical named typed point + exact current proper publisher row and unique native OKTMO + already accepted full three-census graph component',
  'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SELECTED,GRAPH,POINTS,HIST,COVERAGE,QUARANTINE,CONFIG,BUILDER]},
  'baseline_coverage_sha256':sha(COVERAGE),'baseline_joint_full_chain':{str(x['year']):x['axes']['joint_admitted_coordinate_and_full_chain'] for x in json.loads(COVERAGE.read_text())['census_metrics']},
  'baseline_identity_graph':json.loads(COVERAGE.read_text())['identity_graph'],
  'full_chain_missing':aggregates,'staged_candidate_points':len(out),'conditional_point_only_joint_gain_by_year':yr,
  'outputs':{f.name:sha(f) for f in a.output.iterdir() if f.is_file()},
  'limitations':['No identity edges or point admissions are made.','Historical and modern point continuity is an ordinary stable-place assumption subject to review; coordinates are not exact census-date measurements.','The selected modern source OKTMO is retained literally and not compared to Dadata OKATO/provider code.','Candidate rows retain historical record hashes and byte locators; point quarantine flags are not erased.']}
 (a.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'output':str(a.output),'missing_full_chain_rows':len(missing),'candidates':len(out),'by_year':yr,'held_large':len(holds)},ensure_ascii=False))
if __name__=='__main__': main()
