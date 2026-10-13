from pathlib import Path
import urllib.request,urllib.error,gzip,json
O=Path(__file__).parent
for code in ['46768000587','46768000590']:
 u='https://classifikators.ru/oktmo/'+code
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25)as r:b=r.read(2000000);status=r.status
 except urllib.error.HTTPError as e:
  (O/f'Popovka_code{code}_failure.json').write_text(json.dumps({'url':u,'status':e.code,'bypass':False}));print('HTTP',e.code);break
 (O/f'Popovka_code{code}.html.gz').write_bytes(gzip.compress(b));(O/f'Popovka_code{code}_request.json').write_text(json.dumps({'url':u,'status':status,'normal_TLS':True}));print(code,b.decode()[:200],len(b))
