#!/usr/bin/env python3
"""Bounded public medical-source acquisition; preserve every actual outcome.

No credentials, CAPTCHA handling, address geocoding or automatic admission.
Raw responses belong outside Git. A successful HTML page is not a dataset.
"""
from pathlib import Path
import argparse,concurrent.futures,datetime,hashlib,json,urllib.request

URLS={
 'official_subdivision_passport':'https://nsi.rosminzdrav.ru/dictionaries/1.2.643.5.1.13.13.99.2.114/passport/latest',
 'official_subdivision_data_probe':'https://nsi.rosminzdrav.ru/port/rest/data?identifier=1.2.643.5.1.13.13.99.2.114&page=1&size=1',
 'archived_mirror_package':'https://data.apicrafter.ru/packages/nsimz-4612',
 'archived_mirror_sample':'https://data.apicrafter.ru/tables/nsimz/4612/sample.json',
 'archived_mirror_public_api':'https://api.crftr.net/open/rawapi/v3/nsimz/4612?max_results=1',
}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--timeout',type=int,default=30);a=ap.parse_args()
 if a.out.exists() and any(a.out.iterdir()):raise SystemExit('Refusing to replace an existing source directory')
 a.out.mkdir(parents=True,exist_ok=True)
 def fetch(item):
  key,url=item;r={'source_id':key,'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'automatically_admitted':False}
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'SGRTResearch/2026 public-source-probe'})
   with urllib.request.urlopen(req,timeout=a.timeout) as x:b=x.read();r.update(http_status=x.status,content_type=x.headers.get('Content-Type'))
   p=a.out/(key+'.response');p.write_bytes(b);r.update(path=p.name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
   try:
    j=json.loads(b);r['json_root_type']=type(j).__name__
    if isinstance(j,dict):r['json_root_keys']=list(j)[:30]
   except ValueError:r['json_root_type']=None
  except Exception as exc:r['error']=repr(exc)
  return r
 result=list(concurrent.futures.ThreadPoolExecutor(3).map(fetch,URLS.items()))
 (a.out/'acquisition_log.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'attempts':len(result),'http_successes':sum('sha256'in r for r in result),'automatic_admissions':0,'out':str(a.out)}))

if __name__=='__main__':main()
