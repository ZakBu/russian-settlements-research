import urllib.request,urllib.parse,json,gzip
from pathlib import Path
O=Path(__file__).parent
names=['Мочище (дачный посёлок, Новосибирская область)','Муслюмово (посёлок железнодорожной станции, Челябинская область)','Чайковская (посёлок станции)','Мыза (Пролетарский территориальный округ)','Мыза (Привокзальный территориальный округ)','Писцово Новое','Савино (Нердвинское сельское поселение)','Савино (Менделеевское сельское поселение)','Ишалино (посёлок при станции, Челябинская область)','Тарасиха (посёлок станции, Нижегородская область)','Смолино (Челябинская область)','Тальжино','Барсуки (деревня, Тульская область)','Барсуки (Ленинский район)','Барсуки (городской округ Тула)','Ергач','Комарихинский','Титан (Мурманская область)','Петелино (посёлок, Тульская область)','Поповка (Раменский район)','Петровское (Ленинский район)']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(names),'prop':'revisions|pageprops','rvprop':'ids|content','rvslots':'main','format':'json','redirects':1})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(2000000);(O/'additional_pages.json.gz').write_bytes(gzip.compress(b));q=[]
for p in json.loads(b).get('query',{}).get('pages',{}).values():
 if p.get('pageprops',{}).get('wikibase_item'):q.append(p['pageprops']['wikibase_item'])
 print(p['title'],p.get('pageprops',{}).get('wikibase_item'),'MISSING' if 'missing'in p else '')
u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(q),'props':'labels|descriptions|claims|sitelinks','languages':'ru|en','format':'json'})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(3000000);(O/'additional_entities.json.gz').write_bytes(gzip.compress(b))
