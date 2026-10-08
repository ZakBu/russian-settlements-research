from pathlib import Path
import urllib.request,urllib.parse,json,hashlib,re
E=Path(__file__).resolve().parent;inv=json.loads((E/'cached_official_citation_URL_inventory.json').read_text());routes=[]
for x in inv:
 u=x['url'].split('|')[0].replace('\\n','')
 if 'web.archive.org/web/20230430013755/' in u and u.endswith('.pdf'):routes.append(('tula2010.pdf',u.replace('20230430013755/','20230430013755id_/')))
 if 'web.archive.org/web/20250131195029/' in u:routes.append(('alt_catalog.html',u.replace('20250131195029/','20250131195029id_/')))
# sourceheaders first, bounded stream prevents oversized acquisition.
receipt=[];budget=5000000
for name,u in routes:
 try:
  u=urllib.parse.quote(u,safe=':/%+?=&')
  with urllib.request.urlopen(u,timeout=35)as r:
   info={'url':u,'status_code':r.status,'content_type':r.headers.get('content-type'),'declared_length':r.headers.get('content-length'),'TLS_default_verified':True};data=bytearray()
   if r.status==200:
    if r.headers.get('content-length')and int(r.headers['content-length'])>budget:info['hold']='declared_source_exceeds_remaining_5MB_acquisition_budget'
    else:
     while True:
      c=r.read(65536)
      if not c:break
      data.extend(c)
      if len(data)>budget:info['hold']='stream_exceeds_remaining_5MB_budget';break
     if 'hold'not in info:
      (E/name).write_bytes(data);info.update(file=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest());budget-=len(data)
   receipt.append(info);print(json.dumps(info),flush=True)
 except Exception as ex:receipt.append({'url':u,'error':str(ex)});print(str(ex),flush=True)
(E/'bounded_acquisition_receipt.json').write_text(json.dumps({'routes':receipt,'remaining_byte_budget':budget},ensure_ascii=False,indent=2))
