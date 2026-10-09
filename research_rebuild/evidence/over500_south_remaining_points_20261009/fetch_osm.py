import urllib.request,urllib.parse,json,gzip,time,hashlib
from pathlib import Path
import pandas as pd
RAW=Path('/dev/shm/over500-20261009/south_osm');RAW.mkdir(exist_ok=True)
r=pd.read_csv('/dev/shm/over500-20261009/south_remaining.csv');aliases={'Буденного':['имени Будённого'],'1-го отделения совхоза "Михайловский"':['Михайловский'],'1-го отделения племзавода "Тойда"':['Тойда 1-я'],'совхоза "Опыт"':['Опыт'],'совхоза Пальна-Михайловский':['совхоз Пальна-Михайловский'],'совхоза "Маяк"':['Маяк'],'Подъем Первое Отделение':['1-е отделение совхоза Подъём'],'Центральное Отделение Совхоза Сулакский':['совхоза Сулакский'],'Центральное отделение совхоза им. Мичурина':['Мичурина'],'1 Отделение совхоза Бондарский':['1-е отделение совхоза Бондарский'],'Юбилейный':['Юбилейное'],'Школьный':['Школьное'],'Мущули':['Мушули'],'Бильгады':['Бильгади'],'Заречный':['Заречное'],'Верхний Чегем':['Эльтюбю'],'Верхнегнутовский':['Верхнегнутов'],'Плес':['Плёс'],'Головинская Варежка':['Головинская Варежка, Каменка'],'Ивано-Языковка':['Иваново-Языковка'],'Охотничья':['Станция-Охотничья'],'Выры':['станция Выры'],'Гимова':['Гимово'],'железнодорожной станции Питерка':['посёлок станции Питерка'],'совхоза "Серп и Молот"':['Центральная усадьба совхоза Серп и Молот']}
regions={'дагестан':'Республика Дагестан','кабардино балкарская':'Кабардино-Балкарская Республика','северная осетия алания':'Республика Северная Осетия-Алания','адыгея':'Республика Адыгея','ингушетия':'Республика Ингушетия','мордовия':'Республика Мордовия','калмыкия':'Республика Калмыкия'}
records=[];receipts=[]
for row in r.to_dict('records'):
 region=regions.get(row['region_norm'],row['region_norm']+(' край' if row['region_norm'] in ['краснодарский','ставропольский'] else ' область'));district=row['district_raw'] if pd.notna(row['district_raw']) else ''
 for label in [row['settlement_name']]+aliases.get(row['settlement_name'],[]):
  params={'q':', '.join(v for v in [label,district,region,'Россия'] if v),'format':'jsonv2','addressdetails':1,'extratags':1,'namedetails':1,'limit':10};u='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(params);key=hashlib.sha256(u.encode()).hexdigest()[:16];path=RAW/(key+'.json.gz')
  if path.exists():data=json.load(gzip.open(path,'rt'))
  else:
   try:
    resp=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=20);body=resp.read().decode();data={'url':u,'status_code':resp.status,'body':json.loads(body),'query_source_record_id':row['source_record_id'],'query_label':label}
   except Exception as exc:data={'url':u,'error':str(exc),'body':[],'query_source_record_id':row['source_record_id'],'query_label':label}
   with path.open('wb') as f:
    with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as gz:gz.write(json.dumps(data,ensure_ascii=False).encode())
   time.sleep(1.05)
  receipts.append({'source_record_id':row['source_record_id'],'label':label,'capture':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'result_count':len(data['body']),'error':data.get('error','')})
  for a in data['body']:records.append(dict(source_record_id=row['source_record_id'],query_label=label,capture=str(path),capture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),osm_type=a.get('osm_type'),osm_id=a.get('osm_id'),class_name=a.get('class'),type=a.get('type'),latitude=a.get('lat'),longitude=a.get('lon'),display_name=a.get('display_name'),address=json.dumps(a.get('address',{}),ensure_ascii=False),extratags=json.dumps(a.get('extratags',{}),ensure_ascii=False),namedetails=json.dumps(a.get('namedetails',{}),ensure_ascii=False)))
 print(row['settlement_name'],len(records),flush=True)
pd.DataFrame(records).to_csv(RAW/'candidates.csv',index=False);pd.DataFrame(receipts).to_csv(RAW/'receipts.csv',index=False)
