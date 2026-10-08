from pathlib import Path
import pandas as pd,json,gzip,re,ast,unicodedata,urllib.request,urllib.parse,time,hashlib
O=Path(__file__).parent;E=O.parent;OLD=E/'current_live_named_residual_sources_20261008';RULE=OLD/'review_articles.py';normalize=lambda v:str(v).lower().replace('ё','е');tree=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','county']],type_ignores=[]),str(RULE),'exec'));f=pd.read_csv(O/'positive100_priority_roster.csv.gz',dtype=str,keep_default_na=False);rows=[];existing={};entities={}
for Z in [E/'current_positive_residual_point_sources_20261008',OLD]:
 for fn in ['cached_title_article_sources_index.json.gz','searched_own_article_sources_index.json.gz']:
  for z in json.loads(gzip.open(Z/fn,'rt').read()):existing[z['article_title']]=z
 if (Z/'own_article_entities_index.json.gz').exists():entities.update(json.loads(gzip.open(Z/'own_article_entities_index.json.gz','rt').read()))
oldtargets=pd.concat([pd.read_csv(OLD/'searched_own_article_title_candidates_filtered.csv.gz',dtype=str,keep_default_na=False),pd.read_csv(E/'current_positive_residual_point_sources_20261008/searched_own_article_title_candidates_filtered.csv.gz',dtype=str,keep_default_na=False),pd.read_csv(E/'current_positive_residual_point_sources_20261008/cached_title_source_binding_candidates.csv.gz',dtype=str,keep_default_na=False)],ignore_index=True);rows.extend(oldtargets[oldtargets.source_record_id.isin(f.source_record_id)][['source_record_id','article_title']].to_dict('records'));rmap={'московская':'Московская область','кемеровская':'Кемеровская область','пермский':'Пермский край','краснодарский':'Краснодарский край','тульская':'Тульская область','забайкальский':'Забайкальский край','чувашская':'Чувашия','чеченская':'Чечня','хабаровский':'Хабаровский край','калининградская':'Калининградская область'}
for z in f.to_dict('records'):
 rawname=z['settlement_name'].strip();name=re.sub(r'^\s*(?:пос[её]лок\s+)?(?:при\s+)?(?:железнодорожн(?:ая|ой)\s+)?(?:станци[яи]|разъезд[а]?|ст\.)\s+','',rawname,flags=re.I);co=county(z['district_raw']);reg=rmap.get(z['region_norm'],z['region_norm'].title()+' область');co=co[:1].upper()+co[1:];typ=z['settlement_type'];bases={name};quoted=re.findall(r'["«]([^"»]+)["»]',name);bases.update(quoted)
 for b in bases:
  titles={b,f'{b} ({reg})',f'{b} ({co} район)',f'{b} ({co} муниципальный округ)'}
  if typ:titles.update({f'{b} ({typ})',f'{b} ({typ}, {co} район)',f'{b} ({typ}, {co} муниципальный округ)',f'{b} ({typ}, {co} городской округ)'})
  if re.search('станц|разъезд',rawname,re.I):titles.update({f'{b} (посёлок)',f'{b} (посёлок при станции)',f'{b} (посёлок железнодорожной станции)'})
  for title in titles:rows.append({'source_record_id':z['source_record_id'],'article_title':title,'discovery_kind':'closed native literal title/type/county/region variants; discovery only'})
t=pd.DataFrame(rows).fillna('').drop_duplicates(['source_record_id','article_title']);titles=sorted(set(t.article_title)-existing.keys());loaded=[existing[q] for q in set(t.article_title)&existing.keys()];manifest=[]
def request(url,limit=6000000):
 for n in range(3):
  time.sleep(6)
  try:return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0 (+bounded own NP source verification)'}),timeout=25).read(limit)
  except Exception as ex:
   if getattr(ex,'code',None)==429:
    wait=ex.headers.get('Retry-After','30');wait=float(wait) if str(wait).isdigit() else 30;print('429backoff',min(max(wait,30),60),flush=True);time.sleep(min(max(wait,30),60))
   if n==2:raise
   if getattr(ex,'code',None)!=429:time.sleep(3)
# Bounded URL chunks of 20-40 titles; never exceed 7,000-character request URL.
start=0;bn=0
while start<len(titles):
 batch=titles[start:start+40]
 def urlfor(b):return 'https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(b),'prop':'revisions|pageprops','rvprop':'ids|timestamp|content','rvslots':'main','redirects':1,'format':'json','formatversion':2})
 while len(urlfor(batch))>7000 and len(batch)>20:batch=batch[:-1]
 url=urlfor(batch);p=O/f'closed_title_variant_revisions_{bn:03}.json.gz';start+=len(batch);bn+=1
 try:
  b=gzip.open(p,'rb').read() if p.exists() else request(url);d=json.loads(b)
  if not p.exists():p.write_bytes(gzip.compress(b,mtime=0))
  redirects={z['from']:z['to'] for z in d.get('query',{}).get('redirects',[])};norm={z['from']:z['to'] for z in d.get('query',{}).get('normalized',[])}
  for title in batch:
   canonical=redirects.get(norm.get(title,title),norm.get(title,title));page=next((z for z in d.get('query',{}).get('pages',[]) if z.get('title')==canonical),{});loaded.append({'article_title':title,'origin_file':str(p),'page':page,'redirected_to':canonical})
  manifest.append({'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'url':url,'requested_titles':len(batch),'returned_existing_pages':sum(not q.get('missing',False) for q in d.get('query',{}).get('pages',[]))});print('titlesbatch',bn,'ofapprox',len(titles)//35+1,'existing',manifest[-1]['returned_existing_pages'],flush=True)
 except Exception as ex:manifest.append({'url':url,'requested_titles':batch,'failure':type(ex).__name__+':'+str(ex)})
# Missing pages stay in source index as held discovery negatives, not physical point claims.
validtitles={z['article_title'] for z in loaded if z['page'].get('revisions')};t=t[t.article_title.isin(validtitles)];t.to_csv(O/'searched_own_article_title_candidates_filtered.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'cached_title_article_sources_index.json.gz').write_bytes(gzip.compress(b'[]',mtime=0));pd.DataFrame(columns=['source_record_id','article_title']).to_csv(O/'cached_title_source_binding_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'searched_own_article_sources_index.json.gz').write_bytes(gzip.compress(json.dumps(loaded,ensure_ascii=False).encode(),mtime=0));newqids=sorted({z['page'].get('pageprops',{}).get('wikibase_item') for z in loaded if z['page'].get('revisions') and z['page'].get('pageprops',{}).get('wikibase_item')}-entities.keys());emeta=[]
for start in range(0,len(newqids),40):
 ids=newqids[start:start+40];p=O/f'closed_title_variant_ownentities_{start//40:03}.json.gz';url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(ids),'props':'info|labels|aliases|claims|sitelinks','languages':'ru','format':'json'})
 try:
  b=gzip.open(p,'rb').read() if p.exists() else request(url);d=json.loads(b)
  if not p.exists():p.write_bytes(gzip.compress(b,mtime=0))
  for q,z in d.get('entities',{}).items():entities[q]={'entity':z,'origin_file':str(p),'origin_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'origin_locator':'entities.'+q}
  emeta.append({'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'url':url,'QIDs':ids});print('entitiesbatch',start//40,flush=True)
 except Exception as ex:emeta.append({'url':url,'QIDs':ids,'failure':type(ex).__name__+':'+str(ex)})
(O/'own_article_entities_index.json.gz').write_bytes(gzip.compress(json.dumps(entities,ensure_ascii=False).encode(),mtime=0));r={'remaining_positive100_targets':len(f),'new_closed_title_candidates_queried':len(titles),'existing_source_article_titles_reused':len(set(t.article_title)&existing.keys()),'existing_own_article_pairs_after_source_response':len(t),'new_QIDs':len(newqids),'normalTLS':True,'paced_requests_seconds':6,'prior186rate_limited_search_queries_not_retried':True,'article_source_response_pins':manifest,'entity_source_response_pins':emeta};(O/'live_source_fetch_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print({k:v for k,v in r.items() if not k.endswith('_pins')})
