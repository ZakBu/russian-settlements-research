"""Verify the transferred research inputs without network or mutation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
manifest = json.loads((HERE / 'data_manifest.json').read_text())
errors = []
for row in manifest['files']:
    path = ROOT / row['path']
    if not path.is_file():
        errors.append(f"MISSING {row['path']}")
        continue
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if path.stat().st_size != row['bytes'] or digest.hexdigest() != row['sha256']:
        errors.append(f"MISMATCH {row['path']}")
for error in errors:
    print(error)
print(f"Checked {len(manifest['files'])} files; failures: {len(errors)}")
raise SystemExit(bool(errors))
