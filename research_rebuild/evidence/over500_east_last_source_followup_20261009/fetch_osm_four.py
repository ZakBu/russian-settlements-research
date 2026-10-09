from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,time,datetime,pandas as pd
O=Path(__file__).parent;queries=['Центральная усадьба Раевского совхоза, Альшеевский район, Башкортостан','Новые Турналы, Салаватский район, Башкортостан','Новомихайловский, Белебей, Башкортостан','Восточный, Охинский район, Сахалинская область'];rows=[];receipts=[]
for i,q in enumerate(queries,1):
 u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,extratags=1,namedetails=1,limit=10))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=20)as r:b=r.read();status=r.status
  f=O/f'osm_query_{i}.json.gz';f.write_bytes(gzip.compress(b,mtime=0));sha=hashlib.sha256(f.read_bytes()).hexdigest();a=json.loads(b);receipts.append(dict(query=q,url=u,status=status,normal_TLS=True,capture=str(f),sha256=sha,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  for x in a:rows.append(dict(query=q,osm_type=x.get('osm_type'),osm_id=x.get('osm_id'),latitude=x.get('lat'),longitude=x.get('lon'),own_name=x.get('name'),display_name=x.get('display_name'),category=x.get('category'),feature_type=x.get('type'),address_type=x.get('addresstype'),address_json=json.dumps(x.get('address',{}),ensure_ascii=False),extratags_json=json.dumps(x.get('extratags',{}),ensure_ascii=False),namedetails_json=json.dumps(x.get('namedetails',{}),ensure_ascii=False),capture=str(f),sha256=sha,candidate_only=True))
  print(q,len(a),flush=True)
 except Exception as e:
  receipts.append(dict(query=q,url=u,error=str(e)));print(str(e),flush=True)
  if getattr(e,'code',None)==429:break
 time.sleep(1.1)
pd.DataFrame(rows).to_csv(O/'osm_qualified_own_feature_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'osm_capture_receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
print(pd.DataFrame(rows)[['query','own_name','latitude','longitude','extratags_json']].to_string(index=False))
