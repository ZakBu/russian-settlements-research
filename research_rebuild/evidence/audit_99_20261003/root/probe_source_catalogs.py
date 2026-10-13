"""Bounded HTTPS catalogue probe. No bulk sources downloaded or accepted."""
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,re,time
OUT=Path('/workspace/settlements-work/continuation_20261003/audit_99_20261003/root/source_catalogs');OUT.mkdir(exist_ok=True)
urls={'rosstat_classifiers':'https://rosstat.gov.ru/classification','nalog_fias_catalog':'https://www.nalog.gov.ru/opendata/7707329152-fias/','geofabrik_russia_catalog':'https://download.geofabrik.de/russia.html'}
def fetch(item):
 name,url=item;start=time.monotonic();receipt={'name':name,'url':url,'attempted_utc':datetime.now(timezone.utc).isoformat(),'tls_verification':True,'bulk_download':False,'accepted_source':False}
 try:
  with urlopen(Request(url,headers={'User-Agent':'settlements-research-source-audit/1.0'}),timeout=12) as r:
   raw=r.read(1500001);receipt.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'),truncated=len(raw)>1500000)
  raw=raw[:1500000];p=OUT/(name+'.html');p.write_bytes(raw)
  s=raw.decode('utf-8',errors='replace');hrefs=re.findall(r'href\s*=\s*[\"\']([^\"\']+)',s,re.I)
  receipt.update(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),relevant_links=[u for u in hrefs if any(k in u.lower() for k in ['oktmo','октмо','fias','gar','xml','csv','xlsx','pbf','shape','shp','classification'])][:45])
 except Exception as e:receipt.update(error_type=type(e).__name__,error=str(e),http_status=getattr(e,'code',None))
 receipt['seconds']=round(time.monotonic()-start,3);return receipt
with ThreadPoolExecutor(max_workers=3) as pool:receipts=list(pool.map(fetch,urls.items()))
(OUT/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
for r in receipts:print(json.dumps(r,ensure_ascii=False))
