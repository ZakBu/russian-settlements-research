from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,datetime,pandas as pd
O=Path(__file__).parent
names=['Никольское (деревня, Рузский район)','Никольское (село, Рузский район)','Никольское (Рузский район)','Никольское (Рузский городской округ)','Никольское (Дороховское сельское поселение)','Никольское (Ивановское сельское поселение)','Никольское (посёлок, Рузский район)','Захарово (село, Раменский район)','Захарово (деревня, Раменский район)','Захарово (Раменский район)','Захарово (Кратово)','Захарово (Рыболовское сельское поселение)','Захарово (Дементьевское сельское поселение)','Захарово (село, Раменский городской округ)','Захарово (деревня, Раменский городской округ)']
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(names),prop='revisions|pageprops|coordinates',rvprop='ids|content|timestamp',rvslots='main',format='json',redirects=1,colimit='max'))
with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40) as resp:b=resp.read();status=resp.status
f=O/'own_qualified_wiki_batch.json.gz';f.write_bytes(gzip.compress(b,mtime=0));sha=hashlib.sha256(f.read_bytes()).hexdigest()
(O/'own_qualified_wiki_batch_receipt.json').write_text(json.dumps(dict(request_url=u,normal_TLS=True,status=status,sha256=sha,response_sha256=hashlib.sha256(b).hexdigest(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),ensure_ascii=False,indent=2))
rows=[]
for p in json.loads(b).get('query',{}).get('pages',{}).values():
 if 'missing' in p:continue
 rv=p.get('revisions',[{}])[0];content=rv.get('slots',{}).get('main',{}).get('*','')
 for c in p.get('coordinates',[]) or [{}]:
  rows.append(dict(article_title=p['title'],pageid=p.get('pageid'),revid=rv.get('revid'),qid=p.get('pageprops',{}).get('wikibase_item',''),latitude=c.get('lat',''),longitude=c.get('lon',''),disambiguation='disambiguation' in p.get('pageprops',{}),capture=str(f),capture_sha256=sha,history_county_witness=' || '.join(t for t in content.splitlines() if __import__('re').search('переимен|прежн|бывш|2002|2010|район|назван|образован|основан',t,__import__('re').I))[:13000],candidate_only=True))
d=pd.DataFrame(rows);d.to_csv(O/'own_qualified_wiki_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});print(d[['article_title','latitude','longitude','qid']].to_string(index=False))
