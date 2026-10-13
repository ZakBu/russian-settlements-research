from pathlib import Path
import json,gzip,urllib.request,urllib.parse
O=Path(__file__).parent
names=['Московский (город)','Мосрентген (посёлок)','Кокошкино (Москва)','Ватутинки','Киевский (Москва)','Знамя Октября (посёлок)','Воскресенское (посёлок, Москва)','ЛМС (посёлок)','Коммунарка (посёлок)','Птичное (посёлок)','Яковлевское (Москва)','Шишкин Лес','Марушкино','Фабрики имени 1 Мая (посёлок)','Ильинское (Домодедово)','Зелёный (Московская область)','Звёздный городок','Рождествено (Истринский район)','Приокск','Городок-17','Коренёво (Московская область)']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(names),'prop':'revisions|pageprops','rvprop':'ids|content','rvslots':'main','format':'json','redirects':1})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(2100000);(O/'own_pages.json.gz').write_bytes(gzip.compress(b));q=[]
for p in json.loads(b).get('query',{}).get('pages',{}).values():
 if p.get('pageprops',{}).get('wikibase_item'):q.append(p['pageprops']['wikibase_item'])
 print(p['title'],p.get('pageprops',{}).get('wikibase_item'),'MISSING' if 'missing'in p else '')
u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(q),'props':'labels|descriptions|claims|sitelinks','languages':'ru|en','format':'json'})
b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(2500000);(O/'entities.json.gz').write_bytes(gzip.compress(b))
