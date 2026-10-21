#!/usr/bin/env python3
"""Recover exact archived official historical OKTMO ZIP using bounded HTTP ranges."""
from pathlib import Path
import requests,concurrent.futures,hashlib,json,time,datetime,zipfile
H=Path(__file__).resolve().parent;S=H/'sources';URL='https://web.archive.org/web/20220401072917id_/https://rosstat.gov.ru/storage/opentadata/7708234640-oktmo/archive.zip';SIZE=68169573;CHUNK=1024*1024
P=S/'official_oktmo_archive_20220401.zip';TMP=S/'archive_range_parts';TMP.mkdir(exist_ok=True)
def part(start):
 end=min(start+CHUNK,SIZE)-1;name=TMP/f'{start:09d}.bin'
 if name.exists()and name.stat().st_size==end-start+1:return start,name
 for attempt in range(4):
  try:
   r=requests.get(URL,headers={'Range':f'bytes={start}-{end}'},timeout=30);assert r.status_code==206 and len(r.content)==end-start+1 and r.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'),(r.status_code,len(r.content),r.headers.get('Content-Range'));name.write_bytes(r.content);return start,name
  except Exception:
   if attempt==3:raise
 return start,name
starttime=time.monotonic();got=[]
with concurrent.futures.ThreadPoolExecutor(4)as pool:
 for i,(start,p)in enumerate(pool.map(part,range(0,SIZE,CHUNK)),1):
  got.append((start,p))
  if i%10==0:print('downloadedparts',i,flush=True)
with P.with_suffix('.tmp').open('wb')as f:
 for _,p in sorted(got):f.write(p.read_bytes())
P.with_suffix('.tmp').replace(P);assert P.stat().st_size==SIZE
with zipfile.ZipFile(P)as z:
 assert z.testzip()is None;items=[{'name':x.filename,'size':x.file_size,'compressed_size':x.compress_size,'CRC':f'{x.CRC:08x}','ZIP_member_dos_datetime':x.date_time}for x in z.infolist()]
sha=hashlib.sha256(P.read_bytes()).hexdigest();r={'status':'ACTUAL_OFFICIAL_ARCHIVE_BYTES_RECOVERED_ZIP_CRC_PASS','source_official_URL':'https://rosstat.gov.ru/storage/opentadata/7708234640-oktmo/archive.zip','retrieval_URL':URL,'archive_capture_date':'2022-04-01','source_was_linked_from_archived_metadata2022_01_07':True,'bytes':SIZE,'sha256':sha,'seconds':time.monotonic()-starttime,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'members':items};(H/'official_archive_acquisition_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
for _,p in got:p.unlink()
TMP.rmdir();print(json.dumps({'bytes':SIZE,'sha256':sha,'members':items},ensure_ascii=False),flush=True)
