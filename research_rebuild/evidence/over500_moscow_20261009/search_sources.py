from pathlib import Path
import urllib.request,urllib.parse,json,gzip,concurrent.futures
O=Path(__file__).parent
terms=['Порохово Московская','Ильинское Волоколамский','Детского дома МООСО','Зарайский посёлок','Минвнешторга поселок','Холмогорка Волоколамский','Шохово Можайский','Абрамцево Балашиха','опытного хозяйства Толстопальцево','участка 2 Ногинский','Кобяково Одинцовский','РАОС','Тучковского автодорожного','Никольское Рузский','Пустоши Шатурский','Луч Щёлковский','Санаторий Звенигород поселок','Алабино пгт','дорожно ремонтного пункта 3','Захарово Раменский','слободка Алёшино','Щурово деревня','Пограничный Серпуховский','Пешково Чеховский','Агафониха Дмитровский','Стеблево Волоколамский']
def get(q):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',list='search',srsearch=q,srlimit=5,format='json')); 
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:b=r.read(1500000)
  return dict(query=q,url=u,response=json.loads(b))
 except Exception as e:return dict(query=q,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=6)as ex:r=list(ex.map(get,terms))
(O/'own_article_searches.json.gz').write_bytes(gzip.compress(json.dumps(r,ensure_ascii=False).encode()));print(json.dumps([dict(query=z['query'],titles=[v['title']for v in z.get('response',{}).get('query',{}).get('search',[])])for z in r],ensure_ascii=False))
