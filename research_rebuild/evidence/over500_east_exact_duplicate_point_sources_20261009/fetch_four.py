import urllib.request,urllib.parse,json,gzip,hashlib,time,csv
from pathlib import Path
p=Path(__file__).parent;receipts=[];rows=[]
for i,(name,q) in enumerate([('Михайловка','Михайловка, Закаменский район, Бурятия'),('Хуртага','Хуртага, Закаменский район, Бурятия'),('Починок','Починок, Новоуральский городской округ, Свердловская область'),('Тарасково','Тарасково, Новоуральский городской округ, Свердловская область')],1):
 u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,extratags=1,namedetails=1,limit=10))
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40).read();j=json.loads(b);f=f'own_features_{i}.json.gz';gzip.open(p/f,'wb').write(b);sha=hashlib.sha256(b).hexdigest();receipts.append(dict(name=name,url=u,file=f,sha256=sha,count=len(j)));print(name,json.dumps(j,ensure_ascii=False),flush=True)
  for k,x in enumerate(j):rows.append(dict(target_name=name,sourcefile=f,source_sha256=sha,locator=f'JSON[{k}]',osm_type=x.get('osm_type'),osm_id=x.get('osm_id'),lat=x.get('lat'),lon=x.get('lon'),name=x.get('name'),category=x.get('category'),type=x.get('type'),address=json.dumps(x.get('address'),ensure_ascii=False),extratags=json.dumps(x.get('extratags'),ensure_ascii=False),namedetails=json.dumps(x.get('namedetails'),ensure_ascii=False),disposition='source_candidate_only; node versus area centroid distinguished by osm_type; no admission'))
 except Exception as e:receipts.append(dict(name=name,error=str(e)));print(e,flush=True)
 time.sleep(1.2)
(p/'capture_receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
with gzip.open(p/'own_feature_candidates.csv.gz','wt',encoding='utf8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['target_name']);w.writeheader();w.writerows(rows)
