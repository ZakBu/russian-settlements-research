from pathlib import Path
import urllib.request,urllib.parse,json,concurrent.futures
E=Path(__file__).resolve().parent;inv=json.loads((E/'cached_official_citation_URL_inventory.json').read_text());urls=[]
for x in inv:
 u=x['url'].split('|')[0]
 if 'web.archive.org' in u and 'tulastat' in u and '.pdf' in u and ('Том+1'in u or '%D0%A2%D0%BE%D0%BC+1'in u):
  u=u.replace(u.split('/')[4],u.split('/')[4]+'id_',1);urls.append(u)
u='https://web.archive.org/web/20140714151406id_/http://tulastat.gks.ru/wps/wcm/connect/rosstat_ts/tulastat/resources/32a53b80412060b2ac62ef367ccd0f13/Численность+и+размещение+населения+(Том+1).pdf';urls.append(u)
def run(u):
 try:
  a=urllib.request.urlopen(urllib.request.Request(urllib.parse.quote(u,safe=':/%+?=&'),method='HEAD'),timeout=25);return {'url':u,'status':a.status,'headers':dict(a.headers),'TLS_verified':True}
 except Exception as ex:return {'url':u,'error':str(ex)}
r=list(concurrent.futures.ThreadPoolExecutor(3).map(run,set(urls)));(E/'tula_archived_edition_headers.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2)[:10000])
