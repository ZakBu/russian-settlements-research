from pathlib import Path
import json,gzip,urllib.request,urllib.parse
O=Path(__file__).parent
names=['Поселение Московский','Поселение Сосенское','Поселение Воскресенское','Поселение Кокошкино','Поселение Киевский','Поселение Мосрентген','Поселение Щаповское','Поселение Внуковское','Поселение Рязановское','Расширение территории Москвы','Троицкий и Новомосковский административные округа']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(names),'prop':'revisions|pageprops','rvprop':'ids|content','rvslots':'main','format':'json','redirects':1})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(2400000);(O/'municipal_pages.json.gz').write_bytes(gzip.compress(b));q=[]
for p in json.loads(b).get('query',{}).get('pages',{}).values():
 if p.get('pageprops',{}).get('wikibase_item'):q.append(p['pageprops']['wikibase_item'])
 print(p['title'],p.get('pageprops',{}).get('wikibase_item'),'MISSING' if 'missing'in p else '')
u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(q),'props':'labels|descriptions|claims','languages':'ru|en','format':'json'})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(2600000);(O/'municipal_entities.json.gz').write_bytes(gzip.compress(b))
