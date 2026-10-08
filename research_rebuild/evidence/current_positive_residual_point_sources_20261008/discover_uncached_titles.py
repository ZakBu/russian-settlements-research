from pathlib import Path
import pandas as pd,json,gzip,urllib.parse,urllib.request,re,time
O=Path(__file__).parent;f=pd.read_csv(O/'positive100_priority_roster.csv.gz',keep_default_na=False);t=pd.read_csv(O/'cached_title_source_binding_candidates.csv.gz',keep_default_na=False);done=set(t.source_record_id);f=f.head(200);rows=[];receipt=[]
for i,z in enumerate(f[~f.source_record_id.isin(done)].to_dict('records')):
 # Search is candidate discovery only; full article/native rival verification follows.
 q=z['settlement_name']+' '+re.sub(r'\b(?:муниципальный|городской|город|округ|муниципальное|образование)\b',' ',z['district_raw'],flags=re.I);q=' '.join(q.split());u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','list':'search','srsearch':q,'srlimit':5,'format':'json'});p=O/f'own_article_discovery_search_{i:03}.json.gz'
 for a in range(2):
  try:b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 (+bounded locality ownpoint verification)'}),timeout=20).read(150000);d=json.loads(b);p.write_bytes(gzip.compress(b,mtime=0));break
  except Exception as ex:
   d={}
   if a==0:time.sleep(4)
   else:receipt.append({'source_record_id':z['source_record_id'],'query':q,'failure':type(ex).__name__+':'+str(ex)})
 for hit in d.get('query',{}).get('search',[]):rows.append({'source_record_id':z['source_record_id'],'article_title':hit['title'],'pageid':hit.get('pageid'),'search_snippet':hit.get('snippet'),'search_query':q,'search_source_file':str(p)})
 receipt.append({'source_record_id':z['source_record_id'],'query':q,'candidate_hits':len(d.get('query',{}).get('search',[])),'url':u,'file':str(p) if p.exists() else ''})
 if i%20==0:print('searched',i+1,'of',len(f[~f.source_record_id.isin(done)]),flush=True)
pd.DataFrame(rows).to_csv(O/'searched_own_article_title_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'own_article_discovery_search_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print('all candidate hits',len(rows),flush=True)
