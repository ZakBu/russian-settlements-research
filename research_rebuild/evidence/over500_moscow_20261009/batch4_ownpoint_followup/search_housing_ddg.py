from pathlib import Path
import urllib.request,urllib.parse,json,gzip,concurrent.futures,bs4,hashlib
O=Path(__file__).parent;qs=['Гребнево Фирмы Луч жилые дома','Волоколамск Холмогорка жилые дома','Караваевской фабрики жилые дома','поселок санатория Звенигород жилые дома','поселок Участка 2 Буньково','Юдино поселок село жилые дома']
def go(z):
 i,q=z;u='https://html.duckduckgo.com/html/?'+urllib.parse.urlencode(dict(q=q,num=10));out=dict(query=q,url=u)
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30)as r:b=r.read()
  f=O/f'housing_ddg_{i+1}.html.gz';f.write_bytes(gzip.compress(b));out.update(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest());s=bs4.BeautifulSoup(b,'html.parser');out['text']=s.get_text(' ',strip=True)[:18000];out['links']=[dict(href=a.get('href'),text=a.get_text(' ',strip=True))for a in s.select('a')if len(a.get_text(strip=True))>20];print(q,out['text'][:1500],flush=True)
 except Exception as e:out['error']=str(e);print(q,str(e),flush=True)
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=6)as p:z=list(p.map(go,enumerate(qs)))
(O/'housing_ddg_search_receipts.json').write_text(json.dumps(z,ensure_ascii=False,indent=2))
