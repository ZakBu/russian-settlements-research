from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,datetime,pandas as pd
O=Path(__file__).parent
names=['Заречный (Кабардино-Балкария)','Заречный (Прохладненский район)','Дальний (Кабардино-Балкария)','Дальний (Прохладненский район)','Малокановский','Малокановское','Малакановское','Виноградный (Кабардино-Балкария)','Виноградный (Прохладненский район)','Лесной (Кабардино-Балкария)','Лесное (Кабардино-Балкария)','Лесное (Прохладненский район)','Юбилейное (Дагестан)','Юбилейный (Дагестан)','Юбилейный (Кизлярский район)','Школьное (Дагестан)','Школьный (Кизлярский район)','Школьное (Кизлярский район)','Мущули','Мушули','Кадыркент','Кадар','Гиреевский (Ингушетия)','Шидиб','Гоцатль Малый','Малый Гоцатль','Малое Козыревское','Караозек','Караузек']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(names),prop='revisions|pageprops|coordinates',rvprop='ids|content|timestamp',rvslots='main',format='json',redirects=1,colimit='max'))
with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40) as resp:b=resp.read();status=resp.status
f=O/'priority_batch.json.gz';f.write_bytes(gzip.compress(b,mtime=0));sha=hashlib.sha256(f.read_bytes()).hexdigest()
(O/'priority_batch_receipt.json').write_text(json.dumps(dict(request_url=u,normal_TLS=True,status=status,sha256=sha,response_sha256=hashlib.sha256(b).hexdigest(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),ensure_ascii=False,indent=2))
rows=[]
for p in json.loads(b).get('query',{}).get('pages',{}).values():
 if 'missing' in p:continue
 rv=p.get('revisions',[{}])[0];content=rv.get('slots',{}).get('main',{}).get('*','')
 for c in p.get('coordinates',[]) or [{}]:
  rows.append(dict(article_title=p['title'],pageid=p.get('pageid'),revid=rv.get('revid'),qid=p.get('pageprops',{}).get('wikibase_item',''),latitude=c.get('lat',''),longitude=c.get('lon',''),disambiguation='disambiguation' in p.get('pageprops',{}),capture=str(f),capture_sha256=sha,history_county_witness=' || '.join(t for t in content.splitlines() if __import__('re').search('переимен|прежн|бывш|2002|2010|район|назван|образован|основан',t,__import__('re').I))[:13000],candidate_only=True))
d=pd.DataFrame(rows);d.to_csv(O/'priority_article_coordinate_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});print(d[['article_title','latitude','longitude','qid']].to_string(index=False))
