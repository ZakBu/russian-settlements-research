"""Replay the five pinned positive API captures without rerunning discovery."""
from pathlib import Path
import concurrent.futures,json,hashlib,base64,gzip
exec(Path(__file__).with_name('probe_sources.py').read_text().split('urls=[]')[0])
manifest=R/'research/ecommerce_cloud/extension/history/derived_ozon_acquisition.json'
selected=json.loads(manifest.read_text())

def acquire(x):
    timestamp=x['observation_timestamp']
    name='ozon_cms_'+timestamp
    decoded_path=R/x['decoded_body']
    if decoded_path.exists():
        assert hashlib.sha256(decoded_path.read_bytes()).hexdigest()==x['decoded_sha256']
        return {'timestamp':timestamp,'verified_existing':True,'decoded_sha256':x['decoded_sha256']}
    r=fetch((name,'https://web.archive.org/web/'+timestamp+'id_/'+x['original_url']))
    assert r.get('status')==200,r
    body=(R/r['body']).read_bytes()
    assert base64.b32encode(hashlib.sha1(body).digest()).decode().rstrip('=')==x['cdx_digest']
    assert hashlib.sha256(body).hexdigest()==x['sha256']
    decoded=gzip.decompress(body) if body[:2]==b'\x1f\x8b' else body
    assert hashlib.sha256(decoded).hexdigest()==x['decoded_sha256']
    json.loads(decoded)
    decoded_path.write_bytes(decoded)
    return dict(r,cdx_digest_verified=True,observation_timestamp=timestamp,decoded_sha256=x['decoded_sha256'])

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    results=list(pool.map(acquire,selected))
(manifest.parent/'derived_ozon_replay.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print('Five pinned Ozon captures verified; geographic frames remain separate.')
