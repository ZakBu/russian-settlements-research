from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,datetime
O=Path(__file__).parent
T=['Кущёвская','Дыгулыбгей','Кинель-Черкассы','Плиево','Сириус (посёлок городского типа)','Ленина (Краснодар)','Сибирский (ЗАТО)','Лопатино (Ленинский городской округ)','Сергиевск','Ахмат-Юрт','Бичура','Бердыкель','Сабурово (городской округ Красногорск)','Рождествено (городской округ Истра)','Звёздный городок','Барсуки (Ингушетия)','Малиновка (Калтанский городской округ)','Лежнево','Бирюч','Спасск (Пензенская область)']
q={'action':'query','format':'json','formatversion':'2','prop':'revisions|pageprops|coordinates','rvprop':'ids|timestamp|content','rvslots':'main','titles':'|'.join(T),'redirects':'1','colimit':'max'}
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(q)
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=45).read();d=json.loads(b)
p=O/'own_pages.json.gz'
with gzip.open(p,'wb') as f:f.write(b)
(O/'fetch_manifest.json').write_text(json.dumps({'url':u,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_sha256':hashlib.sha256(b).hexdigest(),'requested_titles':T},ensure_ascii=False,indent=2))
for a in d['query']['pages']:
 t=a.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','')
 print('\nPAGE',a['title'],a.get('pageprops',{}).get('wikibase_item'),a.get('coordinates'))
 for l in t.splitlines():
  if any(k in l for k in ['Численность населения','2002','2010','Население по годам']):print(l[:1800])
