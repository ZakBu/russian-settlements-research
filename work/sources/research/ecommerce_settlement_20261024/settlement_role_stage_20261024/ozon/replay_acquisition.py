"""Verify cached acquisitions; optionally replay only successful fixed archive captures.

python3 replay_acquisition.py --download-archives saves replay bodies separately and
checks exact hashes. It never overwrites the original accepted source bodies.
"""
from pathlib import Path
import argparse,hashlib,json
from fetch import fetch

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--download-archives',action='store_true')
args=parser.parse_args()
receipts=json.loads((ROOT/'query_manifest.json').read_text())['requests_and_saved_responses']
checked=0;replayed=0
for receipt in receipts:
    body=(ROOT/receipt['body']).read_bytes()
    assert hashlib.sha256(body).hexdigest()==receipt['sha256']
    checked+=1
    if args.download_archives and receipt.get('status')==200 and '/web/'in receipt['url']:
        data,meta=fetch('replay_'+Path(receipt['body']).name,receipt['url'],timeout=40)
        assert meta.get('status')==200
        assert hashlib.sha256(data).hexdigest()==receipt['sha256'],receipt['url']
        replayed+=1
print('PASS:',checked,'cached receipts verified;',replayed,'fixed archive bodies replayed.')
