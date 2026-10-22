#!/usr/bin/env python3
"""List, fetch and verify catalogued research data without rerunning scientific models."""
import argparse
import fnmatch
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


def copy_verified(source, target, row, obj):
    """A failed copy must not turn a partial file into an apparently existing dataset."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.sgrt-part')
    shutil.copyfile(source, temporary)
    if not verify_file(temporary, row, obj):
        raise ValueError('Copied data checksum mismatch: ' + row['path'])
    if target.exists():
        if verify_file(target, row, obj):
            temporary.unlink()
            return
        raise ValueError('Destination changed during copy: ' + row['path'])
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'fetch', 'verify'])
    parser.add_argument('--catalog', type=Path, default=Path('data/catalog.json'))
    parser.add_argument('--profile', choices=['core', 'current', 'all'], default='core')
    parser.add_argument('--dest', type=Path, default=Path('.'))
    parser.add_argument('--cache', type=Path, default=Path('.research-cache'))
    parser.add_argument('--keep-archives', action='store_true', help='Retain verified ZIP downloads; default materializes one archive at a time and removes its cache')
    parser.add_argument('--match', action='append', default=[], help='Glob over original paths; repeated patterns are OR-combined')
    parser.add_argument('--show-files', action='store_true', help='List matching paths with row/schema metadata')
    parser.add_argument('--show-schema', action='store_true', help='Print unique Parquet schemas for selected paths')
    args = parser.parse_args()
    cat = load_catalog(args.catalog)
    rows = selected_files(cat, args.profile)
    if args.match:
        rows = [r for r in rows if any(fnmatch.fnmatchcase(r['path'], pattern) for pattern in args.match)]
        if not rows:
            parser.error('No catalogued data paths match the requested patterns')
    objects = cat['objects']
    selected = {row['blob'] for row in rows}
    needed_assets = {objects[blob]['asset'] for blob in selected if objects[blob].get('asset')}
    assets = {row['asset']: row for row in cat['assets']}
    print(json.dumps({'profile': args.profile, 'files': len(rows),
                      'unique_objects': len(selected),
                      'logical_bytes': sum(row['bytes'] for row in rows),
                      'download_bytes': sum(assets[name]['bytes'] for name in needed_assets) if all('bytes' in assets[name] for name in needed_assets) else None,
                      'planned_uncompressed_asset_bytes': sum(assets[name].get('uncompressed_bytes', assets[name].get('bytes', 0)) for name in needed_assets),
                      'catalog_status': cat['status']}, ensure_ascii=False), flush=True)
    if args.command == 'list':
        if args.show_files:
            for row in rows:
                obj = objects[row['blob']]
                print(json.dumps({'path': row['path'], 'kind': row.get('kind', 'data'), 'usable_as_table': row.get('usable_as_table'), 'source_provenance': row.get('source_provenance'), 'bytes': row['bytes'], 'rows': obj.get('rows'), 'schema_id': obj.get('schema_id'), 'asset': obj.get('asset'), 'supplied_by_git': not bool(obj.get('asset'))}, ensure_ascii=False))
        if args.show_schema:
            schema_ids = {objects[r['blob']].get('schema_id') for r in rows} - {None}
            for schema_id in sorted(schema_ids):
                print(json.dumps({'schema_id': schema_id, 'schema': cat.get('schemas', {}).get(schema_id)}, ensure_ascii=False))
        return 0
    args.dest.mkdir(parents=True, exist_ok=True)
    if args.command == 'fetch':
        by_blob = {}
        for row in rows:
            by_blob.setdefault(row['blob'], []).append(row)
            target = destination(args.dest, row['path'])
            if target.exists() and not verify_file(target, row, objects[row['blob']]):
                raise ValueError('Existing file differs; preserve and inspect it: ' + row['path'])
        for name in sorted(needed_assets):
            asset = assets[name]
            if asset['status'] != 'verified':
                raise ValueError('Asset is not yet verified: ' + name)
            relevant = selected.intersection(asset['objects'])
            pending = {blob for blob in relevant if any(not destination(args.dest, r['path']).exists() for r in by_blob[blob])}
            if not pending:
                continue
            archive = args.cache / name
            print('Fetching verified archive: ' + name, flush=True)
            download(asset['url'], archive, asset['sha256'])
            with zipfile.ZipFile(archive) as z:
                for blob in sorted(pending):
                    obj = objects[blob]
                    local = args.cache / 'objects' / blob
                    local.parent.mkdir(parents=True, exist_ok=True)
                    temporary = local.with_name(blob + '.part')
                    with z.open('objects/' + blob) as src, open(temporary, 'wb') as out:
                        shutil.copyfileobj(src, out, 4 * 1024 * 1024)
                    if temporary.stat().st_size != obj['bytes'] or sha256(temporary) != obj['sha256']:
                        raise ValueError('Data object checksum mismatch: ' + blob)
                    temporary.replace(local)
                    for row in by_blob[blob]:
                        target = destination(args.dest, row['path'])
                        if not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            # Independent copies prevent one edited historical alias mutating another.
                            copy_verified(local, target, row, obj)
                    local.unlink()
            if not args.keep_archives:
                archive.unlink()
        for row in rows:
            if objects[row['blob']].get('asset'):
                continue
            target = destination(args.dest, row['path'])
            if target.exists():
                continue
            source = destination(Path(__file__).resolve().parents[1], row['path'])
            if not verify_file(source, row, objects[row['blob']]):
                raise ValueError('File supplied by Git is absent or changed: ' + row['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_verified(source, target, row, objects[row['blob']])
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
