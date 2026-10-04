from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_current_long_with_secondary_overlay_20261004 import (
    assert_census_values_preserved,
    remap_secondary_history,
)


def _current_core() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "record_type": "census", "observation_year": 2021,
            "source_record_id": "2021:current-row-1", "observation_id": "census:2021:current-row-1",
            "entity_id": "settlement:2021:final-component-anchor", "settlement_name": "Пример",
            "settlement_type": "город", "region_raw": "Примерская область", "population_value": 4321,
            "population_raw": "4 321", "source_native_id": "NATIVE-2021-001",
            "source_sha256": "source-hash", "source_path": "raw.csv", "source_locator": "row=3",
            "population_scope": "settlement", "spatial_identity_status": "accepted_same_place_component",
            "oktmo_native_raw": "12345678", "latitude": 55.25, "longitude": 37.75,
            "coordinate_admission_status": "reviewed_extension_rule_accepted",
            "coordinate_quality": "automatically_accepted_checked_rule",
            "coordinate_source": "selected raw source point", "coordinate_provider": "source",
            "coordinate_source_record_id": "2021:current-row-1", "coordinate_provenance": "raw witnessed point",
            "point_source_file": "raw.csv", "point_source_sha256": "point-hash",
            "point_source_locator": "row=3", "coordinate_admission_rule": "exact_source_point",
            "coordinate_temporal_basis": "accepted_point_target_year",
            "coordinate_provider_quality_raw": "4", "coordinate_measurement_date_unknown": True,
            "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False,
            "coordinate_uncertainty_flags_json": "[]",
        }
    ])


def _history(guid: str = "GUID-1") -> pd.DataFrame:
    return pd.DataFrame([
        {
            "record_type": "wiki_literal_series", "observation_id": "wiki-row-1",
            "entity_id": "wikidata-series:Q1", "associated_census_entity_id": "settlement:stale-id",
            "source_record_id": "WIKIDATA:Q1:GUID-1", "source_native_id": "secondary-native",
            "current_source_record_id": "2021:current-row-1", "current_wikidata_qid": "Q1",
            "current_place_entity_id": "settlement:stale-id", "current_place_observation_id": "census:stale",
            "current_place_label": "Old label", "current_place_type": "село", "current_place_region": "Old region",
            "current_coordinate_carrier_latitude": 1.0, "current_coordinate_carrier_longitude": 2.0,
            "current_coordinate_admission_status": "stale", "current_2021_population": 999,
            "oktmo_current_observed_2021": "old-okтмо", "latitude": None, "longitude": None,
            "historical_identity_admitted": False, "historical_coordinate_asserted": False,
            "wikidata_statement_id": guid, "population_value": 77.0, "population_raw": "77.0",
            "population_value_raw_for_secondary_display": "77.0", "population_reported_thousand": 0.077,
        }
    ])


def test_stale_current_entity_id_is_remapped_from_final_2021_source_id():
    out = remap_secondary_history(_history(), _current_core(), expected_rows=1)
    assert out.loc[0, "current_place_entity_id"] == "settlement:2021:final-component-anchor"
    assert out.loc[0, "associated_census_entity_id"] == "settlement:2021:final-component-anchor"
    assert out.loc[0, "current_place_observation_id"] == "census:2021:current-row-1"
    assert out.loc[0, "entity_id"] == "wikidata-series:Q1"
    assert out.loc[0, "source_record_id"] == "WIKIDATA:Q1:GUID-1"


def test_current_point_context_refreshes_but_historical_coordinates_stay_null():
    out = remap_secondary_history(_history(), _current_core(), expected_rows=1)
    assert out.loc[0, "current_coordinate_carrier_latitude"] == 55.25
    assert out.loc[0, "current_coordinate_carrier_longitude"] == 37.75
    assert out.loc[0, "current_coordinate_admission_status"] == "reviewed_extension_rule_accepted"
    assert out.loc[0, "current_coordinate_source_sha256"] == "point-hash"
    assert out.loc[0, "current_2021_population"] == 4321
    assert out.loc[0, "current_2021_population_raw"] == "4 321"
    assert out.loc[0, "current_2021_source_native_id"] == "NATIVE-2021-001"
    assert out.loc[0, "oktmo_current_observed_2021"] == "12345678"
    assert pd.isna(out.loc[0, "latitude"]) and pd.isna(out.loc[0, "longitude"])
    assert out.loc[0, "historical_identity_admitted"] == False
    assert out.loc[0, "historical_coordinate_asserted"] == False


def test_census_population_raw_native_id_and_2021_oktmo_must_remain_exact():
    selected = pd.DataFrame([
        {"source_record_id": "2021:current-row-1", "census_year": 2021, "population": 4321,
         "source_population_raw": "4 321", "source_raw_line": "Пример,4 321", "source_native_id": "NATIVE-2021-001", "oktmo": "12345678"}
    ])
    core = _current_core().assign(population_source_raw_line="Пример,4 321")
    assert_census_values_preserved(selected, core)
    core.loc[0, "population_value"] = 4322
    with pytest.raises(ValueError, match="population_value"):
        assert_census_values_preserved(selected, core)


def test_duplicate_statement_guids_are_retained_and_flagged_without_grouping():
    history = pd.concat([_history("GUID-DUP"), _history("GUID-DUP").assign(observation_id="wiki-row-2", source_record_id="WIKIDATA:Q1:GUID-2")], ignore_index=True)
    out = remap_secondary_history(history, _current_core(), expected_rows=2)
    assert len(out) == 2
    assert out.observation_id.tolist() == ["wiki-row-1", "wiki-row-2"]
    assert out.wikidata_statement_id.tolist() == ["GUID-DUP", "GUID-DUP"]
    assert out.secondary_statement_guid_duplicate.all()
    # The overlay builder does not group observations or emit year/national sums.
    assert out.population_value.tolist() == [77.0, 77.0]


def test_published_annual_and_literal_layers_cannot_silently_disappear():
    from build_current_long_with_secondary_overlay_20261004 import assert_supplements_preserved
    # A census-only export previously looked valid while dropping both published supplements.
    census_only = pd.DataFrame({"record_type": ["census"] * 465800})
    with pytest.raises(ValueError, match="lost or duplicated"):
        assert_supplements_preserved(census_only)
    full = pd.concat([census_only,
                      pd.DataFrame({"record_type": ["annual_official"] * 516}),
                      pd.DataFrame({"record_type": ["wiki_literal_series"] * 34004})], ignore_index=True)
    assert_supplements_preserved(full)


def test_nonconsecutive_history_index_preserves_observation_alignment():
    history = pd.concat([_history(), _history().assign(observation_id="wiki-row-2", source_record_id="WIKIDATA:Q1:GUID-2")], ignore_index=True)
    history.index = [4, 9]
    out = remap_secondary_history(history, _current_core(), expected_rows=2)
    assert out.index.tolist() == [4, 9]
    assert out.current_coordinate_carrier_latitude.tolist() == [55.25, 55.25]
    assert out.population_value.tolist() == [77.0, 77.0]


def test_analysis_display_preserves_point_roles_and_historical_unknowns():
    from build_current_long_with_secondary_overlay_20261004 import build_analysis_view
    core = _current_core()
    history = remap_secondary_history(_history(), core, expected_rows=1)
    territory = core.copy().assign(source_record_id="fed-2021", entity_id="statisticalaggregate:fed", latitude=None, longitude=None)
    combined = pd.concat([core, history, territory], ignore_index=True)
    fed_points = pd.DataFrame([{"source_record_id": "fed-2021", "latitude": 60.0, "longitude": 30.0}])
    fed_chains = pd.DataFrame([{"chain_id": "typed-city", "source_record_ids_json": '["fed-2021"]'}])
    out = build_analysis_view(combined, fed_points, fed_chains)
    assert out.loc[0, "display_point_role"] == "admitted_NP_point_use"
    assert out.loc[1, "display_latitude"] == 55.25
    assert "historical_point_not_admitted" in out.loc[1, "display_point_role"]
    assert pd.isna(out.loc[1, "latitude"])
    assert out.loc[1, "historical_identity_admitted"] == False
    assert out.loc[1, "display_series_id"] == core.loc[0, "entity_id"]
    assert "secondary_source_association" in out.loc[1, "display_series_basis"]
    assert out.loc[2, "display_latitude"] == 60.0
    assert "NP_coverage_separate" in out.loc[2, "display_point_role"]
    assert out.loc[2, "display_series_id"] == "typed-city"
    assert pd.isna(out.loc[2, "latitude"])


def test_reviewed_current_binding_source_tag_is_preserved_without_historical_admission():
    history = _history().assign(record_type='wiki_literal_series_candidate_current_binding_review')
    out = remap_secondary_history(history, _current_core(), expected_rows=1)
    assert out.record_type.iloc[0] == 'wiki_literal_series'
    assert out.source_record_type_before_display_projection.iloc[0] == 'wiki_literal_series_candidate_current_binding_review'
    assert out.historical_identity_admitted.iloc[0] == False
    assert pd.isna(out.latitude.iloc[0])
    assert history.record_type.iloc[0] == 'wiki_literal_series_candidate_current_binding_review'
    bad = history.assign(record_type='unknown_unreviewed_source')
    with pytest.raises(ValueError, match='unexpected record_type'):
        remap_secondary_history(bad, _current_core(), expected_rows=1)
