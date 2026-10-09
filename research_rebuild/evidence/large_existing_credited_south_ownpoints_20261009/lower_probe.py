from pathlib import Path
import urllib.request,concurrent.futures
Z=Path(__file__).parent
U={'osm_kamennomost_full.xml':'https://www.openstreetmap.org/api/0.6/relation/3874352/full','foto_kamennomost.html':'https://foto-planeta.com/np/90814/kamennomostskiy.html','geonames_kamennomost.html':'https://www.geonames.org/553515/kamennomostskiy.html','search_lower_yandex.html':'https://yandex.ru/search/?text=Нижний+Каменномост+координаты'}
def f(x):
 n,u=x
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'LocalityCensusEvidence/1.0'}),timeout=40);b=r.read();(Z/n).write_bytes(b);print(n,r.status,len(b))
 except Exception as e:print(n,e)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as p:list(p.map(f,U.items()))
