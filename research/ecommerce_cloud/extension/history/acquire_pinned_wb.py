"""Acquire pinned historical bodies independently of the pending cloud bundle."""
from pathlib import Path
import concurrent.futures,json,hashlib,gzip
__file__=str(Path(__file__).with_name('probe_sources.py'))
exec(Path(__file__).read_text().split('urls=[]')[0])
M=R/'work/sources/research/ecommerce_settlement_20261024/history_stage_20261024/network/acquisition_manifest.json'
entries=json.loads(M.read_text())['historical_snapshots']
def acquire(x):
 name='wb_'+x['observation_date'];p=OUT/(name+'.json')
 if not p.exists():
  r=fetch((name,x['archive_url']));assert r.get('status')==200,r
  b=(R/r['body']).read_bytes();assert hashlib.sha256(b).hexdigest()==x['raw_response_sha256'],name
  decoded=gzip.decompress(b)if b[:2]==b'\x1f\x8b'else b
  assert hashlib.sha256(decoded).hexdigest()==x['decoded_sha256'],name
  p.write_bytes(decoded)
 return {'date':x['observation_date'],'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(acquire,entries))
(R/'research/ecommerce_cloud/extension/history/wb_replay_manifest.json').write_text(json.dumps(rows,indent=2));print(rows)
