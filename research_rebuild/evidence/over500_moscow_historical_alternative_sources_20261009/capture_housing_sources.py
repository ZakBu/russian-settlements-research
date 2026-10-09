from pathlib import Path
import urllib.request,gzip,json,hashlib,datetime
from bs4 import BeautifulSoup
O=Path(__file__).parent
urls=[('Holmogorka_flatinfo15','https://flatinfo.ru/h_info1.asp?hid=109427'),('Holmogorka_gogov17','https://dom.gogov.ru/houses/8332321'),('FirmLuch_flatinfo5','https://flatinfo.ru/h_info1.asp?hid=301183'),('Zvenigorod_old_settlement','https://www.novostroy-m.ru/baza/poselok_sanatoriya_zvenigorod'),('FirmLuch_housing_street','https://fryazino.info/address/street/10060')]
r=[]
for name,url in urls:
 e={'name':name,'URL':url,'normal_TLS':True,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate_source_only':True}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; settlement source research)'}),timeout=12)as resp:raw=resp.read();e.update(status=resp.status,final_url=resp.url)
  f=O/(name+'.html.gz');f.write_bytes(gzip.compress(raw,mtime=0));e.update(capture=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest());s=BeautifulSoup(raw,'html.parser');text=' '.join(s.stripped_strings);(O/(name+'.txt')).write_text(text);e['title']=s.title.get_text()if s.title else '';print(name,len(raw))
 except Exception as exc:e['error']=str(exc);print(name,str(exc))
 r.append(e)
(O/'housing_web_source_receipts.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
