from pathlib import Path
import pandas as pd,json,gzip,hashlib,re,time
O=Path(__file__).parent;E=O.parent;f=pd.read_csv(E/'additional_uncached_census_histories_application_20261008/largest_hard_point_conflicts.csv').fillna('');want=set(f.wikidata_id);found={};T=time.monotonic();scanned=0;errors=[]
for p in sorted(Path('/workspace/settlements-raw/data/raw/wikipedia_articles').glob('batch_*.json.gz')):
 if len(found)==len(want):break
 raw=p.read_bytes();scanned+=1
 try:txt=gzip.decompress(raw).decode('utf-8')
 except Exception as exc:errors.append({'path':str(p),'error':str(exc)});continue
 if not any(q in txt for q in want-found.keys()):continue
 d=json.loads(txt);req={v['wikidata_id_effective']:v for v in d.get('requested',[]) if v.get('wikidata_id_effective') in want-found.keys()};pages=d.get('payload',{}).get('query',{}).get('pages',{});pages=list(pages.values()) if isinstance(pages,dict) else pages
 for q,r in req.items():
  candidates=[v for v in pages if v.get('title')==r['article_title']]
  if len(candidates)!=1:continue
  page=candidates[0];revs=page.get('revisions',[])
  if not revs:continue
  rev=revs[0];text=rev.get('slots',{}).get('main',{}).get('*',rev.get('slots',{}).get('main',{}).get('content',rev.get('*','')))
  if not text:continue
  found[q]={'qid':q,'requested':r,'article_title':page.get('title'),'page_id':page.get('pageid'),'revision_id':rev.get('revid'),'revision_timestamp':rev.get('timestamp'),'retrieved_at_utc':d.get('retrieved_at_utc'),'source_path':str(p),'source_sha256':hashlib.sha256(raw).hexdigest(),'source_locator':f'payload.query.pages.{page.get("pageid")}.revisions[0]','wikitext':text};print(q,page.get('title'),len(text),flush=True)
(O/'cached_own_articles.json.gz').write_bytes(gzip.compress(json.dumps(found,ensure_ascii=False).encode(),mtime=0));receipt={'status':'cached_source_scan_only','requested_own_items':len(want),'exact_own_cached_articles':len(found),'missing_own_cached_QIDs':sorted(want-found.keys()),'raw_article_cache_files_examined':scanned,'API_requests':0,'raw_cache_read_errors':errors,'wall_seconds':time.monotonic()-T};(O/'article_cache_scan_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k!='raw_cache_read_errors'}))
