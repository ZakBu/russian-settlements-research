"""Acquire pinned postcensus municipality population bulletins, TLS verified."""
from pathlib import Path
from datetime import datetime,timezone
import urllib.request,hashlib,json,concurrent.futures,urllib.parse
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent;RAW=ROOT/'work/ecommerce_extension_outcomes/raw';RAW.mkdir(exist_ok=True,parents=True)
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/national'
items=json.loads((BASE/'rosstat_acquisition_inventory.json').read_text())['files']
def get(item):
 year=item['observation_year'];p=RAW/f'population_{year}.xlsx';r={'url':item['source_url'],'year':year,'tls_verification':True,'requested_utc':datetime.now(timezone.utc).isoformat()}
 try:
  if not p.exists():
   u=urllib.parse.quote(item['source_url'],safe=':/?=&%')
   with urllib.request.urlopen(u,timeout=35) as response:p.write_bytes(response.read())
  digest=hashlib.sha256(p.read_bytes()).hexdigest();r.update(sha256=digest,bytes=p.stat().st_size,pinned_sha256_match=digest==item['sha256'],path=str(p.relative_to(ROOT)))
  if digest!=item['sha256']:raise ValueError('Pinned population snapshot differs')
 except Exception as e:r['error']=str(e)
 return r
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(get,[i for i in items if i['observation_year']>=2023]))
 (OUT/'population_acquisition.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(json.dumps(results,ensure_ascii=False,indent=2))
