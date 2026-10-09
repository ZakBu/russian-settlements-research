from pathlib import Path
import urllib.request,urllib.parse,json,gzip
O=Path(__file__).parent
terms=['Мосрентген','Воскресенское Москва посёлок','Фабрики имени 1 Мая','Института полиомиелита','Газопровод Москва','совхоза Крекшино','Ремзавод Москва','Дома отдыха Вороново','Совхоза имени 1 Мая Балашиха']
out=[]
for term in terms:
 params={'action':'query','format':'json','formatversion':2,'list':'search','srsearch':term,'srlimit':5}
 req=urllib.request.Request('https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params),headers={'User-Agent':'SettlementSourceResearch/1.0'})
 with urllib.request.urlopen(req,timeout=40) as r:d=json.load(r)
 out.append({'term':term,'response':d});print(term,[x['title'] for x in d.get('query',{}).get('search',[])],flush=True)
with gzip.open(O/'moscow_remaining_title_search.json.gz','wt') as f:json.dump(out,f,ensure_ascii=False)
