from pathlib import Path
import pandas as pd,json,gzip,urllib.request,urllib.parse,concurrent.futures,datetime,time
O=Path(__file__).parent;C=Path('/dev/shm/over500-20261009/north_wiki');C.mkdir(exist_ok=True)
r=pd.read_csv(O/'assignment.csv').fillna('');r=r[r.has_ownpoint==False];variants={'Гравийного карьера':'Гравийный Карьер','Ушакова':'Ушаково','Санатория "Воробьево"':'санатория Воробьёво','Центральной Усадьбы совхоза им. Ленина':'Совхоз имени Ленина','центрального отделения совхоза "Заря"':'Заря','железнодорожной станции Скалино':'Скалино','Дома Отдыха "Голубой Оки"':'Дом отдыха Голубая Ока'}
def get(params):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params)
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'RussianSettlementResearch/1.0 (bounded own settlement coordinate verification)'}),timeout=20) as h:return json.loads(h.read()),u
 except Exception as e:return {'error':repr(e)},u
def run(z):
 n=variants.get(z['settlement_name'],z['settlement_name']);n=n.replace('железнодорожной станции','').strip();q=' '.join('"'+str(x)+'"' for x in [n,z['district_raw'],z['region_norm']] if x);d,u=get({'action':'query','list':'search','srsearch':q,'srnamespace':0,'srlimit':5,'format':'json','formatversion':2});hits=d.get('query',{}).get('search',[])
 if not hits:
  d,u=get({'action':'query','list':'search','srsearch':'"'+n+'" "'+z['region_norm']+'"','srnamespace':0,'srlimit':5,'format':'json','formatversion':2});hits=d.get('query',{}).get('search',[])
 page={};pu=''
 if hits:page,pu=get({'action':'query','pageids':'|'.join(str(x['pageid']) for x in hits),'prop':'coordinates|pageprops|revisions','rvprop':'ids|timestamp|content','rvslots':'main','coprimary':'primary','colimit':'max','format':'json','formatversion':2})
 return {'native':z,'query_name':n,'search_url':u,'search_response':d,'page_url':pu,'page_response':page,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:out=list(ex.map(run,r.to_dict('records')))
(C/'capture.json.gz').write_bytes(gzip.compress(json.dumps(out,ensure_ascii=False).encode(),mtime=0));print('targets',len(out),'with_pages',sum(bool(x['page_response'].get('query',{}).get('pages')) for x in out))
