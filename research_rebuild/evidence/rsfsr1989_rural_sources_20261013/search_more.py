import urllib.request,urllib.parse,re,json,hashlib,concurrent.futures
from pathlib import Path
E=Path(__file__).resolve().parent
queries=['"1989" "сельских населенных пунктов" "численность" xls','"1989" "lingvarium" "население"','"1989" "сельских населенных пунктов" "3000"','"1989" "сельских населенных пунктов" "по каждому"']
def get(q):
 u='https://html.duckduckgo.com/html/?q='+urllib.parse.quote(q)
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=25).read();s=b.decode();fn='search_'+hashlib.sha256(q.encode()).hexdigest()[:10]+'.html';(E/fn).write_bytes(b)
  matches=re.findall(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',s,re.S)
  return dict(query=q,url=u,path=fn,sha256=hashlib.sha256(b).hexdigest(),results=[dict(url=__import__('html').unescape(a),title=re.sub('<[^>]+>','',__import__('html').unescape(t)))for a,t in matches])
 except Exception as e:return dict(query=q,error=str(e))
a=list(concurrent.futures.ThreadPoolExecutor(4).map(get,queries));(E/'further_search.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));print(json.dumps(a,ensure_ascii=False,indent=2))
