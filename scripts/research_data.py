#!/usr/bin/env python3
"""List, fetch and verify catalogued research data without rerunning scientific models."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import urllib.request
import zipfile


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def destination(root, relative):
    name = PurePosixPath(relative)
    if name.is_absolute() or '..' in name.parts:
        raise ValueError('Unsafe catalog path: ' + relative)
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Catalog path escapes destination: ' + relative)
    return target


def download(url, path, expected):
    if path.exists() and sha256(path) == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'sgrt-research-data/1'})
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, 'wb') as out:
        shutil.copyfileobj(response, out, 4 * 1024 * 1024)
    if sha256(partial) != expected:
        raise ValueError('Archive checksum mismatch: ' + path.name)
    partial.replace(path)


def load_catalog(path):
    cat = json.loads(path.read_text())
    if cat.get('schema') != 'sgrt.portable_data.v1':
        raise ValueError('Unsupported catalog schema')
    return cat


def selected_files(cat, profile):
    return [row for row in cat['files'] if profile in row['profiles']]


def verify_file(path, row, obj):
    if not path.is_file() or path.stat().st_size != row['bytes']:
        return False
    expected = obj.get('sha256') or row.get('sha256')
    if expected:
        return sha256(path) == expected
    # Git-blob SHA-1 is always available, including for files retained directly in Git.
    h = hashlib.sha1(b'blob ' + str(row['bytes']).encode() + b'\0')
    with open(path, 'rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            h.update(block)
    return h.hexdigest() == row['blob']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'fetch', 'verify'])
    parser.add_argument('--catalog', type=Path, default=Path('data/catalog.json'))
    parser.add_argument('--profile', choices=['core', 'current', 'all'], default='core')
    parser.add_argument('--dest', type=Path, default=Path('.'))
    parser.add_argument('--cache', type=Path, default=Path('.research-cache'))
    args = parser.parse_args()
    cat = load_catalog(args.catalog)
    rows = selected_files(cat, args.profile)
    objects = cat['objects']
    selected = {row['blob'] for row in rows}
    needed_assets = {objects[blob]['asset'] for blob in selected if objects[blob].get('asset')}
    assets = {row['asset']: row for row in cat['assets']}
    print(json.dumps({'profile': args.profile, 'files': len(rows),
                      'unique_objects': len(selected),
                      'logical_bytes': sum(row['bytes'] for row in rows),
                      'download_bytes': sum(assets[name].get('bytes', 0) for name in needed_assets),
                      'catalog_status': cat['status']}, ensure_ascii=False), flush=True)
    if args.command == 'list':
        return 0
    args.dest.mkdir(parents=True, exist_ok=True)
    if args.command == 'fetch':
        for name in sorted(needed_assets):
            asset = assets[name]
            if asset['status'] != 'verified':
                raise ValueError('Asset is not yet verified: ' + name)
            archive = args.cache / name
            print('Fetching verified archive: ' + name, flush=True)
            download(asset['url'], archive, asset['sha256'])
            with zipfile.ZipFile(archive) as z:
                for blob in selected.intersection(asset['objects']):
                    obj = objects[blob]
                    local = args.cache / 'objects' / blob
                    if not local.exists() or sha256(local) != obj['sha256']:
                        local.parent.mkdir(parents=True, exist_ok=True)
                        temporary = local.with_name(blob + '.part')
                        with z.open('objects/' + blob) as src, open(temporary, 'wb') as out:
                            shutil.copyfileobj(src, out, 4 * 1024 * 1024)
                        if temporary.stat().st_size != obj['bytes'] or sha256(temporary) != obj['sha256']:
                            raise ValueError('Data object checksum mismatch: ' + blob)
                        temporary.replace(local)
        for row in rows:
            obj = objects[row['blob']]
            target = destination(args.dest, row['path'])
            if target.exists():
                if verify_file(target, row, obj):
                    continue
                raise ValueError('Existing file differs; preserve and inspect it: ' + row['path'])
            if not obj.get('asset'):
                raise ValueError('File is supplied by Git but absent in destination: ' + row['path'])
            source = args.cache / 'objects' / row['blob']
            target.parent.mkdir(parents=True, exist_ok=True)
            # Copy aliases: later edits to one historical path must not mutate another path.
            shutil.copyfile(source, target)
    failures = [row['path'] for row in rows
                if not verify_file(destination(args.dest, row['path']), row, objects[row['blob']])]
    print(json.dumps({'verified_files': len(rows) - len(failures), 'failed_files': failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
