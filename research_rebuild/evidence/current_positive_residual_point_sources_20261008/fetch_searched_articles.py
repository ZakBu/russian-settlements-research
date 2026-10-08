from pathlib import Path
import pandas as pd,json,gzip,urllib.parse,urllib.request,time,re,ast,unicodedata
O=Path(__file__).parent
src=(O/'review_articles.py').read_text();module=ast.parse(src);namespace={'re':re,'unicodedata':unicodedata,'normalize':lambda v:str(v).lower().replace('ё','е')};exec(compile(ast.Module(body=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey']],type_ignores=[]),'<closed_name_rules>','exec'),namespace);namekey=namespace['namekey']
f=pd.read_csv(O/'positive100_priority_roster.csv.gz',keep_default_na=False).set_index('source_record_id');t=pd.read_csv(O/'searched_own_article_title_candidates.csv.gz',keep_default_na=False);keep=[]
for z in t.to_dict('records'):
 source=f.loc[z['source_record_id']];title=z['article_title'];base=re.sub(r'\s*\([^)]*\)\s*$','',title)
 if namekey(base)==namekey(source['settlement_name']):keep.append(z)
t=pd.DataFrame(keep);t.to_csv(O/'searched_own_article_title_candidates_filtered.csv.gz',index=False,compression={'method':'gzip','mtime':0});existing={z['article_title']:z for z in json.loads(gzip.open(O/'cached_title_article_sources_index.json.gz','rt').read())};titles=sorted(set(t.article_title)-set(existing));loaded=[existing[x] for x in set(t.article_title)&set(existing)];manifest=[];print('closed-name candidate title pairs',len(t),'new unique articles',len(titles),flush=True)
for start in range(0,len(titles),15):
 batch=titles[start:start+15];p=O/f'searched_article_revisions_batch_{start//15:03}.json.gz';u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(batch),'prop':'revisions|pageprops','rvprop':'ids|timestamp|content','rvslots':'main','redirects':1,'format':'json','formatversion':2})
 for attempt in range(3):
  try:b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 (+bounded own locality verification)'}),timeout=25).read(1500000);a=json.loads(b);p.write_bytes(gzip.compress(b,mtime=0));break
  except Exception as ex:
   a={}
   if attempt==2:manifest.append({'titles':batch,'failure':type(ex).__name__+':'+str(ex),'url':u})
   else:time.sleep(4+attempt*4)
 redirects={v['from']:v['to'] for v in a.get('query',{}).get('redirects',[])};norm={v['from']:v['to'] for v in a.get('query',{}).get('normalized',[])}
 for title in batch:
  canonical=redirects.get(norm.get(title,title),norm.get(title,title));page=next((z for z in a.get('query',{}).get('pages',[]) if z.get('title')==canonical),{})
  loaded.append({'article_title':title,'origin_file':str(p) if p.exists() else '', 'page':page,'redirected_to':canonical});manifest.append({'title':title,'origin_file':str(p) if p.exists() else '', 'url':u,'pageid':page.get('pageid'),'missing':page.get('missing',False),'revid':page.get('revisions',[{}])[0].get('revid')})
 print('newarticle batch',start//15,'returned',len(a.get('query',{}).get('pages',[])),flush=True)
(O/'searched_own_article_sources_index.json.gz').write_bytes(gzip.compress(json.dumps(loaded,ensure_ascii=False).encode(),mtime=0));(O/'searched_article_fetch_receipt.json').write_text(json.dumps({'candidate_title_pairs':len(t),'new_unique_article_titles':len(titles),'manifest':manifest},ensure_ascii=False,indent=2)+'\n')
