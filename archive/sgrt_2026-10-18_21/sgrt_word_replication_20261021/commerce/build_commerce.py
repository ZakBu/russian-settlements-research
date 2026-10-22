#!/usr/bin/env python3
"""Rebuild national commerce evidence; frozen and fresh observations stay separate.

The WB join requires an address name AND coordinate concordance. Nearest-only
candidates and conditional type variants never enter baseline function masses.
"""
from pathlib import Path
import argparse, datetime, gzip, hashlib, json, re, unicodedata
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
MASTER=REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet'
WB_URL='https://static-basket-01.wbbasket.ru/vol0/data/all-poo-fr-v11.json'
RADIUS_KM=10.0
EARTH_KM=6371.0088

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()

def norm(s):
 return re.sub(r'\s+',' ',re.sub(r'[^\w\s-]',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е'))).strip()

def xyz(lat,lon):
 lat=np.deg2rad(np.asarray(lat));lon=np.deg2rad(np.asarray(lon))
 return np.column_stack([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])

def head(s):
 return re.split(r'\b(?:улица|ул\.?|проспект|пр-кт|переулок|пер\.?|шоссе|бульвар|площадь|проезд|набережная)\b',norm(s),maxsplit=1)[0]

def type_agreement(address,n,t):
 for pat,allowed in [(r'\b(?:село|с)\s+',{'село'}),(r'\b(?:город|г)\s+',{'город'}),(r'\bдеревня\s+',{'деревня'})]:
  if re.search(pat+re.escape(n)+r'(?!\w)',address) and norm(t) not in allowed:return False
 return True

def build():
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 source=HERE/'sources/wb_20261021.json.gz'
 if not source.exists():
  raw=HERE/'sources/wb_20261021.json'
  with raw.open('rb') as inp, gzip.GzipFile(str(source),'wb',mtime=0) as out:
   for b in iter(lambda:inp.read(2**20),b''):out.write(b)
 raw=gzip.decompress(source.read_bytes());corpus=json.loads(raw)
 ru=next(x['items']for x in corpus if x['country']=='ru')
 schema=pd.read_parquet(MASTER,columns=['id','name','type','region','lat','lon'])
 assert len(schema)==142570 and schema.id.is_unique and schema.id.notna().all()
 quarantine=REPO/'research/sgrt_opornost_20261019/model/coordinate_quarantine.csv'
 qids=set(pd.read_csv(quarantine).id)
 a=schema[np.isfinite(schema.lat)&np.isfinite(schema.lon)&~schema.id.isin(qids)].reset_index(drop=True)
 names=a.name.map(norm).to_numpy();types=a.type.to_numpy();uids=a.id.to_numpy()
 patterns={n:re.compile(r'(?<!\w)'+re.escape(n)+r'(?!\w)')for n in set(names)if len(n)>=3}
 tree=cKDTree(xyz(a.lat,a.lon))
 objects=pd.DataFrame([dict(object_id='wb:'+str(x['id']),source_object_id=str(x['id']),address=x.get('address',''),
  latitude=x.get('coordinates',[None,None])[0],longitude=x.get('coordinates',[None,None])[1],
  typePoint=x.get('typePoint'),source_status=x.get('status'),fitting_rooms=x.get('fittingRooms'),
  work_time=x.get('workTime'),source_country='ru',provider='Wildberries',snapshot_date='2026-10-21',
  source_url=WB_URL,opening_date=None,actual_consumer_flows_observed=False)for x in ru])
 assert objects.object_id.is_unique
 valid=objects.latitude.between(-90,90)&objects.longitude.between(-180,180)
 assert valid.all(),'Invalid provider coordinates: preserve and review before linking'
 coords=xyz(objects.latitude,objects.longitude)
 neighbours=tree.query_ball_point(coords,r=2*np.sin(RADIUS_KM/EARTH_KM/2),workers=2)
 chord,near=tree.query(coords,k=1,workers=2)
 nearest_km=2*EARTH_KM*np.arcsin(np.clip(chord/2,0,1))
 links=[]
 for i,(r,ix) in enumerate(zip(objects.itertuples(index=False),neighbours)):
  h=head(r.address);cand=[];relaxed=[]
  foreign=bool(re.search('баренцбург|barentsburg|svalbard',h))
  for k in ix:
   n=names[k]
   if len(n)<3 or not patterns[n].search(h):continue
   d=2*EARTH_KM*np.arcsin(np.clip(np.linalg.norm(coords[i]-tree.data[k])/2,0,1))
   relaxed.append((k,d))
   if type_agreement(h,n,types[k]):cand.append((k,d))
  # More specific compound settlement names supersede substring names.
  for pool in [cand,relaxed]:
   if pool:
    length=max(len(names[k])for k,d in pool);pool[:]=[(k,d)for k,d in pool if len(names[k])==length]
  uid=None;conditional=None;distance=None
  if foreign:status='known_foreign_source_ru_label_no_axis_assignment'
  elif len(cand)==1:uid=uids[cand[0][0]];distance=cand[0][1];status='baseline_literal_name_type_coordinate_within10km'
  elif len(cand)>1:status='ambiguous_named_candidates_preserved'
  elif len(relaxed)==1:conditional=uids[relaxed[0][0]];distance=relaxed[0][1];status='conditional_literal_name_coordinate_type_conflict'
  else:status='unresolved_no_unique_address_identity'
  fed=None
  if uid is None and conditional is None and not foreign:
   if re.search(r'\bмосква\b',h):fed='RU-FED-MOW'
   elif re.search(r'\bсанкт[ -]петербург\b',h):fed='RU-FED-SPB'
   if fed:status='explicit_federal_city_address_territory_context'
  links.append(dict(baseline_uid=uid,conditional_uid=conditional,federal_territory_uid=fed,
   link_status=status,linked_distance_km=distance,named_candidates='|'.join(uids[k]for k,d in cand),
   nearest_uid_unaccepted=uids[near[i]] if not foreign else None,nearest_distance_km=nearest_km[i],
   baseline_stricter_within5km=bool(uid is not None and distance<=5),
   quarantined_coordinates_excluded=True))
  if (i+1)%20000==0:print('WB linked',i+1,flush=True)
 objects=pd.concat([objects,pd.DataFrame(links)],axis=1)
 objects['focus_types_8_34']=objects.typePoint.isin([8,34])
 objects['expanded_types_8_34_28_53_54']=objects.typePoint.isin([8,34,28,53,54])
 objects['technical_types_2_85']=objects.typePoint.isin([2,85])
 objects.to_parquet(HERE/'wb20261021_objects.parquet',index=False)
 objects[objects.baseline_uid.isna()].to_csv(HERE/'wb20261021_review_queue.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 # Existing accepted frozen evidence is retained with its original names and date.
 import pyarrow.parquet as pq
 cols=pq.ParquetFile(MASTER).schema_arrow.names
 chosen=[c for c in cols if c.startswith(('wb_','places_')) and (c.startswith('wb_') or any(t in c for t in ['retail_store','market_count','food_service','bank_count','atm_count','post_office','postal_collection_point','name_signal_ozon','name_signal_wildberries']))]
 chosen += [c for c in cols if re.match(r'econ_native_\d{4}_(retail47|food56)_legal_entities$',c)]
 f=pd.read_parquet(MASTER,columns=['id']+chosen).set_index('id')
 for label,key in [('baseline','baseline_uid'),('conditional_additional','conditional_uid')]:
  z=objects[objects[key].notna()]
  for name,mask in [('all_types',pd.Series(True,index=z.index)),('focus',z.focus_types_8_34),('expanded',z.expanded_types_8_34_28_53_54),('technical',z.technical_types_2_85)]:
   f[f'commerce_wb20261021_{label}_{name}_count']=z[mask].groupby(key).size().reindex(f.index,fill_value=0).astype('int32')
  if label=='baseline':f['commerce_wb20261021_baseline_focus_within5km_count']=z[z.focus_types_8_34&z.baseline_stricter_within5km].groupby(key).size().reindex(f.index,fill_value=0).astype('int32')
 # One goods-access group, regardless of WB also appearing as retail in Places.
 retail=f.places_baseline_retail_store_count
 market=f.places_baseline_market_count
 wb=f.commerce_wb20261021_baseline_focus_count
 f['commerce_goods_access_baseline_present']=(retail.gt(0)|market.gt(0)|wb.gt(0))
 f['commerce_goods_access_log_mass']=np.maximum.reduce([np.log1p(retail),np.log1p(market),np.log1p(wb)])
 f['commerce_food_baseline_present']=f.places_baseline_food_service_count.gt(0)
 f['commerce_food_log_mass']=np.log1p(f.places_baseline_food_service_count)
 f['commerce_finance_baseline_present']=f.places_baseline_bank_count.gt(0)|f.places_baseline_atm_count.gt(0)
 f['commerce_postal_baseline_present']=f.places_baseline_post_office_count.gt(0)|f.places_baseline_postal_collection_point_count.gt(0)
 f['commerce_ozon_name_signal_not_verified_pvz_count']=f.get('places_baseline_name_signal_ozon_count',0)
 f['commerce_historical_legal_retail_2011_2025_available']=True
 f['commerce_physical_network_comparable_time_series_available']=False
 f['commerce_external_catchment_measured']=False
 f['commerce_zero_means']='no_accepted_source_witness_not_proven_absence'
 f=f.reset_index();f.to_parquet(HERE/'settlement_features.parquet',index=False)
 regional=f[['id','commerce_goods_access_baseline_present','commerce_food_baseline_present','commerce_wb20261021_baseline_focus_count']].merge(schema[['id','region']],on='id',validate='one_to_one').groupby('region').agg(axis_settlements=('id','size'),goods_access_settlements=('commerce_goods_access_baseline_present','sum'),food_settlements=('commerce_food_baseline_present','sum'),wb_focus_locations=('commerce_wb20261021_baseline_focus_count','sum'))
 regional.to_csv(HERE/'regional_coverage.csv')
 pd.DataFrame([dict(column=c,meaning=('Original frozen source feature; source-specific baseline/conditional distinction retained' if not c.startswith('commerce_') else 'Derived commerce observation; see README and script'),input_origin='feature_master'if not c.startswith('commerce_')else'WB live snapshot or documented composition')for c in f if c!='id']).to_csv(HERE/'feature_dictionary.csv',index=False)
 temporal=[]
 for y in range(2011,2026):
  retail=f[f'econ_native_{y}_retail47_legal_entities'];food=f[f'econ_native_{y}_food56_legal_entities']
  temporal.append(dict(year=y,retail_registered_entities=int(retail.sum()),settlements_with_registered_retail=int(retail.gt(0).sum()),food_registered_entities=int(food.sum()),settlements_with_registered_food=int(food.gt(0).sum()),meaning='registered_legal_entities_not_physical_sites_or_observed_service',fixed_axis_rows=len(f)))
 pd.DataFrame(temporal).to_csv(HERE/'registered_commerce_calendar.csv',index=False)
 checks={'axis142570_all_unique':len(f)==142570 and f.id.is_unique,'exact_master_order':f.id.equals(schema.id),
  'all_source_ru_objects_preserved':len(objects)==len(ru),'source_ids_unique':objects.object_id.is_unique,
  'no_baseline_conditional_overlap':not(objects.baseline_uid.notna()&objects.conditional_uid.notna()).any(),
  'no_quarantine_baseline':not bool(set(objects.baseline_uid.dropna())&qids),
  'baseline_literal_name_and_coordinates_only':objects.loc[objects.baseline_uid.notna(),'link_status'].eq('baseline_literal_name_type_coordinate_within10km').all(),
  'no_foreign_assignment':objects.loc[objects.link_status.str.startswith('known_foreign'),'baseline_uid'].isna().all(),
  'linked_objects_balance':int(f.commerce_wb20261021_baseline_all_types_count.sum())==objects.baseline_uid.notna().sum(),
  'no_invented_flow':not f.commerce_external_catchment_measured.any(),
  'no_fake_physical_time_series':not f.commerce_physical_network_comparable_time_series_available.any()}
 checks={k:bool(v)for k,v in checks.items()};assert all(checks.values())
 receipt={'status':'PASS','started_utc':start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
  'rows':len(f),'columns':len(f.columns),'source_country_counts':{x['country']:len(x['items'])for x in corpus},
  'wb_objects_ru':len(objects),'wb_link_status_counts':objects.link_status.value_counts().to_dict(),
  'wb_baseline_settlements':int(f.commerce_wb20261021_baseline_all_types_count.gt(0).sum()),
  'wb_baseline_focus_settlements':int(wb.gt(0).sum()),'goods_access_settlements':int(f.commerce_goods_access_baseline_present.sum()),
  'wb_baseline_focus_settlements_within5km':int(f.commerce_wb20261021_baseline_focus_within5km_count.gt(0).sum()),
  'wb_baseline_distance_quantiles_km':{str(k):float(v)for k,v in objects.loc[objects.baseline_uid.notna(),'linked_distance_km'].quantile([0,.5,.9,.95,.99,1]).items()},
  'food_settlements':int(f.commerce_food_baseline_present.sum()),'checks':checks,
  'live_catalog_comparison':{'frozen_20261019_ru_records':91136,'fresh_ru_records':len(objects),'difference':len(objects)-91136,'interpretation':'catalog snapshot difference, not physical openings/closures; no old full-object source restored for stable-id panel'},
  'source_files':{'master':{'path':str(MASTER.relative_to(REPO)),'sha256':sha(MASTER)},'wb_compressed':{'path':str(source.relative_to(REPO)),'sha256':sha(source)},'wb_uncompressed_sha256':hashlib.sha256(raw).hexdigest(),'coordinate_quarantine':{'path':str(quarantine.relative_to(REPO)),'sha256':sha(quarantine)}},
  'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in [HERE/'settlement_features.parquet',HERE/'wb20261021_objects.parquet',HERE/'registered_commerce_calendar.csv']},
  'limitations':['No verified complete official Ozon pickup-point inventory','WB ru is a provider country label, not authoritative national boundaries','WB focus8/34 classification inherited and explicit, not all26 source types are public PVZ','Nearest-only candidates excluded from accepted evidence','No measurement of consumers, catchment boundaries, traffic, capacity, or opening dates','Legal retail history2011–2025 is not physical commerce time series','Frozen Places2026-09-23.1 and WB2026-10-21 must not backcast functions to census dates']}
 probe=HERE/'sources/ozon_access_probe.json'
 if probe.exists():
  receipt['access_probe']=json.loads(probe.read_text());receipt['source_files']['ozon_probe']={'path':str(probe.relative_to(REPO)),'sha256':sha(probe)}
 objects[objects.baseline_uid.notna()].sort_values('linked_distance_km',ascending=False).head(100).to_csv(HERE/'baseline_largest_distance_diagnostic.csv',index=False)
 (HERE/'source_manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in receipt.items()if k not in ['source_files','outputs','limitations']},ensure_ascii=False,indent=2))

if __name__=='__main__':build()
