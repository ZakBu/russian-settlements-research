"""Restore byte-pinned official publications from the preserved source release."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser()
p.add_argument('--output',default='work/ecommerce_rosters_verified')
a=p.parse_args()
out=ROOT/a.output;out.mkdir(parents=True,exist_ok=True)
m=json.loads((ROOT/'research/ecommerce_cloud/continuation/roster_pinned_manifest.json').read_text())
cache=out/'official-rosters-20221228-20241227.zip'
if not cache.exists():
    with urllib.request.urlopen(m['bundle_url'],timeout=60) as r:
        b=r.read(20000001)
    if len(b)>20000000:
        raise ValueError('Unexpected source bundle size')
    cache.write_bytes(b)
body=cache.read_bytes()
if m.get('bundle_sha256'):
    assert hashlib.sha256(body).hexdigest()==m['bundle_sha256']
with zipfile.ZipFile(cache) as z:
    for row in m['records']:
        name=row['filename']
        assert PurePosixPath(name).name==name
        b=z.read(name)
        assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
        (out/name).write_bytes(b)
    for name in ['summary.json','catalogue.html','russian_trusted_root_ca_pem.crt',
                 'russian_trusted_sub_ca_pem.crt','russian_trusted_sub_ca_2024_pem.crt']:
        if name in z.namelist():
            (out/name).write_bytes(z.read(name))
print('PINNED_OFFICIAL_ROSTERS_RESTORED')
print(json.dumps({'records_n':len(m['records']),
                  'bundle_sha256':hashlib.sha256(body).hexdigest(),
                  'January_states_verified':False,'boundaries_verified':False}))
