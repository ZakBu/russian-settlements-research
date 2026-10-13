import json,urllib.request,urllib.parse,hashlib
from pathlib import Path
E=Path(__file__).resolve().parent
names=['Шипуново','Покровка','Крыловская','Тацинская','Мамонтово','Красный Октябрь (Киржач)','Кочетовка','Моховая']
a=[]
for n in names:
 u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(dict(action='wbsearchentities',search=n,language='ru',uselang='ru',format='json',limit=10));fn='search_'+hashlib.sha256(n.encode()).hexdigest()[:12]+'.json'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();(E/fn).write_bytes(b);z=dict(name=n,url=u,path=fn,sha256=hashlib.sha256(b).hexdigest(),results=json.loads(b).get('search',[]));print(n,[(v['id'],v.get('label'),v.get('description'))for v in z['results']],flush=True)
 except Exception as e:z=dict(name=n,url=u,error=str(e));print(n,e,flush=True)
 a.append(z);(E/'search_receipts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2))
 if '429'in z.get('error',''):break
