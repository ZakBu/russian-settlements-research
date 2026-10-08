from pathlib import Path
import urllib.request,urllib.parse,json,concurrent.futures,re,hashlib
from bs4 import BeautifulSoup
E=Path(__file__).resolve().parent
routes={f'{k}_{h}':('https://'+dom+'/vpn2010') for k,a in {'perm':['59.rosstat.gov.ru','permstat.gks.ru'],'mord':['13.rosstat.gov.ru','mordovstat.gks.ru'],'prim':['25.rosstat.gov.ru','primstat.gks.ru']}.items()for h,dom in enumerate(a)}
for k,q in {'perm':'"Пермский край" "2010" "населенных пунктов" росстат','mord':'"Мордовия" "2010" "населенных пунктов" росстат','prim':'"Приморский" "2010" "населенных пунктов" росстат'}.items():routes[k+'_bing']='https://www.bing.com/search?q='+urllib.parse.quote(q)
def fetch(x):
 k,u=x;row={'name':k,'url':u}
 try:
  resp=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=15);d=resp.read(1300000);p=E/(k+'.html');p.write_bytes(d);row.update(status=resp.status,finalurl=resp.url,bytes=len(d),sha256=hashlib.sha256(d).hexdigest(),tls_verified=True);s=BeautifulSoup(d,'html.parser');row['text']=s.get_text(' ',strip=True)[:4000];row['links']=[{'href':a['href'],'title':a.get_text(' ',strip=True)}for a in s.find_all('a',href=True)if a['href'].startswith('http')and not any(v in a['href']for v in ['bing.com','microsoft.com'])]
 except Exception as ex:row['error']=str(ex)
 return row
with concurrent.futures.ThreadPoolExecutor(max_workers=6)as pool:r=list(pool.map(fetch,routes.items()))
(E/'catalog_probe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
