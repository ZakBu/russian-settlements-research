from pathlib import Path
import urllib.request,urllib.parse,json,gzip,time
O=Path(__file__).parent
u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode({'q':'Никольская церковь, Ярославское шоссе 34, Пушкино','format':'jsonv2','limit':3})
with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 public research'}),timeout=30)as r:b=r.read(1000000);st=r.status
(O/'Pushkino_church_searchhint.json.gz').write_bytes(gzip.compress(b));(O/'Pushkino_church_searchhint_request.json').write_text(json.dumps({'url':u,'status':st,'admitted_point':False}));j=json.loads(b);print(j,flush=True)
for i,c in enumerate(j[:1]):
 time.sleep(1.3);u='https://pastvu.com/api2?'+urllib.parse.urlencode({'method':'photo.giveNearestPhotos','params':json.dumps({'geo':[float(c['lat']),float(c['lon'])],'distance':2000,'limit':50})})
 with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:b=r.read(1000000);st=r.status
 (O/'Pushkino_former_selo_nearby_photos.json.gz').write_bytes(gzip.compress(b));(O/'Pushkino_former_selo_nearby_request.json').write_text(json.dumps({'url':u,'status':st,'admitted_query_point':False}));print(json.dumps(json.loads(b),ensure_ascii=False),flush=True)
