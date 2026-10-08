from pathlib import Path
import urllib.request,urllib.parse,json,concurrent.futures,re,hashlib
from bs4 import BeautifulSoup
E=Path(__file__).resolve().parent
qs={'perm':'Пермьстат перепись 2010 численность населенных пунктов таблица','mord':'Мордовиястат перепись 2010 населенных пунктов численность размещение','prim':'Приморскстат перепись 2010 населенных пунктов численность размещение'}
def fetch(k,q):
 u='https://www.google.com/search?q='+urllib.parse.quote(q);row={'query':q,'url':u}
 try:
  req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'});r=urllib.request.urlopen(req,timeout=20);data=r.read(1500000);p=E/(k+'_search.html');p.write_bytes(data);row.update(status=r.status,sha256=hashlib.sha256(data).hexdigest(),path=str(p),tls_verified=True,bytes=len(data));s=BeautifulSoup(data,'html.parser');text=s.get_text(' ',strip=True);(E/(k+'_search_text.txt')).write_text(text);links=[]
  for a in s.find_all('a',href=True):
   href=a['href'];title=a.get_text(' ',strip=True)
   if href.startswith('/url?'):href=urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get('q',[''])[0]
   if href.startswith('http')and not any(x in href for x in ['google.com','accounts.google','support.google']):links.append({'href':href,'title':title})
  row['links']=links
 except Exception as ex:row['error']=str(ex)
 return row
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:rows=list(pool.map(lambda x:fetch(*x),qs.items()))
(E/'discovery_receipt.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False,indent=2))
