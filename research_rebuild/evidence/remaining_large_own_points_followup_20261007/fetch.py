import urllib.request,urllib.parse,gzip,json,time
from pathlib import Path
O=Path(__file__).parent
names=['Сабурово (Красногорский район)','Сибирский (ЗАТО)','Барсуки (Тульская область)','Крюково (городской округ Чехов)','Крюково (Чеховский район)','Мочище (посёлок)','Мирный (Люберецкий район)','Чашниково (Солнечногорский район)','Муслюмово (железнодорожная станция)','Чайковская (посёлок при станции)','Мыза (Тульская область)','Ново-Писцово','Савино (Карагайский район)','Ишалино (железнодорожная станция)','Орёл (Пермский край)','Тарасиха (посёлок станции)','Смолино (железнодорожная станция)','Тальжино (посёлок станции)']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(names),'prop':'revisions|pageprops','rvprop':'ids|content','rvslots':'main','format':'json','redirects':1})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(1800000);(O/'own_pages.json.gz').write_bytes(gzip.compress(b));a=json.loads(b);q=[]
for p in a.get('query',{}).get('pages',{}).values():
 if p.get('pageprops',{}).get('wikibase_item'):q.append(p['pageprops']['wikibase_item'])
 print(p['title'],p.get('pageprops',{}).get('wikibase_item'),'MISSING' if 'missing'in p else '')
u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(q),'props':'labels|descriptions|claims|sitelinks','languages':'ru|en','format':'json'})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(3000000);(O/'entities.json.gz').write_bytes(gzip.compress(b))
