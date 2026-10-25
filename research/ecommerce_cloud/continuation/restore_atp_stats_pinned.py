"""Restore the six verified run inventories without downloading object bodies."""
from pathlib import Path
import hashlib
import json
from acquire_atp_historical import Fetcher
ROOT=Path(__file__).resolve().parents[3]
out=ROOT/'work/ecommerce_atp_history';out.mkdir(parents=True,exist_ok=True)
records=json.loads((ROOT/'research/ecommerce_cloud/continuation/atp_pinned_manifest.json').read_text())['records']
fetch=Fetcher(out,180)
for row in records:
    body,_=fetch.get(row['stats_url'],12*1024*1024)
    assert hashlib.sha256(body).hexdigest()==row['stats_sha256']
    (out/(row['run_id']+'_pinned_runwide_stats.json')).write_bytes(body)
print('Six pinned run inventories verified.')
