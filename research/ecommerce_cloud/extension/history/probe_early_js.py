from pathlib import Path
import concurrent.futures,json,urllib.parse
exec((Path(__file__).with_name('probe_sources.py')).read_text().split('urls=[]')[0])
urls=[]
for i,pattern in enumerate(['cdn2.ozone.ru/_nuxt/services.ae10fe36bf48eb9ab210.js','cdn2.ozone.ru/_nuxt/composer-components.f69216f63b8d31da4828.js','xapi.ozon.ru/principals-geo/*','www.ozon.ru/api/*delivery*','www.ozon.ru/api/*pickpoint*','www.wildberries.ru/webapi/spa/modules/pickups']):
 params={'url':pattern,'output':'json','filter':'statuscode:200','from':'20190101','to':'20211231','collapse':'digest','limit':200}
 urls.append((f'js_cdx_{i}','https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(params)))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(fetch,urls))
(R/'research/ecommerce_cloud/extension/history/js_probe_manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:
 print(r['name'],r.get('status'),r['bytes'])
 try: print(json.loads((R/r['body']).read_bytes())[:5])
 except:pass
