from pathlib import Path
import requests,json,hashlib,concurrent.futures,time,subprocess
ROOT=Path(__file__).resolve().parent;DATA=Path('/workspace/scratch/sgrt_resource_cases');DATA.mkdir(exist_ok=True,parents=True)
URLS={
'yamburg_union2021_archive':'https://www.rogwu.ru/upload/iblock/35b/kuy9ftsewe48ruzkwzr2w8h2psdy81ms.pdf',
'yamburg_operator2013_archive':'https://yamburg-dobycha.gazprom.ru/press/news/2013/05/57/',
'yamburg_operator2016_archive':'https://yamburg-dobycha.gazprom.ru/press/news/2016/09/839/'}
def f(item):
 name,url=item;row={'name':name,'original_url':url}
 try:
  r=requests.get('https://web.archive.org/cdx/search/cdx',params={'url':url,'output':'json','filter':['statuscode:200'],'collapse':'digest'},timeout=20);rows=r.json();row['cdx_rows']=rows
  if len(rows)<2:return row
  chosen=rows[1];stamp=chosen[1];archive='https://web.archive.org/web/'+stamp+'id_/'+chosen[2];rr=requests.get(archive,timeout=30);row.update({'archive_url':archive,'capture_timestamp':stamp,'http_status':rr.status_code,'bytes':len(rr.content),'sha256':hashlib.sha256(rr.content).hexdigest(),'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
  if rr.status_code==200:
   ext='.pdf' if rr.content.startswith(b'%PDF') else '.html';p=DATA/(name+ext);p.write_bytes(rr.content);row['local_path']=str(p)
   if ext=='.pdf':
    import fitz
    d=fitz.open(p);assert len(d)>0;p.with_suffix('.txt').write_text('\n\f\n'.join(x.get_text() for x in d))
   else:
    from bs4 import BeautifulSoup
    p.with_suffix('.txt').write_text(BeautifulSoup(rr.content,'html.parser').get_text('\n',strip=True))
  return row
 except Exception as e:row['error']=str(e);return row
rows=list(concurrent.futures.ThreadPoolExecutor(3).map(f,URLS.items()));(ROOT/'archive_acquisition_receipt.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False,indent=2))
