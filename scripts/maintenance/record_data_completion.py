"""Record verified data publication; never asserts new scientific results."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import subprocess
import re
import os
import hashlib
catalog=json.loads(Path('data/catalog.json').read_text())
assert catalog['status']=='verified_complete'
assert all(a['status']=='verified' for a in catalog['assets'])
release_url=json.loads(subprocess.check_output(['gh','release','view',catalog['release_tag'],'--repo',catalog['repository'],'--json','uploadUrl']))['uploadUrl']
release_id=re.search(r'/releases/(\d+)/',release_url).group(1)
remote=json.loads(subprocess.check_output(['gh','api','repos/'+catalog['repository']+'/releases/'+release_id]))
assert not remote['draft'], 'The data release must be public before handoff is complete'
server={a['name']:a for a in remote['assets']}
for asset in catalog['assets']:
 current=server.get(asset['asset']);assert current and current['size']==asset['bytes'] and current.get('digest')=='sha256:'+asset['sha256'],asset['asset']
legacy=json.loads(subprocess.check_output(['gh','api','repos/'+catalog['repository']+'/releases?per_page=100']))
catalog['related_releases']=[{'tag':r['tag_name'],'url':r['html_url'],'scope':'Previously published supporting datasets; linked without duplicating their existing archives.','assets':[{'name':a['name'],'bytes':a['size'],'url':a['browser_download_url'],'server_digest':a.get('digest')} for a in r['assets']]} for r in legacy if not r['draft'] and r['tag_name']!=catalog['release_tag']]
for blob,obj in catalog['objects'].items():
 if obj.get('stored_in_current_git'):
  raw=Path(obj['source_path']).read_bytes()
  assert len(raw)==obj['bytes']
  assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==blob
  digest=hashlib.sha256(raw).hexdigest()
  if obj.get('sha256'):assert obj['sha256']==digest
  obj['sha256']=digest
catalog['counts']['objects_with_sha256']=sum('sha256' in obj for obj in catalog['objects'].values())
assert catalog['counts']['objects_with_sha256']==catalog['counts']['unique_blobs']
from normalize_data_catalog import normalize
normalize(catalog,json.loads(Path('data/source_special_files.json').read_text()))
assert not catalog['readability']['core_parquet_schema_errors']
Path('data/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
now=datetime.now(ZoneInfo('Europe/Moscow')).isoformat()
p=Path('research_context/current_state.json');state=json.loads(p.read_text());state['updated_moscow']=now;state['active_automation']={'workflow':'.github/workflows/portable-research-data.yml','run_id':int(os.environ.get('GITHUB_RUN_ID','39765368836')),'url':'https://github.com/'+catalog['repository']+'/actions/runs/'+os.environ.get('GITHUB_RUN_ID','39765368836'),'status_at_this_record':'completed_packaging_verification','launch_commit':os.environ.get('GITHUB_SHA'),'instruction':'The GitHub run can have a final commit step after this record; verify its final conclusion.'};state['data_transfer']={'status':'verified_complete','catalog':'data/catalog.json','release_tag':catalog['release_tag'],'counts':catalog['counts'],'verification':'Every extracted source blob matched Git SHA-1 and SHA-256; each uploaded ZIP matched GitHub server SHA-256 digest. Parquet schemas recorded.'};p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
with open('research_context/diary/2026-10-22.md','a') as f:
 f.write('\n## '+now+' — завершение переноса данных\n\n')
 f.write('Автоматическая упаковка завершена. Каталог: data/catalog.json. Релиз: '+catalog['release_tag']+'.\n\n')
 f.write('Проверенные итоги: '+json.dumps(catalog['counts'],ensure_ascii=False)+'.\n\n')
 f.write('Каждый объект побайтно сопоставлен с исходным Git-хешем и SHA-256; ZIP проверены по серверным SHA-256 GitHub. Схемы Parquet сохранены в каталоге. Это проверка переноса, а не новая проверка научной модели. Новая функциональная модель не рассчитана.\n')

# Keep the release entry point byte-identical to the catalog committed to Git.
subprocess.run(['gh','release','upload',catalog['release_tag'],'data/catalog.json','--repo',catalog['repository'],'--clobber'],check=True)
