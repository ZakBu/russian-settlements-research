"""Audit genuine dated Ozon CMS API captures; areaIds never pooled as a national census."""
from pathlib import Path
import json,collections,math,csv,itertools,hashlib
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent;RAW=ROOT/'work/ecommerce_extension_history'
manifest=json.loads((OUT/'derived_ozon_acquisition.json').read_text());summary=[];operators=[];norm=[];samples={}
def flag(props,name):
 p=next((x for x in props if x.get('name')==name),None)
 return None if p is None or 'enabled'not in p else p['enabled']
def distance(a,b):
 x,y=a['coordinates'],b['coordinates'];lat1,lon1=x['latitude'],x['longitude'];lat2,lon2=y['latitude'],y['longitude'];r=math.pi/180;h=math.sin((lat2-lat1)*r/2)**2+math.cos(lat1*r)*math.cos(lat2*r)*math.sin((lon2-lon1)*r/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))
for receipt in manifest:
 f=ROOT/receipt['decoded_body'];assert hashlib.sha256(f.read_bytes()).hexdigest()==receipt['decoded_sha256'];j=json.loads(f.read_bytes())['pvzs'];assert len(j)==len({x['id']for x in j})
 timestamp=receipt['observation_timestamp'];date=timestamp[:4]+'-'+timestamp[4:6]+'-'+timestamp[6:8];area=receipt['original_url'].split('areaId=')[-1]
 samples[timestamp]={str(x['id']):x for x in j}
 lat=[x['coordinates']['latitude']for x in j];lon=[x['coordinates']['longitude']for x in j]
 counts=collections.Counter((str(x.get('provider',{}).get('id')),x.get('provider',{}).get('name'),str(x.get('deliveryType',{}).get('id')),x.get('deliveryType',{}).get('name'))for x in j)
 for (pid,pname,tid,tname),n in counts.items():operators.append({'observation_date':date,'area_id':area,'provider_id':pid,'provider_name':pname,'delivery_type_id':tid,'delivery_type_name':tname,'objects':n})
 summary.append({'observation_date':date,'archive_timestamp':timestamp,'area_id':area,'objects':len(j),'unique_ids':len(set(x['id']for x in j)),'latitude_min':min(lat),'latitude_max':max(lat),'longitude_min':min(lon),'longitude_max':max(lon),'delivery_type_counts':json.dumps(dict(collections.Counter(x.get('deliveryType',{}).get('name')for x in j)),ensure_ascii=False),'available_for_ozon_true':sum(flag(x.get('properties',[]),'AvailableForOzon')is True for x in j),'available_for_ozon_unknown':sum(flag(x.get('properties',[]),'AvailableForOzon')is None for x in j),'hidden_true':sum(flag(x.get('properties',[]),'IsHidden')is True for x in j),'hidden_unknown':sum(flag(x.get('properties',[]),'IsHidden')is None for x in j),'source_original_url':receipt['original_url'],'national_complete':False})
 for x in j:
  norm.append({'observation_date':date,'archive_timestamp':timestamp,'area_id':area,'source_object_id':str(x['id']),'name':x.get('name'),'address':x.get('address'),'latitude':x['coordinates']['latitude'],'longitude':x['coordinates']['longitude'],'provider_id':str(x.get('provider',{}).get('id')),'provider_name':x.get('provider',{}).get('name'),'delivery_type_id':str(x.get('deliveryType',{}).get('id')),'delivery_type_name':x.get('deliveryType',{}).get('name'),'source_link':x.get('link'),'available_for_ozon':flag(x.get('properties',[]),'AvailableForOzon'),'is_hidden':flag(x.get('properties',[]),'IsHidden'),'first_observed_not_opening_date':True})
pairs=[]
moscow=[r for r in summary if r['area_id']=='2']
for r0,r1 in itertools.combinations(moscow,2):
 a,b=samples[r0['archive_timestamp']],samples[r1['archive_timestamp']];ids=set(a)&set(b)
 pairs.append({'date0':r0['observation_date'],'date1':r1['observation_date'],'area_id':'2','same_ids':len(ids),'same_ids_le100m':sum(distance(a[i],b[i])<=.1 for i in ids),'only_earlier_record':len(set(a)-set(b)),'only_later_record':len(set(b)-set(a)),'stable_ids_provider_id_changed':sum(a[i].get('provider',{}).get('id')!=b[i].get('provider',{}).get('id')for i in ids if distance(a[i],b[i])<=.1),'stable_ids_provider_label_changed':sum(a[i].get('provider',{}).get('name')!=b[i].get('provider',{}).get('name')for i in ids if distance(a[i],b[i])<=.1),'stable_ids_delivery_type_id_changed':sum(a[i].get('deliveryType',{}).get('id')!=b[i].get('deliveryType',{}).get('id')for i in ids if distance(a[i],b[i])<=.1),'stable_ids_delivery_type_label_changed':sum(a[i].get('deliveryType',{}).get('name')!=b[i].get('deliveryType',{}).get('name')for i in ids if distance(a[i],b[i])<=.1),'event_interpretation_allowed':False})
for name,rows in [('ozon_cms_summary.csv',summary),('ozon_cms_operators.csv',operators),('ozon_cms_moscow_overlap.csv',pairs)]:
 with (OUT/name).open('w')as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
import pandas as pd
pd.DataFrame(norm).to_parquet(RAW/'ozon_cms_normalized.parquet',index=False)
print(json.dumps(summary,ensure_ascii=False,indent=2));print('OVERLAP',pairs)
