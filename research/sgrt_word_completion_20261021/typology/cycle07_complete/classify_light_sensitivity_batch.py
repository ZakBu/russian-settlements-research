"""Bind/run frozen classifier ONLY after each actual independent population gate.
No scientific rule changes. Full functional profiles remain explicitly unprojected.
"""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
B=Path(__file__).resolve().parent;BASE=B.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True);ap.add_argument('--output',required=True);ap.add_argument('--poll-seconds',type=int,default=5);a=ap.parse_args();manifest=Path(a.manifest);entries=json.loads(manifest.read_text())['entries'];out=Path(a.output);assert not out.exists();out.mkdir(parents=True);done=[];pending=list(entries)
 while pending:
  ready=[]
  for e in pending:
   name=f"{e['scenario']}_cap{e['cap_minutes']:03}";rp=BASE/f'reviews/cycle07_sensitivity_population_types_independent_v1/{name}_population_audit.json';d=Path(e['normalized_output_path'])
   if not rp.exists() or not (d/'receipt.json').exists():continue
   review=json.loads(rp.read_text());assert review['all_checks_passed'] and review['n_failed']==0;assert review['accepted_units_sha256']==sha(d/'normalized_units.parquet');cp=manifest.parent/f'classify_{name}.json';target=B/f"classified_sensitivity_light_source477_v1/{e['scenario']}/cap{e['cap_minutes']:03}_supported_end_forest";log=out/f'{name}.log'
   with log.open('w') as f:
    if not cp.exists():subprocess.run([sys.executable,str(B/'bind_classification_contract_source477_v4.py'),'--normalized',str(d),'--admission',str(rp),'--hierarchy-admission',str(BASE/'reviews/cycle07_sensitivity_actual_independent/raw_source_batch_admission.json'),'--output',str(cp)],check=True,stdout=f,stderr=subprocess.STDOUT)
    contract=json.loads(cp.read_text());assert contract['units_sha256']==review['accepted_units_sha256'] and not contract['context_witnesses'];assert not target.exists();subprocess.run([sys.executable,str(B/'classify_complete.py'),'--contract',str(cp),'--output',str(target)],check=True,stdout=f,stderr=subprocess.STDOUT)
   receipt=json.loads((target/'receipt.json').read_text());scope={'status':'NOT_PROJECTED_FOR_LIGHTWEIGHT_SENSITIVITY_NOT_ABSENCE','primary_population_type_comparison_allowed':True,'full_functional_profile_comparison_allowed':False,'functional_context_empty_registry_is_not_evidence_of_absence':True,'classification_receipt_sha256':sha(target/'receipt.json'),'normalization_receipt_sha256':sha(d/'receipt.json'),'population_audit_sha256':sha(rp)};(target/'PROFILE_SCOPE.json').write_text(json.dumps(scope,indent=2));record={'scenario':e['scenario'],'cap_minutes':e['cap_minutes'],'classification_output_path':str(target),'types_sha256':receipt['files']['complete_typology.parquet'],'receipt_sha256':sha(target/'receipt.json'),'profile_scope_sha256':sha(target/'PROFILE_SCOPE.json'),'n_units':receipt['n_units'],'n_types':receipt['n_types'],'source_population_admission_sha256':sha(rp)};done.append(record);ready.append(e);print(json.dumps(record),flush=True)
   tmp=out/'progress.tmp';tmp.write_text(json.dumps({'status':'RUNNING' if len(done)<len(entries) else 'COMPUTED_ALL31_LIGHT_MEASURED_TYPES_PENDING_INDEPENDENT_TYPE_READBACK','n_closed':len(done),'n_requested':len(entries),'entries':done,'full_functional_profiles_not_projected':True},indent=2));tmp.replace(out/'progress.json')
  for e in ready:pending.remove(e)
  if pending:time.sleep(a.poll_seconds)
if __name__=='__main__':main()
