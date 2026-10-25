"""Replay seven pinned Wayback acquisitions; default verifies cached source bodies.

python3 acquire_history.py              # local cache check
python3 acquire_history.py --download   # refetch pinned historical archive URLs
Then run verify_history.py with the documented PyArrow environment.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--download', action='store_true')
args = parser.parse_args()
manifest = json.loads((ROOT/'acquisition_manifest.json').read_text())
for record in manifest['historical_snapshots']:
    decoded = ROOT/record['decoded_json']
    compressed = decoded.with_suffix('.responsebody.gz')
    if args.download:
        req=urllib.request.Request(record['archive_url'],headers={'User-Agent':'settlement-research'})
        with urllib.request.urlopen(req,timeout=45) as response:
            body=response.read(40000001)
            assert len(body)<=40000000
            assert response.url==record['archive_url'], 'Archive replay changed capture; investigate before reuse'
        assert hashlib.sha256(body).hexdigest()==record['raw_response_sha256']
        compressed.write_bytes(body)
        decoded.write_bytes(gzip.decompress(body))
    assert hashlib.sha256(compressed.read_bytes()).hexdigest()==record['raw_response_sha256']
    assert hashlib.sha256(decoded.read_bytes()).hexdigest()==record['decoded_sha256']
print('PASS: all seven raw and decoded historical bodies match pinned SHA256.')
