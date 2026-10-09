from pathlib import Path
import urllib.request,urllib.parse,urllib.error,gzip,json,time
from bs4 import BeautifulSoup
O=Path(__file__).parent
queries=['посёлок Ткацкой фабрики Опалиха карта','посёлок центральной усадьбы совхоза Подольский карта','совхоз Шеметово посёлок Новый центральная усадьба','село Пушкино Пушкинский 2003 карта']
for i,q in enumerate(queries,1):
 u='https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':q})
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25)as r:b=r.read(2000000);status=r.status
 except urllib.error.HTTPError as e:
  (O/f'extpoint{i}_failure.json').write_text(json.dumps({'status':e.code,'url':u,'bypass':False}));print('HTTP',e.code);break
 (O/f'extpoint{i}.html.gz').write_bytes(gzip.compress(b));(O/f'extpoint{i}_request.json').write_text(json.dumps({'status':status,'url':u,'normal_TLS':True}));s=BeautifulSoup(b,'html.parser');rs=[{'url':a.get('href'),'title':a.get_text(' ',strip=True)}for a in s.select('a.result__a')];print(q,rs,flush=True);time.sleep(1.3)
