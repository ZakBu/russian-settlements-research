"""Catalog actual delivery bytes; do not infer scientific coverage from file presence."""
from pathlib import Path
import argparse,hashlib,json,subprocess
p=argparse.ArgumentParser();p.add_argument('--delivery',type=Path,required=True);p.add_argument('--stage',type=int,required=True);a=p.parse_args()
coverage=json.loads((a.delivery/'current_primary_coverage_receipt.json').read_text())
assert f'stage{a.stage}' in coverage['status']
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
files={}
for f in sorted(a.delivery.rglob('*')):
 if not f.is_file() or f.relative_to(a.delivery).as_posix() in ['asset_manifest.json','SHA256SUMS']:continue
 with f.open('rb') as stream:sh=hashlib.file_digest(stream,'sha256').hexdigest()
 key=f.relative_to(a.delivery).as_posix()
 files[key]={'sha256':sh,'bytes':f.stat().st_size,'historical_retention':key.startswith('retained_') or '.retained_stage' in key}
manifest={'status':'actual_delivery_byte_catalog','applied_working_stage':a.stage,'local_git_HEAD':head,'GitHub_upload_claimed':False,'coverage_definition':coverage['scope'],'coverage_receipt':'current_primary_coverage_receipt.json','coverage_is_not_accuracy_probability':True,'files':files}
(a.delivery/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(a.delivery/'SHA256SUMS').write_text(''.join(f'{v["sha256"]}  {k}\n' for k,v in files.items()))
print(json.dumps({'files':len(files),'stage':a.stage,'HEAD':head,'bytes_catalogued':sum(v['bytes'] for v in files.values())}))
