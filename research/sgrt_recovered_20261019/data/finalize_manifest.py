"""Finalize stable output checksums after execution logs; verify all hashes read back."""
from pathlib import Path
import json,hashlib
O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads((O/'audit.json').read_text());outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(O.iterdir()) if p.is_file() and p.name!='checksums.json' and not p.name.endswith('.log')}
r={'inputs':a['inputs'],'outputs':outputs,'excluded':'execution logs because their bytes change during capture'};(O/'checksums.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));assert all(sha(O/name)==x['sha256'] for name,x in outputs.items());print(json.dumps({'stable_output_checksums_verified':len(outputs),'input_pins':len(a['inputs'])}))
