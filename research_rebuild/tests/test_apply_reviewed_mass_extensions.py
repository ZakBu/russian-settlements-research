"""Regression checks for repeated hashing and mismatched point origins."""
import csv
from collections import Counter
import pytest
from research_rebuild.mass_linkage import apply_reviewed_mass_extensions_20261004 as app


def pin(path):
    return {'path': str(path), 'sha256': app.sha(path)}


def table(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def test_identity_source_hashing_is_bounded_per_file(tmp_path, monkeypatch):
    # A real failed run rehashed the whole candidate CSV for each admitted row.
    rows = [{'from': f'a{i}', 'to': f'b{i}', 'family': 'exact_rule',
             'status': 'reviewed_candidate'} for i in range(100)]
    candidate, eligible, receipt = [tmp_path / name for name in ('candidate.csv', 'eligible.csv', 'review.json')]
    table(candidate, rows); table(eligible, rows); receipt.write_text('{}')
    spec = {'candidate': pin(candidate), 'eligible': pin(eligible), 'review_receipt': pin(receipt),
            'candidate_columns': {'from': 'from', 'to': 'to', 'family': 'family', 'status': 'status'},
            'eligible_columns': {'from': 'from', 'to': 'to', 'family': 'family'},
            'accepted_candidate_statuses': ['reviewed_candidate']}
    original = app.sha; counts = Counter()
    def measured(path):
        counts[str(path)] += 1
        return original(path)
    monkeypatch.setattr(app, 'sha', measured)
    result, _ = app.load_identity({'identity_sources': [spec], '_reviewed_at': '2026-10-03T23:00:00Z'})
    assert len(result) == 100
    assert counts[str(candidate)] <= 3
    assert counts[str(eligible)] <= 3
    assert counts[str(receipt)] <= 3


def test_reviewed_point_cannot_claim_different_raw_origin_hash(tmp_path):
    origin = tmp_path / 'origin.json'; origin.write_text('{"point":[55,37]}')
    candidate, approved, receipt = [tmp_path / name for name in ('points.csv', 'approved.csv', 'review.json')]
    receipt.write_text('{}')
    table(candidate, [{'target': 'source1', 'latitude': '55', 'longitude': '37',
                       'point_origin_file': str(origin), 'point_origin_sha256': '0' * 64,
                       'point_origin_locator': 'point'}])
    table(approved, [{'target': 'source1', 'latitude': '55', 'longitude': '37'}])
    spec = {'candidate': pin(candidate), 'approved': pin(approved), 'review_receipt': pin(receipt), 'origin': pin(origin),
            'candidate_columns': {'target': 'target', 'latitude': 'latitude', 'longitude': 'longitude',
                                  'origin_file': 'point_origin_file', 'origin_sha256': 'point_origin_sha256',
                                  'origin_locator': 'point_origin_locator'},
            'approved_columns': {'target': 'target', 'latitude': 'latitude', 'longitude': 'longitude'}}
    with pytest.raises(ValueError, match='recorded hash differs'):
        app.load_direct_points({'point_sources': [spec]})
