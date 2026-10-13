from pathlib import Path
import pandas as pd,json,gzip,hashlib,urllib.request,urllib.parse,datetime,concurrent.futures,re
O=Path(__file__).parent
r=pd.read_csv('/workspace/russian-settlements-research/research_rebuild/evidence/over500_north_20261009/assignment.csv',dtype=str,keep_default_na=False).query("has_ownpoint=='False'")
labels={'карелия':'Карелия','архангельская':'Архангельская область','нижегородская':'Нижегородская область','ленинградская':'Ленинградская область'}
req=[]
for x in r.to_dict('records'):
 name=x['settlement_name']; variants=list(dict.fromkeys([name,name.capitalize(),name.title()]))
 if '(' in name: variants += [name.split('(')[0].strip(),re.search(r'\(([^)]+)\)',name).group(1)]
 if '[' in name:variants += [name.split('[')[0].strip(),re.search(r'\[([^]]+)\]',name).group(1)]
 for name in list(variants):
  variants += [name+' ('+x['district_raw']+')'] if x['district_raw'] else []
  variants += [name+' ('+labels.get(x['region_norm'],x['region_norm'].capitalize()+' область')+')']
 for title in variants:req.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=x['region_norm'],district_raw=x['district_raw'],requested_title=title))
# Explicit own-name aliases, candidate generation only.
alias={'Гравийного карьера':['Гравийный Карьер (Костромская область)','Гравийный Карьер'],'Санатория "Воробьево"':['Санаторий Воробьёво','Воробьёво (санаторий)'],'Лесной Посёлок Ивакша':['Ивакша'],'населенный пункт лесной поселок ивакша':['Ивакша'],'населенный пункт лесной поселок лепша новый':['Лепша'],'железнодорожнойстанции Скалино':['Скалино (станция)','Скалино'],'Ефремов 3':['Ефремов-3','Ефремов (город)'],'Головино':['Головино (деревня, Судогодский район)','Головино (посёлок, Судогодский район)','Головино (Судогодский район)'],'Газопровода':['Газопровод (Калужская область)'],'центрального отделения совхоза "Заря"':['Заря (Михайловский район)'],'Центральной Усадьбы совхоза им. Ленина':['Центральная усадьба совхоза имени Ленина'],'Истьинское Отделение':['Истьинское Отделение'],'Скуратовский':['Скуратово (Чернский район)','Скуратовский (Тула)'],'ст. Скуратово':['Скуратово (станция)'],'совхоза Чкаловский':['Чкаловский (Калужская область)']}
for x in r.to_dict('records'):
 for title in alias.get(x['settlement_name'],[]):req.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=x['region_norm'],district_raw=x['district_raw'],requested_title=title))
pd.DataFrame(req).to_csv(O/'candidate_title_requests.csv',index=False)
titles=list(dict.fromkeys(x['requested_title'] for x in req))
idx=pd.read_csv('/dev/shm/over500-20261009/wiki_cached_title_index.csv.gz',dtype=str,keep_default_na=False)
cached=idx[idx.article_title.isin(titles)].copy();cached.to_csv(O/'matched_cache_index.csv',index=False)
cache_results=[]
for i,(f,g) in enumerate(cached.groupby('cache_file'),1000):
 raw=Path(f).read_bytes();j=json.loads(gzip.decompress(raw));payload=j.get('payload',j)
 cache_results.append((i,payload,dict(capture=f,sha256=hashlib.sha256(raw).hexdigest(),cached=True,titles=g.article_title.tolist())))
missing=[v for v in titles if v not in set(cached.article_title)]
batches=[missing[i:i+40] for i in range(0,len(missing),40)]
def fetch(z):
 i,names=z;u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(names),prop='revisions|pageprops|coordinates',rvprop='ids|content|timestamp',rvslots='main',format='json',redirects=1,colimit='max'))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40) as resp:b=resp.read(16000000);status=resp.status
  f=O/f'batch_{i:02}.json.gz';f.write_bytes(gzip.compress(b,mtime=0));j=json.loads(b)
  receipt=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),request_url=u,normal_TLS=True,status=status,capture=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),response_sha256=hashlib.sha256(b).hexdigest(),response_bytes=len(b))
  (O/f'batch_{i:02}_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
  pages=j.get('query',{}).get('pages',{});print(i,len(pages),sum(bool(p.get('coordinates')) for p in pages.values()),flush=True)
  return i,j,receipt
 except Exception as e:return i,{},dict(error=str(e),request_url=u)
results=list(concurrent.futures.ThreadPoolExecutor(max_workers=3).map(fetch,enumerate(batches,1)))+cache_results
candidates=[]
for i,j,receipt in results:
 q=j.get('query',{});pagesraw=q.get('pages',{}); pages={p['title']:p for p in (pagesraw.values() if isinstance(pagesraw,dict) else pagesraw)};norm={v['from']:v['to'] for v in q.get('normalized',[])};red={v['from']:v['to'] for v in q.get('redirects',[])}
 for x in req:
  if x['requested_title'] not in (receipt['titles'] if receipt.get('cached') else batches[i-1]):continue
  title=norm.get(x['requested_title'],x['requested_title']);title=red.get(title,title);p=pages.get(title,{})
  if not p or 'missing' in p:continue
  rv=p.get('revisions',[{}])[0];content=rv.get('slots',{}).get('main',{}).get('*',rv.get('slots',{}).get('main',{}).get('content',''))
  coords=p.get('coordinates',[])
  if not coords:
   def coord(axis):
    def field(k):
     m=re.search(r'\|\s*'+k+r'\s*=\s*([0-9.]+)',content);return float(m.group(1)) if m else None
    deg=field(axis+'_deg')
    return deg+(field(axis+'_min') or 0)/60+(field(axis+'_sec') or 0)/3600 if deg is not None else None
   lat,lon=coord('lat'),coord('lon')
   if lat is not None and lon is not None:coords=[dict(lat=lat,lon=lon)]
  for c in coords or [{}]:
   candidates.append(dict(**x,article_title=p['title'],pageid=p.get('pageid'),revid=rv.get('revid'),revision_timestamp=rv.get('timestamp'),qid=p.get('pageprops',{}).get('wikibase_item',''),latitude=c.get('lat',''),longitude=c.get('lon',''),disambiguation='disambiguation' in p.get('pageprops',{}),capture=receipt['capture'],capture_sha256=receipt['sha256'],source_locator=f"pageid={p.get('pageid')};revid={rv.get('revid')};coordinates",county_literal_present=bool(x['district_raw'] and x['district_raw'] in content),history_name_witness=' || '.join(t for t in content.splitlines() if re.search('переимен|прежн|бывш|2002|2010|район|Название',t,re.I))[:7000],candidate_only=True,identity_admitted=False,coordinate_admitted=False))
pd.DataFrame(candidates).to_csv(O/'article_coordinate_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0})
(O/'receipt.json').write_text(json.dumps(dict(target_records=len(r),requested_titles=len(titles),batches=len(batches),fetched_articles=len(set(c['pageid'] for c in candidates)),candidate_rows=len(candidates),own_article_point_rows=sum(c['latitude']!='' and not c['disambiguation'] for c in candidates),accepted_edges=0,accepted_points=0,cache_files=len(cache_results),cached_requested_titles=len(cached),fresh_requested_titles=len(missing),fetch_errors=[v for _,_,v in results if 'error'in v]),ensure_ascii=False,indent=2))
print((O/'receipt.json').read_text())
