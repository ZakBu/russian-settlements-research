from pathlib import Path
import urllib.request,urllib.parse,json,hashlib
E=Path(__file__).resolve().parent;inv=json.load(open(E/'cached_official_citation_URL_inventory.json'));urls=[x['url'].split('|')[0]for x in inv];chosen=[('perm_2010_original_archived.xls',next(u for u in urls if u.startswith('https://web.archive.org/web/20140103195710/'))),('prim_2010_original_archived.mht',next(u for u in urls if u.startswith('https://web.archive.org/web/20171111065941/'))),('mord_catalog_archived.html',next(u for u in urls if u.startswith('https://web.archive.org/web/20231027130407/')))];rows=[];budget=9000000;spent=0
for name,u in chosen:
 parts=u.split('/',5);u=u.replace(parts[4],parts[4]+'id_',1);u=urllib.parse.quote(u,safe=':/%+?=&');r={'output_name':name,'retrieval_url':u,'archived_official_publisher_original':u.split('id_/',1)[-1],'origin_locator':'cached Wikipedia citation URL; countclaim requires publicationbytes','license':'No explicit reuse license inferred; retain publisher attribution and exact factual table locators'}
 try:
  a=urllib.request.urlopen(u,timeout=25);n=a.headers.get('Content-Length');maxread=budget-spent
  if n and int(n)>maxread:raise ValueError('ContentLength exceeds remaining9MB acquisitionbudget')
  d=a.read(maxread+1)
  if len(d)>maxread:raise ValueError('Response exceeds remaining9MB acquisitionbudget')
  p=E/name;p.write_bytes(d);spent+=len(d);r.update(status=a.status,finalurl=a.url,bytes=len(d),content_type=a.headers.get('Content-Type'),sha256=hashlib.sha256(d).hexdigest(),tls_verified=True,path=str(p),acquired=True)
 except Exception as ex:r.update(error=str(ex),acquired=False)
 rows.append(r)
(E/'exact_publication_acquisition_receipt.json').write_text(json.dumps({'rows':rows,'actual_downloaded_bytes':spent,'budget_bytes':budget},ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False,indent=2))
