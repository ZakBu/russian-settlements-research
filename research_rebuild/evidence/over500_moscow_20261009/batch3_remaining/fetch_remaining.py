from pathlib import Path
import gzip,json,urllib.request,urllib.parse,datetime,hashlib,concurrent.futures
O=Path(__file__).parent
def fetch(k,params):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params)
 with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40)as r:b=r.read(12000000)
 f=O/(k+'.json.gz');f.write_bytes(gzip.compress(b));(O/(k+'_request.json')).write_text(json.dumps(dict(url=u,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sha256=hashlib.sha256(f.read_bytes()).hexdigest()),ensure_ascii=False,indent=2));return k,json.loads(b)
names=['Алабино (дачный посёлок, Московская область)','Абрамцево (Балашиха)','Абрамцево (деревня, Балашиха)']
queries=[('remaining_own_articles',dict(action='query',titles='|'.join(names),prop='revisions|pageprops|coordinates',rvprop='ids|content|timestamp',rvslots='main',format='json',redirects=1,colimit='max'))]
for n in ['Кузнецово (Москва)','Захарово (сельское поселение Рыболовское)','Захарово (городское поселение Кратово)','Исаково (Воскресенский район)']:queries.append(('population_'+str(len(queries)),dict(action='expandtemplates',text='{{Население | '+n+' }}',prop='wikitext',format='json')))
with concurrent.futures.ThreadPoolExecutor(max_workers=5)as pool:
 for k,v in pool.map(lambda z:fetch(*z),queries):print(k,str(v)[:600])
