from pathlib import Path
import urllib.request,urllib.parse,json,gzip,time,hashlib
O=Path(__file__).parent
queries=['Холмогорка, Волоколамск, Московская область','Абрамцево, Балашиха, Московская область','Караваевской фабрики, Московская область','Тимоховский, Московская область','поселок Луч, Гребнево, Московская область','санаторий Звенигород, Московская область','поселок Юдино, Одинцовский, Московская область','Участок 2, Ногинск, Московская область']
results=[]
for i,q in enumerate(queries):
 u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,extratags=1,namedetails=1,limit=10))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:b=r.read();status=r.status
  f=O/f'OSM_own_search_{i+1}.json.gz';f.write_bytes(gzip.compress(b));results.append(dict(query=q,url=u,status=status,path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest()));print(q, json.loads(b),flush=True)
 except Exception as e:
  print(q,type(e).__name__,str(e),flush=True);results.append(dict(query=q,url=u,error=str(e)))
  if'429'in str(e):break
 time.sleep(1.1)
(O/'OSM_own_search_requests.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
