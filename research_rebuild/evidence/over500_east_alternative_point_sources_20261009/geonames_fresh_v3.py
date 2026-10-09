from pathlib import Path
import pandas as pd,json,gzip,hashlib,urllib.request,urllib.parse,time,datetime
O=Path(__file__).parent;RAM=Path('/dev/shm/over500-20261009/east_alternative_points')
r=pd.read_csv(O/'exact81_targets.csv.gz',dtype=str,keep_default_na=False);u=set()
for f in ['geonames_cached_own_place_candidates.csv.gz','nominatim_own_feature_candidates.csv.gz','nominatim_v2_own_feature_candidates.csv.gz']:u|=set(pd.read_csv(O/f).source_record_id)
r=r[~r.source_record_id.isin(u)]
rows=[];receipts=[]
for i,(name,g)in enumerate(r.groupby('settlement_name'),1):
 url='https://geocoding-api.open-meteo.com/v1/search?'+urllib.parse.urlencode(dict(name=name,count=50,language='ru',format='json'))
 try:
  with urllib.request.urlopen(url,timeout=20)as resp:b=resp.read();status=resp.status
  f=RAM/f'geonames_fresh_v3_{i}.json.gz';f.write_bytes(gzip.compress(b,mtime=0));sha=hashlib.sha256(f.read_bytes()).hexdigest();j=json.loads(b);receipts.append(dict(query=name,url=url,normal_TLS=True,status=status,capture=str(f),sha256=sha,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),response=j))
  for x in g.to_dict('records'):
   for v in j.get('results',[]):
    if v.get('country_code')!='RU':continue
    rows.append(dict(source_record_id=x['source_record_id'],settlement_name=name,region_norm=x['region_norm'],district_raw=x['district_raw'],feature_id=v['id'],own_name=v.get('name'),feature_code=v.get('feature_code'),latitude=v['latitude'],longitude=v['longitude'],admin1=v.get('admin1'),admin2=v.get('admin2'),admin3=v.get('admin3'),admin4=v.get('admin4'),admin1_id=v.get('admin1_id'),source_file=str(f),source_sha256=sha,source_locator='GeoNamesID='+str(v['id']),original_feature_json=json.dumps(v,ensure_ascii=False),candidate_only=True,coordinate_admitted=False,identity_admitted=False))
  print(name,len(j.get('results',[])),flush=True)
 except Exception as e:
  receipts.append(dict(query=name,url=url,error=str(e)));print(name,str(e),flush=True)
  if getattr(e,'code',None)==429:break
 time.sleep(1.1)
pd.DataFrame(rows).to_csv(O/'geonames_fresh_v3_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'geonames_fresh_v3_capture_bundle.json.gz').write_bytes(gzip.compress(json.dumps(receipts,ensure_ascii=False).encode(),mtime=0));print('COMPLETE',len(rows),flush=True)
