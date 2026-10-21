from pathlib import Path
import requests,json,hashlib
H=Path(__file__).resolve().parent/'sources';rows=[]
for domain in ['istmat.org','istmat.info']:
 url='https://'+domain+'/files/uploads/15861/narhoz_rsfsr_1974_sh.pdf';row=dict(url=url)
 try:
  r=requests.get(url,timeout=20);row.update(status=r.status_code,bytes=len(r.content))
  if not r.content.startswith(b'%PDF'):
   c=requests.get('https://web.archive.org/cdx/search/cdx',params={'url':url,'output':'json','filter':'statuscode:200','limit':'-1'},timeout=25);(H/(domain+'_pdf_cdx.json')).write_bytes(c.content);ts,original=c.json()[-1][1:3];retrieval='https://web.archive.org/web/'+ts+'id_/'+original;r=requests.get(retrieval,timeout=45);row.update(archive_url=r.url,archive_status=r.status_code,archive_bytes=len(r.content))
  assert r.content.startswith(b'%PDF');p=H/'narhoz_rsfsr_1974_agriculture.pdf';p.write_bytes(r.content);row.update(saved_as=p.name,sha256=hashlib.sha256(r.content).hexdigest());rows.append(row);break
 except Exception as e:row['error']=repr(e);rows.append(row)
(H/'yearbook_acquisition.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
