import urllib.request,json,hashlib,re,datetime,concurrent.futures
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path('/workspace/shared/rural1979_new_sources'); BASE='https://rodnaya-vyatka.ru'; records=[];manifest=[]
def fetch(path):
 fn=ROOT/(path.strip('/').replace('/','_')+'.html')
 if fn.exists():b=fn.read_bytes()
 else:raise RuntimeError('Network acquisition disabled pending source-owner permission; cached inspection only')
 return b,dict(url=BASE+path,path=str(fn),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),retrieved_date='2026-10-14')
links={}
for sid,region in [(2,'Кировская область'),(4,'Марийская АССР'),(6,'Татарская АССР'),(8,'Удмуртская АССР'),(9,'Кировская область')]:
 p=f'/perepis1979/pages/source/{sid}';b,m=fetch(p);manifest.append(m)
 for a in BeautifulSoup(b,'html.parser').find_all('a',href=True):
  if re.fullmatch(r'/perepis1979/pages/\d+',a['href']):links[a['href']]=(sid,region)
print('pages',len(links),flush=True)
def run(item):
 path,(sid,region)=item
 try:
  b,m=fetch(path);s=BeautifulSoup(b,'html.parser');rr=[]
  for table in s.find_all('table',class_='sticky-enabled'):
   body=table.find('tbody',recursive=False)
   if not body:continue
   for idx,tr in enumerate(body.find_all('tr',recursive=False),1):
    td=tr.find_all('td',recursive=False);v=[c.get_text(' ',strip=True) for c in td]
    if len(v)==16 and re.fullmatch(r'\d+',v[0]):
     rr.append(dict(year=1979,region=region,source_id=sid,provider_id=v[0],settlement_type=v[2],name=v[3],admin_economic=v[4],admin_economic_code=v[5],ethnicity=v[6],present_male=v[7],present_female=v[8],present_total=v[9],permanent_male=v[10],permanent_female=v[11],permanent_total=v[12],population_category=v[13],archive_locator=v[14],source_url=BASE+path,html_row_index=idx,source_sha256=m['sha256'],retrieved_date='2026-10-14',linked_place_url=next((BASE+a['href'] for a in td[1].find_all('a',href=True) if '/places/' in a['href']),None),raw_cells=v))
  return rr,m,None
 except Exception as e:return [],dict(url=BASE+path),str(e)
errors=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 for i,(rr,m,e) in enumerate(ex.map(run,links.items())):
  records.extend(rr);manifest.append(m)
  if e:errors.append(dict(url=m['url'],error=e))
  if i%25==0:print(i,len(records),'errors',len(errors),flush=True)
for name,data in [('rows',records),('assets',manifest),('errors',errors)]:
 (ROOT/(name+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in data))
summary=dict(pages=len(links),rows=len(records),unique_provider_ids=len({r['provider_id'] for r in records}),errors=errors,region_rows={reg:sum(r['region']==reg for r in records) for reg in set(r['region'] for r in records)})
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(summary,flush=True)
