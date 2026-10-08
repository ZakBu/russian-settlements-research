from pathlib import Path
import json,gzip,time,urllib.request,urllib.parse,urllib.error,ssl,hashlib,datetime
import pandas as pd
O=Path(__file__).parent;E=O.parent;T=O/'request_QIDs.json';W=Path('/workspace/settlements-work/uncached_missing2010_dated_source_mass_20261008');W.mkdir(exist_ok=True);ids=json.loads(T.read_text());assert len(ids)<=540,(len(ids),'540QID bound');assert not list(W.glob('batch_*.json.gz')),'Do not repeat completed requests';records=[];total=0;last=None
for i in range((len(ids)+49)//50):
 if last is not None:time.sleep(max(0,5-(time.monotonic()-last)))
 batch=ids[i*50:(i+1)*50];url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(batch),'props':'claims|labels|descriptions|aliases|sitelinks','languages':'ru|en','format':'json'});rec={'batch':i+1,'QIDs':batch,'request_url':url,'requested_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'TLS_certificate_verification':True,'User_Agent':'RussianSettlementCensusResearch/2026-10-08 (bounded public evidence retrieval; maximum6requests,50items)'};last=time.monotonic()
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':rec['User_Agent'],'Accept':'application/json'}),timeout=30,context=ssl.create_default_context())as resp:
   rec.update(HTTP_status=resp.status,headers_exact=resp.headers.as_string(),Retry_After_exact=resp.headers.get('Retry-After'),request_id=resp.headers.get('X-Request-Id',''),response_date=resp.headers.get('Date',''));raw=resp.read(3000001)
   if len(raw)>3000000:rec['stop_reason']='response_size_bound'
   else:
    payload=json.loads(raw);assert isinstance(payload.get('entities'),dict);compressed=gzip.compress(raw,compresslevel=9,mtime=0)
    if total+len(compressed)>6000000:rec['stop_reason']='compressed_cache_6MB_bound'
    else:
     p=W/f'batch_{i+1:03d}.json.gz';p.write_bytes(compressed);total+=len(compressed);rec.update(cache_path=str(p),sha256=hashlib.sha256(compressed).hexdigest(),raw_sha256=hashlib.sha256(raw).hexdigest(),compressed_bytes=len(compressed),raw_bytes=len(raw),entity_records=len(payload['entities']))
 except urllib.error.HTTPError as ex:rec.update(HTTP_status=ex.code,headers_exact=ex.headers.as_string(),Retry_After_exact=ex.headers.get('Retry-After'),error_body_utf8=ex.read(2000).decode('utf-8','replace'),stop_reason='HTTP_error_stop_no_rotation_no_retry')
 except Exception as ex:rec.update(exception=repr(ex),stop_reason='network_error_stop_no_rotation_no_retry')
 records.append(rec);(O/f'HTTP_batch_{i+1:03d}_headers.txt').write_text(rec.get('headers_exact',''));receipt={'status':'stopped'if 'stop_reason'in rec else 'successful_bounded_same_endpoint_requests','endpoint':'https://www.wikidata.org/w/api.php','maximum_requests':6,'requests_made':len(records),'minimum_interval_seconds':5,'TLS_verified':True,'no_endpoint_rotation':True,'no_repeated_retries':True,'queue_input_path':str(T.resolve()),'queue_input_sha256':hashlib.sha256(T.read_bytes()).hexdigest(),'compressed_cache_bytes':total,'records':records};(O/'network_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:rec.get(k)for k in ['batch','HTTP_status','cache_path','compressed_bytes','entity_records','Retry_After_exact','stop_reason','exception']},ensure_ascii=False),flush=True)
 if 'stop_reason'in rec:break
