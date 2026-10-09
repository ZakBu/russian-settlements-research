from pathlib import Path
import urllib.request,urllib.parse,urllib.error,json,gzip,time
O=Path(__file__).parent
queries=['Центральной усадьбы совхоза Подольский, Московская область','Светлый, Электроугли, Московская область','Ткацкой фабрики, Опалиха, Московская область','посёлок центральной усадьбы совхоза Шеметово, Московская область']
for i,q in enumerate(queries,1):
 u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,namedetails=1,extratags=1,limit=5,countrycodes='ru'))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:b=r.read(1000000);status=r.status
 except urllib.error.HTTPError as e:
  (O/f'nominatim{i}_failure.json').write_text(json.dumps({'status':e.code,'url':u,'Retry-After':e.headers.get('Retry-After'),'bypass':False}));print('HTTP',e.code,flush=True);break
 (O/f'nominatim{i}.json.gz').write_bytes(gzip.compress(b));(O/f'nominatim{i}_request.json').write_text(json.dumps({'url':u,'status':status,'normal_TLS':True}));print(q,b.decode(),flush=True);time.sleep(1.3)
