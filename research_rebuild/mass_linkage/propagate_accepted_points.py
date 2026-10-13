"""Stage exact accepted modern point reuse over approved same-place paths.

This graph delta proposes missing 2002/2010 coordinate uses from one accepted
2021 point per collision-free accepted identity component. It never admits them.
"""
from __future__ import annotations
import argparse,hashlib,json,math,re
from collections import Counter,defaultdict,deque
from pathlib import Path
import pandas as pd
W=Path('/workspace')
ACCEPTED=W/'settlements-work/coordinates/accepted_extension_noncity_v1/accepted_point_uses.parquet'
GRAPH=W/'settlements-work/identity/accepted_historical_v2/accepted_identity_edges.parquet'
SELECTED=W/'settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet'
EVIDENCE=W/'settlements-work/candidates/optimized_run/source_evidence.parquet'
EVENTS=W/'settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json'
REVIEW=W/'settlements-work/coordinates/extension_review_v1/review.json'
OUT=W/'settlements-work/coordinates/graph_delta_propagation_v1'
ACCEPTED_SHA=''
GRAPH_SHA=''
STATUS_OK={'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific'}
ORIGIN=['point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_claim_artifact_file','point_claim_artifact_sha256']

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def txt(v):return '' if v is None or pd.isna(v) else str(v).strip()
def n(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None
def samept(a,b,c,d):return None not in (n(a),n(b),n(c),n(d)) and n(a)==n(c) and n(b)==n(d)
def event_codes(events):
 out=defaultdict(list)
 for e in events:
  date=txt(e.get('source_asserted_effective_date'));m=re.search(r'(?:19|20)\d{2}',date);yr=int(m.group()) if m else None
  codes=[]
  for k,v in e.items():
   if 'settlement_id' in k and v:
    mm=re.fullmatch(r'RU-OKTMO-(\d+)',str(v))
    if mm:codes.append(mm.group(1))
  for code in codes:out[code].append({'event_id':txt(e.get('event_id')),'year':yr,'event_type':txt(e.get('event_type'))})
 return out
def approved_edges(graph):
 return graph[(graph.relation=='same_place')&graph.decision_status.isin(STATUS_OK)]

def apply(out=OUT):
 out=Path(out)
 if out.exists() and any(out.iterdir()):raise FileExistsError(f'output path not empty: {out}')
 accepted=pd.read_parquet(ACCEPTED);graph=pd.read_parquet(GRAPH);selected=pd.read_parquet(SELECTED)
 accepted_sha=sha(ACCEPTED);graph_sha=sha(GRAPH);selected_sha=sha(SELECTED);review_sha=sha(REVIEW)
 if len(accepted)!=304112 or len(graph)!=175448:raise ValueError('accepted-point or graph row count differs from frozen task input')
 # The graph contains only accepted edges; retain accepted same-place decisions.
 edges=approved_edges(graph)
 adj=defaultdict(list);year_by_node={};edge_by_id={}
 for e in edges.itertuples(index=False):
  a,b=txt(e.from_source_record_id),txt(e.to_source_record_id); ya,yb=int(e.from_year),int(e.to_year); did=txt(e.decision_id)
  if a in year_by_node and year_by_node[a]!=ya or b in year_by_node and year_by_node[b]!=yb:raise ValueError('graph node has inconsistent year labels')
  year_by_node[a]=ya;year_by_node[b]=yb;edge_by_id[did]=e._asdict()
  adj[a].append((b,did));adj[b].append((a,did))
 # One traversal assigns components, collision counts, and a spanning-tree path.
 comp_of={};parent={};parent_edge={};depth={};comp_nodes={};cid=0
 for root in adj:
  if root in comp_of:continue
  cid+=1;comp_of[root]=cid;parent[root]=None;depth[root]=0;nodes=[];q=deque([root])
  while q:
   cur=q.popleft();nodes.append(cur)
   for nxt,did in adj[cur]:
    if nxt in comp_of:continue
    comp_of[nxt]=cid;parent[nxt]=cur;parent_edge[nxt]=did;depth[nxt]=depth[cur]+1;q.append(nxt)
  comp_nodes[cid]=nodes
 comp_year_collision={}
 for c,nodes in comp_nodes.items():
  ys=Counter(year_by_node[x] for x in nodes);comp_year_collision[c]=[y for y,k in ys.items() if k>1]
 selected=selected[selected.census_year.isin([2002,2010,2021])].copy()
 selected_by={txt(r.source_record_id):r for r in selected.itertuples(index=False)}
 accepted_by={txt(r.target_source_record_id):r for r in accepted.itertuples(index=False)}
 # A carrier is an already accepted 2021 point-use row, not a mere modern source pointer.
 carriers=defaultdict(list)
 for rid,r in accepted_by.items():
  if int(r.target_year)==2021:carriers[rid].append(r)
 evidence=pd.read_parquet(EVIDENCE,columns=['source_record_id','census_year','source_evidence_json'])
 evidence=evidence[evidence.census_year.isin([2002,2010,2021])]
 ev_by={(txt(r.source_record_id),int(r.census_year)):json.loads(r.source_evidence_json) for r in evidence.itertuples(index=False)}
 events=json.loads(EVENTS.read_text());event_by=event_codes(events)
 # Hash canonical carrier assets once and verify their path/hash pins.
 origin_assets={}
 for r in accepted.itertuples(index=False):
  if int(r.target_year)!=2021:continue
  for fc,hc in [('point_origin_file','point_origin_sha256'),('point_claim_artifact_file','point_claim_artifact_sha256')]:
   fp,h=txt(getattr(r,fc,None)),txt(getattr(r,hc,None))
   if fp and h:origin_assets[fp]=h
 for fp,h in origin_assets.items():
  if sha(Path(fp))!=h:raise ValueError(f'accepted modern origin asset hash mismatch: {fp}')
 proposals=[];holds=[]
 def path_ids(a,b):
  x,y=a,b;left=[];right=[]
  while depth[x]>depth[y]:left.append(parent_edge[x]);x=parent[x]
  while depth[y]>depth[x]:right.append(parent_edge[y]);y=parent[y]
  while x!=y:
   left.append(parent_edge[x]);right.append(parent_edge[y]);x=parent[x];y=parent[y]
  return left+right[::-1]
 missing=selected[(selected.census_year.isin([2002,2010]))&~selected.source_record_id.astype(str).isin(accepted_by)]
 for s in missing.itertuples(index=False):
  rid=txt(s.source_record_id);c=comp_of.get(rid);reason=[]
  if c is None:continue
  if comp_year_collision.get(c):reason.append('accepted_graph_component_has_year_collision')
  modern_nodes=[x for x in comp_nodes[c] if year_by_node[x]==2021 and x in carriers]
  if len(modern_nodes)!=1:reason.append('component_does_not_have_exactly_one_accepted_2021_point_carrier')
  if reason:
   holds.append({'target_source_record_id':rid,'target_year':int(s.census_year),'hold_reasons_json':json.dumps(reason),'component_id':c});continue
  carrier_id=modern_nodes[0];carrier=carriers[carrier_id][0];ce=ev_by.get((carrier_id,2021));se=ev_by.get((rid,int(s.census_year)))
  if not any(txt(getattr(carrier,k,None)) for k in ORIGIN):reason.append('accepted_modern_carrier_missing_canonical_origin')
  if not txt(carrier.point_origin_file) and not txt(carrier.point_claim_artifact_file):reason.append('accepted_modern_carrier_origin_file_missing')
  if txt(carrier.point_origin_file) and txt(carrier.point_origin_file) not in origin_assets:reason.append('accepted_modern_carrier_origin_hash_missing')
  if ce is None:reason.append('accepted_modern_carrier_source_evidence_missing')
  elif ce.get('legacy_identity_conflict') or ce.get('legacy_same_year_collision') or ce.get('is_federal_aggregate') or not ce.get('is_additive_settlement_record'):reason.append('accepted_modern_carrier_source_conflict_or_nonphysical')
  if se is None:reason.append('historical_target_source_evidence_missing')
  elif se.get('legacy_identity_conflict') or se.get('legacy_same_year_collision') or se.get('is_federal_aggregate') or not se.get('is_additive_settlement_record'):reason.append('historical_target_source_conflict_or_nonphysical')
  for ev,label in ((ce,'carrier'),(se,'target')):
   grain=txt(ev.get('entity_grain_status')) if ev else ''
   if grain and any(w in grain.lower() for w in ('aggregate','parent','shared_okato','municipal_total')):reason.append(label+'_source_grain_aggregate_or_shared')
  if not samept(s.latitude,s.longitude,carrier.latitude,carrier.longitude) and n(s.latitude) is not None and n(s.longitude) is not None:
   # Selected R2 historic coordinates may be blank; if present, do not require
   # equality with the modern point since this is an explicit continuity inference.
   pass
  if not (n(carrier.latitude) is not None and n(carrier.longitude) is not None and -90<=n(carrier.latitude)<=90 and -180<=n(carrier.longitude)<=180):reason.append('carrier_point_invalid')
  # The modern carrier's selected native 2021 OKTMO is the event key. Apply only
  # events whose asserted year falls between target year and 2021.
  native=txt(getattr(selected_by.get(carrier_id),'oktmo',None))
  for code in filter(None,{native}):
   for ev in event_by.get(code,[]):
    if ev['year'] is None or int(s.census_year)<=ev['year']<=2021:reason.append('native_2021_code_linked_lineage_event_'+ev['event_id'])
  reason=list(dict.fromkeys(reason))
  if reason:
   holds.append({'target_source_record_id':rid,'target_year':int(s.census_year),'hold_reasons_json':json.dumps(reason,ensure_ascii=False),'component_id':c,'carrier_target_source_record_id':carrier_id});continue
  ids=path_ids(rid,carrier_id)
  # Audit every returned path edge and endpoint before staging.
  cur=rid
  for did in ids:
   e=edge_by_id[did];a,b=e['from_source_record_id'],e['to_source_record_id']
   if cur==a:cur=b
   elif cur==b:cur=a
   else:raise AssertionError(f'nonchaining BFS path for {rid}')
  if cur!=carrier_id or any(d not in edge_by_id for d in ids):raise AssertionError('path does not end at exact modern carrier')
  p=carrier._asdict();p.update({'target_source_record_id':rid,'target_year':int(s.census_year),
   'coordinate_admission_status':'staged_candidate_pending_root_review','admission_allowed':False,
   'coordinate_provenance':txt(carrier.coordinate_provenance)+'; applied by explicit same_place graph continuity from accepted 2021 point; no historical measurement',
   'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,
   'population_scope_comparability_asserted':False,'direct_historical_coordinate_measurement':False,
   'application_inference_kind':'retrospective_continuity_from_accepted_2021_point',
   'inference_modern_point_use_target_source_record_id':carrier_id,
   'inference_identity_path_decision_ids_json':json.dumps(ids),
   'inference_identity_path_from_source_record_id':rid,'inference_identity_path_to_source_record_id':carrier_id,
   'inference_identity_path_edge_count':len(ids),'coordinate_application_family':'R_graph_accepted_2021_carrier_continuity',
   'review_id':'accepted_historical_graph_point_continuity_v1'})
  proposals.append(p)
 # Do not duplicate any existing accepted target; inputs were excluded before graph work.
 staged=pd.DataFrame(proposals)
 ledger=pd.DataFrame(holds)
 out.mkdir(parents=True,exist_ok=True)
 po=out/'staged_point_uses.parquet';ph=out/'held_targets.parquet';staged.to_parquet(po,index=False);ledger.to_parquet(ph,index=False)
 receipt={'status':'graph_delta_point_continuity_staged_pending_root_review','inputs':{
  'accepted_points':{'path':str(ACCEPTED),'sha256':accepted_sha,'rows':len(accepted)},'accepted_identity_graph':{'path':str(GRAPH),'sha256':graph_sha,'rows':len(graph)},
  'selected_r2':{'path':str(SELECTED),'sha256':selected_sha},'extension_rule_review':{'path':str(REVIEW),'sha256':review_sha},
  'source_evidence':{'path':str(EVIDENCE),'sha256':sha(EVIDENCE)},'lineage_events':{'path':str(EVENTS),'sha256':sha(EVENTS)}},
  'accepted_same_place_edges_used':len(edges),'candidate_targets_missing_before_application':len(missing),
  'staged_rows':len(staged),'held_rows':len(ledger),'by_year':staged.target_year.value_counts().to_dict() if len(staged) else {},
  'hold_reasons':dict(Counter(r for x in ledger.hold_reasons_json for r in json.loads(x))) if len(ledger) else {},
  'output':{'staged_point_uses':{'path':str(po),'sha256':sha(po),'rows':len(staged)},'held_targets':{'path':str(ph),'sha256':sha(ph),'rows':len(ledger)}},
  'all_staged_admission_allowed_false':bool(len(staged)==0 or not staged.admission_allowed.any()),
  'all_staged_paths_audited_to_exact_unique_modern_carrier':True,
  'limits':['Modern point assignment is explicit spatial continuity inference; no historical measurement is claimed.',
  'Coordinate measurement date remains unknown; population and boundary comparability are not asserted.',
  'Existing accepted point rows were not replaced or duplicated.']}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 return receipt

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=OUT);a=ap.parse_args();print(json.dumps(apply(a.out),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
