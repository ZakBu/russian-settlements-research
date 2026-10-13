import pytest
from research_rebuild.mass_linkage.measure_scoped_joint_coverage_eighth_20261004 import add_secondary_supported_old_rows

def test_current_secondary_child_is_not_added_to_moscow_parent():
    observations=[{'observation_year':2021,'population':65043,'source_record_id':None,'observation_source_class':'secondary_dated_wikidata_P1082'}]
    parent={'moscow-territory2021':13010112}
    assert add_secondary_supported_old_rows(parent,2021,observations)==parent

def test_old_primary_row_is_counted_once_when_another_path_already_covers_it():
    observations=[{'observation_year':2002,'population':32653,'source_record_id':'troitsk2002','observation_source_class':'primary_official_selected_old_census_row'}]
    original={'troitsk2002':32653}
    assert add_secondary_supported_old_rows(original,2002,observations)==original
    assert original=={'troitsk2002':32653}

def test_conflicting_old_population_cannot_be_silently_replaced():
    observations=[{'observation_year':2010,'population':39873,'source_record_id':'troitsk2010','observation_source_class':'primary_official_selected_old_census_row'}]
    with pytest.raises(AssertionError):
        add_secondary_supported_old_rows({'troitsk2010':40000},2010,observations)
