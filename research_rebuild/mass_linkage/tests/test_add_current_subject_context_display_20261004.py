from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from research_rebuild.mass_linkage import add_current_subject_context_display_20261004 as adapter


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _fixtures(tmp_path, monkeypatch, *, duplicate_guid=False, mismatched_qid=False):
    guid = "Q123$statement-guid"
    rows = [
        {
            "observation_id": "secondary:one",
            "record_type": "wiki_literal_series",
            "wikidata_statement_id": guid,
            "current_wikidata_qid": "Q999" if mismatched_qid else "Q123",
            "current_source_record_id": "2021:current:1",
            "current_place_entity_id": "settlement:2021:current:1",
            "observation_year": 1939,
            "population_value_raw_for_secondary_display": "+123",
            "history_population_admitted": False,
            "historical_identity_admitted": False,
            "historical_coordinate_asserted": False,
            "unchanged_source_field": "literal value",
        },
        {
            "observation_id": "secondary:two",
            "record_type": "wiki_literal_series",
            "wikidata_statement_id": "Q456$other-guid",
            "current_wikidata_qid": "Q456",
            "current_source_record_id": "2021:current:2",
            "current_place_entity_id": "settlement:2021:current:2",
            "observation_year": 2002,
            "population_value_raw_for_secondary_display": "+12",
            "history_population_admitted": False,
            "historical_identity_admitted": False,
            "historical_coordinate_asserted": False,
            "unchanged_source_field": "must remain",
        },
    ]
    if duplicate_guid:
        dup = dict(rows[1])
        dup["observation_id"] = "secondary:duplicate"
        dup["wikidata_statement_id"] = guid
        rows.append(dup)
    long_path = tmp_path / "long.parquet"
    pd.DataFrame(rows).to_parquet(long_path, index=False)

    review = {
        "context_use_id": guid,
        "observation_id": "secondary:one",
        "qid": "Q123",
        "statement_guid": guid,
        "observation_year": 1939,
        "P1082_value_raw": "+123",
        "current_source_record_id": "2021:current:1",
        "current_entity_id": "settlement:2021:current:1",
        "current_point_latitude": "56.0",
        "current_point_longitude": "43.0",
        "current_point_target_year": "2021.0",
        "current_point_status": "reviewed_rule_accepted",
        "current_point_coordinate_source": "verified source",
        "current_point_coordinate_provenance": "accepted current point origin",
        "current_point_origin_file": "/raw/source.csv",
        "current_point_origin_sha256": "point-sha",
        "current_point_origin_locator": "row=1",
        "current_point_origin_kind": "source_point",
        "point_context_vs_statement_year": "2021 point is later; no past location asserted",
        "current_subject_point_context_status": "eligible_current_subject_point_context",
        "historical_identity_admitted": "False",
        "historical_coordinate_asserted": "False",
        "history_population_admitted": "False",
        "boundary_comparability_asserted": "False",
        "quantitative_year_eligible_preserved": "False",
    }
    csv_path = tmp_path / "review.csv"
    pd.DataFrame([review]).to_csv(csv_path, index=False)
    csv_sha = _sha(csv_path)
    receipt_path = tmp_path / "review_receipt.json"
    receipt = {
        "status": adapter.TRUSTED_REVIEW_STATUS,
        "result_counts": {"eligible_current_subject_context_uses": 1, "held_current_subject_context_uses": 0},
        "active_seventh_graph": {"sha256": adapter.TRUSTED_IDENTITY_GRAPH_SHA256},
        "active_seventh_points": {"sha256": adapter.TRUSTED_POINT_LEDGER_SHA256},
        "outputs": {"current_subject_context_eligible.csv": {"sha256": csv_sha}},
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_sha = _sha(receipt_path)

    monkeypatch.setattr(adapter, "TRUSTED_CONTEXT_CSV_SHA256", csv_sha)
    monkeypatch.setattr(adapter, "TRUSTED_CONTEXT_RECEIPT_SHA256", receipt_sha)
    monkeypatch.setattr(adapter, "EXPECTED_CONTEXT_ROWS", 1)
    return long_path, csv_path, receipt_path, _sha(long_path), csv_sha, receipt_sha


def test_appends_context_only_columns_and_preserves_all_source_rows(tmp_path, monkeypatch):
    long_path, csv_path, receipt_path, _, csv_sha, receipt_sha = _fixtures(tmp_path, monkeypatch)
    output = tmp_path / "with_context.parquet"
    result = adapter.build_display_adapter(
        long_path, csv_path, output,
        review_receipt_path=receipt_path,
        context_csv_sha256=csv_sha,
        context_receipt_sha256=receipt_sha,
        expected_context_rows=1,
    )
    before = pd.read_parquet(long_path)
    after = pd.read_parquet(output)
    assert len(after) == len(before) == result["output"]["rows"] == 2
    assert after.columns[:len(before.columns)].tolist() == before.columns.tolist()
    pd.testing.assert_frame_equal(after[before.columns], before)
    match = after.loc[after.wikidata_statement_id.eq("Q123$statement-guid")].iloc[0]
    assert match.current_subject_context_status == "eligible_current_subject_point_context"
    assert match.current_subject_context_point_snapshot_year == 2021
    assert match.current_subject_context_point_context_is_at_statement_date is False
    assert not match.historical_identity_admitted
    assert not match.historical_coordinate_asserted
    assert not match.history_population_admitted
    unmatched = after.loc[after.wikidata_statement_id.eq("Q456$other-guid")].iloc[0]
    assert pd.isna(unmatched.current_subject_context_status)
    assert pd.isna(unmatched.current_subject_context_latitude)


def test_refuses_duplicate_statement_guid_in_full_long_input(tmp_path, monkeypatch):
    long_path, csv_path, receipt_path, _, csv_sha, receipt_sha = _fixtures(tmp_path, monkeypatch, duplicate_guid=True)
    with pytest.raises(ValueError, match="statement GUID is not unique"):
        adapter.build_display_adapter(
            long_path, csv_path, tmp_path / "duplicate_out.parquet",
            review_receipt_path=receipt_path,
            context_csv_sha256=csv_sha,
            context_receipt_sha256=receipt_sha,
            expected_context_rows=1,
        )
    assert not (tmp_path / "duplicate_out.parquet").exists()


def test_refuses_qid_mismatch_even_when_statement_guid_matches(tmp_path, monkeypatch):
    long_path, csv_path, receipt_path, _, csv_sha, receipt_sha = _fixtures(tmp_path, monkeypatch, mismatched_qid=True)
    with pytest.raises(ValueError, match="mismatch source GUID/QID/year/value/entity"):
        adapter.build_display_adapter(
            long_path, csv_path, tmp_path / "mismatch_out.parquet",
            review_receipt_path=receipt_path,
            context_csv_sha256=csv_sha,
            context_receipt_sha256=receipt_sha,
            expected_context_rows=1,
        )
    assert not (tmp_path / "mismatch_out.parquet").exists()
