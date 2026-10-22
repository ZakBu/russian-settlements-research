#!/usr/bin/env python3
from pathlib import Path
import requests,concurrent.futures,os,time,hashlib,json,shutil,threading
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_transport');RAW.mkdir(exist_ok=True)
URL='https://download.geofabrik.de/russia-210101.osm.pbf'
probe=requests.get(URL,headers={'Range':'bytes=0-1023'},timeout=30);assert probe.status_code==206 and b'OSMHeader' in probe.content[:40]
SIZE=int(probe.headers['Content-Range'].split('/')[-1]);ETAG=probe.headers.get('ETag');assert SIZE<3_000_000_000
assert shutil.disk_usage(RAW).free-SIZE>12*1024**3,'Insufficient safe free space'
p=RAW/'russia-210101.osm.pbf.partial';final=RAW/'russia-210101.osm.pbf'
if final.exists():raise SystemExit('Historical PBF exists; reuse rather than redownload')
fd=os.open(p,os.O_CREAT|os.O_RDWR,0o600);os.ftruncate(fd,SIZE);CHUNK=16*1024**2;start=time.time();lock=threading.Lock();done=[]
def one(pair):
 a,b=pair
 for attempt in range(5):
  try:
   headers={'Range':f'bytes={a}-{b}'}
   if ETAG:headers['If-Range']=ETAG
   r=requests.get(URL,headers=headers,timeout=(20,90));r.raise_for_status()
   assert r.status_code==206 and r.headers['Content-Range']==f'bytes {a}-{b}/{SIZE}' and len(r.content)==b-a+1
   os.pwrite(fd,r.content,a)
   row={'start':a,'end':b,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'etag':r.headers.get('ETag')}
   with lock:
    done.append(row)
    if len(done)%8==0:print('chunks',len(done),'seconds',round(time.time()-start),flush=True)
   return row
  except Exception as e:
   if attempt==4:raise
   print('retry',a,repr(e),flush=True);time.sleep(min(2*(attempt+1),6))
try:
 pairs=[(a,min(a+CHUNK,SIZE)-1) for a in range(0,SIZE,CHUNK)]
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:rows=list(ex.map(one,pairs))
 os.close(fd);assert sum(x['bytes'] for x in rows)==SIZE
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 p.rename(final)
 receipt={'status':'DOWNLOADED_COMPLETE','url':URL,'bytes':SIZE,'sha256':h.hexdigest(),'etag':ETAG,'seconds':time.time()-start,'parts':rows,'local_path':str(final),'snapshot_label':'2021-01-01_geofabrik_archive','license':'OpenStreetMap ODbL1.0;Geofabrikdistribution'}
 (ROOT/'history_download_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k!='parts'},indent=2))
except Exception as e:
 (ROOT/'history_download_failure.json').write_text(json.dumps({'error':repr(e),'completed_chunks':done,'seconds':time.time()-start},indent=2));raise
