"""Run immutable light-view contracts with at most two subprocesses.
Only execution orchestration: no scientific inputs, rules or receipts are altered.
"""
import argparse,concurrent.futures,hashlib,json,subprocess,sys,threading,time
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True);ap.add_argument('--normalizer',required=True);ap.add_argument('--output',required=True);ap.add_argument('--workers',type=int,default=2);a=ap.parse_args();assert a.workers in (1,2);manifest=Path(a.manifest);data=json.loads(manifest.read_text());code=Path(a.normalizer).resolve();codehash=sha(code);out=Path(a.output);assert not out.exists();out.mkdir(parents=True);lock=threading.Lock();results=[];started=time.time()
 def execute(e):
  cp=Path(e['contract_path']);assert sha(cp)==e['contract_sha256'];target=Path(e['normalized_output_path']);assert not target.exists();log=out/f"{e['scenario']}_cap{e['cap_minutes']:03}.log";t=time.time()
  with log.open('w') as f:r=subprocess.run([sys.executable,str(code),'--contract',str(cp),'--output',str(target)],stdout=f,stderr=subprocess.STDOUT)
  record={**e,'exit_code':r.returncode,'seconds':time.time()-t,'log_path':str(log.resolve())}
  if r.returncode==0:
   receipt=target/'receipt.json';d=json.loads(receipt.read_text());record.update(receipt_sha256=sha(receipt),normalized_units_sha256=d['normalized_units_sha256'],effective_nodes_sha256=d['effective_nodes_sha256'],n_units=d['n_units'],unit_role_counts=d['unit_role_counts'])
  with lock:
   results.append(record);payload={'status':'RUNNING' if len(results)<len(data['entries']) else 'COMPUTED_ALL' if all(x['exit_code']==0 for x in results) else 'FAILED','normalizer_sha256':codehash,'manifest_sha256':sha(manifest),'n_closed':len(results),'n_requested':len(data['entries']),'seconds':time.time()-started,'entries':results};tmp=out/'progress.tmp';tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2));tmp.replace(out/'progress.json');print(json.dumps({k:record.get(k) for k in ('scenario','cap_minutes','exit_code','n_units','seconds')}),flush=True)
  return record
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:records=list(pool.map(execute,data['entries']))
 assert sha(code)==codehash;assert all(r['exit_code']==0 for r in records),'See immutable per-view logs and progress'
if __name__=='__main__':main()
