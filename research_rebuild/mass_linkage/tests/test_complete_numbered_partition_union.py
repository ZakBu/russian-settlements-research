import pytest

from research_rebuild.mass_linkage.measure_scoped_joint_coverage_eighth_20261004 import union_complete_observed_partition


def test_existing_member_and_repeated_projection_never_double_count():
    observation = {'component_source_record_ids_json': '["part1", "part2"]',
                   'component_populations_json': '[16601, 19939]', 'population': 36540}
    source = {'part1': 16601, 'part2': 19939}
    first = union_complete_observed_partition({'other': 500, 'part1': 16601}, observation, source)
    second = union_complete_observed_partition(first, observation, source)
    assert sum(first.values()) == sum(second.values()) == 37040
    assert len(second) == 3


def test_changed_member_value_cannot_be_hidden_by_a_matching_group_total():
    observation = {'component_source_record_ids_json': '["part1", "part2"]',
                   'component_populations_json': '[16600, 19940]', 'population': 36540}
    with pytest.raises(AssertionError, match='source population changed'):
        union_complete_observed_partition({}, observation, {'part1': 16601, 'part2': 19939})
