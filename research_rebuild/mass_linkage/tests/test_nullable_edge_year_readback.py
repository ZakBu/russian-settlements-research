import pytest
from research_rebuild.mass_linkage.verify_applied_mass_increment_20261004 import validated_endpoint_years


def test_legacy_null_dates_use_authoritative_selected_sources():
    assert validated_endpoint_years({'a': 2002, 'b': 2021}, 'a', 'b', None, None) == (2002, 2021)


def test_explicit_conflicting_year_is_rejected():
    with pytest.raises(AssertionError, match='contradicts'):
        validated_endpoint_years({'a': 2002, 'b': 2021}, 'a', 'b', 2010, 2021)


def test_same_census_edge_is_rejected_even_with_null_metadata():
    with pytest.raises(AssertionError, match='one census'):
        validated_endpoint_years({'a': 2002, 'b': 2002}, 'a', 'b', None, None)
