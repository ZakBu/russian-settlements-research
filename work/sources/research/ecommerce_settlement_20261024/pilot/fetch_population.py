"""Fetch pinned accepted census release; never mutate the source population base."""
import hashlib,json,urllib.request,zipfile,shutil
from pathlib import Path
P=Path(__file__).resolve().parent/'inputs'
URL='https://github.com/ZakBu/russian-settlements-research/releases/download/sgrt-census-population-20261022-v1/'
assets={'catalog.json':'fa288b591ba8b8dbd7dd780c7e075ed6179667913986e009122ef7fd9a892bae','census-population-2002-2010-2021.zip':'e9a51887e540803e34cad0cb0299115deebea5f5a4c1d197475dea66d4b62756'}
P.mkdir(parents=True,exist_ok=True)
for name,sha in assets.items():
 target=P/name
 if not target.exists():
  with urllib.request.urlopen(URL+name,timeout=60) as src, target.with_suffix('.part').open('wb') as dst:
   while chunk:=src.read(1024*1024):dst.write(chunk)
  target.with_suffix('.part').rename(target)
 assert hashlib.sha256(target.read_bytes()).hexdigest()==sha,name
 print(name,'SHA256 matched',flush=True)
catalog=json.loads((P/'catalog.json').read_text())
print('catalog keys',list(catalog),flush=True)
with zipfile.ZipFile(P/'census-population-2002-2010-2021.zip') as z:
 for member in z.infolist():
  if member.is_dir():continue
  dest=(P/member.filename).resolve();assert dest.is_relative_to(P.resolve()),member.filename
  if not dest.exists():z.extract(member,P)
  print('extracted',member.filename,member.file_size,flush=True)
for entry in catalog['files']:
 if not entry['path'].startswith('data/population/'):continue
 raw=(P/'objects'/entry['blob']).read_bytes()
 assert len(raw)==entry['bytes'],entry['path']
 assert hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()==entry['blob'],entry['path']
 dest=P/entry['path'];dest.parent.mkdir(parents=True,exist_ok=True)
 if not dest.exists():shutil.copyfile(P/'objects'/entry['blob'],dest)
 assert dest.read_bytes()==raw,entry['path']
 print('materialized',entry['path'],flush=True)
