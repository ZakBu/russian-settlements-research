from pathlib import Path
import urllib.request,gzip,json,hashlib,concurrent.futures
O=Path(__file__).parent
urls=['https://www.etomesto.com/map-atlas_topo-russia-ural/?x=58.269905&y=55.335754','https://www.etomesto.ru/map-ufa_bashkiriya-1944/?x=55.236784&y=54.051566','https://ufagen.ru/places/alsheevskiy/krimskiy.html','https://bashenc.online/ru/articles/87160/','https://docs.cntd.ru/document/935113266']
def fetch(z):
 i,u=z
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=20)as r:b=r.read();status=r.status;final=r.geturl()
  p=O/f'exact_context_source_{i}.html.gz';p.write_bytes(gzip.compress(b,mtime=0));return dict(url=u,final_url=final,status=status,normal_TLS=True,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=len(b))
 except Exception as e:return dict(url=u,error=str(e))
a=list(concurrent.futures.ThreadPoolExecutor(max_workers=3).map(fetch,enumerate(urls,1)));(O/'exact_context_sources_receipt.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));print(json.dumps(a,ensure_ascii=False,indent=2))
