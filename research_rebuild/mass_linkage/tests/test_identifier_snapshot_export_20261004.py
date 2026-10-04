from __future__ import annotations

import json
import hashlib
import struct

import pandas as pd
import pytest

from research_rebuild.mass_linkage.build_identifier_snapshot_export_20261004 import (
    build_snapshot_rows,
    code_role_2021,
    code_role_geo2011,
    load_inputs,
    recover_geokladr_origin_rows,
)


def test_2021_raw_codes_preserve_leading_zeroes_short_literals_and_federal_scope():
    core = pd.DataFrame([
        {"entity_id": "settlement:town-a", "source_record_id": "2021:a", "census_year": 2021},
        {"entity_id": "settlement:territory-b", "source_record_id": "2021:b", "census_year": 2021},
        {"entity_id": "settlement:short-c", "source_record_id": "2021:c", "census_year": 2021},
    ])
    population = pd.DataFrame([
        {"source_record_id": "2021:a", "census_year": 2021, "oktmo": "00123456789", "source_native_id": "00123456789", "population": 10, "source_file": "census-v20251217.parquet", "source_sheet": "parquet", "source_row": 1, "population_scope": "settlement", "source_sha256": "popsha"},
        {"source_record_id": "2021:b", "census_year": 2021, "oktmo": "00006945", "source_native_id": "00006945", "population": 20, "source_file": "census-v20251217.parquet", "source_sheet": "parquet", "source_row": 2, "population_scope": "federal city territory", "source_sha256": "popsha"},
        {"source_record_id": "2021:c", "census_year": 2021, "oktmo": "6945", "source_native_id": "6945", "population": 30, "source_file": "census-v20251217.parquet", "source_sheet": "parquet", "source_row": 3, "population_scope": "settlement", "source_sha256": "popsha"},
    ])
    points = pd.DataFrame(columns=["target_source_record_id", "target_year", "coordinate_admission_status"])
    native, context, holds = build_snapshot_rows(
        core, population, points, population_layer_sha256="layer-sha",
        accepted_points_sha256="points-sha", final_core_sha256="core-sha",
    )
    assert native.identifier_raw.tolist() == ["00123456789", "00006945", "6945"]
    assert native.identifier_role.tolist() == [
        "lexical_length_11_NP_code",
        "lexical_length_8_federal_territory_code_scope_explicit",
        "format_unverified_raw_literal_preserved",
    ]
    assert native.valid_from.isna().all() and native.valid_to.isna().all()
    assert native.identifier_source_version.eq("v20251217").all()
    assert native.identifier_source_release_date.isna().all()
    assert native.identifier_snapshot_version_date_token.eq("2025-12-17").all()
    assert native.linked_population_observation_year.eq(2021).all()
    assert context.empty
    assert holds.empty


def test_2011_geo_code_is_separate_context_and_only_dedups_same_pinned_origin():
    core = pd.DataFrame([
        {"entity_id": "settlement:shared", "source_record_id": "2002:old", "census_year": 2002},
        {"entity_id": "settlement:shared", "source_record_id": "2010:mid", "census_year": 2010},
        {"entity_id": "settlement:shared", "source_record_id": "2021:new", "census_year": 2021},
    ])
    population = pd.DataFrame([
        {"source_record_id": "2021:new", "census_year": 2021, "oktmo": "00006945", "source_native_id": "00006945", "population": 123, "source_file": "2021.parquet", "source_sheet": "parquet", "source_row": 8, "population_scope": "federal city territory", "source_sha256": "pop-row-sha"},
    ])
    points = pd.DataFrame([
        {"target_source_record_id": "2002:old", "target_year": 2002, "coordinate_admission_status": "reviewed_rule_accepted", "raw_geo_oktmo_2011": "12345678", "raw_geo_data_updated": "2011-06-30", "raw_geo_okato_code": "12345678901", "point_origin_file": "/raw/geokladr.zip", "point_origin_sha256": "geo-sha", "point_origin_locator": "GeoKLADR.txt#record=91", "point_origin_kind": "GeoKLADR 2011"},
        {"target_source_record_id": "2010:mid", "target_year": 2010, "coordinate_admission_status": "reviewed_rule_accepted", "raw_geo_oktmo_2011": "12345678", "raw_geo_data_updated": "2011-06-30", "raw_geo_okato_code": "12345678901", "point_origin_file": "/raw/geokladr.zip", "point_origin_sha256": "geo-sha", "point_origin_locator": "GeoKLADR.txt#record=91", "point_origin_kind": "GeoKLADR 2011"},
        {"target_source_record_id": "2021:new", "target_year": 2021, "coordinate_admission_status": "reviewed_rule_accepted", "raw_geo_oktmo_2011": "12345678", "raw_geo_data_updated": "2011-06-30", "raw_geo_okato_code": "12345678901", "point_origin_file": "/raw/geokladr-copy.zip", "point_origin_sha256": "other-geo-sha", "point_origin_locator": "GeoKLADR.txt#record=8", "point_origin_kind": "GeoKLADR 2011"},
    ])
    native, context, holds = build_snapshot_rows(
        core, population, points, snapshot_version="v20251217",
        population_layer_sha256="layer-sha", accepted_points_sha256="points-sha", final_core_sha256="core-sha",
    )
    assert len(native) == 1
    assert native.identifier_raw.iloc[0] == "00006945"
    assert len(context) == 2  # identical origin deduplicated, different source hash/locator retained
    assert set(context.identifier_raw) == {"12345678"}
    assert set(context.identifier_role) == {"municipal_context_of_origin_place_length_8"}
    assert set(context.entity_id) == {"settlement:shared"}
    assert context.valid_from.isna().all() and context.valid_to.isna().all()
    assert context.related_okato_raw.eq("12345678901").all()
    assert context.current_native_identifier_comparison.str.contains("not compared").all()
    assert context.point_target_entity_join_basis.str.contains("context only").all()
    assert json.loads(context.linked_point_target_source_record_ids_json.iloc[0]) == ["2002:old", "2010:mid"]
    assert holds.empty


def test_numeric_native_code_is_rejected_instead_of_reconstructed():
    with pytest.raises(TypeError, match="raw string"):
        code_role_2021(6945, "settlement")


def test_eight_digit_geo_context_does_not_become_2021_territory_code():
    assert code_role_geo2011("00006945") == "municipal_context_of_origin_place_length_8"
    assert code_role_2021("00006945", "settlement") == "format_unverified_length_8_scope_not_explicitly_federal"
    assert code_role_2021("00006945", "federal territory") == "lexical_length_8_federal_territory_code_scope_explicit"
    assert code_role_2021("00006945", "Central Federal District") == "format_unverified_length_8_scope_not_explicitly_federal"


def test_narrow_parquet_loader_projects_final_core_population_and_point_provenance(tmp_path):
    core_path = tmp_path / "final_core.parquet"
    population_path = tmp_path / "population.parquet"
    points_path = tmp_path / "accepted_points.parquet"
    pd.DataFrame([
        {"entity_id": "settlement:x", "source_record_id": "2021:x", "census_year": 2021, "wide_noise": "unused"},
    ]).to_parquet(core_path, index=False)
    pd.DataFrame([
        {"source_record_id": "2021:x", "census_year": 2021, "oktmo": "00001234567", "source_native_id": "00001234567", "population": 7, "source_file": "v20251217.parquet", "source_sheet": "parquet", "source_row": 1, "population_scope": "settlement", "source_sha256": "source-sha", "wide_noise": "unused"},
    ]).to_parquet(population_path, index=False)
    pd.DataFrame([
        {"target_source_record_id": "2021:x", "target_year": 2021, "coordinate_admission_status": "reviewed_rule_accepted", "raw_geo_oktmo_2011": "12345678", "raw_geo_data_updated": "2011-06-30", "raw_geo_okato_code": "87654321", "point_origin_file": "geo.dbf", "point_origin_sha256": "geo-sha", "point_origin_locator": "record=1", "point_origin_kind": "GeoKLADR 2011", "wide_noise": "unused"},
    ]).to_parquet(points_path, index=False)
    core, population, points = load_inputs(core_path, population_path, points_path)
    assert "wide_noise" not in core and "wide_noise" not in population and "wide_noise" not in points
    assert core.attrs["source_path"] == str(core_path)
    assert population.attrs["source_path"] == str(population_path)
    assert points.attrs["source_path"] == str(points_path)
    native, context, holds = build_snapshot_rows(
        core, population, points, population_layer_sha256="layer-sha",
        accepted_points_sha256="points-sha", final_core_sha256="core-sha",
    )
    assert native.identifier_raw.tolist() == ["00001234567"]
    assert context.identifier_raw.tolist() == ["12345678"]
    assert holds.empty


def test_final_long_core_uses_only_census_observation_rows_and_observation_year():
    core = pd.DataFrame([
        {"record_type": "census", "entity_id": "settlement:current", "source_record_id": "2021:source", "observation_year": 2021},
        {"record_type": "wiki_literal_series", "entity_id": None, "source_record_id": "WIKIDATA:Q123:stmt", "observation_year": 1912},
        {"record_type": "annual_official", "entity_id": "settlement:annual-only", "source_record_id": "annual:source", "observation_year": 2020},
    ])
    population = pd.DataFrame([
        {"source_record_id": "2021:source", "census_year": 2021, "oktmo": "00123456789", "source_native_id": "00123456789", "population": 9, "source_file": "2021.parquet", "source_sheet": "parquet", "source_row": 1, "population_scope": "settlement"},
    ])
    points = pd.DataFrame([
        {"target_source_record_id": "2021:source", "target_year": 2021, "coordinate_admission_status": "reviewed_rule_accepted"},
        {"target_source_record_id": "WIKIDATA:Q123:stmt", "target_year": 1912, "coordinate_admission_status": "reviewed_rule_accepted"},
    ])
    native, context, holds = build_snapshot_rows(
        core, population, points, population_layer_sha256="layer-sha",
        accepted_points_sha256="points-sha", final_core_sha256="core-sha",
    )
    assert native.entity_id.tolist() == ["settlement:current"]
    assert context.empty
    assert holds.target_source_record_id.tolist() == ["2021:source"]


def test_null_point_target_year_uses_authoritative_core_source_year_for_2011_context():
    core = pd.DataFrame([
        {"record_type": "census", "entity_id": "settlement:old", "source_record_id": "2002:source", "census_year": 2002},
    ])
    population = pd.DataFrame(columns=[
        "source_record_id", "census_year", "oktmo", "source_native_id", "population",
        "source_file", "source_sheet", "source_row", "population_scope",
    ])
    points = pd.DataFrame([
        {
            "target_source_record_id": "2002:source",
            "target_year": None,
            "coordinate_admission_status": "reviewed_rule_accepted",
            "raw_geo_oktmo_2011": "00123456",
            "raw_geo_data_updated": "2011-06-30",
            "raw_geo_okato_code": "12345678901",
            "point_origin_file": "geo.dbf",
            "point_origin_sha256": "geo-sha",
            "point_origin_locator": "record=91",
            "point_origin_kind": "GeoKLADR 2011",
        },
    ])
    native, context, holds = build_snapshot_rows(
        core, population, points, population_layer_sha256="layer-sha",
        accepted_points_sha256="points-sha", final_core_sha256="core-sha",
    )
    assert native.empty
    assert context.target_source_record_id.tolist() == ["2002:source"]
    assert context.target_year.tolist() == [2002]
    assert context.point_target_year_raw.isna().all()
    assert context.linked_population_observation_year.tolist() == [2002]
    assert context.identifier_raw.tolist() == ["00123456"]
    assert holds.empty
    wrong_year = points.copy()
    wrong_year.loc[0, "target_year"] = 2011
    with pytest.raises(ValueError, match="target_year disagrees with final-core census year"):
        build_snapshot_rows(
            core, population, wrong_year, population_layer_sha256="layer-sha",
            accepted_points_sha256="points-sha", final_core_sha256="core-sha",
        )


def test_null_convenience_geo_fields_replay_exact_pinned_dbf_origin_and_keep_empty_oktmo_missing(tmp_path):
    dbf_path = tmp_path / "okato.dbf"
    fields = [
        ("TER", 2), ("KOD1", 2), ("KOD2", 2), ("KOD3", 2),
        ("OKTMO", 8), ("DATA_UPD", 10), ("SCOKATO", 25), ("TYPE_NP", 1), ("NAME1", 30),
    ]
    header_len = 32 + len(fields) * 32 + 1
    record_len = 1 + sum(width for _, width in fields)
    payload = bytearray(header_len + record_len)
    payload[0] = 0x03
    payload[4:8] = struct.pack("<I", 1)
    payload[8:10] = struct.pack("<H", header_len)
    payload[10:12] = struct.pack("<H", record_len)
    offset = 1
    record = bytearray(record_len)
    record[0] = 0x20
    values = {
        "TER": "01", "KOD1": "02", "KOD2": "03", "KOD3": "04",
        "OKTMO": "", "DATA_UPD": "2011/05/31", "SCOKATO": "с", "TYPE_NP": "1", "NAME1": "Ягодное",
    }
    for i, (name, width) in enumerate(fields):
        descriptor = 32 + i * 32
        payload[descriptor:descriptor + len(name)] = name.encode("ascii")
        payload[descriptor + 11] = ord("C")
        payload[descriptor + 16] = width
        raw_value = values[name].encode("cp1251").ljust(width, b" ")
        record[offset:offset + width] = raw_value
        offset += width
    payload[32 + len(fields) * 32] = 0x0D
    payload[header_len:header_len + record_len] = record
    dbf_path.write_bytes(payload)
    file_sha = hashlib.sha256(payload).hexdigest()
    locator = f"raw_dbf_record_number_1based=1;byte_offset_0based={header_len}"
    points = pd.DataFrame([{
        "target_source_record_id": "2002:source",
        "target_year": None,
        "coordinate_admission_status": "reviewed_rule_accepted",
        "raw_geo_oktmo_2011": None,
        "raw_geo_data_updated": None,
        "raw_geo_okato_code": None,
        "point_origin_file": str(dbf_path),
        "point_origin_sha256": file_sha,
        "point_origin_locator": locator,
        "point_origin_kind": "GeoKLADR 2011",
    }])
    origin_rows = recover_geokladr_origin_rows(points, dbf_path)
    origin = origin_rows[(str(dbf_path.resolve()), file_sha, locator)]
    assert origin["raw_geo_oktmo_2011"] is None
    assert origin["raw_geo_okato_code"] == "01020304"
    assert origin["SCOKATO"] == "с"
    assert origin["NAME1"] == "Ягодное"
    assert origin["raw_geo_origin_record_replay_status"] == "verified_exact_file_sha_and_dbf_record_offset"

    core = pd.DataFrame([{"record_type": "census", "entity_id": "settlement:old", "source_record_id": "2002:source", "census_year": 2002}])
    population = pd.DataFrame(columns=[
        "source_record_id", "census_year", "oktmo", "source_native_id", "population",
        "source_file", "source_sheet", "source_row", "population_scope",
    ])
    native, context, holds = build_snapshot_rows(
        core, population, points, population_layer_sha256="layer-sha",
        accepted_points_sha256="points-sha", final_core_sha256="core-sha", origin_dbf_rows=origin_rows,
    )
    assert native.empty
    assert len(context) == 1
    assert pd.isna(context.identifier_raw.iloc[0])
    assert context.identifier_role.iloc[0] == "missing_raw_geo_2011_OKTMO"
    assert context.raw_geo_oktmo_empty_in_source.tolist() == [True]
    assert context.raw_geo_okato_2011_literal.tolist() == ["01020304"]
    assert context.raw_geo_record_number_1based.tolist() == [1]
    assert context.target_year.tolist() == [2002]
    assert context.point_target_year_raw.isna().all()
    assert holds.empty
