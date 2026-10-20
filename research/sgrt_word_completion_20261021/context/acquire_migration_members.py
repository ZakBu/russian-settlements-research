#!/usr/bin/env python3
"""Read ZIP central directory and only required annual Parquet members over HTTP Range."""
import requests,struct,io,zipfile,zlib,json,hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_context_completion')
u='https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20260928/indicators/section31/data_Y48112023_112_v20260928.zip'
s=requests.Session();h=s.head(u,timeout=20);h.raise_for_status();size=int(h.headers['Content-Length']);ranges=[]
def rng(a,b):
 r=s.get(u,headers={'Range':f'bytes={a}-{b}'},timeout=(15,120));r.raise_for_status();assert r.status_code==206;assert len(r.content)==b-a+1
 ranges.append({'start':a,'end':b,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()});return r.content
tail=rng(size-65557,size-1);off=tail.rfind(b'PK\x05\x06');e=struct.unpack('<4s4H2LH',tail[off:off+22]);cdsize,cdstart=e[5:7];cd=rng(cdstart,cdstart+cdsize-1)
z=zipfile.ZipFile(io.BytesIO(cd+struct.pack('<4s4H2LH',b'PK\x05\x06',0,0,e[3],e[4],cdsize,0,0)))
items=[x for x in z.infolist() if x.filename.endswith('.parquet') and any(f'year{y}_' in x.filename for y in range(2010,2022))];print([(i.filename,i.compress_size) for i in items],flush=True)
if not items:items=[x for x in z.infolist() if x.filename.endswith('.parquet') and '/' not in x.filename]
receipts=[]
for x in items:
 a=x.header_offset;hdr=rng(a,a+29);f=struct.unpack('<4s5H3L2H',hdr);start=a+30+f[-2]+f[-1];comp=rng(start,start+x.compress_size-1);data=zlib.decompress(comp,-15) if x.compress_type==8 else comp
 assert len(data)==x.file_size and zlib.crc32(data)&0xffffffff==x.CRC
 assert data[:4]==data[-4:]==b'PAR1'
 p=RAW/Path(x.filename).name;p.write_bytes(data);receipts.append({'member':x.filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});print(p.name,len(data),flush=True)
(OUT/'migration_range_acquisition.json').write_text(json.dumps({'url':u,'archive_bytes':size,'archive_sha256':None,'archive_etag':h.headers.get('ETag'),'fetched_ranges':ranges,'members':receipts,'scope':'Only 2010-2021annualParquetmembers fetched; full archive not downloaded'},indent=2))
