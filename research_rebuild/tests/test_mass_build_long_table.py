import pandas as pd
import pytest

from research_rebuild.mass_linkage.build_long_table import build_long_table, _bind_source_hashes, _coordinate_columns


def test_point_event_candidates_do_not_certify_boundary_or_identifier_history():
    point={"latitude":50,"longitude":40,"coordinate_admission_status":"reviewed_extension_rule_accepted",
           "admission_rule":"historical_city_typed_code_and_accepted_modern_point_1km_v1",
           "lineage_event_roles_json":'[{'+'"event_id":"child_absorption","event_evidence_status":"legacy_candidate_not_newly_verified"'+'}]',
           "corroborating_modern_point_distance_km":0.7,"boundary_comparability_asserted":False}
    cols=_coordinate_columns(point,'historical_continuity_inference')
    assert cols['coordinate_lineage_event_candidates_json']==point['lineage_event_roles_json']
    assert cols['coordinate_corroborating_modern_point_distance_km']==0.7
    assert cols['boundary_comparability_asserted'] is False
    assert cols['coordinate_quality']=='automatically_accepted_checked_rule'


def test_exact_source_manifest_binding_preserves_original_and_blocks_conflicts(tmp_path):
    manifest = tmp_path / 'input_manifest.parquet'
    pd.DataFrame([{'path':'raw/source.xls','sha256':'abc'}]).to_parquet(manifest)
    original = pd.DataFrame([{'source_file':'raw/source.xls','source_path':None,'source_sha256':None}])
    result = _bind_source_hashes(original, manifest)
    assert result.source_sha256.iloc[0] == 'abc'
    assert pd.isna(result.source_sha256_original_selected.iloc[0])
    assert result.source_hash_binding.iloc[0] == 'exact_path_in_frozen_input_manifest'
    assert pd.isna(original.source_sha256.iloc[0])
    original.loc[0,'source_sha256'] = 'different'
    with pytest.raises(ValueError, match='disagrees'):
        _bind_source_hashes(original, manifest)


def _write(frame, path):
    frame.to_parquet(path, index=False)
    return path


def _inputs(tmp_path, reverse=False):
    census_rows = [
        {"source_record_id": "r2002", "census_year": 2002, "source_name_raw": "Old town", "settlement_name": "Old town", "settlement_type": "город", "region_raw": "R", "district_raw": "D", "municipality_raw": "M", "population": 10, "source_population_raw": "10", "population_value_quality": "direct_published_census_value", "population_scope": "settlement", "oktmo": "123", "latitude": 1.0, "longitude": 2.0, "source_file": "f02", "source_path": None, "source_sha256": None, "source_locator": None, "source_sheet": None, "source_row": 1, "source_native_id": "1", "entity_grain_status": "atomic_physical_settlement"},
        {"source_record_id": "r2010", "census_year": 2010, "source_name_raw": "Town", "settlement_name": "Town", "settlement_type": "город", "region_raw": "R", "district_raw": "D", "municipality_raw": "M", "population": 11, "source_population_raw": "11", "population_value_quality": "direct_published_census_value", "population_scope": "settlement", "oktmo": "999", "latitude": 3.0, "longitude": 4.0, "source_file": "f10"},
        {"source_record_id": "r2021", "census_year": 2021, "source_name_raw": "Town", "settlement_name": "Town", "settlement_type": "город", "region_raw": "R", "district_raw": "D", "municipality_raw": "M", "population": 12, "source_population_raw": "12", "population_value_quality": "direct_published_census_value", "population_scope": "settlement", "oktmo": "0000123", "latitude": 50.0, "longitude": 60.0, "source_file": "f21"},
        {"source_record_id": "lonely", "census_year": 2010, "source_name_raw": "Unlinked", "settlement_name": "Unlinked", "settlement_type": "село", "region_raw": "R", "district_raw": "D", "municipality_raw": "M", "population": 4, "source_population_raw": None, "population_value_quality": "direct_published_census_value", "population_scope": "settlement", "oktmo": None, "latitude": 70.0, "longitude": 80.0, "source_file": "f10"},
    ]
    if reverse:
        census_rows.reverse()
    census = pd.DataFrame(census_rows)
    edges = pd.DataFrame([
        {"relation": "same_place", "from_source_record_id": "r2002", "to_source_record_id": "r2010", "from_year": "2002", "to_year": "2010", "decision_status": "checked_rule_accepted", "selection_projection_status": "active_endpoints_selected"},
        {"relation": "same_place", "from_source_record_id": "r2010", "to_source_record_id": "r2021", "from_year": "2010", "to_year": "2021", "decision_status": "checked_rule_accepted", "selection_projection_status": "active_endpoints_selected"},
    ])
    if reverse:
        edges = edges.iloc[::-1]
    coords = pd.DataFrame([
        {"target_source_record_id": "r2021", "target_year": 2021, "latitude": 50.0, "longitude": 60.0, "coordinate_quality": "reviewed modern representative point", "coordinate_admission_status": "reviewed_rule_accepted", "admission_rule": "A_rural_exact_code_and_own_name_type", "coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False, "coordinate_source": "accepted source", "coordinate_source_record_id": "point-source-1", "coordinate_provider": "provider", "coordinate_provider_id": "p1", "coordinate_provenance": "direct source point", "source_file": "point.csv", "source_sha256": "sha", "source_locator": "row:1", "provider_binding_status": "bound", "provider_fias_binding_status": "not applicable"},
        {"target_source_record_id": "lonely", "target_year": 2010, "latitude": 70.0, "longitude": 80.0, "coordinate_quality": "4.0", "coordinate_admission_status": "frozen_r5b_reviewed_baseline_preserved", "admission_rule": "independent_osm_polygon_case_review_v1", "coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False, "coordinate_source": "accepted source", "coordinate_source_record_id": "point-source-2", "coordinate_provider": "provider", "coordinate_provider_id": "p2", "coordinate_provenance": "reviewed source point", "source_file": "point.csv", "source_sha256": "sha", "source_locator": "row:2", "provider_binding_status": "bound", "provider_fias_binding_status": "not applicable"},
    ])
    annual = pd.DataFrame([
        {"source_record_id": "annual-city-2022", "source_publication_row_id": "pubrow-city", "observation_year": 2022, "reference_date": "2022-01-01", "population_raw": "187", "population_reported_thousand": 187, "population_reported_scaled_persons": 187000, "population_unit_multiplier": 1000, "rounding_convention": "unspecified_in_publication; no exact population or assumed error interval", "population_value_quality": "official_annual_estimate_rounded_to_thousands", "settlement_name_raw": "Town", "settlement_name": "Town", "region_qualifier_raw": "", "source_pdf_page": 1, "source_line": 2, "source_sha256": "a", "source_path": "yearbook.pdf", "source_table": "4.9", "target_2021_source_record_id": "r2021", "target_population_scope": "settlement"},
        {"source_record_id": "annual-aggregate", "source_publication_row_id": "pubrow-aggregate", "observation_year": 2022, "reference_date": "2022-01-01", "population_raw": "1000", "population_reported_thousand": 1000, "population_reported_scaled_persons": 1000000, "population_unit_multiplier": 1000, "rounding_convention": "unspecified_in_publication; no exact population or assumed error interval", "population_value_quality": "official_annual_estimate_rounded_to_thousands", "settlement_name_raw": "Federal city region", "settlement_name": "Federal city region", "region_qualifier_raw": "", "source_pdf_page": 1, "source_line": 3, "source_sha256": "a", "source_path": "yearbook.pdf", "source_table": "4.9", "target_2021_source_record_id": "r2021", "target_population_scope": "federal_city_region"},
    ])
    wiki = pd.DataFrame([{
        "module_code": "RUS-X", "module_key_raw": "k", "entry_title_comment_raw": "Town", "observation_year": 1900,
        "population_value_raw": "35", "population_value": 35, "source_key_raw": "SRC", "source_text_raw": "{{cite web|url=x}}",
        "source_date_note_raw": "", "source_locator": "literal-cell:1", "module_locator": "line:7", "module_sha256": "b",
        "population_scope": "unknown", "exact_population_status": "unknown", "candidate_id": "RUS-X:k",
        "current_source_oktmo_exact_digits": "0000123", "current_source_name": "Town", "current_source_type": "город",
        "current_source_region": "R", "source_record_id": "WIKI-LUA:RUS-X:k:line:7",
        "source_association_status": "reviewed_current_named_article_history_association",
        "historical_physical_identity_status": "unknown_not_admitted",
        "population_admission_status": "literal_source_assertion_only_support_scope_exactness_unverified",
    }])
    return tuple(_write(frame, tmp_path / f"{name}.parquet") for name, frame in [
        ("census", census), ("edges", edges), ("coords", coords), ("annual", annual), ("wiki", wiki)
    ])


def _build(tmp_path, reverse=False):
    census, edges, coords, annual, wiki = _inputs(tmp_path, reverse)
    return build_long_table(census, edges, coords, annual, tmp_path / ("out_reverse.parquet" if reverse else "out.parquet"), wiki)[0]


def test_components_anchor_deterministically_and_unlinked_rows_stay_unknown(tmp_path):
    table = _build(tmp_path)
    census = table[table.record_type.eq("census")].set_index("source_record_id")
    assert census.loc["r2002", "entity_id"] == census.loc["r2010", "entity_id"] == census.loc["r2021", "entity_id"]
    assert census.loc["r2002", "entity_id"] == "settlement:r2021"
    assert bool(census.loc["r2002", "census_full_chain"])
    assert census.loc["lonely", "association_status"] == "unknown_no_link"
    assert census.loc["lonely", "entity_id"] != census.loc["r2021", "entity_id"]
    assert census.loc["lonely", "census_2002_status"] == "unknown_no_record"
    assert pd.isna(census.loc["lonely", "population_raw"])
    assert census.loc["lonely", "coordinate_quality"] == "individually_reviewed"
    assert census.loc["lonely", "coordinate_provider_quality_raw"] == "4.0"
    reverse = _build(tmp_path, reverse=True)
    assert census.loc["r2002", "entity_id"] == reverse[reverse.source_record_id.eq("r2002")].iloc[0].entity_id


def test_annual_aggregate_has_no_point_and_official_rounded_population_is_preserved(tmp_path):
    table = _build(tmp_path)
    official = table[table.record_type.eq("annual_official")].set_index("source_record_id")
    city = official.loc["annual-city-2022"]
    assert city.population_value == 187000
    assert city.population_raw == "187"
    assert city.population_reported_thousand == 187
    assert city.population_unit_multiplier == 1000
    assert city.population_rounding_convention == "unspecified_in_publication; no exact population or assumed error interval"
    assert city.reference_date == "2022-01-01"
    assert city.population_value_quality == "official_annual_estimate_rounded_to_thousands"
    assert city.coordinate_temporal_basis == "modern_rep_point_spatial_continuity_inference_dateunknown"
    assert city.coordinate_quality == "automatically_accepted_checked_rule"
    assert city.coordinate_provider_quality_raw == "reviewed modern representative point"
    assert city.point_source_file == "point.csv"
    aggregate = official.loc["annual-aggregate"]
    assert aggregate.entity_category == "statistical_aggregate"
    assert aggregate.entity_id.startswith("statisticalaggregate:")
    assert pd.isna(aggregate.latitude) and pd.isna(aggregate.longitude)


def test_wiki_literal_history_does_not_inherit_census_identity_or_coordinates(tmp_path):
    table = _build(tmp_path)
    wiki = table[table.record_type.eq("wiki_literal_series")].iloc[0]
    assert wiki.observation_year == 1900
    assert wiki.population_raw == "35"
    assert "cite web" in wiki.source_locator
    assert wiki.association_status == "current_named_article_association_only"
    assert wiki.historical_physical_identity_status == "unknown_not_admitted"
    assert wiki.entity_id.startswith("wiki-series:")
    assert pd.isna(wiki.associated_census_entity_id)
    assert pd.isna(wiki.latitude) and pd.isna(wiki.longitude)


def test_older_census_code_is_not_backfilled_as_historical_oktmo(tmp_path):
    table = _build(tmp_path)
    census = table[table.record_type.eq("census")].set_index("source_record_id")
    assert census.loc["r2021", "oktmo_current_observed_2021"] == "0000123"
    assert census.loc["r2021", "oktmo_observed_at_year"] == "0000123"
    assert census.loc["r2021", "oktmo_identifier_observation_year"] == 2021
    assert pd.isna(census.loc["r2002", "oktmo_observed_at_year"])
    assert pd.isna(census.loc["r2010", "oktmo_native_raw"])


def test_identity_input_with_unknown_status_or_missing_endpoint_fails_closed(tmp_path):
    census, edges, coords, annual, wiki = _inputs(tmp_path)
    edge_frame = pd.read_parquet(edges)
    edge_frame.loc[0, "decision_status"] = "candidate_only"
    edge_frame.to_parquet(edges, index=False)
    with pytest.raises(ValueError, match="decision_status"):
        build_long_table(census, edges, coords, annual, tmp_path / "bad_status.parquet", wiki)

    edge_frame.loc[0, "decision_status"] = "checked_rule_accepted"
    edge_frame.loc[0, "to_source_record_id"] = "absent"
    edge_frame.to_parquet(edges, index=False)
    with pytest.raises(ValueError, match="endpoint"):
        build_long_table(census, edges, coords, annual, tmp_path / "bad_endpoint.parquet", wiki)


def test_unknown_coordinate_admission_status_fails_closed(tmp_path):
    census, edges, coords, annual, wiki = _inputs(tmp_path)
    coord_frame = pd.read_parquet(coords)
    coord_frame.loc[0, "coordinate_admission_status"] = "candidate_only"
    coord_frame.to_parquet(coords, index=False)
    with pytest.raises(ValueError, match="admission status"):
        build_long_table(census, edges, coords, annual, tmp_path / "bad_coords.parquet", wiki)


def test_existing_outputs_are_immutable(tmp_path):
    census, edges, coords, annual, wiki = _inputs(tmp_path)
    output = tmp_path / "existing.parquet"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError, match="overwrite"):
        build_long_table(census, edges, coords, annual, output, wiki)


def test_source_evidence_legacy_aggregate_changes_category_and_blocks_points(tmp_path):
    census, edges, coords, annual, wiki = _inputs(tmp_path)
    source_census = pd.read_parquet(census)
    evidence = pd.DataFrame({
        "source_record_id": source_census.source_record_id,
        "census_year": source_census.census_year,
        "source_evidence_json": [
            '{"is_federal_aggregate": true}' if source_id == "r2021" else '{"is_federal_aggregate": false}'
            for source_id in source_census.source_record_id
        ],
    })
    evidence_path = _write(evidence, tmp_path / "evidence.parquet")
    table, _ = build_long_table(census, edges, coords, annual, tmp_path / "evidence_out.parquet", wiki, evidence_path)
    row = table[table.source_record_id.eq("r2021")].iloc[0]
    assert row.entity_category == "statistical_aggregate"
    assert row.entity_id.startswith("statisticalaggregate:")
    assert pd.isna(row.latitude) and pd.isna(row.longitude)


def test_canonical_point_origin_is_used_and_duplicate_uses_fail(tmp_path):
    census, edges, coords, annual, wiki = _inputs(tmp_path)
    frame = pd.read_parquet(coords)
    frame["point_origin_file"] = "raw/point-source.dbf"
    frame["point_origin_sha256"] = "raw-point-hash"
    frame["point_origin_locator"] = "record:71"
    frame["point_origin_kind"] = "historical_raw_point"
    frame["application_inference_kind"] = "representative_point_spatial_continuity_inference"
    frame["coordinate_admission_status"] = "reviewed_extension_rule_accepted"
    frame.to_parquet(coords, index=False)
    table, _ = build_long_table(census, edges, coords, annual, tmp_path / "origin.parquet", wiki)
    row = table[table.source_record_id.eq("r2021")].iloc[0]
    assert row.point_source_file == "raw/point-source.dbf"
    assert row.point_source_sha256 == "raw-point-hash"
    assert row.point_source_locator == "record:71"
    assert row.coordinate_temporal_basis == "representative_point_spatial_continuity_inference"
    pd.concat([frame, frame]).to_parquet(coords, index=False)
    with pytest.raises(ValueError, match="duplicate target"):
        build_long_table(census, edges, coords, annual, tmp_path / "duplicate.parquet", wiki)
