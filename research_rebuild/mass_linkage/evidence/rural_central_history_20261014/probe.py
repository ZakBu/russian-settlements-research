"""Recheck retained central-rural sources without weakening HTTPS validation.

Usage: python probe.py --output /workspace/shared/rural_central_history/recheck
Original downloaded bytes are immutable; a recheck writes a fresh directory.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(Path(__file__).with_name('asset_manifest.json').read_text())

    def fetch(row):
        request = urllib.request.Request(row['url'], headers={
            'User-Agent': 'RussianSettlementsResearch/1.0 (https://github.com/ZakBu/russian-settlements-research)'})
        result = {'url': row['url'], 'key': row['key']}
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                target = row['key'] + '.bin'
                (output / target).write_bytes(data)
                result.update(status=response.status, final_url=response.url,
                              sha256=hashlib.sha256(data).hexdigest(),
                              bytes=len(data), file=target)
        except Exception as error:
            result['error'] = str(error)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(fetch, manifest))
    (output / 'receipt.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
