"""Bounded public history-access diagnostics. No credentials, no authentication bypass."""
from pathlib import Path
from datetime import datetime,timezone
import requests,json,hashlib,urllib3
urllib3.disable_warnings()
P=Path(__file__).resolve().parent/'raw'
query='[out:json][timeout:20][date:"2015-01-01T00:00:00Z"];nwr[shop](57.42,45.70,57.52,45.86);out count;'
jobs=[
 ('ohsome_v1_metadata_probe','GET','https://api.ohsome.org/v1/metadata',None),
 ('ohsome_v1_count_probe','GET','https://api.ohsome.org/v1/elements/count',
  {'bboxes':'45.70,57.42,45.86,57.52','time':'2015-01-01,2021-01-01,2026-01-01','filter':'shop=*'}),
 ('ohsome_v2_count_probe','POST','https://api.heigit.org/ohsome-api/v2/stats/features/count',
  {'aoi':[45.70,57.42,45.86,57.52],'filter':'shop=*','time':{'start':'2015-01-01','end':'2026-01-01','interval':'P1Y'}}),
 ('bdpmo_probe','GET','https://www.gks.ru/dbscripts/munst/munst22/DBInet.cgi',None),
 ('dgdat_tree_probe','GET','https://api.github.com/repos/littlepoorgirlfromsyriya/1/git/trees/master',{'recursive':1}),
]
results=[]
for name,method,url,payload in jobs:
 result={'name':name,'method':method,'url':url,'payload':payload,
         'time_utc':datetime.now(timezone.utc).isoformat(),
         'tls_verification':False,'authorization':'none; no credentials used'}
 try:
  kw={'timeout':25,'verify':False}
  r=requests.post(url,json=payload,**kw) if method=='POST' else requests.get(url,params=payload,**kw)
  (P/(name+'.response')).write_bytes(r.content)
  result.update({'status':r.status_code,'final_url':r.url,'bytes':len(r.content),
                 'sha256':hashlib.sha256(r.content).hexdigest()})
 except requests.RequestException as e:result['error']=str(e)
 results.append(result)
(P/'endpoint_probe_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False,indent=2))
