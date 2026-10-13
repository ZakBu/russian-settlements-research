import json,urllib.request,urllib.parse,re,hashlib,concurrent.futures
from pathlib import Path
E=Path(__file__).resolve().parent
pages={'Пошехонье-Володарск':'Пошехонье (город)','Чекановский':'Чекановский (Братск)','Кармаскалы':'Кармаскалы (Кармаскалинский район)','Кулар':'Кулар (Якутия)','Якурим':'Якурим (посёлок)','Михайловка':'Михайловка (Михайловский район, Приморский край)'}
qids=set(json.load(open(E/'selected_qids.json')))
def get(z):
 n,t=z;u='https://ru.wikipedia.org/wiki/'+urllib.parse.quote(t.replace(' ','_'));fn='article_'+hashlib.sha256(t.encode()).hexdigest()[:12]+'.html'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();(E/fn).write_bytes(b);qs=re.findall(r'wgWikibaseItemId[^Q]{0,15}(Q\d+)',b.decode());return dict(source_name=n,title=t,url=u,path=fn,sha256=hashlib.sha256(b).hexdigest(),qid_matches=qs,already_selected_qid=any(q in qids for q in qs))
 except Exception as e:return dict(source_name=n,title=t,url=u,error=str(e))
a=json.load(open(E/'article_receipts.json'));new=list(concurrent.futures.ThreadPoolExecutor(3).map(get,pages.items()));a+=new;(E/'article_receipts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));print([(x['source_name'],x.get('qid_matches'),x.get('already_selected_qid'),x.get('error'))for x in new])
