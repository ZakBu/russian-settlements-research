from pathlib import Path
import concurrent.futures,requests,hashlib,json,subprocess,time
ROOT=Path(__file__).resolve().parent;DATA=Path('/workspace/scratch/sgrt_resource_cases');DATA.mkdir(exist_ok=True,parents=True)
URLS={
'yamburg_union2021':'https://www.rogwu.ru/upload/iblock/35b/kuy9ftsewe48ruzkwzr2w8h2psdy81ms.pdf',
'vorkuta_publichealth2021':'https://s-znc.ru/wp-content/uploads/2021/10/%D0%A1%D0%B1%D0%BE%D1%80%D0%BD%D0%B8%D0%BA_2021_%D0%9D%D0%9E%D0%92%D0%90%D0%AF-%D0%92%D0%95%D0%A0%D0%A1%D0%98%D0%AF_08.10.2021.pdf',
'yamburg_operator2016':'https://yamburg-dobycha.gazprom.ru/press/news/2016/09/839/',
'yamburg_operator2013':'https://yamburg-dobycha.gazprom.ru/press/news/2013/05/57/',
'vorkuta_judgment2017':'https://sudact.ru/regular/doc/CRzJN6NjCy6u/',
'yamburg_municipalpaper2017':'https://xn--80adjabktluddlpcdp4p1b.xn--p1ai/wp-content/uploads/2020/03/99.pdf'}
def run(item):
 name,url=item;t=time.time()
 try:
  r=requests.get(url,timeout=25);row={'name':name,'url':url,'final_url':r.url,'http_status':r.status_code,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'seconds':time.time()-t}
  if r.status_code==200:
   ext='.pdf' if r.content.startswith(b'%PDF') else '.html';p=DATA/(name+ext);p.write_bytes(r.content);row['local_path']=str(p)
   if ext=='.pdf':
    import fitz
    d=fitz.open(p);p.with_suffix('.txt').write_text('\n\f\n'.join(x.get_text() for x in d))
   else:
    from bs4 import BeautifulSoup
    s=BeautifulSoup(r.content,'html.parser');p.with_suffix('.txt').write_text(s.get_text('\n',strip=True))
  return row
 except Exception as e:return {'name':name,'url':url,'error':str(e)}
rows=list(concurrent.futures.ThreadPoolExecutor(6).map(run,URLS.items()));(ROOT/'acquisition_receipt.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False,indent=2))
