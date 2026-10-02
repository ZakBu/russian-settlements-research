"""Apply a hash-pinned independent decision to a frozen identity application.

Original baseline evidence remains in its original file; this combined working
ledger adds the admission receipt without rewriting either frozen input.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def accept(application: Path, review_path: Path, output: Path) -> dict:
    review = json.loads(review_path.read_text())
    if review['review_status'] != 'checked_rule_accepted':
        raise ValueError('application has no accepting independent review')
    pins = review['pinned_artifacts']
    if sha(application / 'application_audit.json') != pins['application_audit']['sha256']:
        raise ValueError('application audit hash differs from independent review')
    for name, expected in pins['output_sha256'].items():
        if sha(application / name) != expected:
            raise ValueError(f'reviewed output changed: {name}')
    if output.exists():
        raise FileExistsError('use a new immutable acceptance output directory')
    baseline = pd.read_csv(application / 'reviewed_baseline_identity_edges.csv', dtype=str)
    new = pd.read_csv(application / 'rule_accepted_edges.csv', dtype=str)
    allowed = {'checked_rule_accepted_pending_independent_application_verification',
               'checked_rule_accepted_redundant_graph_connectivity_effect_pending_independent_application_verification'}
    if not new.decision_status.isin(allowed).all():
        raise ValueError('unexpected staged decision status')
    new['decision_status'] = new.decision_status.str.removesuffix('_pending_independent_application_verification')
    new['application_review_id'] = review['review_id']
    new['application_review_sha256'] = sha(review_path)
    new['selection_projection_status'] = 'active_endpoints_selected'
    combined = pd.concat([baseline, new], ignore_index=True, sort=False)
    keys = combined.apply(lambda r: tuple(sorted((r.from_source_record_id, r.to_source_record_id))), axis=1)
    if keys.duplicated().any() or not combined.decision_id.is_unique:
        raise ValueError('duplicate decision or identity pair')
    output.mkdir(parents=True)
    combined.to_parquet(output / 'accepted_identity_edges.parquet', index=False)
    receipt = {
        'status': 'checked_rule_application_accepted',
        'baseline_edges_preserved': len(baseline), 'new_distinct_edges': len(new),
        'accepted_union_edges': len(combined),
        'review': {'path': str(review_path), 'sha256': sha(review_path)},
        'application_audit_sha256': pins['application_audit']['sha256'],
        'outputs': {'accepted_identity_edges.parquet': sha(output / 'accepted_identity_edges.parquet')},
        'limitations': ['Identity only; no population value, coordinate, or boundary-comparability admission.',
                        'The fixed review sample does not establish a national calibrated error rate.'],
        'builder_sha256': sha(Path(__file__)),
    }
    (output / 'acceptance_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser()
    for name in ('application', 'review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(accept(args.application, args.review, args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
