from pathlib import Path
import concurrent.futures,urllib.parse,json
exec((Path(__file__).with_name('probe_sources.py')).read_text().split('urls=[]')[0])
urls=[]
for i,t in enumerate(['static.wbstatic.net/data/*','www.wildberries.ru/services/besplatnaya-dostavka*','www.wildberries.ru/webapi/spa/modules/pickups*','www.wildberries.ru/webapi/poo*','www.ozon.ru/context/detail/id/*','xapi.ozon.ru/*points*','ozon.ru/api/*geo*']):
 if 'context/detail'in t:continue
 params={'url':t,'output':'json','filter':'statuscode:200','from':'20170101','to':'20211231','collapse':'urlkey','limit':500}
 urls.append((f'wide_cdx_{i}','https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(params)))
rows=json.loads((OUT/'early_cdx_09.body').read_bytes())
for i,slug in enumerate(['borzye-d','istra','chelyabinsk','yakutsk','moskva']):
 rs=[r for r in rows[1:]if '/geo/'+slug+'/'in r[2] and int(r[-1])>5000]
 if rs:
  r=rs[-1];urls.append((f'early_geo_{slug}','https://web.archive.org/web/'+r[1]+'id_/'+r[2]))
urls += [('ozon_official_2023','https://corp.ozon.ru/ru/sth/prodazhi-predprinimateley-iz-malyh-gorodov-rossii-vyrosli-v-2-4-raz-v-2023-godu-b7abc857'),('ozon_official_2024','https://corp.ozon.ru/ru/sth/zhiteli-malyh-gorodov-stali-v-4-raza-chashche-delat-pokupki-na-ozon-70db996e'),('ozon_sec_2020','https://www.sec.gov/Archives/edgar/data/1822829/000119312521099171/d71343dex991.htm')]
with concurrent.futures.ThreadPoolExecutor(max_workers=5)as ex: results=list(ex.map(fetch,urls))
(R/'research/ecommerce_cloud/extension/history/more_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
for r in results:
 print(r['name'],r.get('status'),r['bytes'],r.get('error',''))
 try:
  j=json.loads((R/r['body']).read_bytes())
  if isinstance(j,list):print('CDX',len(j),[(x[1],x[2])for x in j[1:]][:20])
 except:pass
