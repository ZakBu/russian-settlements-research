import urllib.request,json,gzip,time,hashlib
from pathlib import Path
import pandas as pd
RAW=Path('/dev/shm/over500-20261009/south_osm');x=pd.read_csv(RAW/'candidates.csv');objects=x[x.type.isin(['hamlet','village','suburb','neighbourhood','locality','town','administrative'])].drop_duplicates(['osm_type','osm_id']);receipts=[]
for q in objects.itertuples():
 typ=q.osm_type;oid=int(q.osm_id);u=f'https://www.openstreetmap.org/api/0.6/{typ}/{oid}.json';path=RAW/f'object_{typ}_{oid}.json.gz'
 if path.exists():data=json.load(gzip.open(path,'rt'))
 else:
  try:
   response=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=20);data={'url':u,'status_code':response.status,'body':json.loads(response.read().decode())}
  except Exception as exc:data={'url':u,'error':str(exc),'body':{}}
  with path.open('wb') as f:
   with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as gz:gz.write(json.dumps(data,ensure_ascii=False).encode())
  time.sleep(.1)
 receipts.append(dict(osm_type=typ,osm_id=oid,capture=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),error=data.get('error','')));print(typ,oid,data.get('error','ok'),flush=True)
pd.DataFrame(receipts).to_csv(RAW/'object_receipts.csv',index=False)
