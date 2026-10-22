from pathlib import Path
import requests,json,hashlib,concurrent.futures
H=Path(__file__).resolve().parent/'sources'
def get(name):
 url='https://istmat.org/files/uploads/15861/'+name;r=requests.get('https://web.archive.org/cdx/search/cdx',params={'url':url,'output':'json','filter':'statuscode:200','limit':'-1'},timeout=25);(H/(name+'.cdx.json')).write_bytes(r.content);ts,orig=r.json()[-1][1:3];a='https://web.archive.org/web/'+ts+'id_/'+orig;r=requests.get(a,timeout=45);assert r.content.startswith(b'%PDF');p=H/name;p.write_bytes(r.content);return dict(url=url,archive_url=r.url,file=name,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest())
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(get,['narhoz_rsfsr_1974_predislovie.pdf','narhoz_rsfsr_1974_naselenie.pdf']))
(H/'primary_support_acquisition.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
