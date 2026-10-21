"""Pin the exact cycle06 implementation, imported helper and computed derivatives."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import pyarrow.parquet as pq

HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parents[1]

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def run(directory,inputs):
    receipt=directory/'run_receipt.json';r=json.loads(receipt.read_text())
    if r['status']!='COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW':raise ValueError('Cannot freeze incomplete computation')
    if sha(inputs)!=r['configuration_sha256']:raise ValueError('Configuration changed')
    code=HERE/'run_word_model_cycle06.py';helpers=[HERE/'large_city_accessibility_cycle05.py',HERE/'configuration_cycle06.py']
    if sha(code)!=r['model_code_sha256']:raise ValueError('Model implementation changed')
    watched=r['source_sha256']
    for p in [code,*helpers]:
        key=str(p.resolve().relative_to(REPO))
        if key not in watched or watched[key]!=sha(p):raise ValueError('Execution source not captured: '+key)
    archive=HERE/'code_snapshots'/r['model_code_sha256']
    archive.mkdir(parents=True,exist_ok=True)
    snapshots={}
    for p in [code,*helpers]:
        dest=archive/(p.name+'.snapshot')
        if dest.exists() and sha(dest)!=sha(p):raise ValueError('Refusing to replace a different code snapshot')
        if not dest.exists():shutil.copyfile(p,dest)
        snapshots[p.name]={'path':str(dest.relative_to(REPO)),'sha256':sha(dest)}
    outputs={}
    for p in sorted(directory.iterdir()):
        if not p.is_file() or p.name=='output_manifest.json' or p.suffix not in {'.parquet','.csv','.json'}:continue
        item={'sha256':sha(p),'bytes':p.stat().st_size}
        if p.suffix=='.parquet':item['rows']=pq.ParquetFile(p).metadata.num_rows
        outputs[p.name]=item
    manifest={'status':'FROZEN_DERIVATIVES_PENDING_INDEPENDENT_SCIENTIFIC_REVIEW','target_run_id':r['target_run_id'],'model_code_sha256':r['model_code_sha256'],'configuration_sha256':r['configuration_sha256'],'configuration_path':str(inputs.resolve().relative_to(REPO)),'run_receipt_sha256':sha(receipt),'execution_source_snapshots':snapshots,'files':outputs}
    (directory/'output_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Pinned',len(outputs),'outputs and all execution source snapshots')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);a=p.parse_args();run(a.directory,a.inputs)
