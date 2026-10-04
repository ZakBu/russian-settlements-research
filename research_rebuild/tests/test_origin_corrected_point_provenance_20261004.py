"""Regression: distinct Tochno and literal GeoNames origins stay distinct."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


READY = Path(
    "/workspace/settlements-work/continuation_20261004/root/next_batch_manifest_preparation/"
    "fourth_origin_corrected_20261004/ready_bundle"
)
TOCHNO = "/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet"
GN_ZIP = "/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip"
TOCHNO_SHA = "86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14"
GN_ZIP_SHA = "9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4"


def _read(name):
    return pd.read_csv(READY / name, dtype="string", keep_default_na=False, engine="python")


def test_origin_corrected_mixed_provider_application_matches_native_rows():
    tochno = _read("tochno_207_origin_corrected_candidate_points.csv")
    geonames = _read("geonames_67_origin_corrected_candidate_points.csv")
    approved_tochno = _read("tochno_79_origin_corrected_approved_points.csv")
    approved_gn = _read("geonames_28_origin_corrected_approved_points.csv")
    native = _read("v7_point_origin_native_join_checks_274.csv")

    assert len(tochno) == 207 and len(geonames) == 67
    assert len(approved_tochno) == 79 and len(approved_gn) == 28
    assert tochno.target_source_record_id.is_unique and geonames.target_source_record_id.is_unique
    assert native.point_use_id.is_unique and len(native) == 274
    assert native.origin_record_locator_verified.astype(str).str.lower().eq("true").all()

    assert set(tochno.point_origin_file) == {TOCHNO}
    assert set(tochno.point_origin_sha256) == {TOCHNO_SHA}
    assert tochno.coordinate_provider.eq("Tochno 2021 selected raw Parquet source point").all()
    assert tochno.point_origin_locator.str.contains("parquet_row_1based=", regex=False).all()
    assert tochno.point_origin_locator.str.contains("raw_payload_sha256=", regex=False).all()
    assert (tochno.latitude.astype(float) == tochno.native_join_latitude.astype(float)).all()
    assert (tochno.longitude.astype(float) == tochno.native_join_longitude.astype(float)).all()
    assert (tochno.source_raw_payload_sha256 == tochno.native_join_payload_sha256).all()

    assert set(geonames.point_origin_file) == {GN_ZIP}
    assert set(geonames.point_origin_sha256) == {GN_ZIP_SHA}
    assert geonames.coordinate_provider.eq(
        "GeoNames RU 2026-09-07 raw PPL-family coordinate; geonameid is a raw-row locator only"
    ).all()
    assert geonames.point_origin_locator.str.contains("member=RU.txt", regex=False).all()
    assert geonames.point_origin_locator.str.contains("geonameid=", regex=False).all()
    assert geonames.point_origin_locator.str.contains("line_sha256=", regex=False).all()
    assert geonames.point_origin_geonameid.ne("").all()
    assert geonames.point_origin_line_sha256.str.len().eq(64).all()
    assert (geonames.latitude.astype(float) == geonames.native_join_latitude.astype(float)).all()
    assert (geonames.longitude.astype(float) == geonames.native_join_longitude.astype(float)).all()
    assert geonames.coordinate_source_record_id.eq("").all()

    candidates = pd.concat([tochno, geonames], ignore_index=True)
    by_use = candidates.set_index("point_use_id")
    for approved in (approved_tochno, approved_gn):
        for row in approved.to_dict("records"):
            candidate = by_use.loc[row["point_use_id"]]
            assert row["target_source_record_id"] == candidate.target_source_record_id
            assert float(row["latitude"]) == float(candidate.latitude)
            assert float(row["longitude"]) == float(candidate.longitude)
            assert row["origin_file"] == candidate.point_origin_file
            assert row["origin_sha256"] == candidate.point_origin_sha256
            assert row["origin_locator"] == candidate.point_origin_locator

    witnesses = geonames.geo_names_whole_ADM1_witnesses_json.map(json.loads)
    for (_, candidate), witness_set in zip(geonames.iterrows(), witnesses):
        witness = next(w for w in witness_set if str(w["geonameid"]) == candidate.point_origin_geonameid)
        assert float(candidate.latitude) == float(witness["latitude"])
        assert float(candidate.longitude) == float(witness["longitude"])
        assert witness["line_sha256"] == candidate.point_origin_line_sha256

