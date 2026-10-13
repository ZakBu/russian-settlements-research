import urllib.request,urllib.parse,concurrent.futures,json
from pathlib import Path
Z=Path(__file__).parent
U={'wikidata_lower.json':'https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'Q4211209|Q28482727','languages':'ru|en','format':'json'}),'wiki_lower_search.json':'https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','list':'search','srsearch':'"Нижний Каменномост"','format':'json'}),'lower_google.html':'https://www.google.com/search?'+urllib.parse.urlencode({'q':'"Нижний Каменномост" координаты'}),'lower_yandex.html':'https://yandex.ru/search/?'+urllib.parse.urlencode({'text':'"Нижний Каменномост"'}),'lower_bing.html':'https://www.bing.com/search?'+urllib.parse.urlencode({'q':'"Нижний Каменномост"','format':'rss'})}
def f(x):
 n,u=x
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 LocalityCensusEvidence/1.0'}),timeout=35);b=r.read();(Z/n).write_bytes(b);print(n,r.status,len(b))
 except Exception as e:print(n,e)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as p:list(p.map(f,U.items()))
