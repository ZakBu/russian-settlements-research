#!/usr/bin/env python3
"""Fetch primary publication, keeping raw copyright sources in disposable cache."""
from pathlib import Path
import concurrent.futures,hashlib,json,datetime
import requests
HERE=Path(__file__).resolve().parent; RAW=Path('/workspace/scratch/sgrt_commuting_cases');RAW.mkdir(exist_ok=True)
SOURCES=[('tema01','tema01.php'),('tema02','tema02.php'),('tema03','tema03.php'),('full_article','demoscope727.pdf'),('article_http','http://demoscope.ru/weekly/2017/0727/demoscope727.pdf'),('map01','img/t_graf01.jpg'),('map03','img/t_graf03.jpg'),('map07','img/t_graf07.jpg')]
def fetch(v):
 name,rel=v;url=rel if rel.startswith('http') else 'https://www.demoscope.ru/weekly/2017/0727/'+rel;suffix='.pdf' if rel.endswith('.pdf') else '.jpg' if rel.endswith('.jpg') else '.html';p=RAW/(name+suffix)
 r={'name':name,'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'publication_period':'2017-05-01/2017-05-21','raw_path':str(p)}
 try:
  if p.exists() and p.stat().st_size>1000:data=p.read_bytes();r['http_status']=200;r['cache_reused']=True
  else:
   q=requests.get(url,timeout=30);r['http_status']=q.status_code;q.raise_for_status();data=q.content;p.write_bytes(data)
  r.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 except Exception as e:r['error']=str(e)
 print(name,r.get('http_status'),r.get('bytes'),r.get('error'),flush=True);return r
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(4) as e:rows=list(e.map(fetch,SOURCES))
 (HERE/'acquisition_receipt.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
