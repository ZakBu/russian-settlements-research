from pathlib import Path
import urllib.request,urllib.parse,json
Z=Path(__file__).parent
names=['Гумрак (посёлок)','Пашковский (Краснодар)','Заводской (Ростовская область)','Заводской (микрорайон Каменска-Шахтинского)','Верхний Каменномостский','Нижний Каменномостский','Репное (Воронежская область)','Никольское (городской округ Воронеж)','Первое Мая (посёлок, Воронежская область)','Первое Мая (Воронежская область)','Подклетное','Соляной (Волгоградская область)','Головчино','Елань-Колено','Никольское (Аннинский район)','Хохол (село)','Лозовое (Верхнемамонский район)','Нижний Мамон','Архангельское (Аннинский район)','Кущевская']
for i in range(0,len(names),8):
 f=Z/f'wiki_followup_{i//8}.json';u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(names[i:i+8]),prop='revisions|pageprops|coordinates',rvprop='content|ids|timestamp',rvslots='main',format='json',formatversion=2,redirects=1));
 if not f.exists():f.write_bytes(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'LocalityCensusEvidence/1.0'}),timeout=25).read())
 for p in json.loads(f.read_text())['query']['pages']:print(p['title'],p.get('missing'),p.get('coordinates'),p.get('pageprops'),flush=True)
