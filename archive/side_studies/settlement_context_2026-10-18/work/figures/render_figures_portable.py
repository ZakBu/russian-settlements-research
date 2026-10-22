"""Portable CLI wrapper around the frozen scientific renderer; never trains models.

The frozen build_figures.py is intentionally not modified. This wrapper changes
only its input/output path assignment in memory and records both file hashes.
Full regeneration requires geometry/development/audit artifacts, not final-only
predictions or the compact figure CSVs. See PORTABLE_RENDERING.md.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile
import shutil

REQUIRED_STAGING = [
 'geo/features.csv.gz',
 'e1/development/split_manifest.csv.gz',
 'e1/development/result.json', 'e2/development/result.json',
 'e3/development/result.json', 'e2/illustrative_pairs_preoutcome.csv',
 'e3/regional_curves.csv', 'statistics/calibration/run_v1/results.json',
 'final/evaluation.json',
]
REQUIRED_AUDIT = [
 'evidence/data_contract.json', 'evidence/zero_three_way_patterns.csv',
 'evidence/population_value_quality_2010.csv',
]
ASSIGNMENT = "ROOT=Path(__file__).resolve().parents[2]; S=ROOT/'research_staging'; O=S/'figures'; A=ROOT/'repo/research_staging/data_audit'"

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--staging-root',type=Path,required=True,help='Directory containing geo/, e1/, e2/, e3/, statistics/, final/.')
 ap.add_argument('--audit-root',type=Path,required=True,help='Actual data_audit directory containing evidence/.')
 ap.add_argument('--output',type=Path,required=True,help='New output directory; must not already exist.')
 ap.add_argument('--renderer-script',type=Path,default=Path(__file__).with_name('build_figures.py'))
 ap.add_argument('--check-only',action='store_true',help='Verify input inventory, hashes and path patch; do not render or create outputs.')
 a=ap.parse_args();s=a.staging_root.resolve();audit=a.audit_root.resolve();out=a.output.resolve();renderer=a.renderer_script.resolve()
 if out.exists():raise SystemExit('Refusing to overwrite an existing output directory; use a new path.')
 missing=[str(s/p) for p in REQUIRED_STAGING if not (s/p).is_file()]+[str(audit/p) for p in REQUIRED_AUDIT if not (audit/p).is_file()]
 if not renderer.is_file():missing.append(str(renderer))
 if missing:raise SystemExit('Missing required regeneration artifacts:\n'+'\n'.join(missing))
 code=renderer.read_text();assert code.count(ASSIGNMENT)==1,'Frozen renderer path assignment changed; review wrapper before use.'
 receipt={'status':'preflight_passed','renderer_sha256':sha(renderer),'wrapper_sha256':sha(__file__),'staging_root':str(s),'audit_root':str(audit),'output':str(out),'inputs':{}}
 for prefix,root,paths in [('staging',s,REQUIRED_STAGING),('audit',audit,REQUIRED_AUDIT)]:
  for p in paths:receipt['inputs'][prefix+'/'+p]={'sha256':sha(root/p),'bytes':(root/p).stat().st_size}
 if a.check_only:
  print(json.dumps(receipt,ensure_ascii=False,indent=2));return
 # Bind paths directly through the execution namespace, avoiding shell interpolation.
 replacement="ROOT=PORTABLE_STAGING.parent; S=PORTABLE_STAGING; O=PORTABLE_OUTPUT; A=PORTABLE_AUDIT"
 code=code.replace(ASSIGNMENT,replacement)
 # Render in a local temporary directory and verify every PNG before publishing.
 # A failed prior workspace test produced truncated files; do not suppress PIL errors.
 from PIL import Image
 with tempfile.TemporaryDirectory(prefix='settlement_figures_') as tmp:
  work=Path(tmp)
  namespace={'__name__':'__main__','__file__':str(renderer),'PORTABLE_STAGING':s,'PORTABLE_AUDIT':audit,'PORTABLE_OUTPUT':work}
  exec(compile(code,str(renderer),'exec'),namespace)
  png=sorted(work.glob('[0-9][0-9]_*.png'))
  if len(png)!=8:raise RuntimeError(f'Expected8 figures after full-data preflight, got{len(png)}')
  for path in png:
   with Image.open(path) as im:im.load()
  out.mkdir(parents=True,exist_ok=False)
  receipt['generated']={}
  for path in sorted(work.iterdir()):
   if not path.is_file():continue
   target=out/path.name;tmp_target=out/(path.name+'.partial');expected=sha(path)
   for attempt in range(3):
    shutil.copyfile(path,tmp_target)
    if sha(tmp_target)==expected:
     tmp_target.replace(target)
     if sha(target)==expected:break
   else:raise RuntimeError('Failed verified output copy: '+path.name)
   receipt['generated'][path.name]=expected
 receipt['status']='rendered8_from_archived_artifacts'
 (out/'portable_render_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
 print('Portable rendering completed; no models trained.')

if __name__=='__main__':main()
