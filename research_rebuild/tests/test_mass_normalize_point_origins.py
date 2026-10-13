import json

import pytest

from research_rebuild.mass_linkage.normalize_point_origins import (
    exact_point,
    frozen_origin,
    geokladr_origin,
    make_origin,
    retrospective_origin,
    sha256_file,
    verify_wiki_line,
)


def test_geokladr_origin_hash_matches_raw_filename_and_auxiliary_hash_is_separate(tmp_path):
    raw_file = tmp_path / 'okato.dbf'
    parsed_file = tmp_path / 'parsed.parquet'
    raw_file.write_bytes(b'raw dbf')
    parsed_file.write_bytes(b'parsed parquet')
    raw_hash = sha256_file(raw_file)
    parsed_hash = sha256_file(parsed_file)
    origin = geokladr_origin(str(raw_file), raw_hash, str(parsed_file), parsed_hash, 13, 5445)
    assert origin['point_origin_file'] == str(raw_file)
    assert origin['point_origin_sha256'] == raw_hash
    assert origin['point_origin_locator'] == 'raw_dbf_record_number_1based=13;byte_offset_0based=5445'
    assert origin['point_claim_artifact_file'] == str(parsed_file)
    assert origin['point_claim_artifact_sha256'] == parsed_hash
    assert origin['point_origin_file'] != origin['point_claim_artifact_file']


def test_retrospective_point_copies_modern_origin_and_links_carrier_without_census_source():
    carrier = make_origin('/raw/provider.parquet', 'a' * 64, 'parquet_row_1based=42',
                          'tochno_2021_dadata_raw_parquet_point', '/raw/provider.parquet', 'a' * 64)
    retro = retrospective_origin(carrier, 'modern:42', 55.0, 37.0, 55.0, 37.0)
    assert retro['point_origin_file'] == carrier['point_origin_file']
    assert retro['point_origin_sha256'] == carrier['point_origin_sha256']
    assert retro['point_origin_kind'] == 'retrospective_continuity_from_tochno_2021_dadata_raw_parquet_point'
    assert 'carrier_target_source_record_id=modern:42' in retro['point_origin_locator']
    assert 'census' not in retro['point_origin_file'].lower()
    with pytest.raises(ValueError):
        retrospective_origin(carrier, 'modern:42', 55.0001, 37.0, 55.0, 37.0)


def test_wikidata_match_requires_exact_p625_claim_not_other_claim_or_nearby_point():
    entity = {
        'id': 'Q1',
        'claims': {
            'P625': [{'mainsnak': {'datavalue': {'value': {'latitude': 55.0, 'longitude': 37.0}}}}],
            'P159': [{'mainsnak': {'datavalue': {'value': {'latitude': 55.1, 'longitude': 37.1}}}}],
        },
    }
    line = json.dumps(entity)
    assert verify_wiki_line(line, 55.0, 37.0)
    assert not verify_wiki_line(line, 55.1, 37.1)
    assert not verify_wiki_line(line, 55.000001, 37.0)
    flattened_claim = json.dumps({
        'item': 'http://www.wikidata.org/entity/Q649',
        'property': 'http://www.wikidata.org/entity/P625',
        'value': 'POINT(37.000000 55.000000)',
    })
    assert verify_wiki_line(flattened_claim, 55.0, 37.0)


def test_frozen_reviewed_baseline_preserves_unknown_origin_and_exact_review_locator():
    origin = frozen_origin('/frozen/reviews.csv', 'b' * 64, 'target:1', 'review-1', 'review.json#claim')
    assert origin['point_origin_file'] == ''
    assert origin['point_origin_sha256'] == ''
    assert origin['point_origin_kind'] == 'reviewed_frozen_assertion'
    assert origin['point_claim_artifact_file'] == '/frozen/reviews.csv'
    assert origin['point_claim_artifact_sha256'] == 'b' * 64
    assert origin['point_origin_locator'] == (
        'frozen_target_source_record_id=target:1;decision_id=review-1;review_source_locator=review.json#claim'
    )
    assert exact_point(55, 37, 55.0, 37.0)
    assert not exact_point(55, 37, 55.0000001, 37)
