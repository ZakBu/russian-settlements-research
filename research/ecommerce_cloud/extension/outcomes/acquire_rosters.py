"""Try documented official annual OKTMO releases, preserving TLS validation."""
from pathlib import Path
from datetime import datetime, timezone
import urllib.request, hashlib, json, concurrent.futures
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
RAW=ROOT/'work/ecommerce_extension_outcomes/raw'; RAW.mkdir(parents=True,exist_ok=True)
def fetch(item):
 host,date=item
 name=f'data-{date}-structure-20260210T1102.csv'
 url=f'https://{host}/opendata/7708234640-oktmo/{name}'
 record={'url':url,'requested_utc':datetime.now(timezone.utc).isoformat(),'tls_verification':True}
 try:
  with urllib.request.urlopen(url,timeout=35) as r:
   data=r.read();record.update(status=r.status,bytes=len(data),content_type=r.headers.get('Content-Type'),sha256=hashlib.sha256(data).hexdigest())
   if r.status==200 and len(data)>100000 and b';' in data[:1000]:
    path=RAW/(host+'_'+name);path.write_bytes(data);record['path']=str(path.relative_to(ROOT))
   else:record['not_accepted_as_roster']=True
 except Exception as e:record['error']=str(e)
 return record
if __name__=='__main__':
 jobs=[(host,date) for host in ['rosstat.gov.ru','www.rosstat.gov.ru'] for date in ['20221228T1112','20231219T1512','20241227T1412']]
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(fetch,jobs))
 (OUT/'roster_acquisition.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(results,ensure_ascii=False,indent=2))
