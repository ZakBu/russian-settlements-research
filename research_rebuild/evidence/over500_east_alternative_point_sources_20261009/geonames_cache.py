from pathlib import Path
import pandas as pd,zipfile,re,json,hashlib,unicodedata
TRAN=dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya']))
def unidecode(value):
 value=''.join(TRAN.get(c,c)for c in str(value).lower())
 return ''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))
O=Path(__file__).parent
r=pd.read_csv(O/'exact81_targets.csv.gz',dtype=str,keep_default_na=False)
p=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');ap=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_admin1CodesASCII_20260907.txt')
admin={'башкортостан':'08','татарстан':'73','удмуртская':'80','оренбургская':'55','пермский':'90','свердловская':'71','тюменская':'78','челябинская':'13','алтай':'03','алтайский':'04','красноярский':'91','иркутская':'20','новосибирская':'53','омская':'54','томская':'75','забайкальский':'93','приморский':'59','амурская':'05','сахалинская':'64','чукотский':'15','саха якутия':'63','кемеровская':'29','чувашская':'16'}
def norm(x):
 x=unidecode(str(x)).lower().replace('shch','sch').replace('iy','i').replace('yy','y').replace('j','y');return re.sub(r'[^a-z0-9]','',x)
alias={'Березовского Спиртзавода':['Берёзовский спиртзавод','Берёзовка'],'Центральной Усадьбы Раевского совхоза':['Раевский','Раевского совхоза'],'Центральной Усадьбы Конезавода 119':['Конезавода №119','Конезавод119','Конезавод'],'при станции Юматово':['Юматово'],'Комсомольского Отделения':['Комсомольское'],'Центральная Усадьба 3-о Госконезавода':['Конезавод','Третий конезавод'],'станция Кутамыш':['Кутамыш'],'железнодорожная станция Тугулым':['Тугулым'],'Участок Куряты':['Куряты'],'Маракса 1-я':['Первая Маракса','Маракса'],'станции Судженка':['Судженка']}
targets={}
for x in r.to_dict('records'):
 ns=[x['settlement_name']]+alias.get(x['settlement_name'],[])
 if '('in x['settlement_name']:ns += [x['settlement_name'].split('(')[0].strip(),re.search(r'\(([^)]+)\)',x['settlement_name']).group(1)]
 for n in ns:targets.setdefault((admin[x['region_norm']],norm(n)),[]).append((x,n))
sha=hashlib.sha256(p.read_bytes()).hexdigest();rows=[]
with zipfile.ZipFile(p).open('RU.txt')as f:
 for line,b in enumerate(f,1):
  t=b.decode().rstrip('\n').split('\t')
  if t[6]!='P':continue
  ns=[t[1],t[2]]+t[3].split(',');matches={}
  for n in ns:
   for x,requested in targets.get((t[10],norm(n)),[]):matches[x['source_record_id']]=(x,requested,n)
  for sid,(x,requested,matched)in matches.items():
   rows.append(dict(source_record_id=sid,settlement_name=x['settlement_name'],region_norm=x['region_norm'],district_raw=x['district_raw'],requested_alias=requested,matched_name=matched,geonameid=t[0],feature_name=t[1],ascii_name=t[2],alternate_names=t[3],latitude=t[4],longitude=t[5],feature_class=t[6],feature_code=t[7],admin1_code=t[10],admin2_code=t[11],admin3_code=t[12],admin4_code=t[13],provider_population_raw=t[14],modification_date=t[18],source_file=str(p),source_sha256=sha,source_locator=f'RU.txt:line={line};geonameid={t[0]}',candidate_only=True,coordinate_admitted=False,identity_admitted=False))
pd.DataFrame(rows).to_csv(O/'geonames_cached_own_place_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'geonames_source_pins.json').write_text(json.dumps({str(f):dict(sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size)for f in [p,ap]},indent=2));print('candidates',len(rows),'targets',len(set(v['source_record_id']for v in rows)))
