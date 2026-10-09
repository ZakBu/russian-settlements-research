from pathlib import Path
import gzip,json,urllib.request,urllib.parse,datetime,hashlib
O=Path(__file__).parent
names=['Никольская церковь (Пушкино)','Церковь Николая Чудотворца (Пушкино)','Пушкино','Пушкинский сельский округ (Московская область)']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(names),prop='revisions|pageprops|coordinates',rvprop='ids|content|timestamp',rvslots='main',format='json',redirects=1,colimit='max'))
try:
 with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40)as r:b=r.read(9000000);status=r.status
except urllib.error.HTTPError as e:
 (O/'fetch_batch11_failure.json').write_text(json.dumps({'status':e.code,'request_url':u,'retry_after':e.headers.get('Retry-After'),'bypass':False}));raise
f=O/'own_wikipedia_batch11.json.gz';f.write_bytes(gzip.compress(b));j=json.loads(b);rows=[dict(title=p['title'],missing='missing'in p,pageid=p.get('pageid'),revid=p.get('revisions',[{}])[0].get('revid'),point=p.get('coordinates'))for p in j.get('query',{}).get('pages',{}).values()];(O/'fetch_batch11_receipt.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),request_url=u,normal_TLS=True,status=status,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),pages=rows),ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False))
