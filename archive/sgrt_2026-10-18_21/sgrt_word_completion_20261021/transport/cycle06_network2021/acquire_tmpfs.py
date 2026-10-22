#!/usr/bin/env python3
"""Restore exact historical bytes to bounded tmpfs, never the workspace disk."""
from pathlib import Path
import hashlib,json,os,shutil,time,requests
H=Path(__file__).resolve().parent
DEST=Path('/tmp/sgrt_network2021/russia-210101.osm.pbf')
URL='https://download.geofabrik.de/russia-210101.osm.pbf'
SIZE=2969339717
SHA='1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe'
def main():
    DEST.parent.mkdir(exist_ok=True)
    assert not DEST.exists()
    assert shutil.disk_usage('/tmp').free>SIZE+1_000_000_000
    available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
    assert available>SIZE+5_000_000_000
    assert os.stat('/tmp').st_dev!=os.stat('/workspace').st_dev
    temp=DEST.with_suffix('.partial');h=hashlib.sha256();n=0;start=time.monotonic()
    with requests.get(URL,stream=True,timeout=(30,90)) as response:
        response.raise_for_status();assert response.status_code==200
        with temp.open('wb') as stream:
            for block in response.iter_content(8*1024*1024):
                stream.write(block);h.update(block);n+=len(block)
                if n//268435456!=(n-len(block))//268435456:print(n,SIZE,flush=True)
    receipt=dict(status='DOWNLOADED_TMPFS_EXACT_SOURCE',url=URL,path=str(DEST),actual_bytes=n,expected_bytes=SIZE,
        actual_sha256=h.hexdigest(),expected_sha256=SHA,seconds=round(time.monotonic()-start,3),
        storage='separate /tmp tmpfs; no workspace disk source copy',available_memory_before_bytes=available,
        complete_original_bytes_verified=n==SIZE and h.hexdigest()==SHA)
    (H/'tmpfs_acquisition_receipt.json').write_text(json.dumps(receipt,indent=2))
    assert receipt['complete_original_bytes_verified']
    temp.replace(DEST);print(json.dumps(receipt,indent=2),flush=True)
if __name__=='__main__':main()
