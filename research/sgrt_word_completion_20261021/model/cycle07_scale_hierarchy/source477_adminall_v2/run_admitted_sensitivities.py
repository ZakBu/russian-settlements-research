"""Sequential execution only; unchanged admitted scientific driver, no50claim."""
from pathlib import Path
import json,subprocess,hashlib
HERE=Path(__file__).resolve().parent;BASE=next(p for p in HERE.parents if (p/'transport').is_dir() and (p/'model').is_dir())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
primary=HERE/'output_primary_v1/run_receipt.json';assert json.loads(primary.read_text())['status']=='COMPUTED_PRIMARY_PATH_AND_50_CONDITIONAL_STABILITY_REPLICATES'
ip=BASE/'reviews/cycle07_controller_independent/sensitivity_source477_v2/index.json';index=json.loads(ip.read_text());assert index['all_checks_passed']is True
admissions={r['scenario']:r for r in index['admissions']};completed=[]
for scenario in ['tau30','tau90','gamma0.5','gamma2','directed_max','extended180']:
 r=admissions[scenario];ad=BASE/r['admission'];assert sha(ad)==r['sha256'];out=HERE/('output_sensitivity_'+scenario.replace('.','p')+'_v1');assert sha(out/'pre_execution_binding.json')==r['pre_execution_binding_sha256']
 log=HERE/('sensitivity_'+scenario.replace('.','p')+'_execution.log')
 with open(log,'w')as f:
  proc=subprocess.run(['python','-u',str(HERE/'run.py'),'--resume','--scenario',scenario,'--baseline-only','--cache','/tmp/sgrt_cycle07_source477_adminall_cache_v1','--output',str(out),'--admission',str(ad)],stdout=f,stderr=subprocess.STDOUT,cwd=BASE)
 assert proc.returncode==0,(scenario,proc.returncode)
 receipt=out/'baseline_stage_receipt.json';assert json.loads(receipt.read_text())['status']=='BASELINE_ONLY_BOOTSTRAP_NOT_COMPLETE'
 completed.append({'scenario':scenario,'baseline_receipt_sha256':sha(receipt),'output':str(out.relative_to(BASE)),'execution_log_sha256':sha(log),'all_files_sha256':{p.name:sha(p)for p in out.iterdir()if p.is_file()},'bootstrap50_computed':False})
 (HERE/'admitted_sensitivity_batch_checkpoint.json').write_text(json.dumps({'status':'RUNNING_SEQUENTIAL_BASELINE_ONLY_SENSITIVITIES','completed':completed},indent=2));print('COMPLETED_ADMITTED_BASELINE_SENSITIVITY',scenario,flush=True)
result={'status':'ALL_SIX_PREREGISTERED_BASELINE_ONLY_SENSITIVITIES_ACTUALLY_COMPUTED_PENDING_INDEPENDENT_RESULT_REVIEW','primary_complete_receipt_sha256':sha(primary),'admission_index_sha256':sha(ip),'batch_code_sha256':sha(Path(__file__)),'completed':completed,'no_50bootstrap_claim_per_sensitivity':True}
(HERE/'admitted_sensitivity_batch_receipt.json').write_text(json.dumps(result,indent=2));print('ALL_SIX_SENSITIVITIES_COMPLETE',flush=True)
