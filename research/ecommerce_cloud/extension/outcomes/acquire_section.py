"""Independent retrieval of pinned public BDMO trade section; verify before use."""
from pathlib import Path
import urllib.request, hashlib, zipfile, json
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
RAW=ROOT/'work/ecommerce_extension_outcomes/raw';RAW.mkdir(parents=True,exist_ok=True)
URL='https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20260928/by_section/data_section2_112_v20260928_section_file.zip'
SHA='9fc60d9b0531f24dd80d0b58f6e2899571c4418e732c97a814a63e8b916a4c07'
path=RAW/'bdmo_section2.zip'
if not path.exists():
 with urllib.request.urlopen(URL,timeout=120) as r,path.open('wb') as w:
  while b:=r.read(1024*1024):w.write(b)
assert hashlib.sha256(path.read_bytes()).hexdigest()==SHA
with zipfile.ZipFile(path) as z:
 names=[n for n in z.namelist() if n.endswith('.parquet')];assert len(names)==1
 p=RAW/Path(names[0]).name
 with z.open(names[0]) as r,p.open('wb') as w:
  while b:=r.read(1024*1024):w.write(b)
manifest={'url':URL,'tls_verification':True,'download_utc':datetime.now(timezone.utc).isoformat(),'zip_sha256':SHA,'zip_bytes':path.stat().st_size,'parquet_path':str(p.relative_to(ROOT)),'parquet_bytes':p.stat().st_size,'parquet_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(OUT/'section_acquisition.json').write_text(json.dumps(manifest,indent=2)+'\n');print(manifest)
