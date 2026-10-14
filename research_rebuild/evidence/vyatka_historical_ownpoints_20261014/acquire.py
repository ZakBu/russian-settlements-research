import concurrent.futures, hashlib, json, pathlib, re, urllib.request, datetime, sys
import pandas as pd
from bs4 import BeautifulSoup
RAW=pathlib.Path('/workspace/shared/vyatka_historical_ownpoints'); RAW.mkdir(exist_ok=True)
INPUT=pathlib.Path('/workspace/shared/historical_mass_binding_20261014/pilot1979/held_bindings.parquet')
rows=pd.read_parquet(INPUT).head(int(sys.argv[1]) if len(sys.argv)>1 else 300).to_dict('records')
def fetch(row):
 url=str(row['linked_place_url']); nid=url.rstrip('/').split('/')[-1]; f=RAW/(nid+'.html')
 out={k:row[k] for k in ['year','provider_id','name','district_name','linked_place_url','source_url','source_sha256','source_locator']}
 out.update(article_id=nid,coordinate_source_quality='secondary',primary_verified=False,admission_allowed=False,coordinate_order='Yandex latitude,longitude',retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 try:
  if not f.exists():
   raise RuntimeError('Network acquisition disabled pending source-owner permission; cached inspection only')
   b=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'RussianSettlementsResearch/1.0'}),timeout=30).read(); f.write_bytes(b)
  b=f.read_bytes(); html=b.decode('utf-8');out.update(article_raw_path=str(f),article_sha256=hashlib.sha256(b).hexdigest())
  soup=BeautifulSoup(html,'html.parser'); h=soup.find('h1');out['h1']=h.get_text(' ',strip=True) if h else None
  trs=soup.select('#snmx_perepis1979_places_table tr');match=[]
  for tr in trs:
   c=[td.get_text(' ',strip=True) for td in tr.find_all('td')]
   if c and c[0]==str(row['provider_id']):match.append(c)
  out['historical_row_id_present']=len(match)==1;out['historical_row_name']=match[0][3] if len(match)==1 and len(match[0])>3 else None
  out['historical_row_name_exact']=out['historical_row_name']==row['name']
  m=re.search(r'jQuery\.extend\(Drupal.settings,\s*(\{.*?\})\);',html,re.S)
  if not m:out['status']='settings_missing';return out
  settings=json.loads(m.group(1));delta=settings.get('zz_ymap',{}).get('deltas',{}).get(nid,{})
  features=delta.get('markers',{}).get('features',[]);features=[features] if isinstance(features,dict) and 'id' in features else list(features.values()) if isinstance(features,dict) else features
  own=[v for v in features if str(v.get('id'))==nid and v.get('geometry',{}).get('type')=='Point']
  out['own_feature_count']=len(own)
  if len(own)!=1:out['status']='own_feature_missing_or_multiple';return out
  coords=own[0]['geometry']['coordinates'];out['raw_coordinates']=coords
  lat,lon=map(float,coords);out.update(latitude=lat,longitude=lon)
  out['status']='verified_article_ownpoint' if out['historical_row_id_present'] and out['historical_row_name_exact'] and out['h1'] and -90<=lat<=90 and -180<=lon<=180 else 'row_or_coordinate_check_failed'
 except Exception as exc:out['status']='fetch_or_parse_error';out['error']=str(exc)
 return out
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 for out in ex.map(fetch,rows):
  results.append(out)
  if len(results)%25==0:print('completed',len(results),flush=True)
(RAW/'ownpoints.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,default=str)+'\n' for r in results))
df=pd.DataFrame(results);good=df[df.status=='verified_article_ownpoint'].copy()
if len(good):
 good['shared_coordinate_count']=good.groupby(['latitude','longitude'])['provider_id'].transform('count');good['shared_coordinate']=good.shared_coordinate_count>1
 df=df.merge(good[['provider_id','shared_coordinate_count','shared_coordinate']],on='provider_id',how='left')
df.to_parquet(RAW/'ownpoints.parquet',index=False)
receipt={'input':str(INPUT),'input_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),'requested_rows':len(rows),'statuses':df.status.value_counts().to_dict(),'unique_article_urls':df.linked_place_url.nunique(),'verified_ownpoints':len(good),'admissions':0,'threads':3,'raw_output':str(RAW/'ownpoints.parquet')}
pathlib.Path(__file__).with_name('receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False),flush=True)
