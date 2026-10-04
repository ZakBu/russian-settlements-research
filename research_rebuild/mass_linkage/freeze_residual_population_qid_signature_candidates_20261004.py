#!/usr/bin/env python3
"""Freeze review-only packet and exact conditional year-UF/point gains."""
from pathlib import Path
import hashlib,json
import pandas as pd
import numpy as np
from research_rebuild.mass_linkage.stage_residual_population_qid_signature_mass_20261004 import (
    R4,OUT,PAIR_CHECKPOINT,SEL,G,P,COV,sha,pop_int,truth,utc
)
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES, ACCEPTED_COORDINATE_STATUSES

EXP=OUT/'expanded_fetch'; CK=EXP/'progress_2000'; OUTPK=EXP/'final_candidate_packet'

def hash_obj(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def main():
 OUTPK.mkdir(parents=True,exist_ok=True)
 sig=pd.read_csv(CK/'signature_review_candidates.csv',low_memory=False)
 sig['matching_source_pair_count']=pd.to_numeric(sig.matching_source_pair_count,errors='coerce').fillna(0).astype(int)
 sig['event_exact_native_code_guard']=sig.event_exact_native_code_guard.map(truth)
 for c in ['fetched_ru_label_exact','fetched_p764_exact','fetched_physical_p31']:
  sig[c]=sig[c].map(truth)
 sig['candidate_identity_rule_pass']=sig.statement_status.eq('unique_source_pair_signature')&sig.matching_source_pair_count.eq(1)&sig.fetched_ru_label_exact&sig.fetched_p764_exact&sig.fetched_physical_p31&~sig.event_exact_native_code_guard&~sig.current_to_2002_uf_outcome.eq('year_constrained_collision')&~sig.current_to_2010_uf_outcome.eq('year_constrained_collision')
 sig['identity_admitted']=False;sig['population_admitted']=False;sig['point_admitted']=False;sig['candidate_only']=True
 # No multiple-current-QID ambiguity may remain for one historical pair.
 cand=sig[sig.candidate_identity_rule_pass].copy()
 pair_comp=cand.groupby(['old_2002_source_record_id','old_2010_source_record_id']).wikidata_qid.transform('nunique')
 cand['current_qid_count_for_old_pair']=pair_comp
 sig=sig.merge(cand[['wikidata_qid','current_qid_count_for_old_pair']],on='wikidata_qid',how='left')
 sig['current_qid_count_for_old_pair']=pd.to_numeric(sig.current_qid_count_for_old_pair,errors='coerce').fillna(0).astype(int)
 sig['candidate_identity_rule_pass']=sig.candidate_identity_rule_pass&sig.current_qid_count_for_old_pair.eq(1)
 cand=sig[sig.candidate_identity_rule_pass].copy()
 # Attach exact published source cells/context from the frozen all-alternatives ledger.
 cols=['wikidata_qid','current_source_record_id','current_population','current_name_raw','current_type_raw','current_region_raw','current_district_raw','current_native_oktmo_raw','current_native_oktmo_digits','current_p764_raw','current_physical_p31_lineage_qids_json','current_source_sha256','current_source_locator','old_2002_source_record_id','old_2002_population','old_2002_population_quality','old_2002_confidentiality_perturbed','old_2002_name_raw','old_2002_type_raw','old_2002_region_raw','old_2002_district_raw','old_2002_municipality_raw','old_2002_source_sha256','old_2002_source_locator','old_2010_source_record_id','old_2010_population','old_2010_population_quality','old_2010_confidentiality_perturbed','old_2010_name_raw','old_2010_type_raw','old_2010_region_raw','old_2010_district_raw','old_2010_municipality_raw','old_2010_source_sha256','old_2010_source_locator','source_population_vector_unique_among_old_name_type_province_alternatives','old_row_pair_has_required_exact_population_quality','current_to_2002_uf_outcome','current_to_2010_uf_outcome','any_event_exact_native_code_guard']
 wanted=set(cand.wikidata_qid.astype(str)); src=[]
 for ch in pd.read_csv(PAIR_CHECKPOINT,usecols=cols,dtype={'wikidata_qid':str},chunksize=80000,low_memory=False):
  hit=ch[ch.wikidata_qid.isin(wanted)]
  if len(hit):src.append(hit)
 source=pd.concat(src,ignore_index=True) if src else pd.DataFrame(columns=cols)
 # Signature uniquely selects exactly one old pair, preserving same-key competitors.
 key=['wikidata_qid','current_source_record_id','old_2002_source_record_id','old_2010_source_record_id']
 cand=cand.merge(source,on=key,how='left',validate='one_to_one',suffixes=('','_source'))
 cand['source_2002_quality_ok']=cand.old_2002_population_quality.astype(str).eq('direct_published_census_value')
 cand['source_2010_quality_ok']=cand.old_2010_population_quality.astype(str).isin(['direct_published_census_value','secondary_confidentiality_protected_value_exact_scope_unverified'])
 cand['source_population_quality_reviewable']=cand.source_2002_quality_ok&cand.source_2010_quality_ok
 # Simulate exactly against the pinned accepted graph. Candidate edges are only
 # unioned when year constraints still permit them in deterministic QID order.
 sel=pd.read_parquet(SEL,columns=['source_record_id','census_year','population','population_scope','is_additive_settlement_record','entity_grain_status','population_value_quality'])
 sel.source_record_id=sel.source_record_id.astype(str); sel.census_year=sel.census_year.astype(int);sel['pop_int']=sel.population.map(pop_int)
 uf=YearUF(sel.source_record_id.tolist(),sel.census_year.tolist())
 graph=pd.read_parquet(G,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(graph.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(graph.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES):raise RuntimeError('baseline graph statuses not accepted')
 for e in graph.itertuples(index=False):
  if e.relation!='same_place':raise RuntimeError('noncanonical relation in baseline')
  if uf.union_ids(str(e.from_source_record_id),str(e.to_source_record_id))=='year_constrained_collision':raise RuntimeError('baseline graph collision')
 p=pd.read_parquet(P,columns=['target_source_record_id','coordinate_admission_status'])
 p=p[p.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 point_ids=set(p.target_source_record_id.astype(str))
 before_masks=uf.bits_by_row();before_point_roots={uf.find(uf.idx[x]) for x in point_ids if x in uf.idx}
 edge_records=[]
 for r in cand.sort_values('wikidata_qid').to_dict('records'):
  for year,oldid,outcome in [(2002,r['old_2002_source_record_id'],r['current_to_2002_uf_outcome']),(2010,r['old_2010_source_record_id'],r['current_to_2010_uf_outcome'])]:
   if outcome=='already_connected': status='already_connected'
   else: status=uf.union_ids(str(oldid),str(r['current_source_record_id']))
   edge_records.append({'wikidata_qid':r['wikidata_qid'],'historical_year':year,'from_source_record_id':oldid,'to_source_record_id':r['current_source_record_id'],'relation':'same_place','conditional_union_status':status,'candidate_only':True,'identity_admitted':False})
 after_masks=uf.bits_by_row();after_point_roots={uf.find(uf.idx[x]) for x in point_ids if x in uf.idx}
 ids=sel.source_record_id.to_numpy(); years=sel.census_year.to_numpy(); pops=sel.pop_int.to_numpy()
 valid_scope=sel.population_scope.fillna('').astype(str).str.casefold().eq('settlement').to_numpy()&sel.is_additive_settlement_record.fillna(False).to_numpy()&np.isfinite(pd.to_numeric(sel.pop_int,errors='coerce').to_numpy(dtype=float))
 before_j=np.zeros(len(sel),dtype=bool);after_j=np.zeros(len(sel),dtype=bool)
 for i,sid in enumerate(ids):
  root=uf.find(uf.idx[str(sid)])
  # This is after union; baseline roots/masks were snapshotted before union.
  before_j[i]=before_masks[i]==7 and int(before_masks[i]) and root in before_point_roots
  after_j[i]=after_masks[i]==7 and root in after_point_roots
 # `before_j` roots need be evaluated in baseline UF, so reconstruct from snapshots
 # using old node-root map, independent of post-union parents.
 # Restore baseline root lineage from accepted graph with a second deterministic UF.
 base=YearUF(sel.source_record_id.tolist(),sel.census_year.tolist())
 for e in graph.itertuples(index=False):base.union_ids(str(e.from_source_record_id),str(e.to_source_record_id))
 oldroot=np.fromiter((base.find(i) for i in range(len(sel))),dtype=np.int32,count=len(sel))
 base_point_roots={base.find(base.idx[x]) for x in point_ids if x in base.idx}
 before_j=np.array([(before_masks[i]==7 and oldroot[i] in base_point_roots) for i in range(len(sel))],dtype=bool)&valid_scope
 after_j=np.array([(after_masks[i]==7 and uf.find(i) in after_point_roots) for i in range(len(sel))],dtype=bool)&valid_scope
 gains=valid_scope&after_j&~before_j
 rows=[]
 for y in [2002,2010,2021]:
  m=gains&(years==y)
  rows.append({'year':y,'new_joint_point_temporal_rows':int(m.sum()),'new_joint_population_sum':int(np.nansum(pops[m])),'all_quality_rows':int((m&sel.population_value_quality.astype(str).eq('direct_published_census_value').to_numpy()).sum()),'protected_or_secondary_rows':int((m&~sel.population_value_quality.astype(str).eq('direct_published_census_value').to_numpy()).sum())})
 # Preserve all screened signature rows and enriched exact source evidence.
 sig.to_csv(OUTPK/'all_2000_qid_signature_screen.csv',index=False)
 cand.to_csv(OUTPK/'unique_signature_current_binding_source_evidence_candidates.csv',index=False)
 pd.DataFrame(edge_records).to_csv(OUTPK/'conditional_year_uf_candidate_edges.csv',index=False)
 # Raw API response bytes and request-QID correspondence, no re-download.
 oldreq=pd.read_csv(OUT/'fetch_request_uncached_top2000.csv',dtype={'wikidata_qid':str}).head(500)
 newreq=pd.read_csv(EXP/'expanded_fetch_request_to_2000.csv',dtype={'wikidata_qid':str})
 requests=[*oldreq.wikidata_qid.astype(str).tolist(),*newreq.wikidata_qid.astype(str).tolist()]
 rawmanifest=[]
 for i,path in enumerate(sorted((OUT/'raw_entity_batches').glob('raw_entity_batch_*.json')),start=1):
  b=path.read_bytes();d=json.loads(b.decode('utf-8')); returned=sorted(d.get('entities',{}))
  start=(i-1)*50;rq=requests[start:start+50]
  rawmanifest.append({'batch_number':i,'raw_file':str(path),'raw_bytes':len(b),'raw_response_sha256':hashlib.sha256(b).hexdigest(),'requested_qids':rq,'returned_qids':returned,'returned_count':len(returned)})
 pd.DataFrame(rawmanifest).to_json(OUTPK/'raw_response_manifest.json',orient='records',force_ascii=False,indent=2)
 summary={'status':'independent_review_candidates_only_no_identity_population_or_point_admissions','baseline_graph_sha256':sha(G),'baseline_point_uses_sha256':sha(P),'source_pair_checkpoint_sha256':sha(PAIR_CHECKPOINT),'raw_batch_count':len(rawmanifest),'raw_batch_manifest_sha256':sha(OUTPK/'raw_response_manifest.json'),'raw_qids_fetched':len(set(x for m in rawmanifest for x in m['returned_qids'])),'unique_two_year_signature_qids':int((sig.statement_status=='unique_source_pair_signature').sum()),'screen_rows':len(sig),'signature_current_source_rows':int(cand.current_source_record_id.nunique()),'candidate_identity_rule_rows':len(cand),'candidate_qids':int(cand.wikidata_qid.nunique()),'candidate_source_quality_2002_direct_2010_direct_or_protected':int(cand.source_population_quality_reviewable.sum()),'signature_kind_counts':cand.population_signature_kind.value_counts(dropna=False).to_dict(),'gross_signature_endpoint_population_sum_not_net_gain':int(pd.to_numeric(cand.current_population_plus_old_population,errors='coerce').sum()),'gross_current_population_sum':int(pd.to_numeric(cand.current_population,errors='coerce').sum()),'gross_2002_source_population_sum':int(pd.to_numeric(cand.old_2002_source_population,errors='coerce').sum()),'gross_2010_source_population_sum':int(pd.to_numeric(cand.old_2010_source_population,errors='coerce').sum()),'conditional_union_edge_status_counts':pd.DataFrame(edge_records).conditional_union_status.value_counts().to_dict(),'new_joint_row_and_population_by_year':rows,'admission_flags':{'identity':False,'population':False,'point':False},'limits':['P1082 signatures are secondary Wikidata evidence and do not replace publisher populations.','2010 protected-value ±10 cases retain scope-unverified quality.','Cross-year unique typed source context and exact current physical native binding are candidates for independent review; no historical boundary/population equality claim.','Gross endpoint sums overlap rows/components and must not be described as marginal gains.']}
 (OUTPK/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 receipt={'status':summary['status'],'script_sha256':sha(Path(__file__)),'input_pins':{str(x):{'sha256':sha(x),'bytes':x.stat().st_size} for x in [SEL,G,P,PAIR_CHECKPOINT]},'outputs':{x.name:sha(x) for x in sorted(OUTPK.iterdir()) if x.is_file()}}
 (OUTPK/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
