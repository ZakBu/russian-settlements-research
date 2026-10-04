#!/usr/bin/env python3
"""Apply the reviewed 834 raw-source point seeds and safe graph transfers.

Reuses the source-coordinate point construction/graph/source-evidence helpers
from the frozen 177-seed applier. GeoNames remains corroborating evidence only.
"""
from __future__ import annotations
import csv, hashlib, json, math, sys, time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
import pyarrow as pa, pyarrow.parquet as pq
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES
from research_rebuild.mass_linkage.propagate_continuation_points import load_source_evidence,read_blocked_targets,stage_point_use
from research_rebuild.mass_linkage.apply_reviewed_type_false_zero_177_source_points_20261004 import (
 sha,num,hav,components,comp_paths,raw_by_rows,hardflags,EXPECTED as SHARED_EXPECTED,
 RAW,GNZIP,SEL_COLS,POINT_COLS,GRAPH_COLS,
)
from research_rebuild.mass_linkage.apply_reviewed_current_point_retrospective_20261004 import cast_addition_to_schema

REVIEW=Path('/workspace/settlements-work/continuation_20261004/independent_review/admin_homonym_834_point_review')
BASE=Path('/workspace/settlements-work/continuation_20261004/root/accepted_type_false_zero_177_source_points')
GRAPH=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_ninth_reviewed_legacy202/accepted_identity_edges.parquet')
FROZEN=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
BLOCK=Path('/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json')
OUT=Path('/workspace/settlements-work/continuation_20261004/root/accepted_admin_homonym_834_source_points_scope_reconciled')
RECEIPT_SHA='e78eb3fe677d61d6a3088ef97616ef0d71e8d235597028d0537fd4dfdc7be14b'
ELIGIBLE_SHA='43877a13a11bb3b66cd13c68eb1eab2f482b25b4b497e08ea320b535639848c4'
BASE_SHA='3aa163bad676aa71c94083da0853a3c01b2b48bb6b33432666fcf447c9021287'
BASE_GRAPH_SHA='a9fec4648d24afc7345ae23fca9f45058c0962e8fd41d9124deaf01839ef58b6'
SELECTED_SHA='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'
EVIDENCE_SHA='e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327'
BLOCK_SHA='7a715254f965d996541001d08d3422828299f5c300dfae4cbe78b79f9a5b0e70'
RAW_SHA='86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'
GN_SHA='9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4'
RAW_COLS=['object_level','object_name','oktmo','region','settlement','population','latitude_dadata','longitude_dadata']

def csvrows(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def old_scope_gate(ev, selected, review_row, year):
 """Bounded no-grain-veto reconciliation for independently replayed 2002 rows."""
 holds=hardflags(ev);basis=None
 if 'nonsettlement_scope' in holds and ev and ev.get('population_scope') is None:
  selected_scope=selected.get('population_scope')
  if selected_scope in {'settlement','settlement_population'}:
   holds.remove('nonsettlement_scope')
   basis='selected population_scope is settlement; evidence optional scope flag is absent'
  elif year==2002 and selected_scope is None and selected.get('is_additive_settlement_record') is True:
   try: checks=json.loads(review_row['historical_raw_row_checks_json'])
   except Exception as exc: raise ValueError('invalid independently reviewed historical raw-row evidence') from exc
   old=[x for x in checks if '/2002/' in str(x.get('source_file',''))]
   if len(old)!=1 or not all(old[0].get(k) is True for k in ('raw_row_name_match','raw_row_type_match','raw_row_population_match')) or old[0].get('status')!='raw_row_replayed':
    raise ValueError('2002 optional grain field lacks exact independently replayed physical row proof')
   holds.remove('nonsettlement_scope')
   basis='selected row is additive and the exact 2002 source name/type/population row was independently replayed; original unknown scope flag retained'
 if selected.get('is_additive_settlement_record') is not True:
  if 'not_additive' not in holds:holds.append('selected row is nonadditive or unknown')
 if selected.get('population_scope') not in (None,'settlement','settlement_population'):
  holds.append('selected population scope is not settlement-grain')
 return holds,basis
def read_pin(path,digest,label):
 actual=sha(path)
 if actual!=digest:raise ValueError(f'{label} SHA mismatch: {actual}')
 return {'path':str(path),'sha256':actual}
def main():
 t0=time.monotonic()
 if OUT.exists():raise FileExistsError(f'immutable output exists: {OUT}')
 receipt_path=REVIEW/'independent_review_receipt.json'; eligible=REVIEW/'eligible_point_seedlist.csv'
 prior_points=BASE/'accepted_point_uses.parquet'; selected_path=FROZEN/'selected_observations.parquet'; evidence_path=FROZEN/'source_evidence.parquet'
 pins={
  'independent_review_receipt':read_pin(receipt_path,RECEIPT_SHA,'review receipt'),
  'eligible_seeds':read_pin(eligible,ELIGIBLE_SHA,'eligible seed list'),
  'baseline_source_points':read_pin(prior_points,BASE_SHA,'source-coordinate baseline'),
  'accepted_graph':read_pin(GRAPH,BASE_GRAPH_SHA,'accepted graph'),
  'selected_observations':read_pin(selected_path,SELECTED_SHA,'selected observations'),
  'source_evidence':read_pin(evidence_path,EVIDENCE_SHA,'source evidence'),
  'raw_tochno':read_pin(RAW,RAW_SHA,'Tochno raw source'),
  'geonames_corroboration':read_pin(GNZIP,GN_SHA,'GeoNames corroboration archive'),
  'blocklist':read_pin(BLOCK,BLOCK_SHA,'point blocklist'),
 }
 review=json.loads(receipt_path.read_text());rows=csvrows(eligible)
 if review.get('status')!='independent_review_candidate_point_seed_only' or review.get('counts',{}).get('eligible_rows')!=834 or len(rows)!=834:raise ValueError('review receipt/status/count mismatch')
 if review.get('outputs',{}).get('eligible_point_seedlist.csv',{}).get('sha256')!=ELIGIBLE_SHA:raise ValueError('receipt does not pin exact eligible CSV')
 if review.get('mutations',{}).get('accepted_points') is not False or review.get('mutations',{}).get('accepted_graph') is not False:raise ValueError('review packet reports prior mutation')
 if review.get('inputs',{}).get(str(GRAPH))!=BASE_GRAPH_SHA or review.get('inputs',{}).get(str(selected_path))!=SELECTED_SHA or review.get('inputs',{}).get(str(RAW))!=RAW_SHA or review.get('inputs',{}).get(str(GNZIP))!=GN_SHA or review.get('inputs',{}).get(str(BLOCK))!=BLOCK_SHA:raise ValueError('review packet source pins differ')
 ids=[r['target_source_record_id'] for r in rows]
 if len(set(ids))!=834:raise ValueError('duplicate seed targets')
 if any(r['eligible_scoped_point_seed']!='True' or r['hold_reasons'] for r in rows):raise ValueError('candidate list contains a held/noneligible row')
 if any('GeoNames is corroborating witness only and its coordinates are not substituted' not in r['coordinate_use_scope'] for r in rows):raise ValueError('review scope does not authorize raw publisher point')
 adj,yearmap=components(GRAPH);blocked=read_blocked_targets(BLOCK)
 cp={};paths={}
 for sid in ids:cp[sid],paths[sid]=comp_paths(sid,adj)
 if len({tuple(sorted(c)) for c in cp.values()})!=834:raise ValueError('reviewed targets share identity components')
 # Every component must have one selected source record per census year.
 allids=set().union(*cp.values())
 tab=pq.read_table(selected_path,columns=SEL_COLS,filters=[('source_record_id','in',sorted(allids))]);selected={str(r['source_record_id']):r for r in tab.to_pylist()}
 if set(selected)!=allids:raise ValueError('selected component endpoint missing')
 evidence=load_source_evidence(evidence_path,allids)
 existing_rows=pq.read_table(prior_points,columns=POINT_COLS,filters=[('target_source_record_id','in',sorted(allids))]).to_pylist()
 existing={}
 for p in existing_rows:
  if p['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES:
   sid=str(p['target_source_record_id'])
   if sid in existing:raise ValueError(f'duplicate baseline point target: {sid}')
   existing[sid]=p
 baseline_seed_existing=set(ids)&set(existing)
 # Candidate row index is the actual 1-based parquet row identifier.
 rowids={}
 for r in rows:
  suffix=r['target_source_record_id'].rsplit(':parquet:',1)
  if len(suffix)!=2:raise ValueError(f'unsupported raw source ID locator {r["target_source_record_id"]}')
  rowids[r['target_source_record_id']]=int(suffix[1])
 rawrows=raw_by_rows(RAW,set(rowids.values()))
 for r in rows:
  sid=r['target_source_record_id'];sel=selected[sid];raw=rawrows[rowids[sid]]
  # Independently replay the literal 2021 publisher row and coordinates.
  if str(sel['census_year'])!='2021' or str(sel['oktmo'])!=r['current_native_OKTMO_literal']:raise ValueError(f'selected year/native code mismatch: {sid}')
  if str(sel['settlement_name'])!=r['name'] or str(sel['settlement_type'])!=r['type'] or str(sel['region_raw'])!=r['region']:raise ValueError(f'selected name/type/region mismatch: {sid}')
  if str(raw['oktmo'])!=r['current_native_OKTMO_literal'] or str(raw['region'])!=r['region']:raise ValueError(f'raw current code/region mismatch: {sid}')
  if str(raw['settlement']).strip()!=str(raw['object_name']).strip() or not str(raw['object_name']).casefold().endswith(str(r['name']).casefold()):raise ValueError(f'raw object/name mismatch: {sid}')
  if num(raw['population'])!=num(sel['population']) or num(raw['population'])!=num(r['candidate_population']):raise ValueError(f'raw population mismatch: {sid}')
  if num(raw['latitude_dadata'])!=num(r['source_raw_latitude']) or num(raw['longitude_dadata'])!=num(r['source_raw_longitude']):raise ValueError(f'raw publisher coordinate mismatch: {sid}')
  if num(r['proposed_coordinate_latitude'])!=num(raw['latitude_dadata']) or num(r['proposed_coordinate_longitude'])!=num(raw['longitude_dadata']):raise ValueError(f'proposed coordinate not raw source coordinate: {sid}')
  ev=evidence.get((sid,2021));hf=hardflags(ev)
  if hf:raise ValueError(f'current source hard flag {sid}: {hf}')
  if sid in blocked:raise ValueError(f'current target is globally blocked: {sid}')
 # Check archive has no duplicate point targets before additions.
 if baseline_seed_existing:raise ValueError(f'some seed targets already have a point in the baseline: {sorted(baseline_seed_existing)[:8]}')
 additions=[];transfers=[];holds=[];per_component=[];added_ids=set();scope_reconciled=[];review_by_id={r['target_source_record_id']:r for r in rows}
 for r in rows:
  sid=r['target_source_record_id'];sel=selected[sid];ev=evidence.get((sid,2021));lat=num(r['source_raw_latitude']);lon=num(r['source_raw_longitude'])
  comp=cp[sid];years=[yearmap[x] for x in comp if x in yearmap]
  if len(comp)!=3 or len(years)!=3 or set(years)!={2002,2010,2021}:raise ValueError(f'component is not unique exact 2002/2010/2021: {sid}')
  # Retain GN as a witness only: the selected point origin is the raw Tochno row.
  rownum=rowids[sid];rawloc=f'parquet_row_1based={rownum};fields=object_level,object_name,settlement,region,oktmo,population,latitude_dadata,longitude_dadata'
  prov=(f"Independent admin-homonym point review {RECEIPT_SHA}; chosen coordinates are the exact raw 2021 Tochno/DaData fields from {RAW} SHA-256 {RAW_SHA}, row {rownum}: {lat},{lon}. "
        f"GeoNames witness ID {r['geonames_id']} ({r['geonames_feature']}, ADM1 {r['geonames_admin1']}) is corroborating evidence only at {r['geonames_latitude']},{r['geonames_longitude']} ({r['recomputed_current_to_geonames_km']} km); witness coordinates were not substituted. No provider-ID binding, measurement date, historic measurement or census-boundary comparability asserted.")
  carrier={'target_source_record_id':sid,'target_year':2021,'latitude':lat,'longitude':lon,'coordinate_quality':'independently_reviewed_exact_current_publisher_point','coordinate_source':'Raw Tochno/DaData coordinates from exact selected 2021 row; GeoNames is corroboration only','coordinate_source_record_id':None,'coordinate_provider':'DaData via Tochno 2021 publisher row','coordinate_provider_id':None,'coordinate_provider_family':'publisher-carried coordinate','coordinate_provenance':prov,'admission_rule':'admin_homonym_834_reviewed_exact_raw_source_point_20261004','provider_binding_status':'provider identity binding not asserted','coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_sha256':RAW_SHA,'coordinate_source_locator':rawloc,'coordinate_source_file':str(RAW),'coordinate_source_origin':'Tochno raw parquet row latitude_dadata/longitude_dadata','coordinate_source_latitude_raw':lat,'coordinate_source_longitude_raw':lon,'point_origin_file':str(RAW),'point_origin_sha256':RAW_SHA,'point_origin_locator':rawloc,'point_origin_kind':'tochno_2021_raw_DaData_coordinate_fields','coordinate_application_review_sha256':RECEIPT_SHA,'geonames_geonameid':r['geonames_id'],'geonames_feature_code':r['geonames_feature'],'geonames_admin1_raw':r['geonames_admin1'],'provider_id_binding_asserted':False,'native_id_binding_asserted':False,'modern_provider_binding_claimed':False,'historical_measurement_claimed':False,'candidate_only':False}
  direct=stage_point_use(SimpleNamespace(**sel),ev,carrier,sid,ev,[])
  direct.update(carrier);direct.update({'target_source_record_id':sid,'target_year':2021,'point_use_id':f'admin-homonym-834-seed:{sid}','coordinate_application_family':'admin_homonym_834_source_point_seed_20261004','application_inference_kind':'direct_reviewed_current_point_seed','coordinate_admission_status':'reviewed_extension_rule_accepted','admission_allowed':True,'coordinate_admitted':True,'point_admitted':True,'historical_propagation_allowed':True,'identity_edge_admitted':False,'direct_historical_coordinate_measurement':False,'coordinate_uncertainty_flags_json':json.dumps({'measurement_date_unknown':True,'geo_point_id_not_chosen_or_bound':True,'historical_measurement_not_asserted':True,'boundary_comparability_not_asserted':True},sort_keys=True),'review_id':'independent_admin_homonym_834_point_review'})
  additions.append(direct);added_ids.add(sid)
  points_in_comp=[existing[x] for x in comp if x in existing]
  conflicts=[{'source_record_id':str(p['target_source_record_id']),'distance_km':round(hav(lat,lon,num(p['latitude']),num(p['longitude'])),6)} for p in points_in_comp if hav(lat,lon,num(p['latitude']),num(p['longitude']))>5]
  if conflicts:
   holds.append({'target_source_record_id':sid,'scope':'historical_transfer','reason':'existing accepted component point spread >5km from raw current source point','conflicts':conflicts})
   per_component.append({'seed':sid,'transfer_status':'held_component_point_spread_over_5km','conflicts':conflicts});continue
  applied=[]
  for target in sorted(comp,key=lambda x:yearmap[x]):
   y=yearmap[target]
   if y==2021:continue
   if target in existing:continue
   if target in blocked:
    holds.append({'target_source_record_id':target,'scope':'historical_transfer','reason':'global point blocklist'});continue
   oldsel=selected.get(target)
   if not oldsel:holds.append({'target_source_record_id':target,'scope':'historical_transfer','reason':'selected endpoint missing'});continue
   oldev=evidence.get((target,y));oldholds,scope_basis=old_scope_gate(oldev,oldsel,review_by_id[sid],y)
   if oldholds:
    holds.append({'target_source_record_id':target,'scope':'historical_transfer','reason':'source evidence hard flags','details':oldholds});continue
   if scope_basis:
    scope_reconciled.append({'target_source_record_id':target,'seed_source_record_id':sid,'year':y,'population_scope_before':(oldev or {}).get('population_scope'),'selected_population_scope':oldsel.get('population_scope'),'selected_additive':oldsel.get('is_additive_settlement_record'),'resolution_basis':scope_basis,'review_receipt_sha256':RECEIPT_SHA,'exact_historical_raw_row_check':json.loads(review_by_id[sid]['historical_raw_row_checks_json'])})
   if int(oldsel['census_year'])!=y:raise ValueError(f'graph/source selected year mismatch for {target}')
   pathids=paths[sid].get(target)
   if not pathids:raise ValueError(f'accepted graph path missing {target} -> {sid}')
   use=stage_point_use(SimpleNamespace(**oldsel),oldev,carrier,sid,ev,pathids)
   use.update({'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_quality':'reviewed_current_publisher_point_retrospective_same_place_continuity','coordinate_source_record_id':None,'coordinate_provider_id':None,'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,'direct_historical_coordinate_measurement':False,'application_inference_kind':'current_raw_source_point_retrospective_graph_continuity_inference','coordinate_application_family':'admin_homonym_834_graph_point_transfer_20261004','coordinate_application_review_sha256':RECEIPT_SHA,'admission_rule':'reviewed_raw_2021_source_point_plus_accepted_unique_three_year_same_place_component','admission_allowed':True,'coordinate_admitted':True,'point_admitted':True,'historical_propagation_allowed':True,'identity_edge_admitted':False,'historical_measurement_claimed':False,'modern_provider_binding_claimed':False,'provider_binding_status':'provider identity binding not asserted by retrospective graph use','coordinate_provenance':prov+' Retrospective use through accepted canonical same_place path; no historical measurement or boundary/population comparability asserted.','review_id':'independent_admin_homonym_834_point_review','point_use_id':f'admin-homonym-834-retrospective:{target}','target_source_record_id':target,'target_year':y,'supporting_carrier_source_record_id':sid,'inference_modern_point_use_target_source_record_id':sid,'inference_identity_path_from_source_record_id':target,'inference_identity_path_to_source_record_id':sid,'inference_identity_path_decision_ids_json':json.dumps(pathids),'inference_identity_path_edge_count':len(pathids),'coordinate_uncertainty_flags_json':json.dumps({'measurement_date_unknown':True,'provider_identity_not_asserted':True,'historical_measurement_not_asserted':True,'population_boundary_comparability_not_asserted':True,'historical_population_scope_flag_unknown_preserved':bool(scope_basis),'historical_population_scope_reconciliation_basis':scope_basis,'accepted_same_place_path_decision_ids':pathids},sort_keys=True)})
   additions.append(use);added_ids.add(target);existing[target]={'target_source_record_id':target,'coordinate_admission_status':'reviewed_extension_rule_accepted','latitude':lat,'longitude':lon};applied.append({'id':target,'year':y,'population':float(oldsel['population'])})
  per_component.append({'seed':sid,'transfers':applied,'status':'direct_seed_added'})
 schema=pq.read_schema(prior_points);casted=[cast_addition_to_schema(x,schema) for x in additions]
 target_ids=[str(x['target_source_record_id']) for x in casted]
 if len(target_ids)!=len(set(target_ids)):raise ValueError('duplicate point-use targets in additions')
 addtable=pa.Table.from_pylist(casted,schema=schema);addtable.validate(full=True)
 OUT.mkdir(parents=True);out=OUT/'accepted_point_uses.parquet';src=pq.ParquetFile(prior_points)
 with pq.ParquetWriter(out,schema,compression='zstd') as writer:
  for batch in src.iter_batches(batch_size=4096):writer.write_batch(batch)
  writer.write_table(addtable,row_group_size=len(casted))
 op=pq.ParquetFile(out);it=iter(op.iter_batches(batch_size=4096));ob=next(it,None);off=0;copied=0
 for old in src.iter_batches(batch_size=4096):
  left=old.num_rows;parts=[]
  while left:
   if ob is None:raise ValueError('output ended before baseline prefix')
   n=min(left,ob.num_rows-off);parts.append(ob.slice(off,n));off+=n;left-=n
   if off==ob.num_rows:ob=next(it,None);off=0
  if not pa.Table.from_batches([old],schema=schema).equals(pa.Table.from_batches(parts,schema=schema)):raise ValueError('baseline point prefix changed')
  copied+=old.num_rows
 if copied!=src.metadata.num_rows or op.metadata.num_rows!=copied+len(casted):raise ValueError('output point row count mismatch')
 populations=defaultdict(lambda:{'rows':0,'population':0.0})
 for a in additions:
  sid=str(a['target_source_record_id']);y=int(a['target_year']);pop=float(selected[sid]['population']);populations[y]['rows']+=1;populations[y]['population']+=pop
 with (OUT/'appended_point_uses.csv').open('w',encoding='utf-8',newline='') as f:
  fields=['target_source_record_id','target_year','latitude','longitude','application_inference_kind','supporting_carrier_source_record_id','population','point_origin_file','point_origin_sha256','point_origin_locator']
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for a in additions:
   sid=str(a['target_source_record_id']);w.writerow({k:(selected[sid]['population'] if k=='population' else a.get(k)) for k in fields})
 (OUT/'transfer_and_hold_summary.json').write_text(json.dumps({'components':per_component,'holds':holds,'scope_reconciliations':scope_reconciled},ensure_ascii=False,indent=2)+'\n')
 receipt={'status':'root_authorized_raw_source_point_application_complete_scope_reconciled','review_receipt_sha256':RECEIPT_SHA,'input_pins':pins,'reviewed_seed_rows':834,'eligible_seed_population':100507.0,'baseline_seed_targets_already_pointed':len(baseline_seed_existing),'appended_direct_source_point_rows':834,'appended_retrospective_transfer_rows':len(additions)-834,'appended_point_rows':len(additions),'baseline_rows':src.metadata.num_rows,'output_rows':op.metadata.num_rows,'baseline_prefix_all_columns_equal':True,'baseline_prefix_rows_verified':copied,'added_point_rows_and_population_by_year':{str(k):v for k,v in sorted(populations.items())},'transfer_holds':len(holds),'historical_scope_reconciliations':len(scope_reconciled),'historical_scope_reconciliation_rule':'For exact independently replayed 2002 physical rows only, allow a NULL optional population_scope field when selected row is additive and the pinned independent receipt confirms raw name/type/population replay. Preserve the original unknown scope value; explicit federal/nonadditive/collision/successor/aggregate flags remain holds.','first_diagnostic_attempt':{'path':'/workspace/settlements-work/continuation_20261004/root/accepted_admin_homonym_834_source_points/accepted_point_uses.parquet','disposition':'unconsumed; 2002 transfers held because optional source-evidence population_scope was NULL'},'graph_mutated':False,'selected_population_mutated':False,'source_point_choice':'exact raw Tochno/DaData coordinates; GeoNames coordinates are corroboration only','provider_ID_binding_asserted':False,'historical_measurement_asserted':False,'boundary_comparability_asserted':False,'gain_semantics':'Appended-record populations are not net joint-coverage gain; root must recompute against final canonical graph/current point config.','code_sha256':sha(Path(__file__)),'output_path':str(out),'output_sha256':sha(out),'transfer_summary_sha256':sha(OUT/'transfer_and_hold_summary.json'),'elapsed_seconds':round(time.monotonic()-t0,3)}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
