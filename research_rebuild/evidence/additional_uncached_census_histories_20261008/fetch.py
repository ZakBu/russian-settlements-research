from pathlib import Path
import json,gzip,time,urllib.request,urllib.parse,urllib.error,ssl,hashlib,datetime
import pandas as pd
O=Path(__file__).parent;W=Path('/workspace/settlements-work/additional_uncached_census_histories_20261008');f=pd.read_csv(O/'uncached_targets.csv').fillna('');ids=list(dict.fromkeys(f.qid));records=[];total=0;start=time.monotonic();last=None;status='not_started'
assert not list(W.glob('batch_*.json.gz')), 'Do not repeat existing completed requests'
for i in range(min(20,(len(ids)+49)//50)):
 if last is not None:time.sleep(max(0,5-(time.monotonic()-last)))
 batch=ids[i*50:(i+1)*50];url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(batch),'props':'claims|labels|descriptions|aliases','languages':'ru|en','format':'json'})
 rec={'batch':i+1,'QIDs':batch,'request_url':url,'requested_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'TLS_certificate_verification':True,'User_Agent':'RussianSettlementCensusResearch/2026-10-08 (bounded public census evidence retrieval; 50-item batches)'};last=time.monotonic()
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':rec['User_Agent'],'Accept':'application/json'}),timeout=30,context=ssl.create_default_context()) as resp:
   rec['HTTP_status']=resp.status;rec['headers_exact']=resp.headers.as_string();rec['Retry_After_exact']=resp.headers.get('Retry-After');raw=resp.read(3000001)
   if len(raw)>3000000:rec['stop_reason']='raw_response_exceeds_3MB_bound';status='response_size_hold'
   else:
    payload=json.loads(raw);assert isinstance(payload.get('entities'),dict);compressed=gzip.compress(raw,compresslevel=9,mtime=0)
    if total+len(compressed)>5000000:rec['stop_reason']='compressed_cache_5MB_bound';status='cache_size_hold'
    else:
     p=W/f'batch_{i+1:03d}.json.gz';p.write_bytes(compressed);total+=len(compressed);rec.update({'cache_path':str(p),'sha256':hashlib.sha256(compressed).hexdigest(),'compressed_bytes':len(compressed),'raw_bytes':len(raw),'entity_records':len(payload['entities'])});status='successful_public_bounded_batch'
 except urllib.error.HTTPError as exc:
  rec.update({'HTTP_status':exc.code,'headers_exact':exc.headers.as_string(),'Retry_After_exact':exc.headers.get('Retry-After'),'error_body_utf8':exc.read(3000).decode('utf-8','replace')});status='network_hold_no_retry' if exc.code in (429,403) else 'HTTP_error_stop';rec['stop_reason']='stop; no endpoint rotation or retry'
 except Exception as exc:rec['exception']=repr(exc);status='network_error_stop';rec['stop_reason']='stop; no repeated retry'
 (O/f'HTTP_batch_{i+1:03d}_headers.txt').write_text(rec.get('headers_exact',''));records.append(rec)
 receipt={'status':status,'requests_made':len(records),'maximum_requests':20,'compressed_cache_bytes':total,'minimum_request_interval_seconds':5,'endpoint':'https://www.wikidata.org/w/api.php','TLS_certificate_verification':True,'no_endpoint_rotation':True,'no_retries':True,'records':records,'wall_seconds':time.monotonic()-start};tmp=O/'network_receipt.tmp';tmp.write_text(json.dumps(receipt,indent=2));tmp.replace(O/'network_receipt.json');print(json.dumps({k:v for k,v in rec.items() if k not in ('headers_exact','error_body_utf8','QIDs','request_url')},ensure_ascii=False),flush=True)
 if 'stop_reason' in rec:break
