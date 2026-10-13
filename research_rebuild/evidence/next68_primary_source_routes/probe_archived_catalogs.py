from pathlib import Path
import urllib.request,urllib.parse,json,concurrent.futures
E=Path(__file__).resolve().parent
routes=[('mord2010_CDX','https://web.archive.org/cdx/search/cdx?url=mordovstat.gks.ru/*&output=json&filter=statuscode:200&filter=original:.*2010.*&collapse=urlkey&limit=100'),('alt2010_CDX','https://web.archive.org/cdx/search/cdx?url=akstat.gks.ru/*&output=json&filter=statuscode:200&filter=original:.*2010.*&collapse=urlkey&limit=100'),('mord_new2010_CDX','https://web.archive.org/cdx/search/cdx?url=13.rosstat.gov.ru/*&output=json&filter=statuscode:200&filter=original:.*2010.*&collapse=urlkey&limit=50')]
def run(z):
 name,u=z
 try:
  a=urllib.request.urlopen(u,timeout=30);d=a.read(250001)
  if len(d)>250000:raise ValueError('metadata_over250KB_hold')
  (E/(name+'.json')).write_bytes(d);return {'name':name,'url':u,'status':a.status,'bytes':len(d),'body':d.decode()[:12000]}
 except Exception as ex:return {'name':name,'url':u,'error':str(ex)}
r=list(concurrent.futures.ThreadPoolExecutor(3).map(run,routes));(E/'archive_catalog_probe_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
