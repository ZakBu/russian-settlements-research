import json,gzip,re,hashlib,urllib.parse,datetime
from pathlib import Path
import pandas as pd,urllib.request,urllib.error
O=Path(__file__).parent;F=pd.read_csv(O/'disjoint_cached_claim_inventory.csv.gz');F=F[~F.explicit_census2002_unique_population].sort_values('population2010',ascending=False);qtargets={}
for z in F.to_dict('records'):
 qs=json.loads(z['own_native_code_QID_candidates_json'])
 if len(qs)==1:qtargets.setdefault(qs[0],z)
tsv=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');titleq={};qtitle={}
for line in tsv.open():
 v=line.rstrip().split('\t');m=re.search(r'Q\d+',v[0])
 if m and m[0] in qtargets and len(v)>5 and 'ru.wikipedia.org/wiki/' in v[5]:
  title=urllib.parse.unquote(v[5].strip('<>').split('/wiki/')[-1]).replace('_',' ');titleq[title]=m[0];qtitle[m[0]]=title
# Reuse own-title cached pages. The TSV source binds article titles to the exact current own NP code/entity; no generic name search.
cache=[];seenq=set()
paths=list(Path('/workspace/settlements-raw/data/raw/wikipedia_articles').glob('batch*.json.gz'))+list((O.parent/'large2010_residual_native2002_followup_20261008').glob('own_wikipedia_articles_batch*.json.gz'))
for p in paths:
 d=json.load(gzip.open(p,'rt'));d=d.get('payload',d);pages=d.get('query',{}).get('pages',[])
 for pg in (pages if isinstance(pages,list) else pages.values()):
  title=pg.get('title','');q=titleq.get(title)
  if not q:continue
  rev=pg.get('revisions',[{}])[0];text=rev.get('slots',{}).get('main',{}).get('content',rev.get('slots',{}).get('main',{}).get('*',rev.get('*','')))
  if text:cache.append({'qid':q,'title':title,'article_text':text,'source_path':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_locator':f'pageid={pg.get("pageid")};revid={rev.get("revid")}'});seenq.add(q)
pd.DataFrame(cache).to_csv(O/'own_cached_or_bounded_wikipedia_articles.csv.gz',index=False,compression={'method':'gzip','mtime':0})
wanted=[q for q in qtargets if q not in seenq and q in qtitle][:50];titles=[qtitle[q] for q in wanted];pd.DataFrame([{'qid':q,'title':qtitle[q],**qtargets[q]} for q in wanted]).to_csv(O/'bounded_own_article_requests.csv.gz',index=False,compression={'method':'gzip','mtime':0});receipt={'source_tsv':str(tsv),'source_tsv_sha256':hashlib.sha256(tsv.read_bytes()).hexdigest(),'cached_own_articles_reused':len(seenq),'requests':0,'titles':titles,'ordinary_name_lookup_used':False}
if titles:
 params={'action':'query','format':'json','formatversion':2,'prop':'revisions','rvprop':'ids|timestamp|content','rvslots':'main','redirects':1,'titles':'|'.join(titles),'maxlag':5};url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params);req=urllib.request.Request(url,headers={'User-Agent':'SettlementHistoryResearch/2026 (bounded source validation)'})
 try:
  with urllib.request.urlopen(req,timeout=60) as rr:body=rr.read();status=rr.status
 except urllib.error.HTTPError as err:
  body=err.read();status=err.code
 receipt.update(requests=1,url=url,status_code=status,received_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());p=O/'bounded_own_article_response.json.gz';p.write_bytes(gzip.compress(body,mtime=0));receipt.update(raw_response=str(p),raw_response_sha256=hashlib.sha256(p.read_bytes()).hexdigest());(O/'network_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));assert status==200,status;d=json.loads(body);assert 'error' not in d,d.get('error');alias={qtitle[q]:q for q in wanted}
 for z in d.get('query',{}).get('normalized',[])+d.get('query',{}).get('redirects',[]):
  if z['from'] in alias:alias[z['to']]=alias[z['from']]
 for pg in d.get('query',{}).get('pages',[]):
  q=alias.get(pg.get('title'));rev=pg.get('revisions',[{}])[0];text=rev.get('slots',{}).get('main',{}).get('content','')
  if q and text:cache.append({'qid':q,'title':pg['title'],'article_text':text,'source_path':str(p),'source_sha256':receipt['raw_response_sha256'],'source_locator':f'pageid={pg.get("pageid")};revid={rev.get("revid")}'} )
else:(O/'network_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
pd.DataFrame(cache).to_csv(O/'own_cached_or_bounded_wikipedia_articles.csv.gz',index=False,compression={'method':'gzip','mtime':0});print('cached',len(seenq),'requested',len(titles),'own returned total',len(cache))
