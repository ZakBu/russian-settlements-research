from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,datetime
O=Path(__file__).parent
T=['Кущёвская','Дыгулыбгей','Кинель-Черкассы','Плиево','Ленина (Краснодар)','Сибирский (ЗАТО)','Лопатино (Ленинский район)','Сергиевск','Ахмат-Юрт','Бичура (Бурятия)','Комсомольское (Грозненский район)','Сабурово (Красногорский район)','Рождествено (Истринский район)','Звёздный городок','Барсуки (Ингушетия)','Малиновка (Калтанский городской округ)','Лежнево (Ивановская область)','Бирюч (город)','Спасск (Пензенская область)']
q={'action':'query','format':'json','formatversion':'2','prop':'revisions','rvprop':'ids|timestamp|content','rvslots':'main','titles':'|'.join('Шаблон:Население/'+t for t in T),'redirects':'1'}
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(q);b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=45).read();d=json.loads(b);p=O/'population_templates.json.gz'
with gzip.open(p,'wb') as f:f.write(b)
(O/'templates_manifest.json').write_text(json.dumps({'url':u,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_sha256':hashlib.sha256(b).hexdigest()},ensure_ascii=False,indent=2))
for a in d['query']['pages']:
 t=a.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','');print('\nPAGE',a['title']);print(t[:10000])
