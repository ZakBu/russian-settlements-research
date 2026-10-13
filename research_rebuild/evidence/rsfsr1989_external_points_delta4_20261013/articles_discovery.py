import urllib.request,urllib.parse,json,re,hashlib,concurrent.futures
from pathlib import Path
E=Path(__file__).resolve().parent
names=['Покровка (Приморский край)','Кочетовка (Мичуринск)','Моховая (Петропавловск-Камчатский)','Красный Октябрь (Киржач)','Мамонтово (Ханты-Мансийский автономный округ)']
def get(t):
 u='https://ru.wikipedia.org/wiki/'+urllib.parse.quote(t.replace(' ','_'));fn='article_discovery_'+hashlib.sha256(t.encode()).hexdigest()[:10]+'.html'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();(E/fn).write_bytes(b);return dict(title=t,url=u,path=fn,sha256=hashlib.sha256(b).hexdigest(),qid_matches=re.findall(r'wgWikibaseItemId[^Q]{0,15}(Q\d+)',b.decode()))
 except Exception as e:return dict(title=t,url=u,error=str(e))
a=list(concurrent.futures.ThreadPoolExecutor(3).map(get,names));(E/'article_discovery_receipts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));print(a)
