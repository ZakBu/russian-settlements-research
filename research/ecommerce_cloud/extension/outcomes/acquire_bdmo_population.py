"""Bounded population indicator; URL located through public researcher config,
then verified by the downloaded archive's indicator metadata, no entire catalogue.
"""
from pathlib import Path
import urllib.request, hashlib, zipfile, json
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent;RAW=ROOT/'work/ecommerce_extension_outcomes/raw';RAW.mkdir(exist_ok=True,parents=True)
url='https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20260928/indicators/section31/data_Y48112027_112_v20260928.zip'
p=RAW/'bdmo_population_Y48112027.zip'
if not p.exists():
 with urllib.request.urlopen(url,timeout=120) as r,p.open('wb') as w:
  while b:=r.read(1024*1024):w.write(b)
sha=hashlib.sha256(p.read_bytes()).hexdigest()
assert sha=='f73d2c75e238330bdbbe46f3974a884a3df55bb1a9a93bc3cd318e70eab5709c'
with zipfile.ZipFile(p) as z:
 names=z.namelist();print(names)
 for n in names:
  if n.endswith('.parquet'):
   target=RAW/Path(n).name
   with z.open(n) as r,target.open('wb') as w:
    while b:=r.read(1024*1024):w.write(b)
record={'url':url,'source_page':'https://tochno.st/datasets/bdmo','url_discovery':'https://github.com/resarytrew/cashless-demand-network-russia/blob/b27d7b657afad5d86dc459358b9c7b09cb9aaa33/configs/external_bdmo_2024.yaml','tls_verification':True,'download_utc':datetime.now(timezone.utc).isoformat(),'zip_sha256':sha,'zip_bytes':p.stat().st_size,'members':names}
(OUT/'bdmo_population_acquisition.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(record)
