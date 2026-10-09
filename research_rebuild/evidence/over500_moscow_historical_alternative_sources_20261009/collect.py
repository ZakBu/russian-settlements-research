from pathlib import Path
import pandas as pd,json,gzip,hashlib,urllib.request,urllib.parse,time,datetime
O=Path(__file__).parent
source='/workspace/russian-settlements-research/research_rebuild/evidence/over500_moscow_20261009/assigned111.csv'
r=pd.read_csv(source,keep_default_na=False);r=r[r.source_record_id.str.rsplit(':',n=1).str[-1].isin(['273','3859','3860','4184','6888','9'])];assert len(r)==6
r.to_csv(O/'exact6_targets.csv',index=False)
variants={'Холмогорка':['посёлок Холмогорка','Холмогорка жилой квартал','совхоз техникум Волоколамский'],'Караваевской Фабрики':['посёлок Караваевской фабрики','Караваевская фабрика жилой квартал','Караваево фабричная улица','Караваевской фабрики жилые дома'],'Участка N 2':['посёлок Участка 2','Караваево участок 2','Буньковский участок 2'],'Юдино':['посёлок Юдино','Юдино жилой посёлок','Юдино район деревня'],'Фирмы "Луч"':['посёлок фирмы Луч','Гребнево Луч посёлок','Гребнево жилой комплекс Луч','Фирма Луч жилые дома'],'Санатория "Звенигород"':['посёлок санатория Звенигород','санаторий Звенигород жилые дома','Звенигород посёлок санатория Сеченова','Звенигород посёлок санатория МВД']}
queries=[]
for x in r.to_dict('records'):
 for name in variants[x['settlement_name']]:queries.append(dict(x,query_alias=name,query_county=x['district_raw'] or 'Звенигород'))
receipts=[];candidates=[];bundle=[];last=0
for i,x in enumerate(queries,1):
 if 'skip_reason'in x:receipts.append({'source_record_id':x['source_record_id'],'skip_reason':x['skip_reason']});continue
 region='Московская область';q=', '.join(v for v in [x['query_alias'],x['query_county'],region,'Россия']if v);url='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,extratags=1,namedetails=1,limit=8))
 delay=1.1-(time.monotonic()-last)
 if delay>0:time.sleep(delay)
 last=time.monotonic();entry={'source_record_id':x['source_record_id'],'query':q,'request_url':url,'normal_TLS':True,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'RussianSettlementResearch/1.0 (bounded native locality source audit)'}),timeout=12)as resp:raw=resp.read();entry['status']=resp.status
  j=json.loads(raw);entry['results']=len(j);entry['response_sha256']=hashlib.sha256(raw).hexdigest();bundle.append(dict(entry,response=j));receipts.append(entry)
  for v in j:
   candidates.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=x['region_norm'],query_county=x['query_county'],query_alias=x['query_alias'],provider='OSM_Nominatim',feature_id=str(v.get('osm_type'))+'/'+str(v.get('osm_id')),latitude=v.get('lat'),longitude=v.get('lon'),own_name=v.get('name'),display_name=v.get('display_name'),feature_class=v.get('class'),feature_category=v.get('category'),feature_type=v.get('type'),address_type=v.get('addresstype'),address_json=json.dumps(v.get('address',{}),ensure_ascii=False),extratags_json=json.dumps(v.get('extratags',{}),ensure_ascii=False),namedetails_json=json.dumps(v.get('namedetails',{}),ensure_ascii=False),boundingbox_json=json.dumps(v.get('boundingbox',[])),source_file=str(O/'nominatim_historical6_bundle.json.gz'),source_response_sha256=entry['response_sha256'],source_locator=f'bundle request[{len(bundle)-1}];osm_type={v.get("osm_type")};osm_id={v.get("osm_id")}',candidate_only=True,coordinate_admitted=False,identity_admitted=False,automatic_place_selection=False))
  print(i,q,len(j),flush=True)
 except Exception as e:
  entry['error']=str(e);receipts.append(entry);print(i,type(e).__name__,str(e),flush=True)
  if getattr(e,'code',None)==429:break
 (O/'nominatim_historical6_receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2));(O/'nominatim_historical6_bundle.json.gz').write_bytes(gzip.compress(json.dumps(bundle,ensure_ascii=False).encode(),mtime=0));pd.DataFrame(candidates).to_csv(O/'nominatim_historical6_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0})

print('FALLBACK COMPLETE',len(receipts),len(candidates),flush=True)
