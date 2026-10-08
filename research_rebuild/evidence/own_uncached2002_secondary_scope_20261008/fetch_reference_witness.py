from pathlib import Path
import urllib.request,urllib.parse,urllib.error,ssl,json,gzip,hashlib,datetime
O=Path(__file__).parent;W=Path('/workspace/settlements-work/own_uncached2002_secondary_scope_20261008');ids=['Q39825','Q29051383','Q126936423','Q129098375','Q134597830'];p=W/'reference_method_witness.json.gz';assert not p.exists();url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(ids),'props':'labels|descriptions|claims','languages':'ru|en','format':'json'});r={'request_url':url,'QIDs':ids,'requested_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'TLS_verified':True,'no_endpoint_rotation':True}
try:
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'RussianSettlementCensusResearch/2026-10-08 (bounded five reference/method item source witnesses)'}),timeout=30,context=ssl.create_default_context()) as f:
  raw=f.read(500001);r.update(HTTP_status=f.status,headers_exact=f.headers.as_string(),Retry_After=f.headers.get('Retry-After'));assert len(raw)<=500000;d=json.loads(raw);gz=gzip.compress(raw,mtime=0);p.write_bytes(gz);r.update(cache_path=str(p),sha256=hashlib.sha256(gz).hexdigest(),raw_sha256=hashlib.sha256(raw).hexdigest(),compressed_bytes=len(gz));print({q:z.get('labels',{}) for q,z in d['entities'].items()})
except urllib.error.HTTPError as ex:r.update(HTTP_status=ex.code,Retry_After=ex.headers.get('Retry-After'),stop_reason='HTTP_error_stop_no_rotation_no_retry')
(O/'reference_method_network_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
