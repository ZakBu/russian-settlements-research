from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
files=[]
for p in sorted(R.rglob('*')):
    if not p.is_file() or p.name=='MANIFEST.json' or '__pycache__' in p.parts:continue
    b=p.read_bytes();files.append(dict(path=str(p.relative_to(R)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
(R/'MANIFEST.json').write_text(json.dumps(dict(status='FROZEN_FOR_HANDOFF',files=files,source_bytes_note='Hashes cover saved files, web text captures are not raw HTML/PDF bytes'),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(files=len(files),status='FROZEN_FOR_HANDOFF')))
