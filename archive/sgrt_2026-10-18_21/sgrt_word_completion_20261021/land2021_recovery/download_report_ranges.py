from pathlib import Path
import requests,concurrent.futures,hashlib,json,time,subprocess
O=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_land2021');u='https://web.archive.org/web/20230711080041id_/https://journal.tinkoff.ru/media/gosudarstvennyi-doklad-o-sostoyanii-i-ispolzovanii-zemel-v-2021-godu.e8vfqjoy4o9p..pdf';size=25959377;chunk=512*1024
parts=list(range(0,size,chunk))
def get(start):
 end=min(start+chunk,size)-1
 old=RAW/f'archivepart_{start:09d}.bin'
 if old.exists() and old.stat().st_size==end-start+1:return start,old.read_bytes()
 for attempt in range(4):
  try:
   r=requests.get(u,headers={'Range':f'bytes={start}-{end}'},timeout=25);assert r.status_code==206 and len(r.content)==end-start+1 and r.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'),(r.status_code,len(r.content));p=RAW/f'archivepart_{start:09d}.bin';p.write_bytes(r.content);print('part',start,len(r.content),flush=True);return start,r.content
  except Exception:
   if attempt==3:raise
with concurrent.futures.ThreadPoolExecutor(max_workers=8)as ex:rr=sorted(ex.map(get,parts))
p=RAW/'rosreestr2021_full_mirror.pdf'
with p.open('wb')as f:
 for start,b in rr:f.write(b)
assert p.stat().st_size==size;subprocess.run(['pdftotext','-layout',str(p),str(p.with_suffix('.txt'))],check=True);d=dict(url=u,bytes=size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),local_path=str(p),download_method='validated206 byte ranges, concatenated inorder',range_count=len(rr),source_role='mirror_of_primary_Rosreestr_report_not_new_secondary_statistics');(O/'full_report_acquisition_receipt.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(d)
