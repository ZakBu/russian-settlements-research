from pathlib import Path
import urllib.request,urllib.parse,json,gzip,concurrent.futures,datetime,hashlib
O=Path(__file__).parent
names=['Ильинское (сельское поселение Ярополецкое)','Ильинское (сельское поселение Теряевское)','Шохово (деревня)','Шохово (село)','Никольское (сельское поселение Колюбакинское)','Никольское (сельское поселение Волковское)','Кобяково (деревня, Одинцовский район)','Кобяково (посёлок, Одинцовский район)','Лёдово (деревня, городской округ Кашира)','Лёдово (посёлок, городской округ Кашира)','Пешково (село)','Пешково (сельское поселение Стремиловское)','Стеблево (сельское поселение Кашинское)','Стеблево (сельское поселение Теряевское)','Пустоши (Московская область)','Агафониха (Московская область)','Зарайский','Щурово (Коломенский район)']
def fetch(n):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='expandtemplates',text='{{Население | '+n+' }}',prop='wikitext',format='json'))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:b=r.read(1500000)
  return dict(title=n,url=u,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),response=json.loads(b))
 except Exception as e:return dict(title=n,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=5)as ex:r=list(ex.map(fetch,names))
f=O/'own_population_template_expansions.json.gz';f.write_bytes(gzip.compress(json.dumps(r,ensure_ascii=False).encode()));print(json.dumps([dict(title=x['title'],text=x.get('response',{}).get('expandtemplates',{}).get('wikitext','')[:3000],error=x.get('error'))for x in r],ensure_ascii=False))
