#!/usr/bin/env python3
"""Fail-closed Word release gate. Does not equate a successful build to scientific validity.

This is a review-evidence verifier, not a way to manufacture scientific truth.
Each passed criterion must point to frozen bytes and an independently reviewed assertion.
Exit0: every Word gate CLOSED with verified evidence; exit1: repairs remain; exit2: invalid schema.
"""
from pathlib import Path
import argparse,csv,hashlib,json,re,sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
PASS='CLOSED'

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()

def artifact_path(value):
 p=Path(value)
 return p if p.is_absolute() else REPO/p

def json_value(data,pointer):
 if pointer in ('','/'):return data
 parts=pointer.lstrip('/').split('/') if pointer.startswith('/') else pointer.split('.')
 for part in parts:
  part=part.replace('~1','/').replace('~0','~')
  data=data[int(part)] if isinstance(data,list) else data[part]
 return data

def assertion_pass(value,operator,expected):
 if operator=='eq':return type(value)==type(expected) and value==expected
 if operator=='ge':return isinstance(value,(int,float)) and not isinstance(value,bool) and value>=expected
 if operator=='le':return isinstance(value,(int,float)) and not isinstance(value,bool) and value<=expected
 if operator=='nonempty':return value is not None and len(value)>0
 if operator=='in':return value in expected
 raise ValueError('Unknown assertion operator '+str(operator))

def proof_errors(proof,reviewer):
 errors=[]
 if proof.get('status')!='PASS':errors.append('criterion_not_independently_passed')
 if proof.get('verified_by')!=reviewer:errors.append('criterion_reviewer_not_requirement_reviewer')
 if not proof.get('review_rationale'):errors.append('missing_scientific_or_source_review_rationale')
 file=proof.get('artifact');expected=proof.get('sha256')
 if not file or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):return errors+['missing_frozen_artifact_and_sha256']
 p=artifact_path(file)
 if not p.is_file():return errors+['evidence_artifact_not_available']
 if sha(p)!=expected:return errors+['evidence_bytes_changed_after_review']
 for dependency in proof.get('source_artifacts',[]):
  source=artifact_path(dependency.get('artifact',''))
  if not source.is_file() or sha(source)!=dependency.get('sha256'):errors.append('reviewed_source_missing_or_changed:'+str(dependency.get('artifact')))
 # Scientific criteria may be explicit independent decisions, but must still be
 # machine-readable source-backed receipts, not free-standing prose claims.
 assertions=proof.get('assertions',[])
 if not assertions:return errors+['no_machine_readable_assertions']
 try:data=json.loads(p.read_text())
 except Exception:return errors+['criterion_receipt_not_json']
 for a in assertions:
  try:
   value=json_value(data,a['pointer'])
   if not assertion_pass(value,a['operator'],a.get('expected')):errors.append('assertion_false:'+str(a.get('pointer')))
  except Exception as e:errors.append('assertion_invalid:'+str(a.get('pointer'))+':'+type(e).__name__)
 return errors

def evaluate(policy,evidence):
 if policy.get('schema_version')!=1 or evidence.get('schema_version')!=1:raise ValueError('Unsupported schema_version')
 required=policy['requirements'];provided=evidence.get('requirements',{});expected_ids={r['id'] for r in required}
 if len(required)!=32 or expected_ids!={f'W{i:02d}' for i in range(1,33)}:raise ValueError('All32originalWordrequirementsmustremaininthereleasepolicy')
 if not all(r.get('required_for_scientific_release') is True and len(r.get('checks',[]))>=3 for r in required):raise ValueError('RequiredWordgatescannotbedowngradedorremoved')
 if set(provided)-expected_ids:raise ValueError('Unknown Word requirement IDs')
 target=evidence.get('target_run_id');global_errors=[]
 snapshot=evidence.get('model_snapshot')
 if not target:global_errors.append('missing_target_run_id')
 if not isinstance(snapshot,dict):global_errors.append('missing_frozen_current_model_snapshot')
 else:
  p=artifact_path(snapshot.get('artifact',''))
  if not p.is_file() or sha(p)!=snapshot.get('sha256'):global_errors.append('current_model_snapshot_missing_or_changed')
 rows=[]
 for requirement in required:
  rid=requirement['id'];record=provided.get(rid,{});errors=[]
  if record.get('state')!=PASS:errors.append('state='+str(record.get('state','MISSING')))
  for dim in ['implementation','data','scientific']:
   if record.get(dim)!=PASS:errors.append(dim+'='+str(record.get(dim,'MISSING')))
  if record.get('target_run_id')!=target:errors.append('evidence_for_different_target_run')
  author,reviewer=record.get('author'),record.get('reviewer')
  if not author or not reviewer or author==reviewer:errors.append('missing_independent_author_reviewer')
  checks=record.get('criteria',{});verified=0
  for criterion in requirement['checks']:
   proof=checks.get(criterion['id'])
   if proof is None:errors.append('missing:'+criterion['id'])
   else:
    criterion_errors=proof_errors(proof,reviewer)
    if not criterion_errors:verified+=1
    errors += [criterion['id']+':'+e for e in criterion_errors]
  blocker=record.get('external_blocker')
  if record.get('state')=='BLOCKED_EXTERNAL':
   # A blocker is useful to schedule alternatives, never a completed research gate.
   if not isinstance(blocker,dict) or not all(blocker.get(k) for k in ['attempts_receipt','alternatives_checked','next_action']):errors.append('external_blocker_not_documented_with_alternatives')
  rows.append({'requirement_id':rid,'state':'CLOSED' if not errors else 'NEEDS_REPAIR','declared_state':record.get('state','MISSING'),'criteria_verified':verified,'criteria_total':len(requirement['checks']),'dimensions':{d:record.get(d,'MISSING') for d in ['implementation','data','scientific']},'errors':errors,'next_repair':record.get('next_repair') or requirement['next_repair'],'scientific_release_allowed':not errors})
 closed=sum(r['state']=='CLOSED' for r in rows);ok=closed==len(rows) and not global_errors
 return {'schema_version':1,'target_run_id':target,'decision':'ACCEPT_COMPLETE_WORD_RESEARCH' if ok else 'RETURN_TO_REPAIR_LOOP','scientific_final_allowed':ok,'completion_claim_allowed':ok,'requirements_total':len(rows),'requirements_closed':closed,'requirements_open':len(rows)-closed,'criteria_verified':sum(r['criteria_verified'] for r in rows),'criteria_total':sum(r['criteria_total'] for r in rows),'dimension_closed_counts':{d:sum(r['dimensions'][d]==PASS for r in rows) for d in ['implementation','data','scientific']},'global_errors':global_errors,'requirements':rows,'policy_sha256':None,'evidence_sha256':None,'important':'BLOCKED_EXTERNAL and disclosed limitations do not mean CLOSED. A negative scientific finding may close a valid analysis; absence of data may not.'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,default=HERE/'strict_word_gates.json');ap.add_argument('--evidence',type=Path,default=HERE/'current_gate_evidence.json');ap.add_argument('--receipt',type=Path,default=HERE/'strict_gate_receipt.json');ap.add_argument('--queue',type=Path,default=HERE/'current_repair_queue.csv');args=ap.parse_args()
 # Agent writes remain restricted to the assigned review directory.
 for p in [args.receipt,args.queue]:
  if not p.resolve().is_relative_to(HERE):raise ValueError('Output must remain inside strict guardian reviews directory')
 try:
  report=evaluate(json.loads(args.policy.read_text()),json.loads(args.evidence.read_text()));report['policy_sha256']=sha(args.policy);report['evidence_sha256']=sha(args.evidence)
  args.receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  with args.queue.open('w',newline='') as f:
   fields=['requirement_id','state','errors','next_repair'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
   for r in report['requirements']:
    if r['state']!='CLOSED':w.writerow({k:('|'.join(r[k]) if k=='errors' else r[k]) for k in fields})
  print(json.dumps({k:report[k] for k in ['decision','scientific_final_allowed','requirements_total','requirements_closed','requirements_open','global_errors']},ensure_ascii=False,indent=2))
  return 0 if report['scientific_final_allowed'] else 1
 except Exception as e:
  print(json.dumps({'decision':'INVALID_GATE_EVIDENCE','scientific_final_allowed':False,'error':str(e)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
