#!/usr/bin/env python3
"""Send catalogue-pinned bytes to a task-owned GitHub Actions artifact blob.

The short-lived upload ticket is read only from the control artifact of the
specified run. No GitHub/runtime token is extracted or sent to blob storage.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import zipfile

CHUNK = 8 * 1024 * 1024


def send(control_zip, archive, catalog_path, run_id):
    with zipfile.ZipFile(control_zip) as z:
        members = [n for n in z.namelist() if n.endswith('transfer.json')]
        if len(members) != 1:
            raise ValueError('Unexpected control artifact')
        control = json.loads(z.read(members[0]))
    catalog = json.loads(catalog_path.read_text())
    asset = catalog['assets'][0]
    if control['repository'] != catalog['repository'] or str(control['runId']) != str(run_id):
        raise ValueError('Control artifact belongs to another task')
    if control['name'] != 'sgrt-pilot-payload' or control['sha256'] != asset['sha256'] or int(control['size']) != asset['bytes']:
        raise ValueError('Control artifact does not match pinned catalogue')
    if archive.stat().st_size != asset['bytes']:
        raise ValueError('Archive size mismatch')
    h = hashlib.sha256()
    with archive.open('rb') as stream:
        while block := stream.read(4*1024*1024): h.update(block)
    if h.hexdigest() != asset['sha256']:
        raise ValueError('Archive digest mismatch')
    capability = control['signedUploadUrl']
    url = urllib.parse.urlsplit(capability)
    if url.scheme != 'https' or not url.hostname.endswith('.blob.core.windows.net') or url.username or url.password:
        raise ValueError('Unexpected task artifact storage host')
    if 'sig' not in urllib.parse.parse_qs(url.query):
        raise ValueError('Missing task upload signature')
    ids = [base64.b64encode(f'{i:08d}'.encode()).decode() for i in range((asset['bytes'] + CHUNK - 1)//CHUNK)]

    def put(index):
        with archive.open('rb') as stream:
            stream.seek(index*CHUNK);data=stream.read(CHUNK)
        target=capability+'&'+urllib.parse.urlencode({'comp':'block','blockid':ids[index]})
        headers={'x-ms-version':'2023-11-03','Content-Type':'application/octet-stream','Content-Length':str(len(data))}
        request=urllib.request.Request(target,data=data,method='PUT',headers=headers)
        with urllib.request.urlopen(request,timeout=180) as response:
            if response.status != 201: raise ValueError('Block upload rejected')
        return len(data)

    done=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(put,i) for i in range(len(ids))]
        for number,future in enumerate(as_completed(futures),1):
            done+=future.result()
            if number%16==0 or number==len(ids):print(f'Uploaded {number}/{len(ids)} blocks ({done} bytes)',flush=True)
    xml=('<BlockList>'+''.join('<Latest>'+value+'</Latest>' for value in ids)+'</BlockList>').encode()
    request=urllib.request.Request(capability+'&comp=blocklist',data=xml,method='PUT',headers={
        'x-ms-version':'2023-11-03','x-ms-blob-content-type':'application/zip',
        'Content-Type':'application/xml','Content-Length':str(len(xml))})
    with urllib.request.urlopen(request,timeout=180) as response:
        if response.status!=201:raise ValueError('Block-list commit rejected')
    print(json.dumps({'uploaded_bytes':done,'sha256':asset['sha256'],'runner_readback_required':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--control',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--catalog',type=Path,required=True)
    p.add_argument('--run-id',required=True)
    a=p.parse_args()
    try:send(a.control,a.archive,a.catalog,a.run_id)
    except Exception as error:
        # URLs contain task-scoped write capabilities and must never be logged.
        print('Upload failed: '+type(error).__name__+' HTTP='+str(getattr(error,'code','n/a')),file=sys.stderr)
        raise SystemExit(1)
