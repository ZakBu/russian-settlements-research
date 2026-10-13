"""Regression checks for repeated hashing and mismatched point origins."""
import csv
from collections import Counter
import pytest
import pandas as pd
import duckdb
from research_rebuild.mass_linkage import apply_reviewed_mass_extensions_20261004 as app


def test_false_measurement_flag_remains_boolean_after_append(tmp_path):
    frame = pd.DataFrame({'census_date_point_measurement_proven': [False, 'False', None]})
    app.preserve_nullable_booleans(frame, ['census_date_point_measurement_proven'])
    con = duckdb.connect()
    con.register('points', frame)
    assert con.execute('select census_date_point_measurement_proven from points').fetchall() == [(False,), (False,), (None,)]
    assert con.execute('describe points').fetchone()[1] == 'BOOLEAN'


def test_unknown_boolean_literal_blocks_output():
    with pytest.raises(ValueError, match='invalid boolean source flag'):
        app.preserve_nullable_booleans(pd.DataFrame({'flag': ['not checked']}), ['flag'])


def pin(path):
    return {'path': str(path), 'sha256': app.sha(path)}


def table(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def test_complete_large_source_block_witness_is_read(tmp_path):
    # The independently reviewed anchor-block packet exceeded the default
    # 128 KiB CSV field limit. Its raw witness must survive without truncation.
    path = tmp_path / 'reviewed_block.csv'
    witness = 'Строка исходной таблицы\n' * 10000
    table(path, [{'source_record_id': '2010:publication:row', 'raw_block': witness}])
    assert app.read_csv_rows(path) == [{'source_record_id': '2010:publication:row',
                                       'raw_block': witness}]


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


def valid_point_spec(tmp_path, latitude='55'):
    origin, receipt, extra = [tmp_path / name for name in ('origin.json', 'review.json', 'scope.json')]
    for path in (origin, receipt, extra):
        path.write_text('{}')
    candidate, approved = [tmp_path / name for name in ('points.csv', 'approved.csv')]
    table(candidate, [{'target': 'source1', 'latitude': latitude, 'longitude': '37', 'locator': 'row=1'}])
    table(approved, [{'target': 'source1', 'latitude': latitude, 'longitude': '37'}])
    return {'candidate': pin(candidate), 'approved': pin(approved), 'review_receipt': pin(receipt),
            'additional_review_receipts': [pin(extra)], 'origin': pin(origin),
            'candidate_columns': {'target': 'target', 'latitude': 'latitude', 'longitude': 'longitude', 'origin_locator': 'locator'},
            'approved_columns': {'target': 'target', 'latitude': 'latitude', 'longitude': 'longitude'}}


def test_point_scope_supplement_is_pinned_and_recorded(tmp_path):
    spec = valid_point_spec(tmp_path)
    result, inputs = app.load_direct_points({'point_sources': [spec]})
    assert len(result) == 1
    assert inputs['point:0']['additional_review_receipts'] == spec['additional_review_receipts']
    (tmp_path / 'scope.json').write_text('{"decision":"changed"}')
    with pytest.raises(ValueError, match='checksum mismatch'):
        app.load_direct_points({'point_sources': [spec]})


def test_independently_listed_impossible_point_cannot_be_applied(tmp_path):
    spec = valid_point_spec(tmp_path, latitude='91')
    with pytest.raises(ValueError, match='impossible reviewed coordinates'):
        app.load_direct_points({'point_sources': [spec]})
