import urllib.request,concurrent.futures
from pathlib import Path
Z=Path(__file__).parent
U={'map_vlasenko.jpg':'https://maps.vlasenko.net/smtm100/k-37-012.jpg','map_etomesto.jpg':'https://www.etomesto.ru/maps/genshtab/k-37-012.jpg','lower_wikimapia.html':'https://wikimapia.org/#lang=ru&lat=43.747176&lon=41.907951&z=14'}
def f(x):
 n,u=x
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=40);b=r.read();(Z/n).write_bytes(b);print(n,r.status,len(b))
 except Exception as e:print(n,e)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as p:list(p.map(f,U.items()))
