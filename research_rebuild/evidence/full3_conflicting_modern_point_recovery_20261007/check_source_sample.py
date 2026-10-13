import pandas as pd,json,re,struct,hashlib,duckdb
from pathlib import Path
O=Path(__file__).parent;a=pd.read_csv(O/'action_ready_components.csv',dtype={'old_raw_code':str});d=pd.read_csv(O/'existing_full3_point_conflicts.csv');top=a.nlargest(5,'total_population');rest=a[~a.root.isin(top.root)].sample(min(15,len(a)-len(top)),random_state=20261007);sample=pd.concat([top,rest]);raw=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');out=[]
with raw.open('rb') as f:
 h=f.read(32);hlen,rlen=struct.unpack_from('<HH',h,8);fields=[];offset=1
 while True:
  desc=f.read(32)
  if desc[0]==13:break
  name=desc[:11].split(b'\0')[0].decode();width=desc[16];fields.append((name,offset,width));offset+=width
 for z in sample.to_dict('records'):
  g=d[d.root==z['root']];old=g[(g.haspoint)&(g.year!=2021)].iloc[0];p=json.loads(old.point_json);m=re.search('record_number_1based=(\d+)',p.get('point_origin_locator',''));record=int(m[1]);f.seek(hlen+(record-1)*rlen);b=f.read(rlen);values={n:b[o:o+w].decode('cp1251').strip() for n,o,w in fields};code=''.join(values[n].zfill(w) for n,w in [('TER',2),('KOD1',3),('KOD2',3),('KOD3',3)]);lat=float(values['LAT']);lon=float(values['LONG']);assert (lat,lon)==(old.latitude,old.longitude);assert code==z['old_raw_code'];out.append({'root':z['root'],'name':z['name'],'raw_dbf_record_1based':record,'raw_code':code,'raw_label':values.get('NAME1'),'latitude':lat,'longitude':lon,'raw_record_sha256':hashlib.sha256(b).hexdigest(),'point_bytes_and_code_pass':True,'article_url':z['article_url'],'article_sha256':z['article_sha256']})
pd.DataFrame(out).to_csv(O/'fixed15_largest5_physical_source_checks.csv',index=False)
c=duckdb.connect();w=[];p='/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
for z in sample.to_dict('records'):
 g=d[(d.root==z['root'])&(d.year==2021)].iloc[0];pt=json.loads(g.point_json)
 if pt.get('point_origin_kind')!='tochno_2021_dadata_raw_parquet_point':continue
 rn=int(g.source_record_id.rsplit(':',1)[1]);q=c.execute('with r as (select row_number() over() rn,* from read_parquet(?)) select object_name,settlement,mun_upper,settlement_dadata,okato_dadata,latitude_dadata,longitude_dadata from r where rn=?',[p,rn]).fetchone();assert (float(q[-2]),float(q[-1]))==(g.latitude,g.longitude);w.append({'root':z['root'],'raw_row_1based':rn,'raw_object_name':q[0],'raw_settlement':q[1],'raw_county':q[2],'provider_own_label':q[3],'provider_raw_okato':q[4],'latitude':q[5],'longitude':q[6],'exact_current_raw_point_pass':True})
pd.DataFrame(w).to_csv(O/'sample_actual_current_publisher_point_checks.csv',index=False);print('physical old records',len(out),'independent publisher records',len(w))
