from pathlib import Path
import concurrent.futures,json,urllib.parse
exec(Path(__file__).with_name('probe_sources.py').read_text().split('urls=[]')[0])
urls=[]
for i,p in enumerate(['www.ozon.ru/api/composer-api.bx/_action/cmsGetPvzV2*','api.ozon.ru/composer-api.bx/_action/cmsGetPvzV2*','www.ozon.ru/composer-api.bx/_action/cmsGetPvzV2*','www.ozon.ru/api/composer-api.bx/_action/cmsGetPvz*','xapi.ozon.ru/*cmsGetPvz*']):
 q={'url':p,'output':'json','filter':'statuscode:200','from':20170101,'to':20251231,'collapse':'digest','limit':1000}
 urls.append((f'ozon_derived_cdx_{i}','https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(q)))
with concurrent.futures.ThreadPoolExecutor(max_workers=5)as ex:rs=list(ex.map(fetch,urls))
(R/'research/ecommerce_cloud/extension/history/derived_ozon_manifest.json').write_text(json.dumps(rs,ensure_ascii=False,indent=2))
for r in rs:
 print(r['name'],r.get('status'),r['bytes'])
 try:print(json.loads((R/r['body']).read_bytes())[:10])
 except:pass
