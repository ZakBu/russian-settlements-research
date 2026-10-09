from pathlib import Path
import urllib.request,urllib.parse,urllib.error,gzip,json,time
O=Path(__file__).parent
locs=[('Shemetovo',[56.5264,38.0756]),('Podolsky',[55.3874,37.54]),('Kudinovo',[55.76,38.2066]),('Pushkino',[55.9945,37.835]),('Tkatskoy',[55.8429,37.2576])]
for key,geo in locs:
 u='https://pastvu.com/api2?'+urllib.parse.urlencode({'method':'photo.giveNearestPhotos','params':json.dumps({'geo':geo,'distance':2000,'limit':50})})
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25)as r:b=r.read(2000000);st=r.status
 except urllib.error.HTTPError as e:
  (O/f'{key}_failure.json').write_text(json.dumps({'url':u,'status':e.code,'bypass':False}));print('HTTP',e.code);break
 (O/f'{key}_nearby_photos.json.gz').write_bytes(gzip.compress(b));(O/f'{key}_request.json').write_text(json.dumps({'url':u,'status':st,'normal_TLS':True,'query_point_is_spatial_search_hint_only_not_admitted_as_oldNPpoint':True}));j=json.loads(b);print(key,str(j)[:13000],flush=True);time.sleep(1.2)
