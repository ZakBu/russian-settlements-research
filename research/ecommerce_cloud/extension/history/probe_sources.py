from pathlib import Path
import concurrent.futures,urllib.request,urllib.error,urllib.parse,json,hashlib,datetime
R=Path(__file__).resolve().parents[4]; OUT=R/'work/ecommerce_extension_history';OUT.mkdir(parents=True,exist_ok=True)
def fetch(pair):
 name,url=pair;p=OUT/(name+'.body');r={'name':name,'url':url,'requested_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'settlement-research/1.0'}),timeout=35) as f:
   b=f.read(30000001);r.update(status=f.status,resolved_url=f.url,headers=dict(f.headers))
 except urllib.error.HTTPError as e:b=e.read(100000);r.update(status=e.code,error=str(e),headers=dict(e.headers))
 except Exception as e:b=b'';r.update(error=str(e))
 p.write_bytes(b);r.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),body=str(p.relative_to(R)))
 (OUT/(name+'.request.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2));return r
urls=[]
for i,target in enumerate(['www.wildberries.ru/webapi/spa/modules/pickups','www.wildberries.ru/webapi/poo/*','static.wbstatic.net/data/all-poo.json','static.wbstatic.net/data/all-poo-fr.json','static.wbstatic.net/data/pickups*','static-basket-01.wb.ru/vol0/data/all-poo*','xapi.ozon.ru/principals-*','www.ozon.ru/api/composer-api.bx/page/json/v2?url=/geo/*','api.ozon.ru/composer-api.bx/*','ozon.ru/geo/*','ozon.ru/graphics/action/*point*','cdn1.ozone.ru/s3/*points*']):
 params={'url':target,'output':'json','filter':'statuscode:200','from':'20170101','to':'20211231','collapse':'digest','limit':'300'}
 urls.append((f'early_cdx_{i:02d}','https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(params)))
for i,q in enumerate(['ozon pvz created:<2023-01-01','wildberries pvz created:<2023-01-01','ozon pickup created:<2023-01-01','wildberries points created:<2023-01-01','ozon data created:<2023-01-01']):
 urls.append((f'github_early_{i}','https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':100})))
with concurrent.futures.ThreadPoolExecutor(max_workers=5)as ex: rows=list(ex.map(fetch,urls))
(R/'research/ecommerce_cloud/extension/history/probe_manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:
 print(r['name'],r.get('status'),r['bytes'],r.get('error',''))
 try:
  j=json.loads((R/r['body']).read_bytes())
  if isinstance(j,list):print('CDX rows',len(j),str(j)[:600])
  if isinstance(j,dict)and 'items'in j:print('REPOS',[(x['full_name'],x['created_at'])for x in j['items']])
 except Exception:pass
