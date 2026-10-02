import numpy as np
import pandas as pd
import pytest

from research_rebuild.mass_linkage.coordinate_ledger import (
    haversine_array,
    screen_candidate,
    source_row_index,
)


def complete_row():
    return {
        "raw_object_level": "Населенный пункт",
        "population_scope": "settlement",
        "provider_settlement_fias_id": "uuid-settlement",
        "provider_general_fias_id": "uuid-settlement",
        "provider_fias_level": "6",
        "selected_settlement_name": "Чукотское",
        "provider_settlement_name": "Чукотское",
        "selected_settlement_type": "село",
        "provider_settlement_type_full": "село",
        "provider_latitude": 67.0,
        "provider_longitude": -175.0,
        "baseline_provider_coordinate_conflict": False,
        "provider_settlement_fias_duplicate_count": 1,
        "provider_general_fias_duplicate_count": 1,
        "provider_coordinate_duplicate_count": 1,
        "selected_latitude": 67.0,
        "selected_longitude": -175.0,
        "selected_to_dadata_distance_km": 0.0,
    }


def test_exact_raw_row_index_is_one_based_and_checked():
    assert source_row_index("2021:raw.parquet:parquet:17", 17) == 16
    with pytest.raises(ValueError):
        source_row_index("2021:raw.parquet:parquet:17", 16)


def test_candidate_family_needs_physical_source_named_fias_point_but_not_per_row_independent_point():
    row = complete_row()
    result = screen_candidate(row)
    assert result["candidate_family_exact_named_physical_np_fias_point"]
    assert result["provider_admin_context_exactly_compared"] is False
    assert result["admission_allowed"] is False
    assert result["selected_point_matches_dadata_within_1m"]
    row["provider_settlement_fias_id"] = None
    assert screen_candidate(row)["candidate_family_exact_named_physical_np_fias_point"]


def test_wrong_grain_level_or_provider_identity_blocks_family():
    for key, value in [
        ("raw_object_level", "Муниципалитет нижнего уровня"),
        ("population_scope", "federal_city_region"),
        ("provider_fias_level", "7"),
        ("provider_general_fias_id", None),
        ("provider_settlement_fias_id", "different-parent"),
        ("baseline_provider_coordinate_conflict", True),
        ("provider_coordinate_duplicate_count", 2),
    ]:
        row = complete_row()
        row[key] = value
        result = screen_candidate(row)
        assert not result["candidate_family_exact_named_physical_np_fias_point"], key
        assert result["admission_allowed"] is False


def test_type_or_name_mismatch_blocks_but_qc_precision_is_not_an_input_gate():
    row = complete_row()
    row["provider_settlement_name"] = "Другое"
    assert not screen_candidate(row)["candidate_family_exact_named_physical_np_fias_point"]
    row = complete_row()
    row["provider_settlement_type_full"] = "поселок"
    assert not screen_candidate(row)["candidate_family_exact_named_physical_np_fias_point"]
    row = complete_row()
    row["qc_geo_dadata"] = 0
    result = screen_candidate(row)
    assert result["candidate_family_exact_named_physical_np_fias_point"]
    row["selected_settlement_type"] = "пгт"
    row["provider_settlement_type_full"] = "поселок городского типа"
    assert screen_candidate(row)["candidate_family_exact_named_physical_np_fias_point"]


def test_distance_screen_handles_negative_longitude_and_invalid_points():
    near = haversine_array(pd.Series([67.0, 91]), pd.Series([-175.0, 0]), pd.Series([67.001, 0]), pd.Series([-175.0, 0]))
    assert near[0] < 0.2
    assert np.isnan(near[1])
