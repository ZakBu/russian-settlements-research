from pathlib import Path
import urllib.request,urllib.parse,gzip,json,time
O=Path(__file__).parent
qs=[('Shemetovo_centralestate_housing','https://pastvu.com/api2?'+urllib.parse.urlencode({'method':'photo.giveNearestPhotos','params':json.dumps({'geo':[56.524884,38.075372],'distance':1800,'limit':50})})),('Pushkino_oldchurch_article','https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','format':'json','prop':'coordinates|revisions','rvprop':'ids|timestamp|content','rvslots':'main','titles':'Церковь Николая Чудотворца в селе Пушкино'}))]
for k,u in qs:
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 source linkage'}),timeout=35)as r:b=r.read(1500000);status=r.status
 except Exception as e:print(k,str(e));continue
 (O/(k+'.json.gz')).write_bytes(gzip.compress(b));(O/(k+'_request.json')).write_text(json.dumps({'status':status,'url':u,'normal_TLS':True}));j=json.loads(b)
 if k.startswith('Shemet'):print(k,json.dumps(j,ensure_ascii=False)[:13000])
 else:
  for pg in j.get('query',{}).get('pages',{}).values():print(k,pg.get('title'),pg.get('coordinates'));print(str(pg.get('revisions',''))[:1200])
 time.sleep(1.3)
