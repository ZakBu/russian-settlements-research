#!/usr/bin/env python3
"""Restore pinned public research PDFs locally; never republish their contents.

python research/ecommerce_cloud/dependency_20261026/fetch_behaviour_sources.py
Optional --extract invokes installed pdftotext for local reading only.
Values in behaviour_series.csv were transcribed and visually checked in source
figures, not estimated from microdata by this program.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT = ROOT / 'work/sources/research/ecommerce_settlement_20261024/dependency_20261026'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--extract', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sources = json.loads((HERE / 'behaviour_sources.json').read_text())
    for source in sources:
        dest = args.output / source['filename']
        if dest.exists():
            body = dest.read_bytes()
        else:
            request = Request(source['url'], headers={'User-Agent': 'settlement-research/20261026'})
            with urlopen(request, timeout=60) as response:
                body = response.read(20 * 1024 * 1024 + 1)
        if len(body) != source['bytes'] or hashlib.sha256(body).hexdigest() != source['sha256']:
            raise ValueError('Pinned source mismatch; existing file preserved: ' + source['source_id'])
        if not body.startswith(b'%PDF'):
            raise ValueError('Not a PDF: ' + source['source_id'])
        if not dest.exists():
            dest.write_bytes(body)
        if args.extract:
            subprocess.run(['pdftotext', '-layout', str(dest), str(dest.with_suffix('.txt'))], check=True)
        print(json.dumps({'source': source['source_id'], 'bytes': len(body), 'sha256_matches': True}))

if __name__ == '__main__':
    main()
