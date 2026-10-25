"""Retrieve primary methods/literature copies for reading, never commit full texts."""
import hashlib,json,urllib.request,datetime,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'work/sources/research/ecommerce_settlement_20261024/methods_primary_20261025'
OUT.mkdir(parents=True,exist_ok=True)
SOURCES={
 'CH01_author202007.pdf':'https://www.ben-faber.com/ECommerce_CFGL.pdf',
 'CH01_published_appendix.pdf':'https://www.aeaweb.org/articles/materials/14082',
 'US01_published.pdf':'https://oettl.org/pdf/ecommerce-retail.pdf',
 'RU-L01_article.pdf':'https://peasantstudies.ru/ru/category/62-2026-11-3?download=789',
 'METHOD05_spillovers.html':'https://arxiv.org/html/2105.03737v3',
 'METHOD06_author.pdf':'https://arxiv.org/pdf/1803.09015',
 'METHOD07_published.pdf':'https://www.jonathandroth.com/assets/files/HonestParallelTrends_Main.pdf',
 'OZON20221014.html':'https://corp.ozon.ru/ru/sth/ozon-budet-razvivat-pvz-v-selah-i-malyh-gorodah-s-pomoshchyu-predprinimateley-01e20edd',
 'RU-L02_api.json':'https://zenodo.org/api/records/22040878',
}
def deadline_handler(signum,frame):
 raise TimeoutError("absolute request deadline 45 seconds")
signal.signal(signal.SIGALRM,deadline_handler)
manifest_path=Path(__file__).parent/"primary_acquisition.json"
prior={r["url"]:r for r in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
rows=[]
for name,url in SOURCES.items():
 row={'file':str((OUT/name).relative_to(ROOT)),'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  if (OUT/name).exists():
   raw=(OUT/name).read_bytes();row.update(prior.get(url,{}));row.update(reused_local_body=True,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest());rows.append(row);print(name,"cached",flush=True);continue
  signal.alarm(45)
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 settlement research primary-source verification'})
  with urllib.request.urlopen(req,timeout=35) as response:
   raw=response.read();row.update(http_status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
  (OUT/name).write_bytes(raw)
 except Exception as e:row['error']=repr(e)
 signal.alarm(0)
 rows.append(row);print(name,row.get('http_status',row.get('error')),flush=True)
 (Path(__file__).parent/'primary_acquisition.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')

manifest_path.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
