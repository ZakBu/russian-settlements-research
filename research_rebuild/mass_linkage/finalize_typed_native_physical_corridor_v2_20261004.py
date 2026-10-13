#!/usr/bin/env python3
"""Finalize the full-cohort first-pass checkpoint without rerunning it.

Reads the 184k-row register in small CSV chunks, narrows to accepted-graph
residual year vertices before reading source_evidence, and reports nonredundant
conditional coverage only after reproducing the pinned fourth-baseline coverage.
"""
from __future__ import annotations
import csv, gc, hashlib, json, random
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import (
    BLOCKED, DBF, EVID, OUT, YearUF, direct_dbf_witnesses, metrics, sha, truth, write_csv,
)
from research_rebuild.mass_linkage.build_long_table import (
    ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES,
)

CHECKPOINT=OUT/'_scratch_candidate_register.csv'
QUARANTINE_FILES=[Path('/workspace/settlements-work/continuation_20261003')/p for p in (
 'mezhgorye_quarantine_decision.json','podlipkovsky_point_hold_decision_v1.json','rural_shared_point_quarantine_decision.json')]

def main():
 cfg=json.loads((OUT/'diagnostic_input_config.json').read_text())
 GRAPH=Path(cfg['working_identity_graph']);POINTS=Path(cfg['working_point_uses']);COVERAGE=Path(cfg['working_coverage'])
 SEL=Path(cfg['working_population_layer']); APP=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/receipt.json')
 input_paths=[CHECKPOINT,SEL,EVID,GRAPH,POINTS,COVERAGE,APP,DBF,BLOCKED,*[p for p in QUARANTINE_FILES if p.is_file()],OUT/'diagnostic_input_config.json']
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in input_paths}
 if pins[str(GRAPH)]['sha256']!=cfg['working_identity_graph_sha256'] or pins[str(POINTS)]['sha256']!=cfg['working_point_uses_sha256']:
  raise SystemExit('corrected-fourth graph/point pins changed')
 app=json.loads(APP.read_text())
 if app.get('outputs',{}).get('accepted_identity_edges.parquet')!=pins[str(GRAPH)]['sha256'] or app.get('outputs',{}).get('accepted_point_uses.parquet')!=pins[str(POINTS)]['sha256']:
  raise SystemExit('corrected-fourth application receipt mismatch')
 coverage=json.loads(COVERAGE.read_text())
 if app.get('outputs',{}).get('coverage.json')!=pins[str(COVERAGE)]['sha256']:raise SystemExit('coverage receipt mismatch')

 s=pd.read_parquet(SEL,columns=['source_record_id','census_year','population']);s.source_record_id=s.source_record_id.astype(str)
 ids=s.source_record_id.tolist();years=dict(zip(ids,s.census_year.astype(int)))
 uf=YearUF(ids,s.census_year.astype(int).tolist())
 g=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if g.decision_status.isna().any() or not set(g.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES):raise ValueError('noncanonical graph status')
 if g.selection_projection_status.isna().any() or not set(g.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES):raise ValueError('noncanonical graph projection')
 if not g.relation.eq('same_place').all():raise ValueError('non-same_place accepted graph row')
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in uf.idx or b not in uf.idx or years[a]!=int(e.from_year) or years[b]!=int(e.to_year):raise ValueError('accepted graph vertex/year mismatch')
  if uf.union_ids(a,b)=='year_constrained_collision':raise ValueError('accepted graph has a same-year component collision')
 p=pd.read_parquet(POINTS,columns=['target_source_record_id','target_year','coordinate_admission_status'])
 if p.target_source_record_id.astype(str).duplicated().any():raise ValueError('duplicate accepted point target')
 if p.coordinate_admission_status.isna().any() or not set(p.coordinate_admission_status.astype(str)).issubset(ACCEPTED_COORDINATE_STATUSES):raise ValueError('noncanonical point status')
 point_ids=set(p.target_source_record_id.astype(str))
 baseline=metrics(s,uf,point_ids);covm={str(x['year']):x['axes'] for x in coverage['census_metrics']}
 baseline_checks={}
 for yr in (2002,2010,2021):
  z=baseline[str(yr)];a=covm[str(yr)]
  full={'rows':int(a['full_census_chain']['rows']),'population':int(a['full_census_chain']['known_population'])}
  joint={'rows':int(a['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(a['joint_admitted_coordinate_and_full_chain']['known_population'])}
  baseline_checks[str(yr)]={'full_chain':z['full_chain']==full,'joint':z['joint_point_full_chain']==joint,'reproduced':z['full_chain']==full and z['joint_point_full_chain']==joint}
 if not all(x['reproduced'] for x in baseline_checks.values()):raise SystemExit('coverage baseline does not reproduce; conditional gains suppressed')

 # First narrow the huge checkpoint against actual current UF components. This
 # prevents raw-source evidence joins for rows already represented in a full chain.
 cols=['source_record_id','year','population','candidate_status','gate_failures_json','current_direct_source_record_id','historical_2009_code_candidate','historical_2011_code_candidate','historical_object_2011_raw_record_json','native_historic_to_current_direct_point_min_distance_km','old_source_district_context_status']
 residual=[];firstpass=Counter();chunksize=4000
 for ch in pd.read_csv(CHECKPOINT,usecols=cols,dtype={'source_record_id':str,'candidate_status':str,'current_direct_source_record_id':str},chunksize=chunksize,keep_default_na=False,engine='c'):
  for r in ch.itertuples(index=False):
   firstpass['checkpoint_rows']+=1
   if r.candidate_status!='preliminary':continue
   firstpass['preliminary_rule_rows']+=1
   a,b=str(r.source_record_id),str(r.current_direct_source_record_id)
   ia,ib=uf.idx.get(a),uf.idx.get(b)
   if ia is None or ib is None:firstpass['missing_vertex']+=1;continue
   ra,rb=uf.find(ia),uf.find(ib)
   if ra==rb:firstpass['already_connected_no_residual_year']+=1;continue
   if uf.mask[ra]&uf.mask[rb]:firstpass['year_collision_no_residual_year']+=1;continue
   firstpass['adds_residual_year_vertex']+=1
   try:hist=json.loads(r.historical_object_2011_raw_record_json)
   except Exception:hist={}
   residual.append({'source_record_id':a,'year':int(r.year),'population':int(float(r.population)) if r.population else None,
    'current_direct_source_record_id':b,'historical_2009_code_candidate':r.historical_2009_code_candidate,
    'historical_2011_code_candidate':r.historical_2011_code_candidate,'native_historic_to_current_direct_point_min_distance_km':float(r.native_historic_to_current_direct_point_min_distance_km) if r.native_historic_to_current_direct_point_min_distance_km else None,
    'old_source_district_context_status':r.old_source_district_context_status,'historical_object_2011_raw_record_json':json.dumps(hist,ensure_ascii=False),
    'conditional_candidate_status':'residual_year_vertex_pending_source_evidence_and_DBf_gates'})
 del ch;gc.collect()
 if firstpass['checkpoint_rows']!=184762:
  raise SystemExit(f'full first-pass checkpoint row count changed: {firstpass["checkpoint_rows"]}')

 # Reopen native 2011 DBF rows and parse source_evidence only for residual IDs.
 dbf=direct_dbf_witnesses(DBF,[json.loads(r['historical_object_2011_raw_record_json']) for r in residual])
 blocked=set(json.loads(BLOCKED.read_text()).get('blocked_target_source_record_ids',[]))
 for q in QUARANTINE_FILES:
  if q.is_file():
   doc=json.loads(q.read_text());blocked.update(doc.get('quarantine_target_source_record_ids',[]));blocked.update(doc.get('blocked_target_source_record_ids',[]))
 ev_ids=list({z for r in residual for z in (r['source_record_id'],r['current_direct_source_record_id'])})
 evmap={}
 if ev_ids:
  tab=ds.dataset(EVID,format='parquet').to_table(columns=['source_record_id','source_evidence_json'],filter=ds.field('source_record_id').isin(ev_ids))
  evmap={str(x['source_record_id']):json.loads(x['source_evidence_json']) for x in tab.to_pylist()}
 eligible=[];hard=Counter()
 for r in residual:
  sid=r['source_record_id'];tgt=r['current_direct_source_record_id'];why=[]
  witness=dbf.get(sid,{})
  if not witness.get('ok'):why.append(witness.get('reason','raw_dbf_row_not_reopened'))
  if tgt not in point_ids:why.append('current_direct_target_not_in_accepted_point_uses')
  if r['native_historic_to_current_direct_point_min_distance_km'] is None or r['native_historic_to_current_direct_point_min_distance_km']>5:why.append('historic_native_to_current_direct_point_over_5km_or_missing')
  if sid in blocked or tgt in blocked:why.append('existing_hard_point_quarantine')
  for endpoint in (sid,tgt):
   ev=evmap.get(endpoint,{})
   if truth(ev.get('is_federal_aggregate')) or truth(ev.get('legacy_same_year_collision')) or ev.get('legacy_verified_successor_settlement_id'):
    why.append('source_evidence_aggregate_collision_or_verified_event:'+endpoint)
   if ev.get('is_additive_settlement_record') is False:why.append('source_evidence_nonadditive:'+endpoint)
   if truth(ev.get('legacy_identity_conflict')):
    try:cf=set(json.loads(ev.get('legacy_identity_reasons') or '[]'))
    except Exception:cf={'unparsed_conflict'}
    cf-={'administrative_conflict','ordinal_historical_identifier_hypothesis'}
    if cf:why.append('nonadministrative_identity_conflict:'+endpoint+':'+','.join(sorted(cf)))
  r['raw_live_2011_dbf_witness_json']=json.dumps(witness,ensure_ascii=False)
  r['source_evidence_old_legacy_identity_reasons_json']=evmap.get(sid,{}).get('legacy_identity_reasons')
  r['source_evidence_current_legacy_identity_reasons_json']=evmap.get(tgt,{}).get('legacy_identity_reasons')
  r['source_evidence_current_event_collision_aggregate_hold']=any(truth(evmap.get(q,{}).get('legacy_same_year_collision')) or truth(evmap.get(q,{}).get('is_federal_aggregate')) or bool(evmap.get(q,{}).get('legacy_verified_successor_settlement_id')) for q in (sid,tgt))
  r['candidate_status']='candidate_for_independent_rule_review' if not why else 'held'
  r['gate_failures_json']=json.dumps(why,ensure_ascii=False)
  for reason in why:hard[reason]+=1
  if not why:eligible.append(r)

 # Simulate only residual-year candidates, by descending source population.
 # A candidate is nonredundant only when it actually adds a source vertex/year.
 eligible.sort(key=lambda r:(-(r['population'] or 0),r['source_record_id']))
 points_out=[];edges_out=[];applied=[];ufout=Counter()
 for r in eligible:
  sid=r['source_record_id'];tgt=r['current_direct_source_record_id'];outcome=uf.union_ids(sid,tgt);ufout[outcome]+=1
  r['conditional_union_result']=outcome
  if outcome=='merged':
   edges_out.append({'from_source_record_id':sid,'from_year':r['year'],'to_source_record_id':tgt,'to_year':2021,'relation':'same_place','decision_rule':'typed_native_physical_corridor_v2_candidate_only','conditional_union_result':outcome,'candidate_only':True,'identity_admitted':False})
   applied.append(r)
   if sid not in point_ids:
    db=json.loads(r['raw_live_2011_dbf_witness_json'])
    points_out.append({'target_source_record_id':sid,'target_year':r['year'],'latitude':float(db['latitude_raw']),'longitude':float(db['longitude_raw']),
     'coordinate_source':'candidate exact typed physical GeoKLADR 2011 native object; point-only retrospective association pending review',
     'coordinate_source_record_id':'GEOKLADR2011:'+str(r['historical_2011_code_candidate']),'point_origin_kind':'raw_named_typed_2011_physical_geo_object',
     'point_origin_file':str(DBF),'point_origin_sha256':pins[str(DBF)]['sha256'],
     'point_origin_locator':f"DBF_record_1based={db['record_1based']};DBF_byte_offset_0based={db['byte_offset_0based']};OKATO2011_raw={r['historical_2011_code_candidate']}",
     'direct_2021_witness_source_record_id':tgt,'distance_to_2021_direct_point_km':r['native_historic_to_current_direct_point_min_distance_km'],
     'coordinate_admission_status':'candidate_only_no_admission','temporal_identity_admitted':False,'native_publisher_code_binding_claimed':False,
     'population_boundary_comparability_asserted':False,'independent_rule_review_required':True})
  else:
   r['candidate_status']='held_'+outcome;r['gate_failures_json']=json.dumps(['candidate_no_longer_adds_a_residual_year_after_prior_union'],ensure_ascii=False)
 after=metrics(s,uf,point_ids|{r['target_source_record_id'] for r in points_out})
 delta={yr:{axis:{m:after[yr][axis][m]-baseline[yr][axis][m] for m in ('rows','population')} for axis in ('full_chain','joint_point_full_chain')} for yr in baseline}

 # Keep the giant first-pass receipt immutable; final outputs contain only the
 # filtered current-residual cohort, source-evidence gates, and nonredundant joins.
 write_csv(OUT/'residual_year_vertex_candidates.csv',residual)
 write_csv(OUT/'independently_reviewable_candidate_edges.csv',edges_out)
 write_csv(OUT/'candidate_point_only_uses.csv',points_out)
 write_csv(OUT/'conditional_union_results.csv',[{'source_record_id':r['source_record_id'],'year':r['year'],'population':r['population'],'to_source_record_id':r['current_direct_source_record_id'],'conditional_union_result':r.get('conditional_union_result'),'candidate_status':r['candidate_status'],'gate_failures_json':r['gate_failures_json']} for r in residual])
 summary={'status':'typed_native_physical_corridor_candidate_only_no_admissions','baseline_id':'corrected_fourth_current','baseline_graph_sha256':pins[str(GRAPH)]['sha256'],'baseline_points_sha256':pins[str(POINTS)]['sha256'],'baseline_coverage_sha256':pins[str(COVERAGE)]['sha256'],'full_cohort_checkpoint_sha256':pins[str(CHECKPOINT)]['sha256'],'baseline_coverage_reproduced':True,'baseline_checks':baseline_checks,'first_pass_full_h_cohort_rows':firstpass['checkpoint_rows'],'first_pass_screen_counts':dict(firstpass),'source_evidence_hard_holds':dict(hard),'eligible_residual_union_results':dict(ufout),'nonredundant_identity_edges':len(edges_out),'point_only_candidate_uses':len(points_out),'conditional_nonredundant_coverage_delta':delta,'candidate_identity_rule':'Exact typed old/current source name and province are unique in their year; actual classifier/GeoKLADR native typed physical code pair is unique; explicit old source county agrees with actual 2009 parent when available and disambiguates same-signature objects; current accepted direct proper point is within 5 km of the native historic object. P1082 is not used.','interpretation':['All outputs are conditional candidates pending independent review.','Only rows that can add a missing census-year vertex were passed to source-evidence and raw-DBF gates; already-connected triples are excluded.','The reported coverage change is computed from the complete accepted graph before and after simulated nonredundant candidate unions and candidate point uses, not by summing endpoint populations.','Publisher native IDs remain opaque; OKATO identifies the classifier/GeoKLADR object only. No legal boundary dates or population comparability are asserted.'],'inputs':pins}
 summary['outputs']={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in {'summary.json','receipt.json'}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 receipt={'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='receipt.json'},'finalizer_script':str(Path(__file__).resolve()),'finalizer_sha256':sha(Path(__file__))}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
