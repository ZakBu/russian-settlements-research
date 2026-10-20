"""Read-only independent commit-point guard for complete model snapshots."""
import hashlib,json
from pathlib import Path
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def require_snapshot(directory,config,code,files):
 d=Path(directory);rp=d/'run_receipt.json';mp=d/'output_manifest.json'
 if not rp.exists() or not mp.exists():raise SystemExit('WAIT_COMPLETE_MODEL_OUTPUT_MANIFEST')
 r=json.loads(rp.read_text());m=json.loads(mp.read_text())
 if not r.get('status','').startswith('COMPUTED'):raise SystemExit('WAIT_MODEL_COMPUTED')
 if m['run_receipt_sha256']!=sha(rp):raise SystemExit('WAIT_MANIFEST_COMMIT_FOR_CURRENT_RECEIPT')
 for key,path in [('configuration_sha256',config),('model_code_sha256',code)]:
  if r[key]!=sha(path) or m[key]!=r[key]:raise SystemExit('WAIT_CURRENT_CODE_CONFIG_MATCHED_MODEL_SNAPSHOT:'+key)
 for file in files:
  p=d/file;info=m['files'].get(file)
  if not info or not p.exists() or info['sha256']!=sha(p):raise SystemExit('WAIT_ATOMIC_MODEL_FILESET:'+file)
 return r,m
