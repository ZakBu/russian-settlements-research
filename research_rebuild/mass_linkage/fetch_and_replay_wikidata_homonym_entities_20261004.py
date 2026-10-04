#!/usr/bin/env python3
"""Fetch 500 explicitly screened Wikidata entities and replay dated-P1082 candidates.

Raw HTTPS API response bytes are preserved per batch. Results remain diagnostic;
no entity identity or selected population is admitted.
"""
from __future__ import annotations
import csv,hashlib,json,re,time,urllib.parse,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from collections import Counter
import pandas as pd
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF,metrics
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_PROJECTION_STATUSES,ACCEPTED_COORDINATE_STATUSES

W=Path('/workspace'); BASE=W/'settlements-work/continuation_20261004'; R4=BASE/'R4'
STAGE=R4/'wide_qid_homonym_full_entity_retrieval_20261004_v2'; REQUEST=STAGE/'entity_fetch_request_top500.csv'; PAIRS=STAGE/'top500_all_old_source_pair_alternatives.csv'; OUT=STAGE/'entity_fetch_and_replay'
REUSED_STAGE=R4/'wide_qid_homonym_full_entity_retrieval_20261004';REUSED_REQUEST=REUSED_STAGE/'entity_fetch_request_top500.csv';REUSED_RAW=REUSED_STAGE/'entity_fetch_and_replay'
F=W/'settlements-delivery/continuation-consolidated-20261003'; SEL=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'
G=W/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/accepted_identity_edges.parquet';P=W/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/accepted_point_uses.parquet';COV=W/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/coverage.json';CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def fetch_batch(qids):
 params={'action':'wbgetentities','ids':'|'.join(qids),'props':'claims|labels|descriptions','languages':'ru|en','format':'json','formatversion':'2'}
 url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'User-Agent':'RussianSettlementsResearch/1.0 (open research data reconciliation)'})
 for attempt in range(4):
  try:
   with urllib.request.urlopen(req,timeout=45) as response:
    body=response.read();status=response.status;final=response.geturl()
   if not final.startswith('https://www.wikidata.org/'):raise RuntimeError('unexpected final HTTPS host')
   if status!=200:raise RuntimeError(f'HTTP {status}')
   return url,final,status,body
  except urllib.error.HTTPError as e:
   if e.code not in (429,500,502,503,504) or attempt==3:raise
   time.sleep(min(8,2**attempt))
  except Exception:
   if attempt==3:raise
   time.sleep(min(8,2**attempt))

def yearp1082_claim(statement):
 m=statement.get('mainsnak',{});val=m.get('datavalue',{}).get('value',{}) if m.get('snaktype')=='value' else {}
 amount=val.get('amount');unit=val.get('unit');q=statement.get('qualifiers',{}).get('P585',[])
 year=None;precision=None;timeval=None
 if len(q)==1 and q[0].get('snaktype')=='value':
  tv=q[0].get('datavalue',{}).get('value',{});timeval=tv.get('time');precision=tv.get('precision')
  mat=re.fullmatch(r'\+(\d{4})-00-00T00:00:00Z',str(timeval))
  if mat and precision==9:year=int(mat.group(1))
 try:
  pop=int(str(amount).lstrip('+'))
  if pop<0:pop=None
 except Exception:pop=None
 if unit not in ('1','http://www.wikidata.org/entity/Q199'):pop=None
 return {'statement_id':statement.get('id'),'rank':statement.get('rank'),'amount_raw':amount,'amount_int':pop,'unit_raw':unit,'p585_time_raw':timeval,'p585_precision':precision,'year_precision9':year,'raw_statement_json':json.dumps(statement,ensure_ascii=False,separators=(',',':'))}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 cfg=json.loads(CONFIG.read_text());G=Path(cfg['working_identity_graph']);P=Path(cfg['working_point_uses']);COV=Path(cfg['working_coverage']);requests=pd.read_csv(REQUEST,dtype={'wikidata_qid':str,'target_source_record_id':str});pairs=pd.read_csv(PAIRS,dtype={'wikidata_qid':str,'target_source_record_id':str,'old_2002_source_record_id':str,'old_2010_source_record_id':str})
 if not (1<=len(requests)<=2000) or requests.wikidata_qid.nunique()!=len(requests):raise SystemExit('fetch request must contain 1–2000 unique QIDs')
 shortlist_summary=json.loads((STAGE/'summary.json').read_text())
 shortlist_graph=shortlist_summary['baseline_graph_sha256'];shortlist_points=shortlist_summary['baseline_point_uses_sha256']
 pinned_graph=sha(G);pinned_points=sha(P)
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SEL,EVID,G,P,COV,CONFIG,REQUEST,PAIRS]}
 batch_records=[];all_entities={};entity_sources={};rawstatement_rows=[]
 qids=requests.wikidata_qid.astype(str).tolist()
 current_qid_set=set(qids)
 cached={}
 if REUSED_REQUEST.exists() and REUSED_RAW.exists():
  oldreq=pd.read_csv(REUSED_REQUEST,dtype={'wikidata_qid':str});oldq=set(oldreq.wikidata_qid.astype(str))
  for oldbatch in sorted(REUSED_RAW.glob('raw_entity_batch_*.json')):
   oldbody=oldbatch.read_bytes();oldentities=json.loads(oldbody.decode('utf-8')).get('entities',{});oldsha=sha_bytes(oldbody)
   for qid,entity in oldentities.items():
    if qid in oldq and qid in current_qid_set:cached[qid]={'raw_file':str(oldbatch),'raw_sha256':oldsha,'reused_prior_fetch':True,'retrieved_at_utc':datetime.fromtimestamp(oldbatch.stat().st_mtime,timezone.utc).isoformat()};all_entities[qid]=entity
 missing_qids=[q for q in qids if q not in all_entities]
 for qid in qids:
  if qid in cached:entity_sources[qid]=cached[qid]
 fetched_batch_num=0
 for offset in range(0,len(missing_qids),50):
  batch=missing_qids[offset:offset+50];fetched_batch_num+=1;batchnum=fetched_batch_num;rawpath=OUT/f'raw_entity_batch_{batchnum:02d}.json'
  if rawpath.exists():
   body=rawpath.read_bytes();status=200;url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(batch),'props':'claims|labels|descriptions','languages':'ru|en','format':'json','formatversion':'2'});final=url;requested_at=None;retrieved_at=datetime.fromtimestamp(rawpath.stat().st_mtime,timezone.utc).isoformat()
  else:
   requested_at=utc();url,final,status,body=fetch_batch(batch);retrieved_at=utc()
  parsed=json.loads(body.decode('utf-8'))
  if 'entities' not in parsed:raise SystemExit(f'API response batch {offset//50+1} missing entities')
  entities=parsed['entities'];got=set(entities);missing=sorted(set(batch)-got)
  if not rawpath.exists():rawpath.write_bytes(body)
  record={'batch':batchnum,'qids_requested':batch,'request_url':url,'final_url':final,'requested_at_utc':requested_at,'retrieved_at_utc':retrieved_at,'http_status':status,'response_sha256':sha_bytes(body),'response_bytes':len(body),'raw_response_file':rawpath.name,'qids_returned':sorted(got),'qids_missing':missing}
  batch_records.append(record)
  if missing:raise SystemExit(f'API batch {batchnum} missing QIDs: {missing[:5]}')
  all_entities.update(entities)
  for qid in entities:entity_sources[qid]={'raw_file':str(rawpath),'raw_sha256':record['response_sha256'],'reused_prior_fetch':False,'retrieved_at_utc':retrieved_at}
  if offset+50<len(missing_qids):time.sleep(1.1)
 for qid,entity in all_entities.items():
  src=entity_sources[qid]
  for statement in entity.get('claims',{}).get('P1082',[]):
   v=yearp1082_claim(statement)
   rawstatement_rows.append({'wikidata_qid':qid,'property':'P1082',**v,'entity_lastrevid':entity.get('lastrevid'),'entity_modified':entity.get('modified'),'retrieved_at_utc':src['retrieved_at_utc'],'raw_entity_file':src['raw_file'],'raw_entity_sha256':src['raw_sha256'],'reused_prior_fetch':src['reused_prior_fetch']})
 # Raw response files are authoritative. This structured table preserves every P1082
 # statement and the API literal qualifiers for analysis.
 statements=pd.DataFrame(rawstatement_rows)
 if len(statements):statements.to_csv(OUT/'fetched_raw_p1082_statements.csv',index=False)
 qidrows=[]
 for qid,entity in all_entities.items():
  claims=entity.get('claims',{});p31=[]
  for st in claims.get('P31',[]):
   try:p31.append(st['mainsnak']['datavalue']['value']['id'])
   except Exception:pass
  src=entity_sources[qid]
  qidrows.append({'wikidata_qid':qid,'entity_type':entity.get('type'),'lastrevid':entity.get('lastrevid'),'modified':entity.get('modified'),'label_ru':entity.get('labels',{}).get('ru',{}).get('value'),'label_en':entity.get('labels',{}).get('en',{}).get('value'),'description_ru':entity.get('descriptions',{}).get('ru',{}).get('value'),'p31_qids_json':json.dumps(p31),'P31_count':len(claims.get('P31',[])),'P764_count':len(claims.get('P764',[])),'P1082_count':len(claims.get('P1082',[])),'P625_count':len(claims.get('P625',[])),'raw_entity_file':src['raw_file'],'raw_entity_sha256':src['raw_sha256'],'reused_prior_fetch':src['reused_prior_fetch']})
 pd.DataFrame(qidrows).to_csv(OUT/'fetched_entity_metadata.csv',index=False)
 # Confirm actual one-year precision single-valued P1082 statements before matching.
 valid={};claim_counts=Counter()
 for row in rawstatement_rows:
  y=row['year_precision9']
  if y in (2002,2010) and row['rank']!='deprecated':
   claim_counts[(row['wikidata_qid'],y)]+=1
   valid.setdefault((row['wikidata_qid'],y),[]).append(row)
 unique={k:v[0] for k,v in valid.items() if claim_counts[k]==1 and v[0]['amount_int'] is not None}
 stage=[];edge_candidates=[]
 # A single QID value pair must select exactly one actual old source row pair.
 for qid,group in pairs.groupby('wikidata_qid'):
  vals={year:unique.get((str(qid),year)) for year in (2002,2010)}
  request=requests[requests.wikidata_qid.astype(str)==str(qid)].iloc[0]
  p02,p10=vals[2002],vals[2010]
  candidate=[]
  if p02 and p10:
   for r in group.to_dict('records'):
    n02=int(r['old_2002_population']);n10=int(r['old_2010_population'])
    d02=int(p02['amount_int'])-n02;d10=int(p10['amount_int'])-n10
    candidate.append((r,d02,d10))
  exact=[x for x in candidate if x[1]==0 and x[2]==0]
  within=[x for x in candidate if x[1]==0 and abs(x[2])<=10]
  chosen=exact if len(exact)==1 else within if len(within)==1 else []
  status='unique_exact_both_year_signature' if len(exact)==1 else ('unique_exact2002_within10_2010' if len(within)==1 else ('no_two_year_population_match' if p02 and p10 else 'missing_or_multivalued_year_claim'))
  if len(exact)>1 or (not exact and len(within)>1):status='multiple_old_pairs_match_same_qid_population_vector'
  for y,claim in [(2002,p02),(2010,p10)]:
   n=claim_counts.get((str(qid),y),0);claim=claim or {}
   status_year='one_single_year_precision_statement' if n==1 else ('multiple_statements' if n>1 else 'no_single_year_precision_statement')
   es=entity_sources[qid]
   stage.append({'wikidata_qid':qid,'target_source_record_id':request.target_source_record_id,'year':y,'statement_status':status_year,'statement_count':n,'population_value':claim.get('amount_int'),'population_raw':claim.get('amount_raw'),'unit_raw':claim.get('unit_raw'),'statement_id':claim.get('statement_id'),'p585_time_raw':claim.get('p585_time_raw'),'p585_precision':claim.get('p585_precision'),'entity_lastrevid':all_entities[qid].get('lastrevid'),'entity_modified':all_entities[qid].get('modified'),'raw_entity_batch':es['raw_file'],'raw_entity_sha256':es['raw_sha256'],'reused_prior_fetch':es['reused_prior_fetch'],'candidate_match_status':status,'unique_source_pair_match_count_exact_both_years':len(exact),'unique_source_pair_match_count_exact2002_within10_2010':len(within),'population_used_as_corroboration_only':True,'identity_admitted':False,'population_admitted_or_replaced':False})
  if len(chosen)==1:
   r,d02,d10=chosen[0]
   edge_candidates.extend([{'wikidata_qid':qid,'from_source_record_id':r['old_2002_source_record_id'],'from_year':2002,'to_source_record_id':request.target_source_record_id,'to_year':2021,'relation':'same_place','candidate_rule':'two_actual_year_precision_P1082_signature_plus_exact_current_code_label_type_key_and_accepted_current_point','population_2002_delta':d02,'population_2010_delta':d10,'match_quality':status,'identity_admitted':False}, {'wikidata_qid':qid,'from_source_record_id':r['old_2010_source_record_id'],'from_year':2010,'to_source_record_id':request.target_source_record_id,'to_year':2021,'relation':'same_place','candidate_rule':'two_actual_year_precision_P1082_signature_plus_exact_current_code_label_type_key_and_accepted_current_point','population_2002_delta':d02,'population_2010_delta':d10,'match_quality':status,'identity_admitted':False}])
 pd.DataFrame(stage).to_csv(OUT/'qid_two_year_population_signature_review.csv',index=False)
 # Replay every unique pair match in a full year-constrained UF using the exact
 # pinned graph; this remains hypothetical until independent review.
 candidates=pd.DataFrame(edge_candidates)
 # Recheck the 2021 QID binding against fetched full entity P764/P31/label
 # claims and retain the source-side point, scope, and evidence gate per pair.
 from research_rebuild.mass_linkage.stage_wide_qid_homonym_fetch_candidates_20261004 import norm,typ
 current_validation=[]
 for qid in sorted(set(candidates.wikidata_qid.astype(str)) if len(candidates) else set()):
  req=requests[requests.wikidata_qid.astype(str)==qid].iloc[0];entity=all_entities[qid]
  p764=[];p31=[]
  for st in entity.get('claims',{}).get('P764',[]):
   if st.get('rank')=='deprecated':continue
   sn=st.get('mainsnak',{});val=sn.get('datavalue',{}).get('value') if sn.get('snaktype')=='value' else None
   p764.append(re.sub(r'\D','',str(val)) if val is not None else '')
  for st in entity.get('claims',{}).get('P31',[]):
   if st.get('rank')=='deprecated':continue
   sn=st.get('mainsnak',{});val=sn.get('datavalue',{}).get('value') if sn.get('snaktype')=='value' else None
   if isinstance(val,dict) and val.get('id'):p31.append(str(val['id']))
  expected_p31=[]
  try:expected_p31=[str(x['value_qid']) for x in json.loads(req.p31_claims_json or '[]') if x.get('value_qid')]
  except Exception:pass
  qlabel=entity.get('labels',{}).get('ru',{}).get('value')
  label_key=lambda x:re.sub(r'\s*-\s*','-',norm(x))
  label_ok=bool(qlabel) and label_key(qlabel)==label_key(req.current_name)
  code_ok=len(p764)==1 and p764[0]==str(req.native_code_digits)
  p31_ok=bool(expected_p31) and set(expected_p31).issubset(set(p31))
  holds_empty=str(req.source_evidence_holds_json)=='[]'
  source_point_ok=bool(req.current_accepted_point_provider_unknown)
  complete_current=code_ok and p31_ok and label_ok and source_point_ok and str(req.current_scope)=='settlement' and bool(req.source_evidence_gate) and holds_empty
  current_validation.append({'wikidata_qid':qid,'target_source_record_id':str(req.target_source_record_id),'source_native_code_raw':req.native_code_raw,'source_native_code_digits':str(req.native_code_digits),'external_p764_nondeprecated_values_json':json.dumps(p764,ensure_ascii=False),'external_p764_claim_count':len(p764),'full_entity_exact_native_p764_match_count':sum(1 for x in p764 if x==str(req.native_code_digits)),'full_entity_p764_unique_exact_native_code':code_ok,'source_type_raw':req.current_type_raw,'source_type_normalized':typ(req.current_type_raw),'source_region_raw':req.current_region_raw,'full_entity_p31_nondeprecated_qids_json':json.dumps(sorted(set(p31))),'wide_screen_expected_p31_qids_json':json.dumps(sorted(set(expected_p31))),'full_entity_contains_wide_expected_p31':p31_ok,'p31_set_matches_wide_exactly':set(expected_p31)==set(p31),'source_qid_label_ru':qlabel,'full_entity_label_matches_source_name_normalized':label_ok,'accepted_current_point_provider_unknown':source_point_ok,'source_scope':req.current_scope,'source_evidence_holds_json':req.source_evidence_holds_json,'source_evidence_gate':bool(req.source_evidence_gate),'current_uf_year_mask':int(req.current_uf_year_mask),'complete_current_binding_gate':complete_current,'identity_admitted':False})
 pd.DataFrame(current_validation).to_csv(OUT/'candidate_qid_current_full_claim_validation.csv',index=False)
 eligible_current={x['wikidata_qid'] for x in current_validation if x['complete_current_binding_gate']}
 candidates=candidates[candidates.wikidata_qid.astype(str).isin(eligible_current)].copy()
 # Use the canonical graph as promoted; no input edge is modified.
 selected=pd.read_parquet(SEL,columns=['source_record_id','census_year','population']);selected.source_record_id=selected.source_record_id.astype(str);selected.census_year=selected.census_year.astype(int)
 uf=YearUF(selected.source_record_id.tolist(),selected.census_year.tolist());yearmap=dict(zip(selected.source_record_id,selected.census_year))
 graph=pd.read_parquet(G,columns=['decision_id','from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(graph.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(graph.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES) or not set(graph.relation.astype(str)).issubset({'same_place','same_place_candidate'}):raise SystemExit('graph accepted-status guard failed during replay')
 accepted_graph=graph[graph.relation.isin(['same_place','same_place_candidate'])]
 for e in accepted_graph.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if yearmap[a]!=int(e.from_year) or yearmap[b]!=int(e.to_year) or uf.union_ids(a,b)=='year_constrained_collision':raise SystemExit('graph endpoint/year/constrained guard failed')
 pts=pd.read_parquet(P,columns=['target_source_record_id','target_year','coordinate_admission_status']);pts=pts[pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 if pts.target_source_record_id.astype(str).duplicated().any():raise SystemExit('duplicate point target during replay')
 pointids=set(pts.target_source_record_id.astype(str));base=metrics(selected,uf,pointids);cov=json.loads(COV.read_text());axes={str(x['year']):x['axes'] for x in cov['census_metrics']}
 if not eligible_current.issubset(pointids):raise SystemExit('full-claim candidate current target lacks canonical accepted point use')
 for y in (2002,2010,2021):
  z=base[str(y)];a=axes[str(y)]
  if z['full_chain']!={'rows':int(a['full_census_chain']['rows']),'population':int(a['full_census_chain']['known_population'])} or z['joint_point_full_chain']!={'rows':int(a['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(a['joint_admitted_coordinate_and_full_chain']['known_population'])}:raise SystemExit('baseline coverage mismatch')
 outcomes=Counter();edge_outcomes=[]
 if len(candidates):
  candidates=candidates.sort_values(['wikidata_qid','from_year','from_source_record_id'])
  for r in candidates.itertuples(index=False):
   result=uf.union_ids(str(r.from_source_record_id),str(r.to_source_record_id));outcomes[result]+=1;edge_outcomes.append(result)
 after=metrics(selected,uf,pointids)
 delta={y:{ax:{m:after[y][ax][m]-base[y][ax][m] for m in ('rows','population')} for ax in ('full_chain','joint_point_full_chain')} for y in base}
 candidates['union_outcome']=edge_outcomes
 candidates['raw_relation']='same_place'
 group=candidates.groupby('wikidata_qid').union_outcome.agg(lambda x:'+'.join(sorted(x))).rename('qid_pair_edge_replay_outcomes')
 candidates=candidates.merge(group,on='wikidata_qid',how='left')
 candidates.to_csv(OUT/'conditional_identity_edges.csv',index=False)
 summary={'status':'read_only_wikidata_fetch_and_candidate_union_replay_no_admissions','request_nqids':len(requests),'api_batch_count':len(batch_records),'api_batches':batch_records,'entity_returned_nqids':len(all_entities),'entity_P1082_statements':len(rawstatement_rows),'unique_single_year_precision_claims_2002':sum(1 for q,y in unique if y==2002),'unique_single_year_precision_claims_2010':sum(1 for q,y in unique if y==2010),'two_year_population_signature_candidates_before_full_current_claim_gate':len(edge_candidates)//2,'candidate_pair_qids_after_full_current_claim_gate':len(eligible_current),'candidate_identity_edges_after_full_current_claim_gate':len(candidates),'current_full_entity_validation':{'candidate_qids':len(current_validation),'complete_current_binding_gate':len(eligible_current),'full_entity_unique_exact_native_P764':sum(bool(x['full_entity_p764_unique_exact_native_code']) for x in current_validation),'full_entity_contains_wide_expected_P31':sum(bool(x['full_entity_contains_wide_expected_p31']) for x in current_validation),'full_entity_label_matches_normalized_current_name':sum(bool(x['full_entity_label_matches_source_name_normalized']) for x in current_validation),'source_evidence_gate_true_and_holds_empty':sum(bool(x['source_evidence_gate']) and str(x['source_evidence_holds_json'])=='[]' for x in current_validation)},'conditional_union_outcomes':dict(outcomes),'conditional_full_graph_metric_delta':delta,'baseline_graph_sha256':pins[str(G)]['sha256'],'baseline_point_uses_sha256':pins[str(P)]['sha256'],'accepted_legacy_relation_alias_rows_unionable_for_diagnostic':int(graph.relation.eq('same_place_candidate').sum()),'legacy_relation_handling':'canonical relation values in promoted v3 graph are used as written','baseline_coverage_reproduced':True,'inputs':pins}
 summary['outputs']={x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(OUT.iterdir()) if x.is_file()}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (OUT/'receipt.json').write_text(json.dumps({'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{x.name:sha(x) for x in sorted(OUT.iterdir()) if x.is_file() and x.name!='receipt.json'},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs','api_batches'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
