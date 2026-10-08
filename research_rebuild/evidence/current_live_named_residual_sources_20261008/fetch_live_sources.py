from pathlib import Path
import re,json,gzip,urllib.parse,urllib.request,concurrent.futures,time,ast,unicodedata,hashlib
import pandas as pd
O=Path(__file__).parent;OLD=O.parent/'current_positive_residual_point_sources_20261008';RULE=OLD/'review_articles.py';normalize=lambda v:str(v).lower().replace('ё','е');tree=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','county']],type_ignores=[]),str(RULE),'exec'))
f=pd.read_csv(O/'positive100_priority_roster.csv.gz',dtype=str,keep_default_na=False);tasks=[]
for i,z in enumerate(f.to_dict('records')):
 name=namekey(z['settlement_name']);co=county(z['district_raw']);reg=z['region_norm'];
 for k,q in enumerate([name+' '+co,name+' '+reg]):tasks.append((i,k,z['source_record_id'],q))
def request(url,limit=2000000):
 for n in range(3):
  time.sleep(3)
  try:return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0 (+bounded source-bound locality verification)'}),timeout=25).read(limit)
  except Exception as ex:
   if getattr(ex,'code',None)==429:
    retry=ex.headers.get('Retry-After','30');wait=float(retry) if str(retry).isdigit() else 30
    print('API rate limit; backoff',min(max(wait,30),60),flush=True);time.sleep(min(max(wait,30),60))
   elif n<2:time.sleep(2+n*2)
   if n==2:raise
def work(t):
 i,k,sid,q=t;p=O/f'live_search_{i:03}_{k}.json.gz';url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','list':'search','srsearch':q,'srlimit':12,'format':'json'});
 try:
  if p.exists():b=gzip.open(p,'rb').read()
  else:return [],{'source_record_id':sid,'url':url,'status':'no_saved_response_from_initial_bounded_sweep; live_API_429_rate_limit_observed; hold_unavailable_not_requeried'}
  d=json.loads(b);hits=[{'source_record_id':sid,'article_title':z['title'],'pageid':z.get('pageid'),'search_snippet':z.get('snippet'),'search_source_file':str(p),'search_query':q} for z in d.get('query',{}).get('search',[])];return hits,{'source_record_id':sid,'source_file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'url':url,'hits':len(hits)}
 except Exception as ex:return [],{'source_record_id':sid,'url':url,'failure':type(ex).__name__+':'+str(ex)}
rows=[];searchmeta=[]
print('serial normalTLS requests paced>=3sec, honoring429backoff; reuseexisting rawresponses',flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
 for i,(r,m) in enumerate(ex.map(work,tasks)):
  rows.extend(r);searchmeta.append(m)
  if i%40==0:print('livequeries',i+1,'/',len(tasks),flush=True)
# Reuse already fetched plausible own articles, retaining all proper-title alternatives.
oldindex=[]
for fn in ['cached_title_article_sources_index.json.gz','searched_own_article_sources_index.json.gz']:oldindex.extend(json.loads(gzip.open(OLD/fn,'rt').read()))
existing={z['article_title']:z for z in oldindex};oldtargets=pd.concat([pd.read_csv(OLD/'cached_title_source_binding_candidates.csv.gz',dtype=str,keep_default_na=False),pd.read_csv(OLD/'searched_own_article_title_candidates_filtered.csv.gz',dtype=str,keep_default_na=False)],ignore_index=True);oldtargets=oldtargets[oldtargets.source_record_id.isin(f.source_record_id)];rows.extend(oldtargets[['source_record_id','article_title']].to_dict('records'));allt=pd.DataFrame(rows).fillna('').drop_duplicates(['source_record_id','article_title']);by=f.set_index('source_record_id');keep=[]
for z in allt.to_dict('records'):
 base=re.sub(r'\s*\([^)]*\)\s*$','',z['article_title'])
 if namekey(base)==namekey(by.loc[z['source_record_id'],'settlement_name']) or (z['source_record_id'],z['article_title']) in set(zip(oldtargets.source_record_id,oldtargets.article_title)):keep.append(z)
t=pd.DataFrame(keep);t.to_csv(O/'searched_own_article_title_candidates_filtered.csv.gz',index=False,compression={'method':'gzip','mtime':0});loaded=[existing[x] for x in set(t.article_title)&existing.keys()];titles=sorted(set(t.article_title)-existing.keys());meta=[]
for start in range(0,len(titles),15):
 batch=titles[start:start+15];p=O/f'live_article_revisions_{start//15:03}.json.gz';url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(batch),'prop':'revisions|pageprops','rvprop':'ids|timestamp|content','rvslots':'main','redirects':1,'format':'json','formatversion':2})
 try:
  b=gzip.open(p,'rb').read() if p.exists() else request(url);d=json.loads(b)
  if not p.exists():p.write_bytes(gzip.compress(b,mtime=0))
  redirects={z['from']:z['to'] for z in d.get('query',{}).get('redirects',[])};norm={z['from']:z['to'] for z in d.get('query',{}).get('normalized',[])}
  for title in batch:
   canonical=redirects.get(norm.get(title,title),norm.get(title,title));page=next((z for z in d.get('query',{}).get('pages',[]) if z.get('title')==canonical),{});loaded.append({'article_title':title,'origin_file':str(p),'page':page,'redirected_to':canonical})
  meta.append({'source_file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'url':url,'titles':batch});print('articles batch',start//15,'pages',len(d.get('query',{}).get('pages',[])),flush=True)
 except Exception as ex:meta.append({'url':url,'titles':batch,'failure':type(ex).__name__+':'+str(ex)})
(O/'cached_title_article_sources_index.json.gz').write_bytes(gzip.compress(b'[]',mtime=0));pd.DataFrame(columns=['source_record_id','article_title']).to_csv(O/'cached_title_source_binding_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'searched_own_article_sources_index.json.gz').write_bytes(gzip.compress(json.dumps(loaded,ensure_ascii=False).encode(),mtime=0));qids=sorted({z['page'].get('pageprops',{}).get('wikibase_item') for z in loaded if z['page'].get('pageprops',{}).get('wikibase_item')});entities={};emeta=[]
for start in range(0,len(qids),40):
 ids=qids[start:start+40];p=O/f'live_own_article_entities_{start//40:03}.json.gz';url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(ids),'props':'info|labels|aliases|claims|sitelinks','languages':'ru','format':'json'})
 try:
  b=gzip.open(p,'rb').read() if p.exists() else request(url,5000000);d=json.loads(b)
  if not p.exists():p.write_bytes(gzip.compress(b,mtime=0))
  for q,z in d.get('entities',{}).items():entities[q]={'entity':z,'origin_file':str(p),'origin_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'origin_locator':'entities.'+q}
  emeta.append({'source_file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'url':url,'qids':ids});print('entities batch',start//40,'entities',len(d.get('entities',{})),flush=True)
 except Exception as ex:emeta.append({'url':url,'qids':ids,'failure':type(ex).__name__+':'+str(ex)})
(O/'own_article_entities_index.json.gz').write_bytes(gzip.compress(json.dumps(entities,ensure_ascii=False).encode(),mtime=0));r={'positive100_targets':len(f),'search_requests':len(searchmeta),'candidate_title_pairs':len(t),'existing_cached_articles_reused':len(loaded)-len(titles),'new_article_titles':len(titles),'own_article_entity_QIDs':len(qids),'normal_TLS':True,'search_is_discovery_not_admission':True,'search_raw_response_pins':searchmeta,'article_raw_response_pins':meta,'entity_raw_response_pins':emeta};(O/'live_source_fetch_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print({k:v for k,v in r.items() if not k.endswith('_pins')},flush=True)
