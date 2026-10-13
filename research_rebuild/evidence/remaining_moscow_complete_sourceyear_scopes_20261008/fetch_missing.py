from pathlib import Path
import json,gzip,urllib.request,urllib.parse
D=Path(__file__).parent
names=['Вороновское (поселение, Москва)','Кленовское (поселение, Москва)','Новофёдоровское (поселение, Москва)','Первомайское (поселение, Москва)','Роговское (поселение, Москва)','Троицк (Москва)','Щербинка']
def fetch(base,params,out):
 u=base+'?'+urllib.parse.urlencode(params)
 b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(3000000)
 j=json.loads(b);(D/out).write_bytes(gzip.compress(b,mtime=0));return j
j=fetch('https://ru.wikipedia.org/w/api.php',dict(action='query',titles='|'.join(names),prop='revisions|pageprops',rvprop='ids|content',rvslots='main',format='json',redirects=1),'missing_municipal_pages.json.gz')
qs=[]
for p in j.get('query',{}).get('pages',{}).values():
 q=p.get('pageprops',{}).get('wikibase_item');print(p['title'],q,'MISSING' if 'missing' in p else '')
 if q:qs.append(q)
fetch('https://www.wikidata.org/w/api.php',dict(action='wbgetentities',ids='|'.join(qs),props='labels|descriptions|claims',languages='ru|en',format='json'),'missing_municipal_entities.json.gz')
