from pathlib import Path
import json,hashlib,tarfile,gzip,io
R=Path(__file__).resolve().parents[3];D=Path('/workspace/settlements-delivery/working-full-chain-20261007');O=R/'publication/stage67';O.mkdir(parents=True,exist_ok=True)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
source=json.loads((D/'asset_manifest.json').read_text());assert source['applied_working_stage']==67;files={k:v for k,v in source['files'].items() if not v['historical_retention']}
for n,h in files.items():assert sha(D/n)==h['sha256'] and (D/n).stat().st_size==h['bytes'],n
manifest={'status':'verified_current_stage67_data_inventory','research_commit':'c169f51145ce3aea0d6180461d4431d49b354f3b','coverage_definition':source['coverage_definition'],'not_accuracy_probability':True,'files':files,'historical_backup_exports_excluded':len(source['files'])-len(files),'external_source_corpus_not_complete':True,'source_licenses_not_unified':True}
mp=O/'current_files_manifest.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');ap=O/'working-settlements-stage67.tar.gz'
def metadata(t):t.uid=t.gid=0;t.uname=t.gname='';t.mtime=0;return t
with ap.open('wb') as raw:
 with gzip.GzipFile(fileobj=raw,filename='',mode='wb',mtime=0,compresslevel=6) as gz:
  with tarfile.open(fileobj=gz,mode='w|') as tar:
   for n in sorted(files):tar.add(D/n,arcname='working-stage67/'+n,recursive=False,filter=metadata)
   tar.add(mp,arcname='working-stage67/current_files_manifest.json',filter=metadata)
with tarfile.open(ap,'r:gz') as tar:
 members=tar.getmembers();assert len(members)==len(files)+1
 for m in members:
  assert m.isfile() and m.name.startswith('working-stage67/');name=m.name.removeprefix('working-stage67/');h=files[name] if name in files else {'sha256':sha(mp),'bytes':mp.stat().st_size}
  with tar.extractfile(m) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==h['sha256'] and m.size==h['bytes'],name
receipt={'status':'all_archive_members_verified_against_source_byte_hashes','archive':str(ap),'archive_sha256':sha(ap),'archive_bytes':ap.stat().st_size,'source_current_files':len(files),'archive_members':len(members),'code_sha256':sha(Path(__file__)),'source_catalog_sha256':sha(D/'asset_manifest.json'),'source_current_data_unchanged':True,'no_full_uncompressed_CSV_materialized':True}
(Path(__file__).parent/'archive_verification_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
