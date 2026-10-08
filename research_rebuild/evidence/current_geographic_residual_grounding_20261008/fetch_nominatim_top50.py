from pathlib import Path
import pandas as pd,json,gzip,urllib.request,urllib.parse,time,hashlib,re
O=Path(__file__).parent;f=pd.read_csv(O/'priority89_roster.csv.gz',dtype=str,keep_default_na=False).head(50);records=[];sources=[];service_unavailable=False
for i,z in enumerate(f.to_dict('records')):
 if service_unavailable:records.append({'source_record_id':z['source_record_id'],'status':'not_requested_after_service_unavailable'});continue
 name=re.sub(r'^\s*(?:пос[её]лок\s+)?(?:при\s+)?(?:железнодорожн(?:ая|ой)\s+)?(?:станци[яи]|разъезд[а]?)\s+','',z['settlement_name'],flags=re.I);q=', '.join([name,z['district_raw'],z['region_norm'],'Россия']);url='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode({'q':q,'format':'jsonv2','countrycodes':'ru','addressdetails':1,'extratags':1,'namedetails':1,'limit':10});p=O/f'nominatim_ownplace_{i:03}.json.gz'
 try:
  if p.exists():b=gzip.open(p,'rb').read()
  else:time.sleep(2);b=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0 (bounded public locality-source verification)'}),timeout=20).read(250000);p.write_bytes(gzip.compress(b,mtime=0))
  d=json.loads(b);records.append({'source_record_id':z['source_record_id'],'status':'source_response_saved','url':url,'origin_file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'returned_results':len(d)});sources.extend({'source_record_id':z['source_record_id'],'source_response_file':str(p),'source_locator':f'json_results[{j}]','raw_ownplace_result':r} for j,r in enumerate(d));print('nominatim',i+1,'of50',len(d),flush=True)
 except Exception as ex:
  code=getattr(ex,'code',None);records.append({'source_record_id':z['source_record_id'],'status':'source_unavailable','url':url,'failure':type(ex).__name__+':'+str(ex),'http_status':code});print('nominatim_source_unavailable',code,str(ex),flush=True)
  if code in [403,429]:
   if hasattr(ex,'read'):(O/'nominatim_service_unavailable_body.txt').write_bytes(ex.read(5000))
   service_unavailable=True
(O/'nominatim_ownplace_results_index.json.gz').write_bytes(gzip.compress(json.dumps(sources,ensure_ascii=False).encode(),mtime=0));(O/'nominatim_source_receipt.json').write_text(json.dumps({'bounded_top50_targets':len(f),'normal_TLS':True,'request_pace_seconds':2,'stop_on403or429_no_bypass':True,'service_unavailable':service_unavailable,'requests':records},ensure_ascii=False,indent=2)+'\n')
