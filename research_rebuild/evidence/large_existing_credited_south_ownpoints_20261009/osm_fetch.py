from pathlib import Path
import urllib.request,urllib.parse,json,time
Z=Path(__file__).parent
names=['Никольское Воронеж','Репное Воронеж','Первое Мая Воронеж','Подклетное Воронеж','Соляной Волгоград','Гумрак Волгоград','Пашковский Краснодар','Заводской Каменск-Шахтинский','Верхний Каменномост Карачаевский район','Нижний Каменномост Карачаевский район']
for i,q in enumerate(names):
 f=Z/f'osm_own_{i}.json';u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',namedetails=1,addressdetails=1,limit=8));
 if not f.exists():
  try:f.write_bytes(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'LocalityCensusEvidence/1.0'}),timeout=25).read())
  except Exception as e:print(q,e,flush=True);continue
 print(q,[(a['name'],a['category'],a['type'],a['lat'],a['lon'],a['display_name'],a['osm_type'],a['osm_id']) for a in json.loads(f.read_text())],flush=True)
 time.sleep(1)
