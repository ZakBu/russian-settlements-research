import urllib.request,json,hashlib
from pathlib import Path
from PIL import Image
p=Path(__file__).parent;rs=[]
for name,sheet in [('golovino','n-37-009'),('kuznetsy','o-39-051'),('istye_estate','n-37-026'),('efremov3','n-37-101')]:
 u=f'https://maps.vlasenko.net/smtm100/{sheet}.jpg'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=45).read();f=p/f'{name}_{sheet}.jpg';f.write_bytes(b);im=Image.open(f);size=im.size;im.thumbnail((1400,1700));im.save(p/f'{name}_overview.jpg');rs.append(dict(target=name,url=u,file=f.name,sha256=hashlib.sha256(b).hexdigest(),dimensions=size));print(name,size,flush=True)
 except Exception as e:rs.append(dict(target=name,url=u,error=str(e)));print(name,str(e),flush=True)
(p/'source_capture_receipt.json').write_text(json.dumps(rs,ensure_ascii=False,indent=2))
