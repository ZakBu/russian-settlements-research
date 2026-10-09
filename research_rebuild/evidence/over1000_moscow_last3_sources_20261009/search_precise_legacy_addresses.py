from pathlib import Path
import urllib.request,urllib.parse,urllib.error,gzip,json,time
from bs4 import BeautifulSoup
O=Path(__file__).parent
qs=['"пос. Ткацкой" дом','"поселок Ткацкой" дом','"свх Шеметово" "д."','"Центральная усадьба" "Шеметово" история','"село Пушкино" "Ярославское" улица дом']
for i,q in enumerate(qs,21):
 u='https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':q})
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25)as r:b=r.read(1800000);status=r.status
 except urllib.error.HTTPError as e:
  (O/f'search{i}_failure.json').write_text(json.dumps({'status':e.code,'url':u,'bypass':False}));print('HTTP',e.code);break
 (O/f'search{i}.html.gz').write_bytes(gzip.compress(b));(O/f'search{i}_request.json').write_text(json.dumps({'status':status,'url':u,'normal_TLS':True}));s=BeautifulSoup(b,'html.parser');print(q,flush=True)
 for a in s.select('.result'):print(a.get_text(' ',strip=True)[:1000],flush=True)
 time.sleep(1.3)
