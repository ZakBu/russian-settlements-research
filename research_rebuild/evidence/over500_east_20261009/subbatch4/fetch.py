from pathlib import Path
import pandas as pd,json,gzip,urllib.request,urllib.parse,concurrent.futures
O=Path(__file__).parent;d=pd.read_csv(O.parent/'record_dispositions.csv');d=d[d.region_norm.eq('башкортостан')&d.disposition.str.startswith('unresolved')];names=d.settlement_name.tolist()+['Лоза (Удмуртия)','Кушья','Пижил','Люкшудья','Шаргайта','Истимисс']
def query(name):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',format='json',list='search',srsearch=name,srlimit=3));req=urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'});
 try:
  with urllib.request.urlopen(req,timeout=30)as f:return name,json.load(f)
 except Exception as e:return name,{'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=8)as ex:j=dict(ex.map(query,names))
with gzip.open(O/'searches.json.gz','wt')as f:json.dump(j,f,ensure_ascii=False)
print([(k,[a['title']for a in v.get('query',{}).get('search',[])])for k,v in j.items()])
T=list(dict.fromkeys(a['title']for v in j.values()for a in v.get('query',{}).get('search',[])))
for n in range(0,len(T),30):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',format='json',titles='|'.join(T[n:n+30]),prop='revisions|coordinates',rvprop='ids|timestamp|content',rvslots='main',colimit='max',redirects=1));req=urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'});
 with urllib.request.urlopen(req,timeout=45)as f:q=json.load(f)
 with gzip.open(O/f'articles{n//30}.json.gz','wt')as f:json.dump(q,f,ensure_ascii=False)
