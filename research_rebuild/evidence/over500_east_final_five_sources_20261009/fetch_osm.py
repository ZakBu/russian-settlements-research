import urllib.request,urllib.parse,gzip,json,hashlib,time
from pathlib import Path
p=Path(__file__).parent;r=[]
for i,q in enumerate(['Успеновка, Благовещенский район, Амурская область','Дмитриевка, Ивановский район, Амурская область','Пригородный, Славгород, Алтайский край'],1):
 u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,extratags=1,namedetails=1,limit=10))
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40).read();j=json.loads(b);gzip.open(p/f'qualified_osm_{i}.json.gz','wb').write(b);r.append(dict(query=q,url=u,file=f'qualified_osm_{i}.json.gz',sha256=hashlib.sha256(b).hexdigest(),features=j));print(q,json.dumps(j,ensure_ascii=False),flush=True)
 except Exception as e:r.append(dict(query=q,error=str(e)));print(e,flush=True)
 time.sleep(1.2)
(p/'qualified_osm_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
