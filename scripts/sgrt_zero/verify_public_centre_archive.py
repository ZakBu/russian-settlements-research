"""Verify a centre-release ZIP by streaming; retain only small result evidence.

Usage: python scripts/sgrt_zero/verify_public_centre_archive.py MANIFEST_JSON OUTPUT_DIR
The manifest is the separately downloaded release asset, not a research_data catalog.
"""
import hashlib, json, struct, sys, urllib.request, zlib
from pathlib import Path

manifest_path, output_dir = map(Path, sys.argv[1:3])
m=json.loads(manifest_path.read_text()); output_dir.mkdir(parents=True,exist_ok=True)
url='https://github.com/ZakBu/russian-settlements-research/releases/download/'+m['release_tag']+'/'+m['archive']['asset']
archive_hash=hashlib.sha256(); total=0
with urllib.request.urlopen(url,timeout=120) as response:
    def read(n):
        global total
        data=response.read(n);archive_hash.update(data);total+=len(data)
        return data
    def exact(n):
        data=b''
        while len(data)<n:
            more=read(n-len(data))
            if not more: raise ValueError('Truncated archive')
            data+=more
        return data
    seen={}; prefix='sgrt/centre20261025/'
    while True:
        signature=exact(4)
        if signature!=b'PK\x03\x04':
            while read(1024*1024):pass
            break
        version,flags,method,tm,dt,crc,compressed,uncompressed,nlen,xlen=struct.unpack('<HHHHHIIIHH',exact(26))
        name=exact(nlen).decode('utf-8' if flags&2048 else 'cp437');exact(xlen)
        if flags&8 or method not in (0,8) or not name.startswith(prefix):raise ValueError('Unexpected ZIP encoding: '+name)
        relative=name[len(prefix):]
        decoder=zlib.decompressobj(-15) if method==8 else None
        digest=hashlib.sha256();actual_crc=0;size=0
        capture=relative.startswith('analysis/figures/') and relative.endswith('.png') or relative in {
            'analysis/readout.json','analysis/independent_subset_check.json','analysis/independent_tail_audit.json',
            'analysis/cloud_scientific_control.json','analysis/immutable_inputs_check.json','analysis/checked_model_centres.csv',
            'routes/independent_forward_checks.json','manifest.json'}
        contents=bytearray() if capture else None
        remaining=compressed
        while remaining:
            block=exact(min(262144,remaining));remaining-=len(block)
            decoded=decoder.decompress(block) if decoder else block
            digest.update(decoded);actual_crc=zlib.crc32(decoded,actual_crc);size+=len(decoded)
            if capture:contents.extend(decoded)
        if decoder:
            tail=decoder.flush();digest.update(tail);actual_crc=zlib.crc32(tail,actual_crc);size+=len(tail)
            if capture:contents.extend(tail)
            if not decoder.eof:raise ValueError('Incomplete deflate stream: '+relative)
        if size!=uncompressed or actual_crc!=crc:raise ValueError('CRC/length mismatch: '+relative)
        actual={'bytes':size,'sha256':digest.hexdigest()}
        if relative=='manifest.json':
            internal=json.loads(contents)
            for key in ('files','source_commit','release_tag'):
                if internal[key]!=m[key]:raise ValueError('Internal/external manifest mismatch: '+key)
        else:
            if actual!=m['files'].get(relative):raise ValueError('Manifest mismatch: '+relative)
            seen[relative]=actual
        if capture:
            target=output_dir/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(contents)
    if set(seen)!=set(m['files']):raise ValueError('Manifest members missing')
    if total!=m['archive']['bytes'] or archive_hash.hexdigest()!=m['archive']['sha256']:raise ValueError('Archive hash mismatch')
result={'release_tag':m['release_tag'],'source_commit':m['source_commit'],'archive_bytes':total,
        'archive_sha256':archive_hash.hexdigest(),'all_member_hashes_and_crcs_verified':len(seen),
        'large_zip_retained_locally':False}
(output_dir/'public_download_verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
