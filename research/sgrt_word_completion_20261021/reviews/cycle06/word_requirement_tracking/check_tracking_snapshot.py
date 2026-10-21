#!/usr/bin/env python3
"""Pointer/literal/legacy integrity checks only; never judges scientific completion."""
from pathlib import Path
from docx import Document
import json,hashlib,csv
H=Path(__file__).resolve().parent;R=H.parents[4];B=R/'research/sgrt_word_completion_20261021'
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
d=json.loads((H/'requirement_tracking.json').read_text());c=json.loads((H/'evidence_catalog.json').read_text())['evidence'];g=json.loads((B/'reviews/strict_word_gates.json').read_text());old=json.loads((B/'reviews/strict_gate_receipt.json').read_text());word=Document(H/'original_user_concept.docx');checks=[]
def ck(n,v):checks.append({'check':n,'pass':bool(v)});assert v,n
ck('exact32legacy_requirementIDs', [r['requirement_id'] for r in d['requirements']]==[r['id'] for r in g['requirements']])
ck('legacy_policy_sha_unchanged',sha(B/'reviews/strict_word_gates.json')==d['legacy_policy_sha256'])
ck('legacy_stop_receipt_sha_unchanged',sha(B/'reviews/strict_gate_receipt.json')==d['legacy_stop_receipt_sha256'])
ck('legacy9of32decision_not_changed',old['requirements_closed']==9 and old['requirements_total']==32 and old['decision']=='RETURN_TO_REPAIR_LOOP')
ck('no_new_approval_count_or_stop_verdict',d['current_cycle06_accepted_requirements_count'] is None and d['not_a_new_stop_decision'] is True)
ck('exact_originalWord_bytes_preserved',sha(H/'original_user_concept.docx')==d['original_word_sha256'])
ck('legacy_export_matches_policyWordtextSHA',sha(B/'reviews/original_word_source.txt')==g['source_word_text_sha256'])
for rid,r,gg in zip([x['id'] for x in g['requirements']],d['requirements'],g['requirements']):
 ck(rid+'_exactlegacy96criterion_mapping',r['legacy_checks_immutable']==[{'id':x['id'],'criterion':x['criterion']} for x in gg['checks']])
 ck(rid+'_no_self_scientific_requirement_acceptance',r['current_requirement_acceptance']=='NOT_REASSESSED_NO_SELF_ACCEPTANCE')
 ck(rid+'_nonempty_boundary_gap_action',all(r[k] for k in ['declared_operational_estimand_and_scope','known_open_gap','next_falsifiable_step','literal_vs_added_acceptance_condition']))
 for q in r['word_source_quotes']:
  p=word.paragraphs[q['paragraph_1based']-1];ck(rid+'_literal_P'+str(q['paragraph_1based']),q['literal_visible_text']==p.text and q['omml_math_texts']==[x.text for x in p._p.xpath('.//m:t')])
 for eid in r['evidence_ids']:ck(rid+'_evidence_pointer_exists_'+eid,eid in c)
 ck(rid+'_pending_output_no_fabricated_SHA',all(x['sha256'] is None and x['actual_bound_output_path'] is None for x in r['pending_output_contracts']))
for eid,x in c.items():ck('artifact_SHA_'+eid,sha(R/x['path'])==x['sha256'])
with open(H/'requirement_tracking.csv') as f:rows=list(csv.DictReader(f));ck('CSV32consistentIDs',[x['requirement_id'] for x in rows]==[x['requirement_id'] for x in d['requirements']])
r={'status':'TECHNICAL_POINTER_AND_LITERAL_QUOTE_CHECKS_PASS_NOT_SCIENTIFIC_ACCEPTANCE','n_checks':len(checks),'n_failed':sum(not x['pass'] for x in checks),'checks':checks,'requirement_approvals_created':0,'new_stop_decision_created':False,'input_sha256':{p.name:sha(p) for p in [H/'requirement_tracking.json',H/'evidence_catalog.json',H/'word_source_index.json',H/'original_user_concept.docx']},'code_sha256':sha(Path(__file__))};(H/'technical_integrity_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:r[k] for k in ['status','n_checks','n_failed']}))
