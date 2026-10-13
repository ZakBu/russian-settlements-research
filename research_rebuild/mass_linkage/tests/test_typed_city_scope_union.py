"""Guard exclusive population accounting when a former city becomes a district."""
import pytest
from research_rebuild.mass_linkage.measure_scoped_joint_coverage_eighth_20261004 import add_typed_scope_old_city

OLD = {'source_record_id': 'old:talnakh', 'population': 58654}

def test_old_city_is_counted_once_alongside_separate_norilsk_city():
    original = {'old:norilsk': 134832, 'old:talnakh': 58654}
    assert add_typed_scope_old_city(original, 2002, OLD, 'old:norilsk') == original
    assert original == {'old:norilsk': 134832, 'old:talnakh': 58654}

def test_later_child_values_are_not_added_to_receiving_city():
    for year, population in [(2010, 175365), (2021, 174453)]:
        parent = {'norilsk': population}
        assert add_typed_scope_old_city(parent, year, OLD, 'norilsk') == parent

def test_unrepresented_parent_and_conflicting_old_population_fail():
    with pytest.raises(AssertionError):
        add_typed_scope_old_city({}, 2002, OLD, 'old:norilsk')
    with pytest.raises(AssertionError):
        add_typed_scope_old_city({'old:norilsk': 134832, 'old:talnakh': 1}, 2002, OLD, 'old:norilsk')
