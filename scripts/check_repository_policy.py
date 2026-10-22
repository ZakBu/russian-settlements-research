#!/usr/bin/env python3
"""Check the current Git tree against repository_policy.json (sizes and file types)."""
import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath


def tree_entries(ref):
    data = subprocess.check_output(['git', 'ls-tree', '-r', '-l', '-z', ref])
    for item in data.split(b'\0'):
        if item:
            meta, path = item.split(b'\t', 1)
            mode, kind, _, size = meta.split()
            yield path.decode(), kind.decode(), mode.decode(), 0 if size == b'-' else int(size)


def check(entries, policy):
    errors, total, present = [], 0, set()
    forbidden = set(policy['forbidden_extensions'])
    for path, kind, mode, size in entries:
        present.add(path)
        total += size
        if kind != 'blob':
            errors.append({'path': path, 'reason': 'submodules_not_allowed'})
            continue
        if PurePosixPath(path).suffix.lower() in forbidden and path not in policy['allowed_exceptions']:
            errors.append({'path': path, 'reason': 'binary_or_data_file_belongs_in_releases'})
        limit = policy['file_size_overrides'].get(path, policy['max_file_bytes'])
        if size > limit:
            errors.append({'path': path, 'reason': 'file_too_large', 'bytes': size, 'limit': limit})
    for path in policy['required_paths']:
        if path not in present:
            errors.append({'path': path, 'reason': 'required_file_missing'})
    if total > policy['max_tree_bytes']:
        errors.append({'reason': 'tree_too_large', 'bytes': total})
    return {'ok': not errors, 'files': len(present), 'bytes': total, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', default='repository_policy.json')
    parser.add_argument('--ref', default='HEAD')
    args = parser.parse_args()
    policy = json.loads(Path(args.policy).read_text())
    result = check(tree_entries(args.ref), policy)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
