import urllib.request,urllib.parse,json,gzip,hashlib,datetime
from pathlib import Path
OUT=Path(__file__).resolve().parent
T=['Железнодорожный (Балашиха)','Климовск','Пашковский (посёлок)','Калинино (Краснодар)','Юбилейный (Королёв)','Власиха (Московская область)','Сходня','Никольско-Архангельский','Придонской','Кедровка (Кемерово)','Косая Гора','Московский (город)','Северо-Задонск','Востряково (Домодедово)','Новосиликатный']
text='\n'.join('PLACE='+t+'\n{{Население|'+t+'}}\nENDPLACE' for t in T)
url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'expandtemplates','format':'json','formatversion':'2','prop':'wikitext','text':text})
b=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=45).read();d=json.loads(b)
with gzip.open(OUT/'expanded_population_tables.json.gz','wb') as f:f.write(b)
(OUT/'expanded_tables_fetch_manifest.json').write_text(json.dumps({'url':url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'response_sha256':hashlib.sha256(b).hexdigest(),'compressed_sha256':hashlib.sha256((OUT/'expanded_population_tables.json.gz').read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
t=d.get('expandtemplates',{}).get('wikitext','');(OUT/'expanded_population_tables.txt').write_text(t)
print(t)
