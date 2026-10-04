"""Regression tests for reviewed relation aliases and point carrier fidelity."""
import csv
from pathlib import Path

import pandas as pd
import pytest

from research_rebuild.mass_linkage import apply_reviewed_mass_extensions_20261004 as app


def _pin(path: Path) -> dict:
    return {"path": str(path), "sha256": app.sha(path)}


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _identity_manifest(tmp_path: Path, relation: str) -> dict:
    candidate = tmp_path / "candidate.csv"
    eligible = tmp_path / "eligible.csv"
    receipt = tmp_path / "review.json"
    _write_csv(candidate, [{
        "source_id": "old:1",
        "target_id": "new:1",
        "family_key": "reviewed_alias_rule",
        "review_status": "eligible",
        "raw_relation": relation,
    }])
    _write_csv(eligible, [{
        "source_id": "old:1",
        "target_id": "new:1",
        "family_key": "reviewed_alias_rule",
    }])
    receipt.write_text("{}", encoding="utf-8")
    spec = {
        "candidate": _pin(candidate),
        "eligible": _pin(eligible),
        "review_receipt": _pin(receipt),
        "candidate_columns": {
            "from": "source_id", "to": "target_id", "family": "family_key",
            "status": "review_status", "relation": "raw_relation",
        },
        "eligible_columns": {
            "from": "source_id", "to": "target_id", "family": "family_key",
        },
        "accepted_candidate_statuses": ["eligible"],
        "canonical_columns": {"relation": "raw_relation"},
    }
    return {"identity_sources": [spec], "_reviewed_at": "2026-10-04T00:00:00+00:00"}


def test_reviewed_same_place_candidate_alias_is_canonicalized(tmp_path):
    loaded, _ = app.load_identity(_identity_manifest(tmp_path, "same_place_candidate"))

    assert len(loaded) == 1
    assert loaded.loc[0, "relation"] == "same_place"
    assert loaded.loc[0, "source_candidate_relation_before_application"] == "same_place_candidate"


def test_unknown_reviewed_relation_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unsupported reviewed identity relation"):
        app.load_identity(_identity_manifest(tmp_path, "similar_name_only"))


def test_lazy_carrier_keeps_full_proof_and_nulls_without_eager_row_materialization(monkeypatch):
    arbitrary_proof = {"raw": ["SQL", None], "locator": {"line": 17}}
    points = pd.DataFrame({
        "target_source_record_id": ["source:1", "source:2"],
        "latitude": [55.1, 56.2],
        "longitude": [37.3, 38.4],
        "nullable_flag": pd.Series([pd.NA, None], dtype=object),
        "arbitrary_proof_json": [arbitrary_proof, {"second": True}],
        "unknown_extra_column": ["kept-1", "kept-2"],
    })
    calls = []
    original = pd.Series.to_dict

    def counted_to_dict(self, *args, **kwargs):
        calls.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pd.Series, "to_dict", counted_to_dict)
    point_ids, get_carrier = app.lazy_point_carriers(points)

    assert point_ids == {"source:1", "source:2"}
    assert calls == []  # No complete carrier rows are materialized until requested.

    carrier = get_carrier("source:1")
    assert len(calls) == 1
    assert set(carrier) == set(points.columns)
    assert carrier["arbitrary_proof_json"] is arbitrary_proof
    assert carrier["unknown_extra_column"] == "kept-1"
    assert pd.isna(carrier["nullable_flag"])
    assert get_carrier("source:1") is carrier
    assert len(calls) == 1


def test_lazy_carrier_rejects_duplicate_targets():
    points = pd.DataFrame({"target_source_record_id": ["dup", "dup"]})
    with pytest.raises(ValueError, match="duplicate carrier targets"):
        app.lazy_point_carriers(points)
