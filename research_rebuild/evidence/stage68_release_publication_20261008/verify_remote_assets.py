from pathlib import Path
import json,subprocess,tempfile,hashlib,os
manifest=json.loads(Path('publication/stage68/release-assets-manifest.json').read_text())
repo=os.environ.get('GH_REPO') or subprocess.check_output(['gh','repo','view','--json','nameWithOwner','--jq','.nameWithOwner'],text=True).strip()
releases=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/releases?per_page=100'],text=True))
release=next(x for x in releases if x['tag_name']=='working-settlements-stage68-2026-10-08')
assert isinstance(release['id'],int)
mp=Path('publication/stage68/release-assets-manifest.json')
with mp.open('rb') as f:manifest['assets'].append({'name':mp.name,'bytes':mp.stat().st_size,'sha256':hashlib.file_digest(f,'sha256').hexdigest()})
assets=json.loads(subprocess.check_output(['gh','api',f"repos/{repo}/releases/{release['id']}/assets"],text=True));byname={x['name']:x for x in assets}
for expected in manifest['assets']:
 name=expected['name'];a=byname[name];assert a['state']=='uploaded' and a['size']==expected['bytes'],name
 digest=a.get('digest')
 if digest:assert digest=='sha256:'+expected['sha256'],name
 else:
  with tempfile.TemporaryDirectory() as tmp:
   subprocess.run(['gh','release','download','working-settlements-stage68-2026-10-08','--pattern',name,'--dir',tmp],check=True)
   with (Path(tmp)/name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==expected['sha256'],name
 print('Verified remote release asset',name)
