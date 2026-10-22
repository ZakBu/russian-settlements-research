#!/usr/bin/env python3
"""Index deliverable bytes, excluding raw books, generated caches and this index itself."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def run():
 rows=[]
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file() or p.name=='artifact_manifest.json' or '__pycache__' in p.parts:continue
  if subprocess.run(['git','check-ignore','-q',str(p)],cwd=ROOT).returncode==0:continue
  rows.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
 receipt={'title':'SGRT Word national preliminary pass','date_moscow':'2026-10-21','starting_commit':'5443e767c3313f001d35e8f6b42f667558f5ebc3','files':rows,'file_count':len(rows),'total_bytes':sum(x['bytes'] for x in rows),'raw_books_included':False,'source_master_reconstructs_from_existing_committed_parts':True}
 (ROOT/'coordination/artifact_manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(receipt['file_count'],receipt['total_bytes'])
if __name__=='__main__':run()
