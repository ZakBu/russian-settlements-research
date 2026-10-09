from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,time
from bs4 import BeautifulSoup
O=Path(__file__).parent;receipts=[]
for i,title in enumerate(['Надеждино (Белебеевский район)','Сайгафар'],1):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='parse',page=title,prop='text|revid',format='json'))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=20)as r:b=r.read();status=r.status
  p=O/f'additional_v6_rendered_{i}.json.gz';p.write_bytes(gzip.compress(b,mtime=0));j=json.loads(b);html=j.get('parse',{}).get('text',{}).get('*','');text=BeautifulSoup(html,'html.parser').get_text(' ',strip=True);rec=dict(requested_title=title,url=u,normal_TLS=True,status=status,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_file=str(p),revid=j.get('parse',{}).get('revid'),parsed_visible_text=text);receipts.append(rec);print(title,text[:5000],flush=True)
 except Exception as e:receipts.append(dict(requested_title=title,url=u,error=str(e)));print(str(e),flush=True)
 time.sleep(1.1)
(O/'additional_v6_rendered_articles_receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
