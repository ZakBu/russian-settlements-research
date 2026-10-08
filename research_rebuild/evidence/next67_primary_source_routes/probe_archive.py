from pathlib import Path
import urllib.request,urllib.parse,json,concurrent.futures,hashlib
E=Path(__file__).resolve().parent
queries={'perm_2010':'permstat.gks.ru/*2010*','mord_2010':'mordovstat.gks.ru/*2010*','prim_2010':'primstat.gks.ru/*2010*','perm_storage':'permstat.gks.ru/storage/mediabank/*','mord_storage':'mordovstat.gks.ru/storage/mediabank/*','prim_storage':'primstat.gks.ru/storage/mediabank/*'}
def fetch(x):
 k,q=x;u='https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode({'url':q,'output':'json','filter':'statuscode:200','collapse':'urlkey','limit':'150','fl':'timestamp,original,mimetype,length'});r={'name':k,'url':u}
 try:
  a=urllib.request.urlopen(u,timeout=20);d=a.read(2000000);p=E/(k+'_CDX.json');p.write_bytes(d);r.update(status=a.status,tls_verified=True,bytes=len(d),sha256=hashlib.sha256(d).hexdigest(),entries=json.loads(d))
 except Exception as e:r['error']=str(e)
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=6)as pool:rows=list(pool.map(fetch,queries.items()))
(E/'archive_probe_receipt.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False,indent=2))
