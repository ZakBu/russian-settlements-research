from pathlib import Path
import json,subprocess,tempfile,hashlib
manifest=json.loads(Path('publication/stage67/release-assets-manifest.json').read_text())
release=json.loads(subprocess.check_output(['gh','release','view','working-settlements-stage67-2026-10-08','--json','id'],text=True))
repo=subprocess.check_output(['gh','repo','view','--json','nameWithOwner','--jq','.nameWithOwner'],text=True).strip()
assets=json.loads(subprocess.check_output(['gh','api',f"repos/{repo}/releases/{release['id']}/assets"],text=True));byname={x['name']:x for x in assets}
for expected in manifest['assets']:
 name=expected['name'];a=byname[name];assert a['state']=='uploaded' and a['size']==expected['bytes'],name
 digest=a.get('digest')
 if digest:assert digest=='sha256:'+expected['sha256'],name
 else:
  with tempfile.TemporaryDirectory() as tmp:
   subprocess.run(['gh','release','download','working-settlements-stage67-2026-10-08','--pattern',name,'--dir',tmp],check=True)
   with (Path(tmp)/name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==expected['sha256'],name
 print('Verified remote release asset',name)
