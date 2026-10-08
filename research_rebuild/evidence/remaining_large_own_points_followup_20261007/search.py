import urllib.request,urllib.parse,json,gzip,concurrent.futures
from pathlib import Path
O=Path(__file__).parent
queries=['Мочище посёлок Новосибирский','Муслюмово станция Кунашакский','Чайковская посёлок станция Нытвенский','Мыза деревня Тула','Ново-Писцово Вичуга','Савино Карагайский','Ишалино станция Аргаяшский','Тарасиха станция Семёновский','Смолино станция Сосновский','Тальжино станция Новокузнецкий','Барсуки деревня Тула','Ергач посёлок станция','Петелино посёлок Тула','Поповка деревня Раменский','Комарихинский посёлок','Петровское посёлок Ленинский','Титан Мурманская']
def run(q):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','list':'search','srsearch':q,'srlimit':3,'format':'json'})
 try:
  a=json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=12).read());return q,[r['title'] for r in a.get('query',{}).get('search',[])]
 except Exception as ex:return q,[]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:r=list(pool.map(run,queries))
(O/'search_results.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False))
