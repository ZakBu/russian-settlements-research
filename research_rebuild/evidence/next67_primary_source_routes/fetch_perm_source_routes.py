from pathlib import Path
import urllib.request,urllib.parse,json,hashlib,concurrent.futures
from bs4 import BeautifulSoup
E=Path(__file__).resolve().parent;original='http://permstat.old.gks.ru/wps/wcm/connect/rosstat_ts/permstat/ru/census_and_researching/census/national_census_2010/score_2010/';xls='http://permstat.gks.ru/perepis10/2010/'+urllib.parse.quote('Численность и размещение  населения Пермского края.xls');routes={'perm_score_catalog_archived':'https://web.archive.org/web/20200626220914id_/'+original,'perm_exact_xls_CDX':'https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode({'url':xls,'output':'json','filter':'statuscode:200','collapse':'digest','fl':'timestamp,original,mimetype,length','limit':'20'}),'perm_score_files_CDX':'https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode({'url':'permstat.old.gks.ru/*','output':'json','filter':'original:.*(2010|score).*','collapse':'urlkey','fl':'timestamp,original,mimetype,length','limit':'80'})}
def fetch(x):
 k,u=x;r={'name':k,'url':u}
 try:
  a=urllib.request.urlopen(u,timeout=25);d=a.read(2000000);p=E/(k+('.json'if'CDX'in k else '.html'));p.write_bytes(d);r.update(status=a.status,finalurl=a.url,tls_verified=True,bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
  if 'CDX'in k:r['entries']=json.loads(d)
  else:
   s=BeautifulSoup(d,'html.parser');r['text']=s.get_text(' ',strip=True)[-14000:];r['links']=[{'title':z.get_text(' ',strip=True),'href':z['href']}for z in s.find_all('a',href=True)]
 except Exception as ex:r['error']=str(ex)
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:r=list(pool.map(fetch,routes.items()))
(E/'perm_exact_source_route_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
