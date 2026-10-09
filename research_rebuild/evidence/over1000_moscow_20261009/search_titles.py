from pathlib import Path
import json,urllib.request,urllib.parse,gzip,concurrent.futures
O=Path(__file__).parent
queries=['"Агрогород" Домодедово','"Красный Холм" Воскресенск','"Центральной Усадьбы" Сергиево','"Пушкино" "село"','"Бужаниново" "посёлок"','"Светлый" "Вишняковские"','"Волоколамец"','"Ильинское" Домодедово','"Петелинской"','"Хлюпинского"','"Масловский" Московской','"Шарапово" Чехов','"Поповка" Раменский','"Подсобного" "Поречье"','"Щёкино" Волоколамский','"Кирпичного" Серпухов','"Клязьминское" "пансионат"','"Центральной" "Чапаева"','"50-летия" Ногинский','"Пирогово" Мытищи','"Абрамцево" село']
def f(q):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',list='search',srsearch=q,srlimit=5,format='json'))
 with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=30)as r:j=json.load(r)
 return dict(query=q,url=u,response=j)
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:res=list(ex.map(f,queries))
(O/'live_title_searches.json.gz').write_bytes(gzip.compress(json.dumps(res,ensure_ascii=False).encode()))
for r in res:print(r['query'],[x['title']for x in r['response'].get('query',{}).get('search',[])])
