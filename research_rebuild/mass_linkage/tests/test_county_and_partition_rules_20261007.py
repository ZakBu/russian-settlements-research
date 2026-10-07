"""Regression checks for administrative names and lost source partitions."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apply_unique_county_name_bridge_20261007 import county_key
from apply_complete_numbered_partition_batch_20261007 import validate_members


def test_county_level_change_does_not_change_toponym():
    assert county_key("Кинель-Черкасский район") == county_key("Кинель-Черкасский муниципальный район")
    assert county_key("Красногорский район") != county_key("Красногвардейский муниципальный округ")
    assert county_key(None) == ""


def test_missing_blank_part_not_assumed_zero():
    selected = pd.DataFrame([dict(source_record_id="2010:p1", settlement_name="Нижнее Гурово (часть 1)", population=223, census_year=2010, region_norm="курская")])
    with pytest.raises(ValueError, match="Incomplete"):
        validate_members(selected, pd.DataFrame(), pd.DataFrame())


def test_whole_name_competitor_not_summed_into_partition():
    selected = pd.DataFrame([dict(settlement_name="Троицкое (часть 1)"), dict(settlement_name="Троицкое (часть 2)"), dict(settlement_name="Троицкое")])
    with pytest.raises(ValueError, match="homonyms"):
        validate_members(selected, pd.DataFrame(), pd.DataFrame())


def test_changed_member_population_rejected_even_when_total_preserved():
    selected = pd.DataFrame([
        dict(source_record_id="2002:p1", settlement_name="Бичура (часть 1)", population=4898, census_year=2002, region_norm="бурятия"),
        dict(source_record_id="2002:p2", settlement_name="Бичура (часть 2)", population=4839, census_year=2002, region_norm="бурятия"),
    ])
    reviewed = pd.DataFrame([dict(source_record_id="2002:p1", selected_population=4897), dict(source_record_id="2002:p2", selected_population=4840)])
    with pytest.raises(ValueError, match="population changed"):
        validate_members(selected, reviewed, pd.DataFrame())


def test_no_space_partition_suffix_is_recognized():
    selected = pd.DataFrame([
        dict(source_record_id="2002:p1", settlement_name="Плешаново (часть1)", population=1659, census_year=2002, region_norm="оренбургская"),
        dict(source_record_id="2002:p2", settlement_name="Плешаново (часть 2)", population=2108, census_year=2002, region_norm="оренбургская"),
    ])
    reviewed = pd.DataFrame([dict(source_record_id="2002:p1", selected_population=1659), dict(source_record_id="2002:p2", selected_population=2108)])
    groups = pd.DataFrame([dict(year=2002, region="оренбургская", base_name="Плешаново", origin_workbook_parts="1;2", selected_part_count=2, selected_part_sum=3767, official_candidates_equal_sum=1)])
    assert validate_members(selected, reviewed, groups)
