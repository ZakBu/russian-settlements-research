from pathlib import Path
import urllib.request,urllib.error,gzip,json,time
from bs4 import BeautifulSoup
O=Path(__file__).parent
for cid in [1164869,195534,1573402,1159296,1746703,1758515,360474,360472]:
 u=f'https://pastvu.com/p/{cid}'
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25)as r:b=r.read(2000000);st=r.status
 except urllib.error.HTTPError as e:
  (O/f'photo_{cid}_failure.json').write_text(json.dumps({'status':e.code,'url':u,'bypass':False}));break
 (O/f'own_historical_photo_{cid}.html.gz').write_bytes(gzip.compress(b));(O/f'photo_{cid}_request.json').write_text(json.dumps({'status':st,'url':u,'normal_TLS':True}));so=BeautifulSoup(b,'html.parser');t=next(x.get_text()for x in so.find_all('script')if'photo:{'in x.get_text());v=json.JSONDecoder().raw_decode(t.split('photo:',1)[1])[0]['photo'];w={k:x for k,x in v.items()if k in ['cid','title','geo','year','year2','address','desc']};(O/f'photo_{cid}_owngeo_witness.json').write_text(json.dumps(w,ensure_ascii=False,indent=2));print(w,flush=True);time.sleep(.6)
