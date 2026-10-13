from pathlib import Path
import urllib.request,urllib.parse,urllib.error,gzip,json,time
O=Path(__file__).parent
locs=[('Podolsky_estate_north',[55.392,37.539]),('Pushkino_selo',[55.9987,37.844]),('Pushkino_seloEast',[56.001,37.848]) ]
for key,geo in locs:
 u='https://pastvu.com/api2?'+urllib.parse.urlencode({'method':'photo.giveNearestPhotos','params':json.dumps({'geo':geo,'distance':2000,'limit':50})})
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25)as r:b=r.read(2000000);st=r.status
 except urllib.error.HTTPError as e:
  (O/f'{key}_failure.json').write_text(json.dumps({'url':u,'status':e.code,'bypass':False}));print('HTTP',e.code);break
 (O/f'{key}_nearby_photos.json.gz').write_bytes(gzip.compress(b));(O/f'{key}_request.json').write_text(json.dumps({'url':u,'status':st,'normal_TLS':True,'query_point_is_spatial_search_hint_only_not_admitted_as_oldNPpoint':True}));j=json.loads(b);print(key,str(j)[:22000],flush=True);time.sleep(1.2)
