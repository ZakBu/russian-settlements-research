from pathlib import Path
import pandas as pd,json,gzip,hashlib,urllib.request,urllib.parse,datetime,concurrent.futures,re
O=Path(__file__).parent
r=pd.read_csv('/dev/shm/over500-20261009/residual.csv',dtype=str,keep_default_na=False)
regions='дагестан тамбовская воронежская краснодарский волгоградская липецкая самарская ульяновская пензенская саратовская чеченская адыгея ставропольский ростовская калмыкия мордовия белгородская астраханская ингушетия'.split()+['северная осетия алания','кабардино балкарская','марий эл']
r=r[(r.has_ownpoint=='False')&r.region_norm.isin(regions)&~r.settlement_name.str.contains('часть',case=False)]
labels={'дагестан':'Дагестан','кабардино балкарская':'Кабардино-Балкария','северная осетия алания':'Северная Осетия','адыгея':'Адыгея','ингушетия':'Ингушетия','калмыкия':'Калмыкия','мордовия':'Мордовия','краснодарский':'Краснодарский край','ставропольский':'Ставропольский край'}
req=[]
for x in r.to_dict('records'):
 name=x['settlement_name']; variants=[name]
 if '(' in name: variants += [name.split('(')[0].strip(),re.search(r'\(([^)]+)\)',name).group(1)]
 if '[' in name:variants += [name.split('[')[0].strip(),re.search(r'\[([^]]+)\]',name).group(1)]
 for name in list(variants):
  variants += [name+' ('+x['district_raw']+')'] if x['district_raw'] else []
  variants += [name+' ('+labels.get(x['region_norm'],x['region_norm'].capitalize()+' область')+')']
 for title in variants:req.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=x['region_norm'],district_raw=x['district_raw'],requested_title=title))
# Explicit own-name aliases, candidate generation only.
alias={'Инхело (Новое Инхело)':['Новое Инхело','Инхело'],'Анчик (Анчих)':['Анчих'],'Наибика (Нанибика)':['Нанибика'],'Караозек (Караузек)':['Караузек'],'Цияб-Цилитли (Ново-Цилитли)':['Цияб-Цилитли'],'Бильгады':['Бильгади'],'Малакановский':['Малокановский'],'Верхний Чегем':['Эльтюбю'],'Гиреевский':['Гази-Юрт'],'Гудаловка':['Плеханово (Липецкая область)'],'Ярославка Первая':['Первая Ярославка'],'Ярославка Вторая':['Вторая Ярославка'],'Иноковка Первая':['Первая Иноковка'],'совхоза "Серп и Молот"':['Серп и Молот (Пензенская область)']}
for x in r.to_dict('records'):
 for title in alias.get(x['settlement_name'],[]):req.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=x['region_norm'],district_raw=x['district_raw'],requested_title=title))
pd.DataFrame(req).to_csv(O/'candidate_title_requests.csv',index=False)
titles=list(dict.fromkeys(x['requested_title'] for x in req));batches=[titles[i:i+40] for i in range(0,len(titles),40)]
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
results=list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(fetch,enumerate(batches,1)))
candidates=[]
for i,j,receipt in results:
 q=j.get('query',{});pages={p['title']:p for p in q.get('pages',{}).values()};norm={v['from']:v['to'] for v in q.get('normalized',[])};red={v['from']:v['to'] for v in q.get('redirects',[])}
 for x in req:
  if x['requested_title'] not in batches[i-1]:continue
  title=norm.get(x['requested_title'],x['requested_title']);title=red.get(title,title);p=pages.get(title,{})
  if not p or 'missing' in p:continue
  rv=p.get('revisions',[{}])[0];content=rv.get('slots',{}).get('main',{}).get('*','')
  coords=p.get('coordinates',[])
  for c in coords or [{}]:
   candidates.append(dict(**x,article_title=p['title'],pageid=p.get('pageid'),revid=rv.get('revid'),revision_timestamp=rv.get('timestamp'),qid=p.get('pageprops',{}).get('wikibase_item',''),latitude=c.get('lat',''),longitude=c.get('lon',''),disambiguation='disambiguation' in p.get('pageprops',{}),capture=receipt['capture'],capture_sha256=receipt['sha256'],source_locator=f"pageid={p.get('pageid')};revid={rv.get('revid')};coordinates",county_literal_present=bool(x['district_raw'] and x['district_raw'] in content),history_name_witness=' || '.join(t for t in content.splitlines() if re.search('переимен|прежн|бывш|2002|2010|район|Название',t,re.I))[:7000],candidate_only=True,identity_admitted=False,coordinate_admitted=False))
pd.DataFrame(candidates).to_csv(O/'article_coordinate_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0})
(O/'receipt.json').write_text(json.dumps(dict(target_records=len(r),requested_titles=len(titles),batches=len(batches),fetched_articles=len(set(c['pageid'] for c in candidates)),candidate_rows=len(candidates),own_article_point_rows=sum(c['latitude']!='' and not c['disambiguation'] for c in candidates),accepted_edges=0,accepted_points=0,fetch_errors=[v for _,_,v in results if 'error'in v]),ensure_ascii=False,indent=2))
print((O/'receipt.json').read_text())
