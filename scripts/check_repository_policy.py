#!/usr/bin/env python3
"""Check the current Git tree, not the size of remote historical objects."""
import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import PurePosixPath, Path


def allowed(path, policy):
    p = PurePosixPath(path)
    return (
        path in policy.get('_protected_context_paths', policy.get('protected_context_paths', []))
        or p.suffix in policy.get('context_extensions', [])
        or path in policy['exact_paths']
        or p.name in policy['instruction_or_license_names']
        or p.suffix in policy['code_extensions']
        or p.suffix in policy['configuration_extensions']
        or (p.name.startswith('requirements') and p.suffix == '.txt')
        or (p.suffix == '.json' and (
            'config' in p.name.lower()
            or any(x in {'config', 'configs'} for x in p.parts[:-1])
            or p.name in {'package.json', 'package-lock.json', 'tsconfig.json'}))
        or (p.suffix == '.html' and 'templates' in p.parts[:-1])
        or (path.startswith('references/') and p.suffix in {'.json', '.csv', '.bib'})
    )


def check(entries, policy):
    errors = []
    protected = set(policy.get('protected_context_paths', []))
    policy = {**policy, '_protected_context_paths': protected}
    present = {entry['path'] for entry in entries}
    for path in sorted(protected - present):
        errors.append({'path': path, 'reason': 'protected_research_context_missing'})
    total = 0
    for entry in entries:
        path, size = entry['path'], entry.get('size', 0)
        total += size
        if not allowed(path, policy):
            errors.append({'path': path, 'reason': 'path_not_allowed'})
        limit = policy.get('protected_context_max_file_bytes', policy['max_file_bytes']) if path in protected else policy['max_file_bytes']
        limit = policy.get('file_size_overrides', {}).get(path, limit)
        if size > limit:
            errors.append({'path': path, 'reason': 'file_too_large', 'bytes': size})
    if total > policy['max_snapshot_bytes']:
        errors.append({'reason': 'snapshot_too_large', 'bytes': total})
    return {'ok': not errors, 'scope': 'current_tree_only', 'files': len(entries),
            'bytes': total, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree-json', help='GitHub recursive tree response')
    parser.add_argument('--policy', default='repository_policy.json')
    parser.add_argument('--ref', default='HEAD')
    args = parser.parse_args()
    policy = json.loads(Path(args.policy).read_text())
    if args.tree_json:
        tree = json.loads(Path(args.tree_json).read_text())
        if tree.get('truncated'):
            parser.error('A truncated tree cannot establish compliance')
        entries = [x for x in tree['tree'] if x['type'] == 'blob']
        if any(x['type'] == 'commit' for x in tree['tree']):
            parser.error('Submodules require an explicit policy')
    else:
        data = subprocess.check_output(['git', 'ls-tree', '-r', '-l', '-z', args.ref])
        entries = []
        for item in data.split(b'\0'):
            if not item:
                continue
            meta, path = item.split(b'\t', 1)
            mode, kind, sha, size = meta.split()
            if kind != b'blob':
                parser.error('Only regular source files are allowed')
            entries.append({'path': path.decode(), 'size': int(size)})
    result = check(entries, policy)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
