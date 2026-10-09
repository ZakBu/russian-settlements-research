from pathlib import Path
import urllib.request,urllib.parse,gzip,json
O=Path(__file__).parent;titles=['Краснояр-I','Краснояр-II','Ергач (посёлок)','Ергач (деревня)','Вильва (Добрянский городской округ)','Вильва (Добрянский район)','Лётно-Хвалынское','Авангард (Приморский край)','Шумный (Приморский край)','Шумное (Приморский край)'];u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','format':'json','prop':'coordinates|revisions','rvslots':'main','rvprop':'ids|timestamp|content','titles':'|'.join(titles)})
with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 ownnative record context'}),timeout=35)as r:b=r.read(2000000);st=r.status
(O/'own_wikipedia_batch1.json.gz').write_bytes(gzip.compress(b));(O/'own_wikipedia_batch1_request.json').write_text(json.dumps({'url':u,'status':st,'normal_TLS':True}));j=json.loads(b)
for p in j.get('query',{}).get('pages',{}).values():
 print(p['title'],'missing'in p,p.get('coordinates'),flush=True)
 if'missing'not in p:
  t=p.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('*','');print(t[:6000],flush=True)
