#!/usr/bin/env python3
"""Meaningful fail-closed tests: preliminary acceptance, removed gates, stale bytes and fake proof."""
import copy,hashlib,json,tempfile
from pathlib import Path
from check_release_gate import HERE,evaluate

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 policy=json.loads((HERE/'strict_word_gates.json').read_text());evidence=json.loads((HERE/'current_gate_evidence.json').read_text());checks=[]
 def check(name,condition):
  if not condition:raise AssertionError(name)
  checks.append({'check':name,'pass':True})
 r=evaluate(policy,evidence);check('all_open_blocks_release',not r['scientific_final_allowed'] and r['requirements_open']==32)
 p=copy.deepcopy(policy);p['requirements']=p['requirements'][:1]
 try:evaluate(p,evidence);rejected=False
 except ValueError:rejected=True
 check('cannot_remove_word_requirements',rejected)
 p=copy.deepcopy(policy);p['requirements'][0]['required_for_scientific_release']=False
 try:evaluate(p,evidence);rejected=False
 except ValueError:rejected=True
 check('cannot_downgrade_required_gate',rejected)
 e=copy.deepcopy(evidence)
 for row in e['requirements'].values():row.update(state='CLOSED',implementation='CLOSED',data='CLOSED',scientific='CLOSED',author='same',reviewer='same')
 r=evaluate(policy,e);check('self_review_and_status_only_cannot_pass',not r['scientific_final_allowed'])
 with tempfile.TemporaryDirectory(prefix='gate_test_',dir=HERE) as temp:
  file=Path(temp)/'reviewed_assertions.json';file.write_text(json.dumps({'verified':True,'target_run_id':e['target_run_id']}))
  e['model_snapshot']={'artifact':str(file),'sha256':sha(file)}
  for req in policy['requirements']:
   row=e['requirements'][req['id']];row['author']='author';row['reviewer']='independent_reviewer'
   row['criteria']={c['id']:{'status':'PASS','verified_by':'independent_reviewer','artifact':str(file),'sha256':sha(file),'review_rationale':'Synthetic proof for exercising validator, never scientific evidence.','assertions':[{'pointer':'verified','operator':'eq','expected':True}]} for c in req['checks']}
  r=evaluate(policy,e);check('complete_valid_synthetic_evidence_exercises_accept_path',r['scientific_final_allowed'])
  broken=copy.deepcopy(e);broken['requirements']['W06']['criteria'][policy['requirements'][5]['checks'][0]['id']]['assertions'][0]['expected']=False
  r=evaluate(policy,broken);check('false_json_assertion_blocks_release',not r['scientific_final_allowed'])
  file.write_text(json.dumps({'verified':False}))
  r=evaluate(policy,e);check('changed_frozen_bytes_invalidates_acceptance',not r['scientific_final_allowed'])
 e=copy.deepcopy(evidence);e['requirements']['W06']['state']='BLOCKED_EXTERNAL'
 r=evaluate(policy,e);check('external_blocker_never_counts_closed',not r['scientific_final_allowed'] and r['requirements_open']==32)
 receipt={'status':'PASS_GATE_IMPLEMENTATION_ONLY','checks':checks,'synthetic_accept_fixture_persisted':False,'scientific_word_research_accepted':False}
 (HERE/'gate_selftest_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
