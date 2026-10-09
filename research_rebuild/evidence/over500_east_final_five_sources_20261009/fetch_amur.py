import urllib.request,urllib.parse,gzip,json,hashlib,time
from pathlib import Path
from bs4 import BeautifulSoup
p=Path(__file__).parent;r=[]
for i,t in enumerate(['Успеновка (Благовещенский район)','Дмитриевка (Ивановский район)'],1):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='parse',page=t,prop='text|revid',format='json'))
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40).read();j=json.loads(b);gzip.open(p/f'amur_rendered_{i}.json.gz','wb').write(b);s=BeautifulSoup(j.get('parse',{}).get('text',{}).get('*',''),'html.parser').get_text(' ',strip=True);r.append(dict(title=t,url=u,file=f'amur_rendered_{i}.json.gz',sha256=hashlib.sha256(b).hexdigest(),revid=j.get('parse',{}).get('revid'),literal_text=s));print(t,s[:16000],flush=True)
 except Exception as e:r.append(dict(title=t,error=str(e)));print(e,flush=True)
 time.sleep(1.2)
(p/'amur_rendered_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
