from pathlib import Path
import urllib.request,urllib.parse,json,gzip,concurrent.futures,datetime,hashlib
O=Path(__file__).parent.parent
names=['Кобяково (городское поселение Голицыно)','Кобяково (сельское поселение Захаровское)','Ледово (сельское поселение Домнинское)','Лёдово (сельское поселение Колтовское)','Захарово (Рыболовское сельское поселение)','Захарово (Новохаритоновское сельское поселение)','Пешково (сельское поселение Баранцевское)','Пешково (сельское поселение Стремиловское)']
def fetch(n):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='expandtemplates',text='{{Население | '+n+' }}',prop='wikitext',format='json'))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:b=r.read(1500000)
  return dict(title=n,url=u,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),response=json.loads(b))
 except Exception as e:return dict(title=n,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=5)as ex:r=list(ex.map(fetch,names))
f=O/'batch2_lifecycle_homonyms/own_population_template_expansions2.json.gz';f.write_bytes(gzip.compress(json.dumps(r,ensure_ascii=False).encode()));print(json.dumps([dict(title=x['title'],text=x.get('response',{}).get('expandtemplates',{}).get('wikitext','')[-1600:],error=x.get('error'))for x in r],ensure_ascii=False))
