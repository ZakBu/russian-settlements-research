from pathlib import Path
import urllib.request,urllib.parse,json,hashlib
E=Path(__file__).resolve().parent;routes=[]
for name in ['alt2010_CDX','mord_new2010_CDX']:
 a=json.loads((E/(name+'.json')).read_text())
 for row in a[1:]:
  u=urllib.parse.unquote(row[2])
  if u.endswith('/national_census_2010'):routes.append(('alt2010_catalog.html',row))
  if 'Население+Республики+Мордовия.'in u and u.endswith('.rar'):routes.append(('mord2010_census_population.rar',row))
receipts=[]
for fn,row in routes:
 u=f'https://web.archive.org/web/{row[1]}id_/{row[2]}'
 try:
  a=urllib.request.urlopen(u,timeout=30);data=a.read(700001)
  if len(data)>700000:raise ValueError('source exceeds700KBboundedroute')
  (E/fn).write_bytes(data);receipts.append({'file':fn,'url':u,'original':row[2],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'status':a.status,'TLS_verified':True});print(receipts[-1],flush=True)
 except Exception as ex:receipts.append({'url':u,'error':str(ex)});print(receipts[-1],flush=True)
(E/'discovered_source_receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
