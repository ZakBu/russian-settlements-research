"""Read-only regression checks for the fourth-batch write allowlist."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PREP = REPO_ROOT / "research_rebuild" / "mass_linkage" / "prepare_reviewed_mass_manifest_20261004.py"
INPUTS = Path(
    "/workspace/settlements-work/continuation_20261004/root/next_batch_manifest_preparation/fourth_20261004/preparation_inputs.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("fourth_manifest_prep", PREP)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load prep helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = load_module()
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    pins = module.collect_inputs(inputs)
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


if __name__ == "__main__":
    main()
