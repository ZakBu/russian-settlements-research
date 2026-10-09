from pathlib import Path
import urllib.request,urllib.parse,json
Z=Path(__file__).parent
names=['Масловка (Воронеж)','Никольское (Воронеж)','Репное (Воронеж)','Подгорное (Воронеж)','Первое Мая (Воронеж)','Подклетное (Воронеж)','Краснолесный','Придонской','Сомово (Воронеж)','Шилово (Воронеж)','Троицкое (Новохопёрский район)','Соляной (Волгоград)','Горный (Волгоград)','Водстрой','Горьковский (Волгоград)','Гумрак','Южный (Волгоград)','Краснооктябрьский (Волгоградская область)','Калинино (Краснодар)','Пашковский','Дугулубгей','Верхний Каменномост','Нижний Каменномост','Кора-Урсдон','Сидорово-Кадамовский','Заводской (Каменск-Шахтинский)','Лиховской','Донской (Новочеркасск)','Красный (Новошахтинск)','Самбек (Новошахтинск)','Соколово-Кундрюченский','Аютинский','Майский (Шахты)','Таловый']
for i in range(0,len(names),8):
 f=Z/f'wiki_batch_{i//8}.json';u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(names[i:i+8]),prop='revisions|pageprops|coordinates',rvprop='content|ids|timestamp',rvslots='main',format='json',formatversion=2,redirects=1));
 if not f.exists():f.write_bytes(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'LocalityCensusEvidence/1.0'}),timeout=25).read())
 for p in json.loads(f.read_text())['query']['pages']:
  print(p['title'],p.get('missing'),p.get('coordinates'),p.get('pageprops'),flush=True)
