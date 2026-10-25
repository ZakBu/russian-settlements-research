"""Independently verify every downloaded object before optional immutable input caching."""
import argparse,hashlib,json,os,sys,zipfile
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()

p=argparse.ArgumentParser();p.add_argument('--catalog',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--manual-root',type=Path);p.add_argument('--dest',type=Path);a=p.parse_args()
c=json.loads(a.catalog.read_text());asset=next(x for x in c['assets'] if x['asset']==a.archive.name)
if a.archive.stat().st_size!=asset['bytes'] or sha(a.archive)!=asset['sha256']:raise ValueError('Archive checksum differs')
checked=[]
with zipfile.ZipFile(a.archive) as z:
 if len(z.namelist())!=len(set(z.namelist())):raise ValueError('Duplicate ZIP entry')
 expected={'objects/'+b for b in asset['objects']}
 if set(z.namelist())!=expected:raise ValueError('Unexpected or missing archive objects')
 for b in sorted(asset['objects']):
  m=c['objects'][b];h=hashlib.sha256();size=0
  with z.open('objects/'+b) as f:
   for block in iter(lambda:f.read(4<<20),b''):h.update(block);size+=len(block)
  if size!=m['bytes'] or h.hexdigest()!=m['sha256']:raise ValueError('Invalid downloaded object '+b)
  checked.append(b)
report={'source_commit':c['source_commit'],'archive_sha256':asset['sha256'],'archive_bytes':asset['bytes'],'downloaded_objects_independently_crc_size_sha256_verified':len(checked),'failures':[],'immutable_input_cache':[]}
if a.manual_root:
 if not a.dest:raise ValueError('Cache destination required')
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
 from scripts.sgrt_zero.reproduce import payload_files
 candidates=payload_files(a.manual_root);memo={}
 prefixes=('inputs/','context/','health/','education/','commerce/','federal_medical/','literature/','routes/','routes_wb/','routes_yandex/','derived_nearest/')
 base=a.dest.resolve();base.mkdir(parents=True,exist_ok=True)
 for row in c['files']:
  rel=str(Path(row['path']).relative_to('sgrt/zero20261025'))
  if not rel.startswith(prefixes) or rel not in candidates:continue
  source=candidates[rel].resolve();m=c['objects'][row['blob']]
  if source.stat().st_size!=row['bytes']:continue
  actual=memo.setdefault(source,sha(source)) if source not in memo else memo[source]
  if actual!=m['sha256']:continue
  target=base/row['path']
  if not target.resolve().is_relative_to(base):raise ValueError('Unsafe catalog path')
  target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():raise ValueError('Cache target already exists')
  os.link(source,target)
  report['immutable_input_cache'].append({'path':row['path'],'sha256':actual,'bytes':row['bytes']})
 report['local_input_cache_is_content_identical_to_independently_downloaded_objects']=True
 report['cached_inputs_read_only_during_following_verification']=True
 report['cached_logical_bytes']=sum(x['bytes'] for x in report['immutable_input_cache'])
a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='immutable_input_cache'},ensure_ascii=False))
