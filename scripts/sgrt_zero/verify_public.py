#!/usr/bin/env python3
"""Recompute a restored public bundle with its own frozen code.

Hardlinks save disk; input checksums are verified before and after execution.
Only the bundle's scientific analyses run. A second duplicate ZIP is not built.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
import sys

SOURCE_FOLDERS = [
    'inputs', 'context', 'health/public_scope_corrected',
    'health/saratov_2021_supplement', 'health/legacy_primary_child_scope_corrected',
    'education', 'commerce', 'derived_nearest', 'routes', 'routes_wb',
    'routes_yandex', 'literature/external_fua_russia', 'federal_medical',
]
RESULT_FOLDERS = [
    'hierarchy', 'upward', 'upward_extended', 'population_context_readout',
    'hierarchy_readout', 'functional_complexity',
]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def verify_and_recompute(bundle, work, output, source_commit):
    import pandas as pd
    bundle = bundle.resolve()
    work = work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError('Choose an empty verification work directory')
    work.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('An exact frozen source commit is required')
    source_checked = 0
    repository = Path(__file__).resolve().parents[2]
    for path in sorted((bundle / 'reproduction').rglob('*.py')):
        relative = path.relative_to(bundle / 'reproduction').as_posix()
        result = subprocess.run(['git', 'show', source_commit + ':' + relative],
                                cwd=repository, capture_output=True, check=True)
        if hashlib.sha256(result.stdout).hexdigest() != sha(path):
            raise ValueError('Public code differs from pinned commit: ' + relative)
        source_checked += 1
    if not source_checked:
        raise ValueError('No archived scientific source code checked')
    frozen = bundle / 'reproduction/scripts/sgrt_zero/reproduce.py'
    if not frozen.is_file():
        raise ValueError('The restored public bundle lacks frozen code')
    sys.path.insert(0, str(bundle / 'reproduction'))
    spec = importlib.util.spec_from_file_location('public_zero_reproduction', frozen)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verified_before = module.verify_bundle(bundle)
    for name in SOURCE_FOLDERS:
        source = bundle / name
        if source.exists():
            shutil.copytree(source, work / name, copy_function=os.link)
    for name in ['analysis_options.json']:
        if (bundle / name).is_file():
            shutil.copy2(bundle / name, work / name)
    (work / 'compact_prepare.json').write_text(json.dumps({
        'mode': 'public_bundle_frozen_code_analyses_with_immutable_hardlinked_inputs',
        'source_bundle_files_verified': verified_before,
        'new_directed_routing': False, 'live_API_calls': False,
        'duplicate_result_archive_built': False,
    }, indent=2) + '\n')
    module.analyses(work)
    module.check_complete(work)
    comparisons = []
    for name in RESULT_FOLDERS + ['screens_final']:
        directory = bundle / name
        for original in sorted(directory.rglob('*.parquet')):
            relative = original.relative_to(bundle)
            target = work / relative
            if not target.is_file():
                raise ValueError('Recomputed scientific table missing: ' + str(relative))
            identical_bytes = sha(original) == sha(target)
            exact = True
            if identical_bytes:
                import pyarrow.parquet as pq
                row_count = pq.ParquetFile(original).metadata.num_rows
            else:
                a, b = pd.read_parquet(original), pd.read_parquet(target)
                row_count = len(a)
                try:
                    pd.testing.assert_frame_equal(a, b, check_exact=True)
                except AssertionError:
                    exact = False
                    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-12, atol=1e-12)
                del a, b
            comparisons.append({'path': relative.as_posix(), 'rows': row_count,
                                'values_equal_exactly': exact,
                                'byte_identical': identical_bytes})
    if not comparisons:
        raise ValueError('No scientific tables compared')
    png = []
    for original in sorted((bundle / 'figures').glob('*.png')):
        target = work / 'figures' / original.name
        if not target.is_file():
            raise ValueError('Recomputed map missing: ' + original.name)
        png.append({'path': original.name, 'byte_identical': sha(original) == sha(target)})
    verified_after = module.verify_bundle(bundle)
    report = {
        'source_commit': source_commit,
        'archived_python_files_equal_pinned_git_commit': source_checked,
        'bundle_files_verified_before': verified_before,
        'bundle_files_verified_after': verified_after,
        'frozen_reproduce_sha256': sha(frozen),
        'frozen_code_executed_without_file_edits': True,
        'scientific_tables_compared': len(comparisons),
        'scientific_tables_equal_exactly': sum(r['values_equal_exactly'] for r in comparisons),
        'numeric_fallback_relative_and_absolute_tolerance': 1e-12,
        'scientific_tables_byte_identical': sum(r['byte_identical'] for r in comparisons),
        'maps_compared': len(png),
        'maps_byte_identical': sum(r['byte_identical'] for r in png),
        'new_routing_or_live_APIs': False,
        'input_files_unchanged': verified_before == verified_after,
        'tables': comparisons, 'maps': png,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'tables', 'maps'}}, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    verify_and_recompute(args.bundle, args.workdir, args.output, args.source_commit)


if __name__ == '__main__':
    main()
