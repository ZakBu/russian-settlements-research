"""Pin completed model derivatives for independent review and exact edge reconstruction."""
from pathlib import Path
import argparse,hashlib,json,shutil
import pyarrow.parquet as pq

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
 return h.hexdigest()
def run(directory):
 receipt=directory/'run_receipt.json';r=json.loads(receipt.read_text())
 if r['status']!='COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW':raise ValueError('Only completed model outputs may be finalized')
 outputs={}
 for p in sorted(directory.iterdir()):
  if p.name.startswith('independent_') or p.name=='output_manifest.json' or p.suffix not in ['.parquet','.csv','.json'] or not p.is_file():continue
  info={'sha256':sha(p),'bytes':p.stat().st_size}
  if p.suffix=='.parquet':info['rows']=pq.ParquetFile(p).metadata.num_rows
  outputs[p.name]=info
 code=Path(__file__).with_name('run_word_model.py');archive=code.parent/'code_snapshots'/r['model_code_sha256']/'run_word_model.py.snapshot'
 if not archive.exists():
  if sha(code)!=r['model_code_sha256']:raise ValueError('Exact model source must be archived before changing it')
  archive.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code,archive)
 if sha(archive)!=r['model_code_sha256']:raise ValueError('Archived implementation hash mismatch')
 result={'status':'FROZEN_DERIVATIVES_PENDING_INDEPENDENT_SCIENTIFIC_REVIEW','target_run_id':r['target_run_id'],'run_receipt_sha256':sha(receipt),'model_code_sha256':r['model_code_sha256'],'configuration_sha256':r['configuration_sha256'],'files':outputs}
 temp=directory/'output_manifest.json.tmp';temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');temp.replace(directory/'output_manifest.json');print('Pinned',len(outputs),'output files in',directory)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);a=p.parse_args();run(a.directory)
