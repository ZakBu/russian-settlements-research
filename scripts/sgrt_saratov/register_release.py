"""Verify downloaded release bytes and derive a portable companion catalogue.

No upload, replacement or publication happens here. Every ZIP member and source
file is checked before a catalogue is emitted; standalone maps/figures are
verified from downloaded files too. The population default catalogue is untouched.
"""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,zipfile
from pathlib import Path,PurePosixPath

REPOSITORY='ZakBu/russian-settlements-research'
REPO=Path(__file__).resolve().parents[2]


def digest_bytes(value):return hashlib.sha256(value).hexdigest()
def digest_file(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def safe_member(name):
 p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts or not p.parts or str(p)!=name:
  raise ValueError('Unsafe or noncanonical archive member')
 return p


def register(manifest_path,archive,standalone_dir,producer,prefix):
 m=json.loads(Path(manifest_path).read_text());archive=Path(archive)
 if not re.fullmatch('[0-9a-f]{40}',producer) or m['source_commit']!=producer:
  raise ValueError('Exact committed scientific producer is required')
 safe_member(prefix.rstrip('/'))
 if not prefix.endswith('/'):raise ValueError('Logical prefix must end in /')
 a=m['archive'];tag=m['release_tag']
 if archive.stat().st_size!=a['bytes'] or digest_file(archive)!=a['sha256']:
  raise ValueError('Downloaded archive does not match release manifest')
 rows=m['files'];expected={r['path']:r for r in rows}
 if len(expected)!=len(rows):raise ValueError('Duplicate manifest path')
 objects={};files=[];source_count=0
 with zipfile.ZipFile(archive) as z:
  names=z.namelist()
  if len(names)!=len(set(names)) or set(names)!=set(expected):raise ValueError('ZIP members differ from manifest')
  for name in sorted(names):
   safe_member(name);spec=expected[name];data=z.read(name)
   if len(data)!=spec['bytes'] or digest_bytes(data)!=spec['sha256']:
    raise ValueError('Member size/SHA mismatch: '+name)
   if name.startswith('reproduction/'):
    git_path=name[len('reproduction/'):];safe_member(git_path)
    original=subprocess.check_output(['git','show',producer+':'+git_path],cwd=REPO)
    if original!=data:raise ValueError('Reproduction source differs from producer Git: '+git_path)
    source_count+=1
   blob=spec['sha256'];objects.setdefault(blob,{'bytes':len(data),'sha256':blob,'asset':a['asset'],'archive_member':name})
   files.append({'path':prefix+name,'blob':blob,'bytes':len(data),'profiles':['core','all'],'asset':a['asset']})
  if 'controls/expected_control.json' not in expected or 'controls/actual_control.json' not in expected:
   raise ValueError('Both completed local and independent fresh controls are required')
  if json.loads(z.read('controls/expected_control.json'))!=json.loads(z.read('controls/actual_control.json')):
   raise ValueError('Scientific controls differ')
 standalone={}
 for name,spec in m.get('standalone_assets',{}).items():
  safe_member(name)
  if len(PurePosixPath(name).parts)!=1:raise ValueError('Standalone asset must have one filename')
  path=Path(standalone_dir)/name
  if path.stat().st_size!=spec['bytes'] or digest_file(path)!=spec['sha256']:
   raise ValueError('Downloaded standalone asset differs: '+name)
  standalone[name]={'bytes':spec['bytes'],'sha256':spec['sha256']}
 base='https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'
 proof={'schema':'sgrt.saratov.downloaded_release_verification.v1','release_tag':tag,'source_commit':producer,
  'downloaded_archive_bytes':a['bytes'],'downloaded_archive_sha256':a['sha256'],
  'zip_members_verified':len(files),'producer_git_sources_verified':source_count,
  'downloaded_standalone_assets':standalone,'fresh_and_local_scientific_controls_equal':True}
 catalogue={'schema':'sgrt.portable_data.v1','status':'verified_complete','source_commit':producer,
  'release_tag':tag,'repository':REPOSITORY,
  'scientific_scope':m['scope'],'verification_scope':'Downloaded archive, every member, every packaged producer Git source, standalone assets and complete scientific controls verified.',
  'population_default_catalog_unchanged':True,
  'profiles':{'core':'Complete Saratov pilot results, contexts, primary-source evidence and reproduction code; national inputs remain in pinned previous releases.','all':'Same complete companion'},
  'assets':[{'asset':a['asset'],'url':base+a['asset'],'bytes':a['bytes'],'sha256':a['sha256'],'status':'verified','objects':sorted(objects)}],
  'files':files,'objects':objects,'counts':{'files':len(files),'unique_objects':len(objects),'archive_bytes':a['bytes']},
  'public_download_evidence':proof}
 return catalogue,proof


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('manifest','archive','standalone-dir','catalog-output','proof-output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--producer',required=True);p.add_argument('--logical-prefix',default='sgrt/saratov-fields20261029/');a=p.parse_args()
 c,v=register(a.manifest,a.archive,a.standalone_dir,a.producer,a.logical_prefix)
 for path,value in [(a.catalog_output,c),(a.proof_output,v)]:
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'members':v['zip_members_verified'],'producer_sources':v['producer_git_sources_verified'],'standalone_assets':len(v['downloaded_standalone_assets'])}))
if __name__=='__main__':main()
