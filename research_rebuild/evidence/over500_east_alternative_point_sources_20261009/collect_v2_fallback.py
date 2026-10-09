from pathlib import Path
import json,gzip,hashlib,time,datetime,urllib.request,urllib.parse,pandas as pd,zipfile,re,unicodedata
O=Path(__file__).parent;RAM=Path('/dev/shm/over500-20261009/east_alternative_points');RAM.mkdir(exist_ok=True)
r=pd.read_csv(O/'exact81_targets.csv.gz',dtype=str,keep_default_na=False)
initial=json.loads((O/'nominatim_capture_receipt.json').read_text());missing={x['source_record_id']for x in initial if x.get('results')==0}
r=r[r.source_record_id.isin(missing)].copy()
alias={'Березовского Спиртзавода':'Берёзовский спиртзавод','Центральной Усадьбы Раевского совхоза':'Раевского совхоза','Центральной Усадьбы Конезавода 119':'Конезавод 119','при станции Юматово':'Юматово','Комсомольского Отделения':'Комсомольское','Центральная Усадьба 3-о Госконезавода':'Конезавод','железнодорожная станция Тугулым':'Тугулым','станции Судженка':'Судженка','Маракса 1-я':'Первая Маракса','Санаторный':'Санаторное'}
regions={'башкортостан':'Башкортостан','татарстан':'Татарстан','удмуртская':'Удмуртия','алтай':'Республика Алтай','саха якутия':'Якутия','чувашская':'Чувашия','пермский':'Пермский край','алтайский':'Алтайский край','красноярский':'Красноярский край','забайкальский':'Забайкальский край','приморский':'Приморский край','чукотский':'Чукотка'}
receipt=[];candidates=[];last=0
for i,x in enumerate(r.to_dict('records'),1):
 nm=alias.get(x['settlement_name'],x['settlement_name'].split('(')[0].strip())
 q=', '.join(v for v in [nm,regions.get(x['region_norm'],x['region_norm'].capitalize()+' область'),'Россия']if v)
 u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,extratags=1,namedetails=1,limit=5))
 delay=1.1-(time.monotonic()-last)
 if delay>0:time.sleep(delay)
 last=time.monotonic();status=None
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'RussianSettlementResearch/1.0 (source audit; own-place coordinates)'}),timeout=15)as resp:b=resp.read();status=resp.status
  f=RAM/f'nominatim_v2_{i:03}.json.gz';f.write_bytes(gzip.compress(b,mtime=0));j=json.loads(b);sha=hashlib.sha256(f.read_bytes()).hexdigest();receipt.append(dict(source_record_id=x['source_record_id'],query=q,request_url=u,status=status,capture=str(f),sha256=sha,normal_TLS=True,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),results=len(j)))
  for v in j:
   candidates.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=x['region_norm'],district_raw=x['district_raw'],provider='OSM_Nominatim',feature_id=str(v.get('osm_type'))+'/'+str(v.get('osm_id')),latitude=v.get('lat'),longitude=v.get('lon'),own_name=v.get('name'),display_name=v.get('display_name'),feature_class=v.get('class'),feature_category=v.get('category'),feature_type=v.get('type'),address_type=v.get('addresstype'),address_json=json.dumps(v.get('address',{}),ensure_ascii=False),extratags_json=json.dumps(v.get('extratags',{}),ensure_ascii=False),namedetails_json=json.dumps(v.get('namedetails',{}),ensure_ascii=False),boundingbox_json=json.dumps(v.get('boundingbox',[])),source_file=str(f),source_sha256=sha,source_locator='osm_type='+str(v.get('osm_type'))+';osm_id='+str(v.get('osm_id')),candidate_only=True,coordinate_admitted=False,identity_admitted=False))
  print(i,x['settlement_name'],len(j),flush=True)
 except Exception as e:
  receipt.append(dict(source_record_id=x['source_record_id'],query=q,request_url=u,error=str(e),normal_TLS=True));print(i,type(e).__name__,str(e),flush=True)
  if getattr(e,'code',None)==429:break
pd.DataFrame(candidates).to_csv(O/'nominatim_v2_own_feature_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'nominatim_v2_capture_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print('COMPLETE',len(receipt),len(candidates),flush=True)
