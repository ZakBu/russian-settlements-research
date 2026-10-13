#!/usr/bin/env python3
"""Prepare (do not apply) the eleventh reviewed identity/point batch."""
from __future__ import annotations
import csv, hashlib, json
from collections import Counter
from pathlib import Path
import pyarrow.parquet as pq

ROOT=Path('/workspace/settlements-work/continuation_20261004')
OUT=ROOT/'root/next_batch_manifest_preparation/eleventh_gostsup_type12'
FROZEN=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
BASE=ROOT/'accepted_mass_tenth_reviewed1117'
TYPEDIR=Path('/workspace/settlements-work/continuation_20261004/independent_review/type_transition_13_review_final')
GOSTDIR=Path('/workspace/settlements-work/continuation_20261004/independent_review/gostagaevskaya_classifier_point_review_v2')
TEMPLATE=ROOT/'root/next_batch_manifest_preparation/next_batch_application_manifest.json'
BLOCKED=Path('/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json')
GNZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
TYPECSV=TYPEDIR/'eligible_type_transition_edges.csv'
TYPERECEIPT=TYPEDIR/'review_receipt.json'
GOSTEDGE=GOSTDIR/'eligible_identity_edges.csv'
GOSTPOINT=GOSTDIR/'eligible_point_uses.csv'
GOSTRECEIPT=GOSTDIR/'independent_review_receipt.json'

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def pin(path):return {'path':str(path),'sha256':sha(path)}
def readcsv(path):
 csv.field_size_limit(100_000_000)
 with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(path,rows,fields):
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader();w.writerows(rows)
def bool_is(x,expected):
 return x is expected

def main():
 if OUT.exists():raise FileExistsError(f'immutable preparation folder already exists: {OUT}')
 exp_base_graph='19861c11048f191a540aba453f11194a540934fbe350f553e37a42908393d013'
 exp_base_points='870ccd0af86889e5c8e2c01bddd1d3c53401ccba216d7ce77624e5f848f724cc'
 exp_frozen_selected='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'
 exp_frozen_ev='e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327'
 exp_type_receipt='374006cb726fb8c9cf35d73b0ffc074cfa08693d41e6ffc9549a45913dffe514'
 exp_type_eligible='add7569ee4a7bf148fff3c5d2185db3426b1c4cf7885e3a2106bb3d204a4b90e'
 exp_gost_receipt='e6cdc2b0b6103402f502f279c06a51f504345a9407c4c7d49158f78eadefcb5c'
 exp_gost_edges='11e9983b854d0760ab92e161dda92e33277f8a6b136fe5458e9e1b0df659a6cc'
 exp_gost_points='186c013ee81acb351fcd35b1249449d1eabe20fd529a9d63337fd311b930778c'
 for path,expected in [(BASE/'accepted_identity_edges.parquet',exp_base_graph),(BASE/'accepted_point_uses.parquet',exp_base_points),(FROZEN/'selected_observations.parquet',exp_frozen_selected),(FROZEN/'source_evidence.parquet',exp_frozen_ev),(TYPERECEIPT,exp_type_receipt),(TYPECSV,exp_type_eligible),(GOSTRECEIPT,exp_gost_receipt),(GOSTEDGE,exp_gost_edges),(GOSTPOINT,exp_gost_points)]:
  got=sha(path)
  if got!=expected:raise ValueError(f'input pin mismatch {path}: {got}')
 type_receipt=json.loads(TYPERECEIPT.read_text());gost_receipt=json.loads(GOSTRECEIPT.read_text())
 if type_receipt['status']!='independent_type_transition_review_complete_candidate_only' or type_receipt['candidate_counts']['eligible_edges']!=24:raise ValueError('type review receipt status/count mismatch')
 if type_receipt['graph10_sha256']!=exp_base_graph:raise ValueError('type review was made against a different graph10')
 if type_receipt['outputs']['eligible_type_transition_edges.csv']['sha256']!=exp_type_eligible:raise ValueError('type receipt does not pin eligible input')
 if gost_receipt['status']!='independent_finite_identity_and_point_review_complete_candidate_only':raise ValueError('Gost/Sup review receipt status mismatch')
 if gost_receipt['baseline_graph_sha256']!=exp_base_graph or gost_receipt['baseline_point_ledger_sha256']!=exp_base_points:raise ValueError('Gost/Sup review baseline differs from application baseline')
 if gost_receipt['outputs']['eligible_identity_edges.csv']['sha256']!=exp_gost_edges or gost_receipt['outputs']['eligible_point_uses.csv']['sha256']!=exp_gost_points:raise ValueError('Gost/Sup receipt does not pin exact reviewed CSVs')
 types=readcsv(TYPECSV);gedges=readcsv(GOSTEDGE);gpoints=readcsv(GOSTPOINT)
 if len(types)!=24 or any(r['independent_status']!='eligible_scoped_type_transition' for r in types):raise ValueError('type eligible list contains wrong row count/status')
 if any(r['graph10_outcome']!='new_union' for r in types):raise ValueError('type reviewed edge is not a new graph10 union')
 if len(gedges)!=4 or len(gpoints)!=2:raise ValueError('Gost/Sup eligible candidate counts changed')
 if len({(r['from_source_record_id'],r['to_source_record_id']) for r in types+gedges})!=28:raise ValueError('combined identity proposal pairs are not unique')
 if any(r['relation']!='same_place' for r in gedges):raise ValueError('Gost/Sup relation is not ordinary same_place')
 # Pin the accepted selected endpoints and canonical endpoint-level source evidence.
 all_edge_ids={r[k] for r in types+gedges for k in ('from_source_record_id','to_source_record_id')}
 point_ids={r['target_source_record_id'] for r in gpoints}
 all_ids=all_edge_ids|point_ids
 selected=pq.read_table(FROZEN/'selected_observations.parquet',columns=['source_record_id','census_year'],filters=[('source_record_id','in',sorted(all_ids))]).to_pylist()
 years={r['source_record_id']:int(r['census_year']) for r in selected}
 if set(years)!=all_ids:raise ValueError('reviewed endpoint is missing from frozen selected observations')
 for r in types+gedges:
  a,b=r['from_source_record_id'],r['to_source_record_id']
  if 'from_year' in r and r['from_year'] and int(float(r['from_year']))!=years[a]:raise ValueError(f'from_year mismatch for {a}')
  if 'to_year' in r and r['to_year'] and int(float(r['to_year']))!=years[b]:raise ValueError(f'to_year mismatch for {b}')
  if years[a]==years[b]:raise ValueError(f'same-year edge candidate {a} -> {b}')
  if years[b] not in (2002,2010,2021) or years[a] not in (2002,2010,2021):raise ValueError('unsupported year')
 evrows=pq.read_table(FROZEN/'source_evidence.parquet',columns=['source_record_id','census_year','source_evidence_json'],filters=[('source_record_id','in',sorted(all_ids))]).to_pylist()
 ev={}
 for outer in evrows:
  d=json.loads(outer['source_evidence_json']);sid=outer['source_record_id'];year=int(outer['census_year'])
  if sid not in all_ids or int(d.get('census_year',year))!=year:raise ValueError('canonical endpoint evidence identity mismatch')
  ev[sid]=d
 if set(ev)!=all_ids:raise ValueError('canonical source evidence is missing an endpoint')
 flags=[]
 for sid in sorted(all_ids):
  d=ev[sid]
  if d.get('is_additive_settlement_record') is not True:raise ValueError(f'canonical additive flag is not true: {sid}')
  if d.get('is_federal_aggregate') is not False:raise ValueError(f'canonical federal aggregate flag is not explicitly false: {sid}')
  if d.get('legacy_same_year_collision') is not False:raise ValueError(f'canonical same-year collision flag is not explicitly false: {sid}')
  if d.get('legacy_verified_successor_settlement_id') not in (None,'','null'):raise ValueError(f'canonical successor/event pointer blocks endpoint: {sid}')
  flags.append({'source_record_id':sid,'census_year':years[sid],'additive':d['is_additive_settlement_record'],'federal_aggregate':d['is_federal_aggregate'],'same_year_collision':d['legacy_same_year_collision'],'verified_successor':d.get('legacy_verified_successor_settlement_id'),'legacy_identity_conflict_preserved':d.get('legacy_identity_conflict'),'legacy_identity_reasons_preserved':d.get('legacy_identity_reasons'),'population_scope_preserved':d.get('population_scope')})
 # Verify that the only point additions are the independently reviewed, missing 2021 GN points.
 if {years[s] for s in point_ids}!={2021}:raise ValueError('direct point source includes a non-2021 target')
 if len(point_ids)!=2:raise ValueError('expected two direct point targets')
 current_point_rows=pq.read_table(BASE/'accepted_point_uses.parquet',columns=['target_source_record_id'],filters=[('target_source_record_id','in',sorted(point_ids))]).to_pylist()
 if current_point_rows:raise ValueError('direct current targets already have baseline point uses')
 blocked=set(json.loads(BLOCKED.read_text())['blocked_target_source_record_ids'])
 if point_ids & blocked:raise ValueError('direct point target is on the global blocked-target list')
 pointcheck=[]
 for r in gpoints:
  if years[r['target_source_record_id']]!=int(r['target_year']):raise ValueError('point row target year differs from selected endpoint')
  if r['target_year']!='2021' or r['point_origin_file']!=str(GNZIP) or r['point_origin_sha256']!=sha(GNZIP):raise ValueError('point row not the approved exact GeoNames current point choice')
  if r['coordinate_provider_id'] or 'not asserted' not in r['provider_binding_status'].lower():raise ValueError('unexpected point provider-binding claim')
  if r['coordinate_measurement_date_unknown'].lower()!='true' or r['coordinate_precision_claimed'].lower()!='false' or r['boundary_comparability_asserted'].lower()!='false':raise ValueError('point-use limitations were lost')
  pointcheck.append({'target_source_record_id':r['target_source_record_id'],'target_year':int(r['target_year']),'latitude':float(r['latitude']),'longitude':float(r['longitude']),'point_origin_file':r['point_origin_file'],'point_origin_sha256':r['point_origin_sha256'],'point_origin_locator':r['point_origin_locator'],'provider_binding_status':r['provider_binding_status']})
 OUT.mkdir(parents=True)
 # The type packet is passed through byte-for-byte. A compact adapter maps the
 # second, separately reviewed packet into the app's common input columns while
 # retaining every original proof column in raw_reviewed_row_json.
 adapter=[]
 for n,r in enumerate(gedges,1):
  adapter.append({'decision_id':r['proposal_id'],'from_source_record_id':r['from_source_record_id'],'to_source_record_id':r['to_source_record_id'],'from_year':r['from_year'],'to_year':r['to_year'],'relation':r['relation'],'family':'independent_gost_sup_classifier_point_continuity_20261004','status':'independently_reviewed_candidate_for_root_application','raw_reviewed_row_json':json.dumps(r,ensure_ascii=False,sort_keys=True)})
 adapter_path=OUT/'gost_sup_identity_candidate_adapter.csv'
 writecsv(adapter_path,adapter,['decision_id','from_source_record_id','to_source_record_id','from_year','to_year','relation','family','status','raw_reviewed_row_json'])
 template=json.loads(TEMPLATE.read_text())
 manifest=dict(template)
 manifest['manifest_version']='eleventh_gost_sup_type_transition_20261004'
 manifest['reviewed_at_utc']='2026-10-04T12:30:00Z'
 manifest['base']={'graph':pin(BASE/'accepted_identity_edges.parquet'),'points':pin(BASE/'accepted_point_uses.parquet')}
 manifest['identity_sources']=[
  {'candidate':pin(TYPECSV),'eligible':pin(TYPECSV),'review_receipt':pin(TYPERECEIPT),
   'candidate_columns':{'from':'from_source_record_id','to':'to_source_record_id','family':'candidate_rule','status':'independent_status'},
   'eligible_columns':{'from':'from_source_record_id','to':'to_source_record_id','family':'candidate_rule'},
   'accepted_candidate_statuses':['eligible_scoped_type_transition'],
   'canonical_columns':{'relation':'relation','decision_class':'candidate_rule','source':'independent_status'},
   'additional_review_receipts':[],
   'exclude_if_true':[]},
  {'candidate':pin(adapter_path),'eligible':pin(adapter_path),'review_receipt':pin(GOSTRECEIPT),
   'candidate_columns':{'from':'from_source_record_id','to':'to_source_record_id','family':'family','id':'decision_id','status':'status'},
   'eligible_columns':{'from':'from_source_record_id','to':'to_source_record_id','family':'family'},
   'accepted_candidate_statuses':['independently_reviewed_candidate_for_root_application'],
   'canonical_columns':{'relation':'relation','decision_class':'family','source':'status'},
   'additional_review_receipts':[],
   'exclude_if_true':[]}
 ]
 manifest['point_sources']=[
  {'candidate':pin(GOSTPOINT),'approved':pin(GOSTPOINT),'review_receipt':pin(GOSTRECEIPT),
   'candidate_columns':{'target':'target_source_record_id','latitude':'latitude','longitude':'longitude','origin_file':'point_origin_file','origin_sha256':'point_origin_sha256','origin_locator':'point_origin_locator'},
   'approved_columns':{'target':'target_source_record_id','latitude':'latitude','longitude':'longitude','origin_file':'point_origin_file','origin_sha256':'point_origin_sha256','origin_locator':'point_origin_locator'},
   'origin':{'path':str(GNZIP),'sha256':sha(GNZIP)},'output_columns':{},
   'output_values':{'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,'direct_historical_coordinate_measurement':False,'provider_binding_status':'GeoNames feature row is used as a physical-point witness; provider entity binding is not asserted'}}
 ]
 manifest['review_context_inputs']=[
  {'role':'type_transition_13_independent_review_receipt','path':str(TYPERECEIPT),'sha256':sha(TYPERECEIPT)},
  {'role':'type_transition_13_eligible_rows','path':str(TYPECSV),'sha256':sha(TYPECSV)},
  {'role':'gost_sup_classifier_point_independent_review_receipt','path':str(GOSTRECEIPT),'sha256':sha(GOSTRECEIPT)},
  {'role':'gost_sup_independently_eligible_identity_edges','path':str(GOSTEDGE),'sha256':sha(GOSTEDGE)},
  {'role':'gost_sup_independently_eligible_points','path':str(GOSTPOINT),'sha256':sha(GOSTPOINT)},
  {'role':'authoritative_canonical_source_evidence_preflight','path':str(FROZEN/'source_evidence.parquet'),'sha256':sha(FROZEN/'source_evidence.parquet')}
 ]
 manifest['application_scope']='Prepared only, not applied: 24 type-transition edges plus 4 Gostagaevskaya/Supsekh same-place edges and two independently reviewed current GeoNames point uses. Independent source receipts remain candidate-only until root invokes application.'
 manifest_path=OUT/'eleventh_application_manifest.json'
 manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 flag_path=OUT/'canonical_endpoint_hard_flag_preflight.json'
 flag_path.write_text(json.dumps({'source_evidence_file':pin(FROZEN/'source_evidence.parquet'),'endpoint_count':len(flags),'checked_flags':['is_additive_settlement_record == true','is_federal_aggregate == false','legacy_same_year_collision == false','legacy_verified_successor_settlement_id is null'],'legacy_identity_conflict_and_reasons_are_preserved_not_used_as_hard_flags':True,'endpoints':flags},ensure_ascii=False,indent=2)+'\n')
 receipt={'status':'prepared_only_candidate_batch_not_applied','batch_scope':{'type_transition_edges':24,'gost_sup_edges':4,'total_identity_edges':28,'direct_current_point_uses':2,'historical_gost_sup_point_rows_already_in_baseline':4,'reviewed_holds_not_included':2},'baseline':{'graph':pin(BASE/'accepted_identity_edges.parquet'),'points':pin(BASE/'accepted_point_uses.parquet'),'selected':pin(FROZEN/'selected_observations.parquet'),'source_evidence':pin(FROZEN/'source_evidence.parquet')},'independent_reviews':{'type_transition_receipt':pin(TYPERECEIPT),'type_transition_eligible':pin(TYPECSV),'type_transition_receipt_source_evidence_sha256':type_receipt['source_evidence_sha256'],'gost_sup_receipt':pin(GOSTRECEIPT),'gost_sup_edge_csv':pin(GOSTEDGE),'gost_sup_point_csv':pin(GOSTPOINT)},'preflight':{'endpoint_count':len(flags),'all_source_hard_flags_clear':True,'all_years_verified_against_selected':True,'point_targets_missing_from_baseline_and_not_globally_blocked':True,'only_reviewed_type_eligible_rows_included':True,'holds_excluded':2,'point_choices_are_geonames_ppl_and_binding_unasserted':True},'derived_adapter':pin(adapter_path),'manifest':pin(manifest_path),'hard_flag_preflight':pin(flag_path),'app_script':pin(Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/apply_reviewed_mass_extensions_20261004.py')),'application_run':'not performed; root controls memory slot and final invocation'}
 receipt_path=OUT/'preparation_receipt.json';receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':receipt['status'],'output_dir':str(OUT),'manifest':receipt['manifest'],'identity_edges':28,'direct_points':2,'canonical_endpoint_count':len(flags),'root_invoke_only':True},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
