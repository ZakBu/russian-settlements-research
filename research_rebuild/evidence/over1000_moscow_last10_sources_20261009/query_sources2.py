from pathlib import Path
import urllib.request,urllib.parse,urllib.error,json,gzip,time
O=Path(__file__).parent
queries=['"Луговая" "объединении"','"Пушкино" "включено"','"Ткацкой Фабрики" "посёлок"','"Шеметово" "усадьба"']
for i,q in enumerate(queries,5):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',list='search',srsearch=q,srlimit=12,format='json'))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25)as r:b=r.read(2000000)
 except urllib.error.HTTPError as e:
  (O/f'search{i}_failure.json').write_text(json.dumps({'status':e.code,'url':u,'Retry-After':e.headers.get('Retry-After'),'bypass':False}));print('HTTP',e.code);break
 (O/f'own_search{i}.json.gz').write_bytes(gzip.compress(b));j=json.loads(b);print(q,[(x['title'],x.get('snippet'))for x in j.get('query',{}).get('search',[])],flush=True);time.sleep(1.1)
