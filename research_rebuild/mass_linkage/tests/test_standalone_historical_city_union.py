import pytest
from research_rebuild.mass_linkage.load_reviewed_inclusion_scope_20261004 import apply_scoped_inclusion_reference


def city():
    return dict(year=2010,source_record_id='old-city',population=56186,
                source_type='город',old_same_year_city_proper_source_record_id=None,
                standalone_historical_city_reference=True,
                current_2021_receiver_source_record_id='receiving-city')


def test_former_independent_city_counts_once_without_inventing_an_old_parent():
    r=city(); first=apply_scoped_inclusion_reference({},2010,r,represented_current_receivers={'receiving-city'})
    assert first=={'old-city':56186}
    assert apply_scoped_inclusion_reference(first,2010,r,represented_current_receivers={'receiving-city'})==first
    assert apply_scoped_inclusion_reference({},2021,r,represented_current_receivers={'receiving-city'})=={}


def test_missing_parent_does_not_waive_other_locality_or_receiving_city_guards():
    r=city();r['source_type']='пгт'
    with pytest.raises(ValueError):
        apply_scoped_inclusion_reference({},2010,r,represented_current_receivers={'receiving-city'})
    with pytest.raises(ValueError):
        apply_scoped_inclusion_reference({},2010,city(),represented_current_receivers=set())
