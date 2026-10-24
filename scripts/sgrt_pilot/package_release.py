#!/usr/bin/env python3
"""Build a companion catalogue and ZIP compatible with research_data.py.

Files below payload_root retain their relative paths. No upload or overwrite of
an existing release is performed. Main population catalogue is not replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def package(payload_root, output, tag, source_commit):
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'sgrt-pilot-data.zip'
    if archive.exists():
        raise ValueError('Archive already exists; choose a new output directory')
    rows, objects = [], {}
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(payload_root.rglob('*')):
            if not path.is_file():
                continue
            if path.is_symlink():
                raise ValueError('Symlink not allowed in portable release')
            size = path.stat().st_size
            h = hashlib.sha1(b'blob ' + str(size).encode() + b'\0')
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    h.update(block)
            blob = h.hexdigest()
            rel = path.relative_to(payload_root).as_posix()
            rows.append({'path': rel, 'blob': blob, 'bytes': size,
                         'profiles': ['core', 'all'], 'asset': archive.name})
            if blob in objects:
                objects[blob]['paths'].append(rel)
                continue
            sha = digest(path)
            obj = {'blob': blob, 'sha256': sha, 'bytes': size, 'asset': archive.name,
                   'paths': [rel], 'source_path': rel}
            if path.suffix == '.parquet':
                import pyarrow.parquet as pq
                metadata = pq.ParquetFile(path)
                obj['rows'] = metadata.metadata.num_rows
                obj['fields'] = [{'name': f.name, 'type': str(f.type)} for f in metadata.schema_arrow]
            objects[blob] = obj
            z.write(path, 'objects/' + blob)
    cat = {'schema': 'sgrt.portable_data.v1', 'status': 'verified_complete',
           'source_commit': source_commit, 'release_tag': tag,
           'repository': 'ZakBu/russian-settlements-research',
           'scientific_scope': 'Dated incomplete functional pilot scenarios and source audits; not accepted multilevel nationwide SGRT. Companion catalogue only; default population catalogue unchanged.',
           'profiles': {'core': 'All files of this explicitly selected pilot companion catalogue', 'all': 'Same pilot files'},
           'files': rows, 'objects': objects,
           'assets': [{'asset': archive.name, 'status': 'verified', 'bytes': archive.stat().st_size,
                       'sha256': digest(archive), 'objects': list(objects),
                       'url': f'https://github.com/ZakBu/russian-settlements-research/releases/download/{tag}/{archive.name}'}],
           'counts': {'files': len(rows), 'unique_objects': len(objects),
                      'logical_bytes': sum(r['bytes'] for r in rows)}}
    target = output / 'pilot_catalog.json'
    target.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'catalog': str(target), 'archive': str(archive), 'counts': cat['counts'],
                      'archive_bytes': archive.stat().st_size, 'archive_sha256': cat['assets'][0]['sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--payload-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--tag', required=True)
    p.add_argument('--source-commit', required=True)
    a = p.parse_args()
    package(a.payload_root, a.output, a.tag, a.source_commit)
