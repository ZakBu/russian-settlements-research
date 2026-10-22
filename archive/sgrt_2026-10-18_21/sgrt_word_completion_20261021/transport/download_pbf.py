#!/usr/bin/env python3
from pathlib import Path
import requests,concurrent.futures,os,time,hashlib,json,threading
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_transport');RAW.mkdir(exist_ok=True)
URL='https://download.geofabrik.de/russia-261019.osm.pbf';SIZE=4183109834;ETAG='"f95530ca-65e3dd53f5f63"';CHUNK=16*1024**2
p=RAW/'russia.osm.pbf.partial';fd=os.open(p,os.O_CREAT|os.O_RDWR,0o600);os.ftruncate(fd,SIZE)
start=time.time();lock=threading.Lock();done=[]
def one(pair):
 a,b=pair
 for attempt in range(5):
  try:
   r=requests.get(URL,headers={'Range':f'bytes={a}-{b}','If-Range':ETAG},timeout=(20,90));r.raise_for_status()
   assert r.status_code==206,(r.status_code,len(r.content))
   assert r.headers['Content-Range']==f'bytes {a}-{b}/{SIZE}',r.headers
   assert len(r.content)==b-a+1
   os.pwrite(fd,r.content,a)
   row={'start':a,'end':b,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'etag':r.headers.get('ETag')}
   with lock:
    done.append(row)
    if len(done)%8==0:print('chunks',len(done),'bytes',sum(x['bytes'] for x in done),'seconds',round(time.time()-start),flush=True)
   return row
  except Exception as e:
   if attempt==4:raise
   print('retry',a,repr(e),flush=True)
   time.sleep(min(2*(attempt+1),6))
try:
 pairs=[(a,min(a+CHUNK,SIZE)-1) for a in range(0,SIZE,CHUNK)]
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:rows=list(ex.map(one,pairs))
 os.close(fd)
 assert sum(x['bytes'] for x in rows)==SIZE
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 final=RAW/'russia.osm.pbf';p.rename(final)
 receipt={'status':'DOWNLOADED_COMPLETE','url':URL,'bytes':SIZE,'sha256':h.hexdigest(),'etag':ETAG,'seconds':time.time()-start,'parts':rows,'local_path':str(final),'OSM_snapshot_to':'2026-10-19T20:21:11Z','license':'OpenStreetMap ODbL1.0;Geofabrikdistribution'}
 (ROOT/'download_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k!='parts'},indent=2))
except Exception as e:
 (ROOT/'download_failure.json').write_text(json.dumps({'error':repr(e),'completed_chunks':done,'seconds':time.time()-start},indent=2));raise
