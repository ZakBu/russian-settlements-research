#!/usr/bin/env python3
"""Recompute the national experiment in a new directory and compare all tabular outputs."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,time
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def read(p):return pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p,low_memory=False)
def run():
 start=time.monotonic();out=Path(tempfile.mkdtemp(prefix='sgrt_word_replay_'));report={'status':'RUNNING','output':str(out),'commands':[],'comparisons':[],'scope':'author computation replay; independent algorithms in reviews/statistics'}
 inputs=[REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',REPO/'research/sgrt_national_integration_20261019/core/external_federal_features.csv',REPO/'research/sgrt_national_integration_20261019/screening/support_point_profiles.parquet']
 inputs +=[ROOT/m/'settlement_features.parquet' for m in ['medical','education','commerce']]
 inputs +=[ROOT/'education/validation_external_edges.csv']
 before={str(p.relative_to(REPO)):sha(p) for p in inputs}
 env=os.environ.copy();env.update(SGRT_RESULT_DIR=str(out),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
 try:
  for script,args in [('run_model.py',['--output',str(out)]),('compare_models.py',[]),('extended_checks.py',[]),('run_demographic_scaffold.py',[])]:
   t=time.monotonic();cmd=[sys.executable,str(ROOT/'model'/script)]+args;p=subprocess.run(cmd,cwd=REPO,env=env,capture_output=True)
   log=ROOT/'coordination'/('replay_'+script.replace('.py','.log'));log.write_bytes(p.stdout+b'\n'+p.stderr)
   report['commands'].append({'script':script,'exit_code':p.returncode,'seconds':round(time.monotonic()-t,3),'log':str(log.relative_to(ROOT)),'script_sha256':sha(ROOT/'model'/script)})
   if p.returncode:raise RuntimeError('Replay failed '+script)
  for p in sorted(out.rglob('*')):
   if not p.is_file() or not p.name.endswith(('.parquet','.csv','.csv.gz')):continue
   rel=p.relative_to(out);original=ROOT/'results'/rel
   if not original.exists():raise RuntimeError('Missing original '+str(rel))
   left,right=read(original),read(p)
   pd.testing.assert_frame_equal(left,right,check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-10)
   report['comparisons'].append({'table':str(rel),'rows':len(right),'columns':len(right.columns),'matches':True,'original_sha256':sha(original),'replay_sha256':sha(p)})
  after={str(p.relative_to(REPO)):sha(p) for p in inputs};report['source_bytes_unchanged']=before==after
  assert before==after
  report['status']='PASS'
 except Exception as e:report['status']='FAIL';report['error']=repr(e)
 report['input_sha256']=before;report['tables_compared']=len(report['comparisons']);report['seconds']=round(time.monotonic()-start,3)
 (ROOT/'coordination/replay_receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['comparisons','input_sha256']},ensure_ascii=False,indent=2))
 if report['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':run()
