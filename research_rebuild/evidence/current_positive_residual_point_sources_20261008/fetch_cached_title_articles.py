from pathlib import Path
import json,gzip,urllib.parse,urllib.request,time,hashlib
import pandas as pd
O=Path(__file__).parent;w=pd.read_csv(O/'cached_Wikidata_positive100_bindings.csv.gz',keep_default_na=False);targets=[]
for z in w.to_dict('records'):
 for u in json.loads(z['wikidata_tsv_article_urls_json']):
  if 'ru.wikipedia.org/wiki/' in u:targets.append({'source_record_id':z['source_record_id'],'cached_own_qid':z['wikidata_qid'],'article_title':urllib.parse.unquote(u.split('/wiki/',1)[1]).replace('_',' ')})
# Source title cache discovery consumes existing bytes before requesting revisions.
cached={};roots=[Path('/workspace/settlements-raw/data/raw/wikipedia_settlement_lists'),Path('/workspace/settlements-work/continuation_20261004')];wanted={z['article_title'] for z in targets}
def pages(a):
 if not isinstance(a,dict):return []
 q=a.get('query',{}).get('pages',[]);return list(q.values()) if isinstance(q,dict) else q if isinstance(q,list) else []
for root in roots:
 for p in root.rglob('*.json.gz'):
  try:a=json.loads(gzip.open(p,'rt').read())
  except (ValueError,UnicodeError,OSError):continue
  for z in pages(a):
   if z.get('title') in wanted and z.get('revisions'):cached[z['title']]=(str(p),z)
manifest=[];loaded=[]
for title,(p,z) in cached.items():loaded.append({'article_title':title,'origin_file':p,'page':z});manifest.append({'title':title,'origin_file':p,'existing_cache_used':True})
titles=sorted(wanted-set(cached));print('existing own article revisions',len(cached),'fetch missing',len(titles),flush=True)
for start in range(0,len(titles),15):
 batch=titles[start:start+15];p=O/f'cached_title_article_revisions_batch_{start//15:03}.json.gz';u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(batch),'prop':'revisions|pageprops','rvprop':'ids|timestamp|content','rvslots':'main','redirects':1,'format':'json','formatversion':2})
 for attempt in range(3):
  try:
   b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 (+bounded physical locality source verification)'}),timeout=25).read(1500000);a=json.loads(b);p.write_bytes(gzip.compress(b,mtime=0));break
  except Exception as ex:
   if attempt==2:a={};manifest.append({'titles':batch,'failure':type(ex).__name__+':'+str(ex),'url':u})
   else:time.sleep(4+attempt*4)
 redirects={v['from']:v['to'] for v in a.get('query',{}).get('redirects',[])};norm={v['from']:v['to'] for v in a.get('query',{}).get('normalized',[])}
 for title in batch:
  canonical=redirects.get(norm.get(title,title),norm.get(title,title));page=next((z for z in pages(a) if z.get('title')==canonical),{})
  loaded.append({'article_title':title,'origin_file':str(p) if p.exists() else '', 'page':page,'redirected_to':canonical});manifest.append({'title':title,'origin_file':str(p) if p.exists() else '', 'url':u,'pageid':page.get('pageid'),'missing':page.get('missing',False),'revid':page.get('revisions',[{}])[0].get('revid')})
 print('fetched batch',start//15,'pages',len(pages(a)),flush=True)
(O/'cached_title_article_sources_index.json.gz').write_bytes(gzip.compress(json.dumps(loaded,ensure_ascii=False).encode(),mtime=0));pd.DataFrame(targets).to_csv(O/'cached_title_source_binding_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'cached_title_article_fetch_receipt.json').write_text(json.dumps({'existing_article_revisions':len(cached),'requested_titles':len(titles),'title_manifest':manifest,'asset_pins':{z['origin_file']:hashlib.sha256(Path(z['origin_file']).read_bytes()).hexdigest() for z in loaded if z['origin_file']}},ensure_ascii=False,indent=2)+'\n');print('all titles',len(targets),'returned',sum(bool(z['page'].get('revisions')) for z in loaded),flush=True)
