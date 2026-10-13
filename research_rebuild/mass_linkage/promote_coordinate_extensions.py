"""Promote only reviewed, origin-normalized point uses; preserve accepted prefix."""
import argparse
import json
from pathlib import Path
import pandas as pd
from .coverage import sha


def promote(normalized, application, review_addendum, output):
    if output.exists():
        raise FileExistsError('New immutable output required')
    review = json.loads(review_addendum.read_text())
    if not str(review.get('verdict', '')).upper().startswith('APPROVE'):
        raise ValueError('Explicit coordinate application approval required')
    data = pd.read_parquet(normalized / 'normalized_point_uses.parquet')
    receipt = json.loads((normalized / 'receipt.json').read_text())
    path = normalized / 'normalized_point_uses.parquet'
    if sha(path) != receipt['output']['sha256']:
        raise ValueError('Normalized point ledger changed')
    if not receipt['original_columns_unchanged']:
        raise ValueError('Original coordinate columns changed')
    if sha(path) != review['normalized_point_uses_sha256']:
        raise ValueError('Independent approval does not bind this ledger')
    manifest = json.loads((application / 'manifest.json').read_text())
    if sha(application / 'manifest.json') != review['application_manifest_sha256']:
        raise ValueError('Reviewed application changed')
    original = pd.read_parquet(application / 'staged_proposed_point_uses.parquet')
    if not data[original.columns].equals(original):
        raise ValueError('Normalization altered scientific input columns')
    pending = data.coordinate_admission_status.eq('staged_candidate_pending_root_review')
    if int(pending.sum()) != int(review['approved_new_point_uses']):
        raise ValueError('Approval count disagrees with pending ledger')
    if data.target_source_record_id.duplicated().any():
        raise ValueError('Duplicate point-use targets')
    for field in ['point_origin_file', 'point_origin_sha256', 'point_origin_locator']:
        if data.loc[pending, field].isna().any() or data.loc[pending, field].astype(str).eq('').any():
            raise ValueError('Canonical point source missing: ' + field)
    if data.loc[pending, 'boundary_comparability_asserted'].fillna(False).any():
        raise ValueError('Coordinate extension must not assert boundary equivalence')
    data.loc[pending, 'coordinate_admission_status'] = 'reviewed_extension_rule_accepted'
    case = pending & data.coordinate_application_family.eq('M_2002_moscow_standalone_physical_city_point')
    if int(case.sum()) != 1:
        raise ValueError('Expected one independently reviewed Moscow 2002 standalone point')
    data.loc[case, 'coordinate_admission_status'] = 'reviewed_case_accepted'
    data.loc[pending, 'coordinate_quality'] = 'automatically_accepted_checked_rule'
    data.loc[case, 'coordinate_quality'] = 'individually_reviewed'
    data.loc[pending, 'admission_allowed'] = True
    data.loc[pending, 'application_gate_status'] = 'accepted_after_independent_application_and_origin_review'
    data.loc[pending, 'coordinate_application_review_sha256'] = sha(review_addendum)
    output.mkdir(parents=True)
    result = output / 'accepted_point_uses.parquet'
    data.to_parquet(result, index=False)
    acceptance = {'status': 'reviewed_coordinate_extensions_accepted', 'accepted_point_uses': len(data),
                  'new_accepted_point_uses': int(pending.sum()), 'original_accepted_prefix_preserved': len(data) - int(pending.sum()),
                  'review_sha256': sha(review_addendum), 'application_manifest_sha256': sha(application / 'manifest.json'),
                  'normalized_input_sha256': sha(path), 'origin_receipt_sha256': sha(normalized / 'receipt.json'),
                  'output': {'path': str(result), 'sha256': sha(result)},
                  'limits': 'Representative points and stated spatial continuity only. No exact historical measurement, population-quality upgrade, boundary equivalence or new official external-ID binding.'}
    (output / 'acceptance_receipt.json').write_text(json.dumps(acceptance, ensure_ascii=False, indent=2) + '\n')
    return acceptance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['normalized', 'application', 'review_addendum', 'output']:
        parser.add_argument('--' + key.replace('_', '-'), required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(promote(args.normalized, args.application, args.review_addendum, args.output), ensure_ascii=False))
