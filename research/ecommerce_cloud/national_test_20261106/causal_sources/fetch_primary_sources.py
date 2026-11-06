#!/usr/bin/env python3
"""Restore pinned primary sources; source bodies remain in ignored work/."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'AGENTS.md').exists())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', action='store_true', help='Also fetch mutable HTML; a changed revision fails SHA verification.')
    args = parser.parse_args()
    sources = json.loads((HERE / 'sources.json').read_text())
    for source in sources:
        if not source.get('sha256') or not source.get('raw_path'):
            continue
        path = ROOT / source['raw_path']
        if path.suffix == '.json' or (path.suffix == '.html' and not args.html):
            continue
        if not path.exists():
            request = urllib.request.Request(source['url'], headers={'User-Agent': 'ecommerce-research-source-verification/1.0'})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            digest = hashlib.sha256(payload).hexdigest()
            if digest != source['sha256']:
                raise RuntimeError(f"Source changed: {source['source_id']}: expected {source['sha256']}, received {digest}; original pin preserved")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != source['sha256']:
            raise RuntimeError(f'Cached source checksum differs: {path}')
        if path.suffix == '.pdf':
            subprocess.run(['pdftotext', '-layout', str(path), str(path.with_suffix('.txt'))], check=True)
        print(f"Verified {source['source_id']} {path.stat().st_size} bytes")


if __name__ == '__main__':
    main()
