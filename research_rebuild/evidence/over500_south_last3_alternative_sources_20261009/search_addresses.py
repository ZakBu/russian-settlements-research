from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,time
from bs4 import BeautifulSoup
O=Path(__file__).parent
queries=['"Ярославка-1" "Никифоровский"','"Ярославка 2" "Ярославский"','"Ярославка Первая" село','"хутор Гиреевский" адрес']
r=[];rows=[]
for i,q in enumerate(queries):
 u='https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':q});e={'query':q,'url':u,'normal_TLS':True}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=15)as response:raw=response.read();e['status']=response.status
  f=O/f'address_search_{i}.html.gz';f.write_bytes(gzip.compress(raw,mtime=0));e.update(capture=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest());s=BeautifulSoup(raw,'html.parser');results=s.select('.result');e['results']=len(results)
  for result in results:
   a=result.select_one('.result__a')
   if a:rows.append({'query':q,'title':a.get_text(' ',strip=True),'href':a.get('href'),'snippet':result.get_text(' ',strip=True),'search_capture':str(f),'search_sha256':e['sha256'],'candidate_source_only':True})
  print(i,q,e['results'],flush=True)
 except Exception as x:e['error']=str(x);print(i,str(x),flush=True)
 r.append(e);time.sleep(1.1)
(O/'address_search_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));(O/'address_candidate_sources.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
