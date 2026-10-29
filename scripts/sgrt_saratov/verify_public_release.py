"""Download and hash every public release asset without an Authorization header."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

REPOSITORY = 'ZakBu/russian-settlements-research'


def request(url):
    return Request(url, headers={'User-Agent': 'sgrt-public-release-verification',
                                'Accept-Encoding': 'identity'})


def verify_public(manifest_path, workers=4):
    path = Path(manifest_path)
    raw = path.read_bytes()
    manifest = json.loads(raw)
    tag = manifest['release_tag']
    if not re.fullmatch(r'[A-Za-z0-9._-]+', tag):
        raise ValueError('Expected a single release-tag component')
    api = 'https://api.github.com/repos/'+REPOSITORY+'/releases/tags/'+quote(tag)
    with urlopen(request(api), timeout=60) as response:
        release = json.load(response)
    if release['draft'] or release['target_commitish'] != manifest['source_commit']:
        raise ValueError('Public release or committed source differs')
    expected = {manifest['archive']['asset']: manifest['archive'],
                **manifest['standalone_assets'],
                'manifest.json': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
    actual = {row['name']: row for row in release['assets']}
    if set(actual) != set(expected):
        raise ValueError('Public release asset inventory differs')

    def download(item):
        name, spec = item
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Expected a single asset filename')
        row = actual[name]
        if row['size'] != spec['bytes'] or row.get('digest') != 'sha256:'+spec['sha256']:
            raise ValueError('Public asset metadata differs: '+name)
        url = 'https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'+quote(name)
        digest = hashlib.sha256(); count = 0
        with urlopen(request(url), timeout=60) as response:
            status = response.status
            resolved_host = urlsplit(response.url).hostname
            while chunk := response.read(4*1024*1024):
                count += len(chunk)
                if count > spec['bytes']:
                    raise ValueError('Public asset exceeds pinned size: '+name)
                digest.update(chunk)
        if status != 200 or count != spec['bytes'] or digest.hexdigest() != spec['sha256']:
            raise ValueError('Public asset download differs: '+name)
        return name, {'url': url, 'http_status': status, 'bytes': count,
                      'sha256': digest.hexdigest(), 'resolved_host': resolved_host,
                      'authorization_header_sent': False}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        downloads = dict(pool.map(download, sorted(expected.items())))
    return {'schema': 'sgrt.saratov.public_download_verification.v1',
            'release_tag': tag, 'source_commit': manifest['source_commit'],
            'computation_source_commit': manifest.get('computation_source_commit', manifest['source_commit']),
            'release_is_public': True, 'every_public_asset_downloaded_and_hashed': True,
            'downloads': downloads}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    proof = verify_public(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'public_assets_downloaded_and_hashed': len(proof['downloads']),
                      'bytes': sum(r['bytes'] for r in proof['downloads'].values())}))


if __name__ == '__main__':
    main()
