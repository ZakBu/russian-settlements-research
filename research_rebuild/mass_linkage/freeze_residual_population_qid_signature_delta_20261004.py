#!/usr/bin/env python3
"""Freeze the post-2k fetch as a separate, candidate-only review packet."""
from pathlib import Path
import hashlib, json
import pandas as pd
from research_rebuild.mass_linkage.stage_residual_population_qid_signature_mass_20261004 import (
    R4, OUT, SEL, PAIR_CHECKPOINT, sha, utc, truth
)

EXP = OUT / 'expanded_fetch'
RAW = OUT / 'raw_entity_batches'
BASE = EXP / 'final_candidate_packet' / 'all_2000_qid_signature_screen.csv'
CK = EXP / 'round2_progress' / 'checkpoint_007000' / 'cumulative_signature_review_candidates.csv'
INDEX = EXP / 'source_pair_signature_eval_index.parquet'
PK = EXP / 'final_candidate_packet_delta_post2000_5000'

def hbytes(b): return hashlib.sha256(b).hexdigest()

def main():
    if PK.exists():
        raise RuntimeError(f'packet path already exists; refusing to overwrite: {PK}')
    PK.mkdir(parents=True)
    base = pd.read_csv(BASE, dtype={'wikidata_qid': str}, low_memory=False)
    cumulative = pd.read_csv(CK, dtype={'wikidata_qid': str}, low_memory=False)
    base_ids = set(base.wikidata_qid.astype(str))
    delta = cumulative[~cumulative.wikidata_qid.astype(str).isin(base_ids)].copy()
    if len(base_ids) != 2000 or delta.wikidata_qid.nunique() != 5000 or len(delta) != 5000:
        raise RuntimeError(f'expected 2k + 5k unique screen rows; found {len(base_ids)}, {len(delta)}, {delta.wikidata_qid.nunique()}')
    delta['matching_source_pair_count'] = pd.to_numeric(delta.matching_source_pair_count, errors='coerce').fillna(0).astype(int)
    for c in ['fetched_ru_label_exact', 'fetched_p764_exact', 'fetched_physical_p31', 'event_exact_native_code_guard']:
        delta[c] = delta[c].map(truth)
    delta['candidate_identity_rule_pass'] = (
        delta.statement_status.eq('unique_source_pair_signature') &
        delta.matching_source_pair_count.eq(1) & delta.fetched_ru_label_exact &
        delta.fetched_p764_exact & delta.fetched_physical_p31 &
        ~delta.event_exact_native_code_guard &
        ~delta.current_to_2002_uf_outcome.eq('year_constrained_collision') &
        ~delta.current_to_2010_uf_outcome.eq('year_constrained_collision'))
    delta['identity_admitted'] = False
    delta['population_admitted'] = False
    delta['point_admitted'] = False
    delta['candidate_only'] = True
    prelim = delta[delta.candidate_identity_rule_pass].copy()
    pair_key = ['old_2002_source_record_id', 'old_2010_source_record_id']
    prelim['current_qid_count_for_old_pair'] = prelim.groupby(pair_key).wikidata_qid.transform('nunique')
    qcounts = prelim[['wikidata_qid', 'current_qid_count_for_old_pair']]
    delta = delta.drop(columns=['current_qid_count_for_old_pair'], errors='ignore').merge(qcounts, on='wikidata_qid', how='left')
    delta['current_qid_count_for_old_pair'] = pd.to_numeric(delta.current_qid_count_for_old_pair, errors='coerce').fillna(0).astype(int)
    delta['candidate_identity_rule_pass'] &= delta.current_qid_count_for_old_pair.eq(1)
    cand = delta[delta.candidate_identity_rule_pass].copy()

    # Keep every source-key alternative for every newly fetched QID, not just
    # the signature-matching pair, then attach literal selected-source rows.
    idx = pd.read_parquet(INDEX)
    new_ids = set(delta.wikidata_qid.astype(str))
    alternatives = idx[idx.wikidata_qid.astype(str).isin(new_ids)].copy()
    alternatives['candidate_only'] = True
    alternatives['identity_admitted'] = False
    alternatives['population_admitted'] = False
    source_ids = set(alternatives.current_source_record_id.dropna().astype(str))
    source_ids |= set(alternatives.old_2002_source_record_id.dropna().astype(str))
    source_ids |= set(alternatives.old_2010_source_record_id.dropna().astype(str))
    src_cols = ['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','population_value_quality','source_path','source_sha256','source_locator','source_population_raw','source_raw_line','displaced_source_record_id','publication_binding_basis']
    selected = pd.read_parquet(SEL, columns=src_cols)
    selected = selected[selected.source_record_id.astype(str).isin(source_ids)].copy()
    quality = selected.set_index(selected.source_record_id.astype(str)).population_value_quality.astype(str).to_dict()
    cand['old_2002_population_quality'] = cand.old_2002_source_record_id.astype(str).map(quality)
    cand['old_2010_population_quality'] = cand.old_2010_source_record_id.astype(str).map(quality)

    # Preserve full raw P1082 statement JSON and entity-level lineage. The raw
    # response itself remains the authoritative byte source, pinned below.
    raw_entities = {}
    raw_manifest = []
    for path in sorted(RAW.glob('raw_entity_batch_*.json')):
        b = path.read_bytes(); obj = json.loads(b.decode('utf-8'))
        ent = obj.get('entities', {})
        raw_manifest.append({'file': str(path), 'sha256': hbytes(b), 'bytes': len(b), 'returned_qids': sorted(map(str, ent.keys())), 'returned_count': len(ent)})
        for q, e in ent.items():
            if str(q) in new_ids:
                raw_entities[str(q)] = e
    if set(raw_entities) != new_ids:
        raise RuntimeError(f'raw entity coverage mismatch: {len(raw_entities)} of {len(new_ids)}')
    claim_rows=[]
    entity_rows=[]
    for q,e in sorted(raw_entities.items()):
        compact=json.dumps(e,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        cl=e.get('claims',{})
        entity_rows.append({'wikidata_qid':q,'raw_entity_sha256':hbytes(compact),'raw_label_ru':e.get('labels',{}).get('ru',{}).get('value',''),'raw_label_en':e.get('labels',{}).get('en',{}).get('value',''),'P31_claims_json':json.dumps(cl.get('P31',[]),ensure_ascii=False,separators=(',',':')),'P764_claims_json':json.dumps(cl.get('P764',[]),ensure_ascii=False,separators=(',',':'))})
        for statement in cl.get('P1082',[]):
            claim_rows.append({'wikidata_qid':q,'statement_id':statement.get('id'),'rank':statement.get('rank'),'claim_json':json.dumps(statement,ensure_ascii=False,separators=(',',':'))})
    pd.DataFrame(delta).to_csv(PK/'new_5000_signature_screen.csv',index=False)
    pd.DataFrame(cand).to_csv(PK/'single_pair_current_binding_candidates.csv',index=False)
    alternatives.to_csv(PK/'all_old_source_pair_alternatives.csv',index=False)
    selected.to_csv(PK/'literal_selected_source_context.csv',index=False)
    pd.DataFrame(entity_rows).to_csv(PK/'raw_entity_claim_index.csv',index=False)
    pd.DataFrame(claim_rows).to_csv(PK/'raw_P1082_statements.csv',index=False)
    (PK/'raw_batch_manifest.json').write_text(json.dumps(raw_manifest,ensure_ascii=False,indent=2)+'\n')
    # Keep request orders that led to the 5k delta. Exact returned QID mapping is
    # also in the raw batch manifest; this row list fixes the intended pool order.
    request_files=[EXP/'expanded_fetch_request_next5000.csv', EXP/'expanded_fetch_request_round2_remaining4500.csv', EXP/'expanded_fetch_request_round2_remaining3500.csv', EXP/'expanded_fetch_request_round2_remaining3000.csv', EXP/'expanded_fetch_request_to7000_remaining2050.csv', EXP/'expanded_fetch_request_to7000_remaining1550.csv']
    req_frames=[]
    for f in request_files:
        if f.exists():
            r=pd.read_csv(f,dtype={'wikidata_qid':str})
            if 'wikidata_qid' in r:
                r=r[r.wikidata_qid.astype(str).isin(new_ids)].copy(); r['request_file']=f.name; req_frames.append(r)
    request=pd.concat(req_frames,ignore_index=True) if req_frames else pd.DataFrame(columns=['wikidata_qid','request_file'])
    request=request.drop_duplicates('wikidata_qid',keep='first')
    request.to_csv(PK/'new_qid_fetch_request_lineage.csv',index=False)
    summary={
      'status':'candidate_only_independent_review_required_no_identity_population_or_point_admission',
      'created_utc':utc(),'seed':20261004,
      'baseline':'accepted_mass_sixth_reviewed (diagnostic baseline only; root may have since promoted later snapshots)',
      'baseline_graph_sha256':'cc62fc8d3184c43f6ce09cea0ce71618077347ea4dee0f53ad9709f5c20a8241',
      'baseline_point_uses_sha256':'a67529375e63391e7d05e3ab902ff20884ec3fd4483c7b0bbc988ca056b3c994',
      'source_pair_index_sha256':sha(INDEX),'source_pair_ledger_sha256':sha(PAIR_CHECKPOINT),
      'raw_qids_total':len(set(q for m in raw_manifest for q in m['returned_qids'])),
      'delta_qids_post_previously_frozen_2000':len(new_ids),
      'delta_screen_rows':len(delta),
      'status_counts':delta.statement_status.value_counts(dropna=False).to_dict(),
      'single_pair_current_binding_candidate_qids':int(cand.wikidata_qid.nunique()),
      'single_pair_current_binding_candidate_rows':len(cand),
      'reviewable_population_quality_qids':int((cand.old_2002_population_quality.eq('direct_published_census_value') & cand.old_2010_population_quality.isin(['direct_published_census_value','secondary_confidentiality_protected_value_exact_scope_unverified'])).sum()),
      'population_signature_kind_counts':cand.population_signature_kind.value_counts(dropna=False).to_dict(),
      'all_source_pair_alternative_rows_for_delta_qids':len(alternatives),
      'selected_source_context_rows':len(selected),
      'raw_P1082_claim_rows':len(claim_rows),
      'request_lineage_unique_qids':int(request.wikidata_qid.nunique()),
      'raw_batch_count':len(raw_manifest),
      'raw_batch_manifest_sha256':sha(PK/'raw_batch_manifest.json'),
      'admission_flags':{'identity':False,'population':False,'point':False},
      'limitations':['P1082 claims are secondary corroboration and do not replace publisher population values.','2010 protected-value cases retain their published protection status.','Signature and source-context rows remain candidates pending independent review.','Conditional baseline metrics from earlier packet are not represented as current marginal gain.']}
    (PK/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    receipt={'status':summary['status'],'script_sha256':sha(Path(__file__)),'inputs':{str(f):{'sha256':sha(f),'bytes':f.stat().st_size} for f in [BASE,CK,INDEX,PAIR_CHECKPOINT,SEL]},'outputs':{p.name:sha(p) for p in sorted(PK.iterdir()) if p.is_file()}}
    (PK/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
