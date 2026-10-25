"""Verify and package the newly recovered official source publications."""
from pathlib import Path
import hashlib
import json
import zipfile
ROOT=Path(__file__).resolve().parents[3]
D=ROOT/'work/ecommerce_rosters_verified'
O=ROOT/'work/ecommerce_roster_source_release';O.mkdir(parents=True,exist_ok=True)
m=json.loads((ROOT/'research/ecommerce_cloud/continuation/roster_pinned_manifest.json').read_text())
for r in m['records']:
    p=D/r['filename']
    b=p.read_bytes()
    assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
dest=O/'official-rosters-20221228-20241227.zip'
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(D.iterdir()):
        if p.is_file():
            z.write(p,p.name)
    z.writestr('pinned_source_manifest.json',json.dumps(m,ensure_ascii=False,indent=2))
digest=hashlib.sha256(dest.read_bytes()).hexdigest()
(O/'SHA256SUMS.txt').write_text(digest+'  '+dest.name+'\n')
print('ROSTER_SOURCE_RELEASE_BEGIN')
print(json.dumps({'bytes':dest.stat().st_size,'sha256':digest,'records':m['records'],
                  'exact_january_state_verified':False,'boundaries_verified':False},ensure_ascii=False))
print('ROSTER_SOURCE_RELEASE_END')
