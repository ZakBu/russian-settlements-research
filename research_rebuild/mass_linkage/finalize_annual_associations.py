"""Finalize reviewed source-series associations, without admitting place continuity.

Also correct keyed-reference line locators from the frozen Lua bytes. Original
reviewed inputs remain immutable; population assertions are compared literally.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from .annual_module_recovery import recover_module

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()

def finalize(staged, review, raw_dir, output):
    decision = json.loads(Path(review).read_text())
    if decision['review_status'] != 'conditional_acceptance_with_explicit_source_quality_limits':
        raise ValueError('Unexpected review status')
    if sha(staged) != decision['reviewed_inputs']['staged_annual_module_series_sha256']:
        raise ValueError('Reviewed staging hash mismatch')
    output = Path(output)
    if output.exists():
        raise ValueError('Output must be a new immutable directory')
    source = pd.read_parquet(staged)
    raw_rows = []
    for path in sorted(Path(raw_dir).glob('*.lua.gz')):
        if not path.name.startswith('._'):
            raw_rows.extend(recover_module(path)[0])
    raw = pd.DataFrame(raw_rows)
    keys = ['module_code', 'module_key_raw', 'module_locator', 'module_sha256']
    if raw.duplicated(keys).any():
        raise ValueError('Raw locator collision')
    linked = source.merge(raw[keys + ['observation_year', 'population_value_raw',
                                     'source_key_raw', 'source_text_raw', 'source_locator']],
                          on=keys, how='left', validate='one_to_one', suffixes=('', '_reread'), indicator=True)
    if not linked['_merge'].eq('both').all():
        raise ValueError('Missing literal raw assertion')
    for field in ['observation_year', 'population_value_raw', 'source_key_raw', 'source_text_raw']:
        if not linked[field].fillna('').eq(linked[field + '_reread'].fillna('')).all():
            raise ValueError('Literal assertion changed: ' + field)
    corrected = linked['source_locator'].fillna('').ne(linked['source_locator_reread'].fillna(''))
    corrections = linked.loc[corrected, keys + ['source_key_raw', 'source_locator', 'source_locator_reread']].copy()
    source['source_locator_original_reviewed'] = linked['source_locator'].values
    source['source_locator'] = linked['source_locator_reread'].values
    source['source_record_id'] = 'WIKI-LUA:' + source['module_code'] + ':' + source['module_key_raw'] + ':' + source['module_locator']
    if source['source_record_id'].duplicated().any():
        raise ValueError('Assertion IDs not unique')
    source['source_association_status'] = 'reviewed_current_named_article_history_association'
    source['historical_physical_identity_status'] = 'unknown_not_admitted'
    source['population_admission_status'] = 'literal_source_assertion_only_support_scope_exactness_unverified'
    source['independent_review_sha256'] = sha(review)
    output.mkdir(parents=True)
    assertions = output / 'annual_named_history_associations.parquet'
    changes = output / 'source_locator_corrections.parquet'
    source.to_parquet(assertions, index=False, compression='zstd')
    corrections.to_parquet(changes, index=False, compression='zstd')
    receipt = {'status': 'reviewed_source_associations_only_not_historical_place_identity',
               'input_sha256': sha(staged), 'review_sha256': sha(review),
               'raw_literal_rows_verified': len(source), 'keyed_reference_locators_corrected': len(corrections),
               'population_values_changed': 0, 'physical_identity_admissions': 0,
               'coordinate_admissions': 0, 'primary_citation_support_verified': 0,
               'outputs': {p.name: sha(p) for p in [assertions, changes]}}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['staged', 'review', 'raw-dir', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.staged, args.review, args.raw_dir, args.output), indent=2))

if __name__ == '__main__':
    main()
