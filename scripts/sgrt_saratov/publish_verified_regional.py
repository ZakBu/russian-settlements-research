"""Independently verify the v2 draft, publish it, then verify all public bytes.

Run on a worker separate from the mathematical producer. No asset is replaced;
registration metadata is emitted only after both complete verification passes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_saratov.register_release import register
from scripts.sgrt_saratov.verify_public_release import verify_public

REPOSITORY = 'ZakBu/russian-settlements-research'
TAG = 'sgrt-saratov-fields-20261029-v2'
PREFIX = 'sgrt/saratov-fields20261029-v2/'
CATALOG = 'data/saratov_fields_catalog_20261029_v2.json'
BYTE_PROOF = 'research_context/analysis_snapshots/saratov_fields_public_verification_20261029_v2.json'
PUBLIC_PROOF = 'research_context/analysis_snapshots/saratov_fields_public_download_20261029_v2.json'
MANIFEST = 'research_context/analysis_snapshots/saratov_fields_manifest_20261029_v2.json'
REGISTRATION_FILES = (CATALOG, BYTE_PROOF, PUBLIC_PROOF, MANIFEST)


def _gh(*arguments):
    result = subprocess.run(['gh', *map(str, arguments)], capture_output=True, text=True)
    if result.returncode:
        message = re.sub(r'https?://[^\s\"]+', '[download URL redacted]', result.stderr)
        raise RuntimeError('GitHub operation failed: '+message[-2000:])
    return result.stdout


def snapshot(release, release_id, producer):
    if release['id'] != release_id or release['tag_name'] != TAG or release['target_commitish'] != producer:
        raise ValueError('Release ID, version tag or exact producer differs')
    assets = release['assets']; names = [a['name'] for a in assets]
    if len(names) != 19 or len(set(names)) != 19 or 'manifest.json' not in names:
        raise ValueError('Exactly nineteen distinct release assets required')
    if any(Path(name).name != name or '/' in name or '\\' in name or name in {'.', '..'} for name in names):
        raise ValueError('Unsafe release asset filename')
    if any(not re.fullmatch(r'sha256:[0-9a-f]{64}', str(a.get('digest', ''))) for a in assets):
        raise ValueError('GitHub asset digests are required')
    return {a['name']: (a['id'], a['size'], a['digest']) for a in assets}


def check_manifest(release, manifest_path, producer):
    raw = Path(manifest_path).read_bytes(); manifest = json.loads(raw)
    if manifest['release_tag'] != TAG or manifest['source_commit'] != producer:
        raise ValueError('Downloaded manifest version or producer differs')
    expected = {manifest['archive']['asset']: manifest['archive'], **manifest['standalone_assets'],
        'manifest.json': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
    actual = {a['name']: a for a in release['assets']}
    if len(expected) != 19 or set(expected) != set(actual):
        raise ValueError('Manifest and release asset inventories differ')
    for name, spec in expected.items():
        if actual[name]['size'] != spec['bytes'] or actual[name]['digest'] != 'sha256:'+spec['sha256']:
            raise ValueError('Manifest and GitHub size/digest differ: '+name)
    return manifest


def _write(root, name, value):
    path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def publish(release_id, producer, download_dir, registration_dir):
    if not re.fullmatch(r'[0-9a-f]{40}', producer) or release_id <= 0:
        raise ValueError('Exact producer SHA and positive release ID required')
    if not os.environ.get('GH_TOKEN'):
        raise ValueError('Explicit workflow GitHub token required for authenticated metadata provenance')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip()
    if head != producer or dirty:
        raise ValueError('Independent verifier must check out the clean exact producer')
    download_dir, registration_dir = Path(download_dir).resolve(), Path(registration_dir).resolve()
    if any(p.exists() or p.is_relative_to(REPO) for p in (download_dir, registration_dir)):
        raise ValueError('Use fresh external download and registration directories')
    endpoint = f'repos/{REPOSITORY}/releases/{release_id}'
    release = json.loads(_gh('api', endpoint)); original = snapshot(release, release_id, producer)
    download_dir.mkdir(parents=True)
    _gh('release', 'download', TAG, '--repo', REPOSITORY, '--dir', download_dir)
    if {p.name for p in download_dir.iterdir() if p.is_file()} != set(original):
        raise ValueError('Downloaded asset inventory differs')
    manifest_path = download_dir/'manifest.json'
    manifest = check_manifest(release, manifest_path, producer)
    catalogue, proof = register(manifest_path, download_dir/manifest['archive']['asset'],
        download_dir, producer, PREFIX)
    current = json.loads(_gh('api', endpoint))
    if snapshot(current, release_id, producer) != original:
        raise ValueError('Release assets changed during independent byte verification')
    # A retry after publication is read-only. No published asset or tag changes.
    if current['draft']:
        current = json.loads(_gh('api', '--method', 'PATCH', endpoint, '-F', 'draft=false'))
    if current['draft'] or snapshot(current, release_id, producer) != original:
        raise ValueError('Public release identity or immutable assets changed')
    public = verify_public(manifest_path, release_metadata=current)
    public['release_metadata_request_authorization_header_sent'] = True
    public['independent_verifier_worker'] = True
    if len(public['downloads']) != 19 or not public['every_public_asset_downloaded_and_hashed']:
        raise ValueError('All nineteen public asset downloads must pass')
    registration_dir.mkdir(parents=True)
    _write(registration_dir, CATALOG, catalogue)
    _write(registration_dir, BYTE_PROOF, proof)
    _write(registration_dir, PUBLIC_PROOF, public)
    target = registration_dir/MANIFEST; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(manifest_path.read_bytes())
    return {'release_id': release_id, 'release_tag': TAG,
        'source_commit': producer, 'public_assets_verified': 19,
        'zip_members_verified': proof['zip_members_verified'], 'registration_files': list(REGISTRATION_FILES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-id', required=True, type=int)
    parser.add_argument('--producer', required=True)
    parser.add_argument('--download-dir', required=True, type=Path)
    parser.add_argument('--registration-dir', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.release_id, args.producer, args.download_dir, args.registration_dir)))


if __name__ == '__main__':
    main()
