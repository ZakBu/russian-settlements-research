#!/usr/bin/env python3
"""Reacquire exact published sources, cache SHA256; extract only required members.
Migration uses acquire_migration_members.py and HTTP ranges instead of1.47GB archive.
"""
from pathlib import Path
import requests,zipfile,json,hashlib,datetime
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_context_completion');RAW.mkdir(parents=True,exist_ok=True)
BASE='https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20260928'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(2**20),b''):h.update(c)
 return h.hexdigest()
def catalog():
 rows=[]
 for code in ['Y48112001','Y48112003','Y48112004','Y48112027']:
  rows.append(dict(file=code+'.zip',url=f'{BASE}/indicators/section31/data_{code}_112_v20260928.zip',members=[f'data_{code}_112_v20260928.'+('parquet' if code=='Y48112027' else 'csv')]))
 for n in [6,7,37]:rows.append(dict(file=f'section{n}.zip',url=f'{BASE}/by_section/data_section{n}_112_v20260928_section_file.zip',members=[f'data_section{n}_112_v20260928.parquet']))
 for kind in ['tavg','prec']:rows.append(dict(file=f'wc2.1_10m_{kind}.zip',url=f'https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_{kind}.zip',members=[f'wc2.1_10m_{kind}_{m:02d}.tif' for m in range(1,13)]))
 rows.append(dict(file='Global-AI_ET0__annual_v3_1.zip',url='https://ndownloader.figshare.com/files/56300327',members=['Global-AI_ET0__annual_v3_1/ai_v31_yr.tif','Global-AI_ET0__annual_v3_1/et0_v31_yr.tif']))
 for name in ['ts3','riS']:
  f=f'{name}_CRUTS32_Hist_8110.tif';rows.append(dict(file=f,url=f'https://s3.eu-west-1.amazonaws.com/data.gaezdev.aws.fao.org/res01/CRUTS32/Hist/{f}',members=[]))
 for name in ['SQ0_mze_v9aL','SQ1_mze_v9aL','SQ3_mze_v9aL','SQ4_mze_v9aL','SQ5_mze_v9aL','SQ6_mze_v9aL','SQ7_mze_v9aL']:
  rows.append(dict(file=name+'.tif',url=f'https://s3.eu-west-1.amazonaws.com/data.gaezdev.aws.fao.org/LR/soi1/{name}.tif',members=[]))
 return rows
def run():
 rows=catalog()
 for row in rows:
  p=RAW/row['file']
  if not p.exists():
   with requests.get(row['url'],stream=True,timeout=90) as r:
    r.raise_for_status()
    with p.open('wb') as f:
     for c in r.iter_content(2**20):f.write(c)
  row.update(bytes=p.stat().st_size,sha256=sha(p),retrieval_verified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
  if row['members']:
   with zipfile.ZipFile(p) as z:
    for member in row['members']:
     q=RAW/member
     if not q.exists():z.extract(member,RAW)
    row['member_receipts']=[dict(file=m,bytes=(RAW/m).stat().st_size,sha256=sha(RAW/m)) for m in row['members']]
  print(row['file'],row['bytes'],flush=True)
 manifest=dict(status='ACTUALLY_RETRIEVED',sources=rows,bdmo_origin='Rosstat BDMO redistributed by Tochnо',bdmo_release='v20260928',municipal_grain='source upper-level municipalities, projected via frozen2021 bridge; no settlement allocation',migration_range_receipt='migration_range_acquisition.json',units='metric-specific source units retained in municipal_annual_context.parquet',climate_normal_periods={'WorldClim2.1':'1970-2000','GlobalAIv3.1':'1970-2000','FAOGAEZv4CRUTS32':'1981-2010'},licenses='Consult publisher terms; public redistribution is not a claim that every item is CC0.')
 (ROOT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
