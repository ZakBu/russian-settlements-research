from __future__ import annotations

import pandas as pd
import pytest

from research_rebuild.mass_linkage.build_long_table import (
    COORDINATE_OPTIONAL_COLUMNS,
    COORDINATE_REQUIRED_COLUMNS,
    IDENTITY_REQUIRED_COLUMNS,
    _accepted_coordinate_map,
    _coordinate_columns,
    _read_parquet_projection,
)


def test_wide_identity_and_point_ledgers_are_projected_without_losing_origin_fields(tmp_path):
    oversized_proof_payload = "private-wide-proof-field:" + ("x" * 100_000)
    edge_path = tmp_path / "edges.parquet"
    edges = pd.DataFrame([
        {
            "from_source_record_id": "2010:source-a",
            "to_source_record_id": "2021:source-b",
            "from_year": 2010,
            "to_year": 2021,
            "relation": "same_place",
            "decision_status": "checked_rule_accepted",
            "selection_projection_status": "active_endpoints_selected",
            "wide_unconsumed_proof_payload": oversized_proof_payload,
        }
    ])
    edges.to_parquet(edge_path, index=False)
    edge_projection = _read_parquet_projection(edge_path, IDENTITY_REQUIRED_COLUMNS)
    assert edge_projection.columns.tolist() == list(IDENTITY_REQUIRED_COLUMNS)
    assert edge_projection.iloc[0].from_source_record_id == "2010:source-a"
    assert "wide_unconsumed_proof_payload" not in edge_projection

    point_path = tmp_path / "points.parquet"
    points = pd.DataFrame([
        {
            "target_source_record_id": "2021:source-b",
            "target_year": 2021,
            "coordinate_admission_status": "reviewed_extension_rule_accepted",
            "latitude": 55.25,
            "longitude": 37.75,
            "coordinate_source": "reviewed provider point",
            "coordinate_source_record_id": "Q123",
            "coordinate_provider": "wikidata_p625",
            "coordinate_provider_id": "Q123",
            "source_file": "raw/source.parquet",
            "source_sha256": "source-sha256",
            "source_locator": "row=218",
            "coordinate_measurement_date_unknown": True,
            "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False,
            "wide_unconsumed_proof_payload": oversized_proof_payload,
        }
    ])
    points.to_parquet(point_path, index=False)
    projected = _read_parquet_projection(
        point_path, COORDINATE_REQUIRED_COLUMNS, COORDINATE_OPTIONAL_COLUMNS,
    )
    accepted = _accepted_coordinate_map(projected)

    assert set(accepted) == {"2021:source-b"}
    point = accepted["2021:source-b"]
    assert "wide_unconsumed_proof_payload" not in point
    assert point["coordinate_source_record_id"] == "Q123"
    assert point["coordinate_provider_id"] == "Q123"
    assert point["source_file"] == "raw/source.parquet"
    assert point["source_sha256"] == "source-sha256"
    assert point["source_locator"] == "row=218"
    assert point["coordinate_measurement_date_unknown"] is True
    assert point["boundary_comparability_asserted"] is False
    assert point["population_scope_comparability_asserted"] is False
    # Optional scientific metadata absent from a legacy point ledger stays unknown.
    output = _coordinate_columns(point, "accepted_point_target_year")
    assert output["point_source_file"] == "raw/source.parquet"
    assert output["point_source_sha256"] == "source-sha256"
    assert output["point_source_locator"] == "row=218"
    assert output["coordinate_provider_id"] == "Q123"
    assert output["coordinate_source_date"] is None
    assert output["coordinate_measurement_date_unknown"] is True
    assert output["boundary_comparability_asserted"] is False
    assert output["population_scope_comparability_asserted"] is False


def test_parquet_projection_requires_consumed_key_columns(tmp_path):
    path = tmp_path / "edges.parquet"
    pd.DataFrame([{"from_source_record_id": "a", "to_source_record_id": "b"}]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        _read_parquet_projection(path, IDENTITY_REQUIRED_COLUMNS)
