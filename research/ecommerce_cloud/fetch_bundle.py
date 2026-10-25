"""Download pinned release data with TLS and SHA256, then extract safe files."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
catalog = json.loads((HERE / 'bundle_catalog.json').read_text())
cache = ROOT / '.research-cache/ecommerce'
cache.mkdir(parents=True, exist_ok=True)
archive = cache / catalog['asset_name']

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

if not archive.exists() or digest(archive) != catalog['sha256']:
    temp = archive.with_suffix('.partial')
    with urllib.request.urlopen(catalog['url'], timeout=120) as response, temp.open('wb') as out:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            out.write(block)
    if temp.stat().st_size != catalog['bytes'] or digest(temp) != catalog['sha256']:
        raise RuntimeError('Release asset hash/size mismatch')
    temp.replace(archive)

manifest = json.loads((HERE / 'data_manifest.json').read_text())
expected = {r['path']: r for r in manifest['files']}
with tarfile.open(archive, 'r:gz') as tar:
    members = tar.getmembers()
    assert len(members) == len(expected)
    assert {m.name for m in members} == set(expected)
    for member in members:
        relative = PurePosixPath(member.name)
        if not member.isfile() or relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError(f'Unsafe archive member: {member.name}')
        target = ROOT / member.name
        if not target.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError(f'Path escapes repository: {member.name}')
        row = expected[member.name]
        if member.size != row['bytes']:
            raise RuntimeError(f'Member size mismatch: {member.name}')
        if target.exists() and digest(target) != row['sha256']:
            raise RuntimeError(f'Existing file differs; preserve it: {member.name}')
    for member in members:
        target = ROOT / member.name
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = tar.extractfile(member)
        with stream, target.open('wb') as out:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                out.write(block)
        if digest(target) != expected[member.name]['sha256']:
            raise RuntimeError(f'Extracted hash mismatch: {member.name}')
print(f"Restored {len(expected)} pinned research files. Run check_bundle.py next.")
