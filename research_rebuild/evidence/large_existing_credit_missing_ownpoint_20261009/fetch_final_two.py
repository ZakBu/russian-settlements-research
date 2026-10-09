import urllib.request,urllib.parse,urllib.error,json,gzip,time
from pathlib import Path
O=Path(__file__).parent
names=['Ремзавод (Наро-Фоминский район)','Балашиха-Парк','Балашиха-парк']
params={'action':'query','format':'json','formatversion':2,'titles':'|'.join(names),'redirects':1,'prop':'coordinates|revisions|pageprops','ppprop':'wikibase_item','colimit':'max','rvprop':'ids|timestamp|content','rvslots':'main'}
req=urllib.request.Request('https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params),headers={'User-Agent':'SettlementSourceResearch/1.0'})
for attempt in range(3):
 try:
  with urllib.request.urlopen(req,timeout=60) as r:raw=r.read()
  d=json.loads(raw)
  with gzip.open(O/'moscow_final_two_exact_ownwiki_batch.json.gz','wt',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False)
  print('OK',len(raw))
  for p in d.get('query',{}).get('pages',[]):print(p['title'],p.get('missing'),p.get('coordinates'),p.get('pageprops'))
  break
 except urllib.error.HTTPError as x:
  delay=max(40,min(60,int(x.headers.get('Retry-After','40'))))
  (O/f'moscow_batch3_http_attempt{attempt}.json').write_text(json.dumps({'status':x.code,'retry_after':x.headers.get('Retry-After'),'bounded_backoff_seconds':delay}))
  if x.code!=429 or attempt==2:raise
  print('HTTP429 boundedbackoff',delay,flush=True);time.sleep(delay)
