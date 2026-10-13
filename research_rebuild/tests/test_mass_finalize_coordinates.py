import json

import pandas as pd

from research_rebuild.mass_linkage.finalize_coordinates import (
    CITY_A,
    CITY_C,
    PROVIDER_FAMILY,
    _family_sources,
    _point_key,
)


def test_point_key_rejects_invalid_coordinates_and_normalizes_precision():
    assert _point_key(55.75000001, 37.61000001) == (55.75, 37.61)
    assert _point_key(91, 0) is None
    assert _point_key(float('nan'), 0) is None


def test_family_source_sets_deduplicate_overlapping_rules():
    proposals = pd.DataFrame([
        {'source_record_id': 'a', 'candidate_families_json': json.dumps([PROVIDER_FAMILY])},
        {'source_record_id': 'b', 'candidate_families_json': json.dumps([CITY_C, CITY_A])},
        {'source_record_id': 'b', 'candidate_families_json': json.dumps([CITY_C])},
    ])
    assert _family_sources(proposals, PROVIDER_FAMILY) == {'a'}
    assert _family_sources(proposals, CITY_C) == {'b'}
    assert _family_sources(proposals, CITY_A) == {'b'}
