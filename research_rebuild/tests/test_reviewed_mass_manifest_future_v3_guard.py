"""Read-only regression checks for the fourth-batch write allowlist."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PREP = REPO_ROOT / "research_rebuild" / "mass_linkage" / "prepare_reviewed_mass_manifest_future_v3_20261004.py"
INPUTS = None


def load_module():
    spec = importlib.util.spec_from_file_location("fourth_manifest_prep", PREP)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load prep helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = load_module()
    pins = {str((HERE / "test_reviewed_mass_manifest_future_v3_guard.py").resolve()): hashlib.sha256((HERE / "test_reviewed_mass_manifest_future_v3_guard.py").read_bytes()).hexdigest()}
    result = module.run_write_guard_regression(pins)
    allowed = module.output_path(module.OUTPUT_ROOT / "regression_target_only_not_written.txt")
    if not allowed.is_relative_to(module.OUTPUT_ROOT):
        raise AssertionError("allowlisted destination did not remain below output root")
    for allowed_root in module.ALLOWED_OUTPUT_ROOTS:
        module.OUTPUT_ROOT = allowed_root
        resolved = module.output_path(allowed_root / "regression_target_only_not_written.txt")
        if not resolved.is_relative_to(allowed_root):
            raise AssertionError(f"allowlisted output root was rejected: {allowed_root}")
    module.OUTPUT_ROOT = next(iter(module.ALLOWED_OUTPUT_ROOTS))
    if result["pinned_input_count"] != len(pins) or not result["pinned_inputs_unchanged"]:
        raise AssertionError("input hash preservation regression failed")
    print(json.dumps({**result, "allowed_output_path_resolves_inside_root": True,
                      "no_output_file_written": not allowed.exists()}, ensure_ascii=False, indent=2))


def test_output_guard_rejects_review_escape_symlink_and_overwrite(tmp_path, monkeypatch):
    module = load_module()
    root = tmp_path / "ready_bundle"
    root.mkdir()
    monkeypatch.setattr(module, "OUTPUT_ROOT", root.resolve())

    review = tmp_path / "independent_review.csv"
    review.write_bytes(b"approved bytes\n")
    before = hashlib.sha256(review.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        module.output_path(review)
    with pytest.raises(ValueError):
        module.output_path(root / ".." / "escape.json")

    symlink = root / "linked_directory"
    symlink.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        module.output_path(symlink / "review.json")

    existing = root / "existing.json"
    existing.write_bytes(b"keep existing bytes")
    with pytest.raises(FileExistsError):
        module.write_bytes_new(existing, b"replacement")
    assert existing.read_bytes() == b"keep existing bytes"
    assert hashlib.sha256(review.read_bytes()).hexdigest() == before


def test_hash_snapshot_detects_change_without_touching_source(tmp_path):
    module = load_module()
    source = tmp_path / "input.csv"
    source.write_bytes(b"source\n")
    wrong_pin = {str(source): "0" * 64}
    with pytest.raises(ValueError, match="hash mismatch"):
        module.hash_snapshot(wrong_pin, "unit regression")
    assert source.read_bytes() == b"source\n"


def test_canonical_preflight_reads_authoritative_source_flags(tmp_path):
    import pandas as pd

    module = load_module()
    eligible = tmp_path / "eligible.csv"
    eligible.write_text(
        "from_source_record_id,to_source_record_id\nold-1,current-1\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "source_evidence.parquet"
    frame = pd.DataFrame([{
        "source_record_id": "old-1",
        "source_evidence_json": json.dumps({"is_additive_settlement_record": True,
            "is_federal_aggregate": False, "legacy_verified_successor_settlement_id": None,
            "legacy_same_year_collision": False}),
    }, {
        "source_record_id": "current-1",
        "source_evidence_json": json.dumps({"is_additive_settlement_record": True,
            "is_federal_aggregate": False, "legacy_verified_successor_settlement_id": None,
            "legacy_same_year_collision": False}),
    }])
    frame.to_parquet(evidence, index=False)
    evidence_sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
    spec = {"frozen": {"source_evidence": {"path": str(evidence), "sha256": evidence_sha}},
            "wk_v2_identity_source": {"eligible": {"path": str(eligible)},
                "eligible_columns": {"from": "from_source_record_id", "to": "to_source_record_id"}}}
    passed = module.preflight_frozen_identity_endpoint_flags(spec)
    assert passed["status"] == "passed_no_canonical_endpoint_hardflags"
    assert passed["evidence_rows_checked"] == 2
    frame.loc[frame.source_record_id == "old-1", "source_evidence_json"] = json.dumps({
        "is_additive_settlement_record": True, "is_federal_aggregate": False,
        "legacy_verified_successor_settlement_id": None, "legacy_same_year_collision": True})
    frame.to_parquet(evidence, index=False)
    bad_sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
    with_flag = evidence.read_bytes()
    spec["frozen"]["source_evidence"]["sha256"] = bad_sha
    with pytest.raises(ValueError, match="same_year_collision"):
        module.preflight_frozen_identity_endpoint_flags(spec)
    assert evidence.read_bytes() == with_flag


if __name__ == "__main__":
    main()
