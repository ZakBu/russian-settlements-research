#!/usr/bin/env python3
"""Resolve GeoNames archive-member pseudo-paths to the actual pinned ZIP file.

Metadata-only reconciliation for the exact 15 rows added by the reviewed
five-seed point application. Coordinates, statuses, targets, and all 414,875
pre-existing point rows must remain value-identical.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import zipfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

BASE_POINTS = Path("/workspace/settlements-work/continuation_20261004/accepted_mass_ninth_reviewed_legacy202/accepted_point_uses.parquet")
APPLIED_DIR = Path("/workspace/settlements-work/continuation_20261004/root/accepted_point_gap_five_reviewed")
REVIEW_DIR = Path("/workspace/settlements-work/continuation_20261004/independent_review/point_gap_five_2021_review")
ZIP_PATH = Path("/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip")
OUTPUT = Path("/workspace/settlements-work/continuation_20261004/root/accepted_point_gap_five_reviewed_origin_reconciled")

INPUT_LEDGER_SHA = "65bb713b9fe30c06b8d882b4be4bac03e13187254949c82d34cdab83d85b0e37"
INPUT_RECEIPT_SHA = "650e6df94855ae102eb7038a4af249c586413334c08449f7e18552c7e8fcf71d"
BASE_LEDGER_SHA = "264812092d0bc1df17929d945609d6f12f096ab28d085a85bb26dee09cc17d5b"
REVIEW_SEEDS_SHA = "7a51b0244cf06cd946a81b01f1cce41a3ce1daa3b4af90c19543f311972603a9"
REVIEW_RECEIPT_SHA = "30deddc0e41a86680f243724783124275a9cd902d875ea987fa240327312ca35"
ZIP_SHA = "9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4"
BASELINE_ROWS = 414875
LEDGER_ROWS = 414890
RECONCILED_FIELDS = {
    "point_origin_file", "coordinate_source_file", "point_claim_artifact_file",
    "geonames_source_file", "coordinate_provenance",
}
ROW_VALIDATION_FIELDS = RECONCILED_FIELDS | {
    "point_origin_locator", "coordinate_source_sha256", "point_origin_sha256",
}
UNCHANGED_GUARD_FIELDS = {
    "target_source_record_id", "target_year", "latitude", "longitude",
    "coordinate_admission_status", "coordinate_quality", "coordinate_source",
    "coordinate_provider", "coordinate_provider_id", "coordinate_source_sha256",
    "point_origin_sha256", "point_origin_locator", "point_origin_kind",
    "coordinate_source_locator", "coordinate_source_input_artifact_sha256",
    "coordinate_measurement_date_unknown", "direct_historical_coordinate_measurement",
    "boundary_comparability_asserted", "population_scope_comparability_asserted",
    "application_inference_kind", "inference_identity_path_decision_ids_json",
    "inference_identity_path_from_source_record_id", "inference_identity_path_to_source_record_id",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def file_and_member(review_label: str) -> tuple[Path, str]:
    if "!" not in review_label:
        raise ValueError(f"review packet origin label lacks archive member delimiter: {review_label!r}")
    file_label, member = review_label.split("!", 1)
    path = Path(file_label)
    if not path.is_file() or member != "RU.txt":
        raise ValueError(f"review origin cannot be resolved to expected GeoNames archive: {review_label!r}")
    return path, member


def verify_archive_lines(zip_path: Path, seeds: list[dict[str, str]]) -> list[dict[str, Any]]:
    if sha(zip_path) != ZIP_SHA:
        raise ValueError("GeoNames source archive hash mismatch")
    if any(Path(r["proposed_point_source_path"].split("!", 1)[0]) != zip_path for r in seeds):
        raise ValueError("review rows do not refer to the pinned archive file")
    need = {int(r["proposed_point_line_1based"]): r for r in seeds}
    replayed: list[dict[str, Any]] = []
    byte_offset = 0
    with zipfile.ZipFile(zip_path) as zf:
        if "RU.txt" not in zf.namelist():
            raise ValueError("pinned GeoNames ZIP has no RU.txt member")
        with zf.open("RU.txt", "r") as member:
            for line_no, raw in enumerate(member, start=1):
                if line_no in need:
                    row = need[line_no]
                    content = raw.rstrip(b"\r\n")
                    actual_line_sha = hashlib.sha256(raw).hexdigest()
                    start = byte_offset
                    end = start + len(raw)
                    fields = content.decode("utf-8").split("\t")
                    if len(fields) < 15:
                        raise ValueError(f"GeoNames row {line_no} has an unexpected field count")
                    checks = {
                        "line_sha256": actual_line_sha == row["proposed_point_line_sha256"],
                        "byte_start": start == int(row["proposed_point_byte_start_0based"]),
                        "byte_end": end == int(row["proposed_point_byte_end_0based"]),
                        "geonameid": fields[0] == row["proposed_point_geonameid"],
                        "raw_name": fields[1] == row["proposed_point_raw_name"],
                        "latitude": float(fields[4]) == float(row["proposed_point_latitude"]),
                        "longitude": float(fields[5]) == float(row["proposed_point_longitude"]),
                        "feature_class": fields[6] == "P",
                        "feature_code": fields[7] == row["proposed_point_feature_code"] == "PPL",
                        "country": fields[8] == "RU",
                        "admin1": fields[10] == row["proposed_point_admin1"],
                    }
                    if not all(checks.values()):
                        bad = [k for k, ok in checks.items() if not ok]
                        raise ValueError(f"GeoNames line {line_no} failed origin replay: {bad}")
                    replayed.append({
                        "target_source_record_id": row["target_source_record_id"],
                        "review_packet_origin_label": row["proposed_point_source_path"],
                        "archive_file": str(zip_path),
                        "archive_file_sha256": ZIP_SHA,
                        "archive_member": "RU.txt",
                        "line_1based": line_no,
                        "byte_start_0based": start,
                        "byte_end_0based": end,
                        "raw_line_sha256": actual_line_sha,
                        "geonameid_locator_only": fields[0],
                        "raw_name": fields[1],
                        "feature_code": fields[7],
                        "latitude": float(fields[4]),
                        "longitude": float(fields[5]),
                        "origin_replay_status": "exact_raw_member_line_and_coordinate_verified",
                    })
                byte_offset += len(raw)
    if len(replayed) != 5 or {r["target_source_record_id"] for r in replayed} != {r["target_source_record_id"] for r in seeds}:
        raise ValueError("did not replay exactly the five approved GeoNames source lines")
    return replayed


def rewrite_metadata(row: dict[str, Any], expected_label: str, archive_path: Path, member: str = "RU.txt") -> dict[str, Any]:
    if row.get("point_origin_file") != expected_label:
        raise ValueError("input point origin does not match the reviewed archive-member label")
    if row.get("coordinate_source_file") != expected_label or row.get("point_claim_artifact_file") != expected_label or row.get("geonames_source_file") != expected_label:
        raise ValueError("input source paths diverge from the reviewed archive-member label")
    if row.get("point_origin_locator") is None or f"member={member};" not in str(row["point_origin_locator"]):
        raise ValueError("point-origin locator does not preserve the raw archive member")
    if row.get("coordinate_source_sha256") != ZIP_SHA or row.get("point_origin_sha256") != ZIP_SHA:
        raise ValueError("point-origin source hashes do not match the pinned archive")
    old_provenance = str(row.get("coordinate_provenance") or "")
    addition = f"archive origin resolved: review_packet_origin_label={expected_label}; actual_archive_file={archive_path}; archive_member={member}; raw source row replay verified"
    if addition not in old_provenance:
        old_provenance = (old_provenance + "; " + addition).strip("; ")
    result = dict(row)
    for field in ("point_origin_file", "coordinate_source_file", "point_claim_artifact_file", "geonames_source_file"):
        result[field] = str(archive_path)
    result["coordinate_provenance"] = old_provenance
    return result


def _slice_next(iterator, current, offset, count):
    remaining, slices = count, []
    batch = current
    while remaining:
        if batch is None:
            raise ValueError("output ended before matching input rows")
        take = min(remaining, batch.num_rows - offset)
        slices.append(batch.slice(offset, take))
        offset += take
        remaining -= take
        if offset == batch.num_rows:
            batch = next(iterator, None)
            offset = 0
    return slices, batch, offset


def verify_same_rows(left_path: Path, right_path: Path, allowed_target_fields: dict[str, dict[str, Any]] | None = None) -> int:
    """Compare ledgers rowwise, allowing only explicitly pinned metadata changes."""
    allowed_target_fields = allowed_target_fields or {}
    left, right = pq.ParquetFile(left_path), pq.ParquetFile(right_path)
    if left.metadata.num_rows != right.metadata.num_rows:
        raise ValueError("row count changed during metadata reconciliation")
    if left.schema_arrow != right.schema_arrow:
        raise ValueError("schema changed during metadata reconciliation")
    li, ri = iter(left.iter_batches(batch_size=8192)), iter(right.iter_batches(batch_size=8192))
    lb, rb = next(li, None), next(ri, None)
    lo = ro = compared = 0
    schema = left.schema_arrow
    while lb is not None:
        n = lb.num_rows
        left_batch = lb.slice(lo, n - lo) if lo else lb
        n = left_batch.num_rows
        right_slices, rb, ro = _slice_next(ri, rb, ro, n)
        right_table = pa.Table.from_batches(right_slices, schema=schema)
        left_table = pa.Table.from_batches([left_batch], schema=schema)
        if left_table.equals(right_table):
            compared += n
        else:
            lid = left_table["target_source_record_id"].to_pylist()
            rid = right_table["target_source_record_id"].to_pylist()
            if lid != rid:
                raise ValueError("target source IDs changed or reordered")
            for col in schema.names:
                if col == "target_source_record_id":
                    continue
                lv, rv = left_table[col].to_pylist(), right_table[col].to_pylist()
                for i, (a, b) in enumerate(zip(lv, rv)):
                    if a == b:
                        continue
                    sid = str(lid[i])
                    allowed = allowed_target_fields.get(sid, {})
                    if col not in allowed or b != allowed[col]:
                        raise ValueError(f"unexpected row-value change at {sid}.{col}")
            compared += n
        lo += left_batch.num_rows
        if lo == lb.num_rows:
            lb = next(li, None)
            lo = 0
    if compared != left.metadata.num_rows:
        raise ValueError("not all source rows were compared")
    return compared


def run(input_dir: Path, base_path: Path, review_dir: Path, zip_path: Path, output: Path) -> dict[str, Any]:
    started = time.monotonic()
    input_path = input_dir / "accepted_point_uses.parquet"
    input_receipt_path = input_dir / "receipt.json"
    seed_path = review_dir / "eligible_point_seeds.csv"
    review_receipt_path = review_dir / "review_receipt.json"
    for path, expected, label in (
        (input_path, INPUT_LEDGER_SHA, "prior accepted point ledger"),
        (input_receipt_path, INPUT_RECEIPT_SHA, "prior application receipt"),
        (base_path, BASE_LEDGER_SHA, "414,875-row base point ledger"),
        (seed_path, REVIEW_SEEDS_SHA, "independent eligible seed list"),
        (review_receipt_path, REVIEW_RECEIPT_SHA, "independent point review receipt"),
        (zip_path, ZIP_SHA, "GeoNames ZIP origin"),
    ):
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"pinned input mismatch: {label} ({path})")
    seeds = read_csv(seed_path)
    if len(seeds) != 5:
        raise ValueError("expected exactly five independently reviewed point seeds")
    replays = verify_archive_lines(zip_path, seeds)
    old_by_target = {r["target_source_record_id"]: r["proposed_point_source_path"] for r in seeds}
    if len(old_by_target) != 5:
        raise ValueError("duplicate reviewed target in seed list")
    input_pf = pq.ParquetFile(input_path)
    schema = input_pf.schema_arrow
    missing_fields = RECONCILED_FIELDS - set(schema.names)
    if missing_fields:
        raise ValueError(f"input point ledger is missing expected metadata fields: {sorted(missing_fields)}")
    prior_receipt = json.loads(input_receipt_path.read_text(encoding="utf-8"))
    if prior_receipt.get("point_use_rows_appended") != 15 or prior_receipt.get("baseline_point_rows") != BASELINE_ROWS:
        raise ValueError("prior application receipt does not describe the exact five-seed/15-row append")
    # Load only the fifteen appended targets, checking original metadata and hard invariants.
    target_ids = set()
    if len(prior_receipt.get("outputs", {}).get("point_use_additions.csv", {})) == 0:
        # The ledger receipt lists the CSV output hash; the frozen CSV supplies exact target IDs.
        additions_csv = input_dir / "point_use_additions.csv"
    else:
        additions_csv = input_dir / "point_use_additions.csv"
    additions_rows = read_csv(additions_csv)
    target_ids = {r["target_source_record_id"] for r in additions_rows}
    if len(target_ids) != 15:
        raise ValueError("prior append target list is not exactly 15 rows")
    seed_by_id = {r["target_source_record_id"]: r for r in seeds}
    labels_by_target = {}
    for row in additions_rows:
        sid = row["target_source_record_id"]
        seed_id = row["reviewed_current_seed_source_record_id"]
        if seed_id not in seed_by_id:
            raise ValueError(f"appended target has no approved reviewed seed: {sid}")
        source_path, member = file_and_member(seed_by_id[seed_id]["proposed_point_source_path"])
        if source_path != zip_path or member != "RU.txt":
            raise ValueError(f"unapproved origin path for target {sid}")
        labels_by_target[sid] = seed_by_id[seed_id]["proposed_point_source_path"]
    if len(target_ids & set(old_by_target)) != 5:
        raise ValueError("all five direct current seeds must be in the appended target list")

    target_index = schema.get_field_index("target_source_record_id")
    source = pq.ParquetFile(input_path)
    output.mkdir(parents=True, exist_ok=False)
    result_path = output / "accepted_point_uses.parquet"
    count, changed, modified_fields = 0, 0, set()
    actual_file = str(zip_path)
    allowed_values: dict[str, dict[str, Any]] = {}
    receipt_origin = {r["target_source_record_id"]: r for r in replays}
    with pq.ParquetWriter(result_path, schema, compression="zstd") as writer:
        for batch in source.iter_batches(batch_size=8192):
            ids = [str(v) for v in batch.column(target_index).to_pylist()]
            row_indices = {i: sid for i, sid in enumerate(ids) if sid in target_ids}
            arrays = list(batch.columns)
            rewritten_by_index: dict[int, dict[str, Any]] = {}
            for idx, sid in row_indices.items():
                old_row = {"target_source_record_id": sid}
                for f_i, f in enumerate(schema):
                    if f.name in ROW_VALIDATION_FIELDS:
                        old_row[f.name] = arrays[f_i][idx].as_py()
                rewritten_by_index[idx] = rewrite_metadata(old_row, labels_by_target[sid], zip_path)
            for col_i, field in enumerate(schema):
                if field.name not in RECONCILED_FIELDS or not row_indices:
                    continue
                vals = arrays[col_i].to_pylist()
                for idx, sid in row_indices.items():
                    rec = rewritten_by_index[idx]
                    old_value = arrays[col_i][idx].as_py()
                    vals[idx] = rec[field.name]
                    if old_value != rec[field.name]:
                        allowed_values.setdefault(sid, {})[field.name] = rec[field.name]
                        modified_fields.add(field.name)
                arrays[col_i] = pa.array(vals, type=field.type)
            writer.write_batch(pa.RecordBatch.from_arrays(arrays, schema=schema))
            changed += len(row_indices)
            count += batch.num_rows
    if count != LEDGER_ROWS or changed != 15:
        raise ValueError(f"expected 414,890 input rows and 15 metadata reconciliations, got {count}/{changed}")
    # Full ledger rowwise comparison proves no coordinate, status, target, or any
    # unrelated proof value changed; only the five explicitly reconciled strings may differ.
    compared = verify_same_rows(input_path, result_path, allowed_values)
    # Also prove every source row in the original 414,875-row base is byte-value unchanged.
    base_pf = pq.ParquetFile(base_path)
    output_pf = pq.ParquetFile(result_path)
    if base_pf.metadata.num_rows != BASELINE_ROWS or output_pf.metadata.num_rows != LEDGER_ROWS:
        raise ValueError("unexpected baseline or final row count")
    # Compare the original base row prefix to the reconciled output.  The first
    # 414,875 rows must be identical in every column, including optional fields.
    original = base_pf.iter_batches(batch_size=8192)
    final = iter(output_pf.iter_batches(batch_size=8192))
    final_batch = next(final, None)
    final_offset = 0
    baseline_compared = 0
    for old in original:
        remain, pieces = old.num_rows, []
        while remain:
            if final_batch is None:
                raise ValueError("final output ended before original baseline prefix")
            take = min(remain, final_batch.num_rows - final_offset)
            pieces.append(final_batch.slice(final_offset, take))
            final_offset += take
            remain -= take
            if final_offset == final_batch.num_rows:
                final_batch = next(final, None)
                final_offset = 0
        if not pa.Table.from_batches([old], schema=base_pf.schema_arrow).equals(pa.Table.from_batches(pieces, schema=schema)):
            raise ValueError("one or more of the original 414,875 point rows changed")
        baseline_compared += old.num_rows
    if baseline_compared != BASELINE_ROWS:
        raise ValueError("not all original baseline points were verified")

    audit_rows = []
    for row in additions_rows:
        sid = row["target_source_record_id"]
        replay = receipt_origin[row["reviewed_current_seed_source_record_id"]]
        audit_rows.append({
            "target_source_record_id": sid,
            "target_year": row["target_year"],
            "reviewed_current_seed_source_record_id": row["reviewed_current_seed_source_record_id"],
            "review_packet_origin_label": labels_by_target[sid],
            "actual_archive_file": str(zip_path),
            "archive_file_sha256": ZIP_SHA,
            "archive_member": "RU.txt",
            "archive_member_line_1based": replay["line_1based"],
            "archive_member_byte_start_0based": replay["byte_start_0based"],
            "archive_member_byte_end_0based": replay["byte_end_0based"],
            "raw_line_sha256": replay["raw_line_sha256"],
            "coordinate_latitude": replay["latitude"],
            "coordinate_longitude": replay["longitude"],
            "metadata_reconciled_status": "actual_archive_file_plus_member_locator_verified",
        })
    audit_path = output / "origin_path_reconciliation.csv"
    with audit_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(audit_rows[0]))
        w.writeheader(); w.writerows(audit_rows)
    elapsed = time.monotonic() - started
    receipt = {
        "status": "five_seed_point_origin_metadata_reconciled_actual_archive_path",
        "input_ledger_sha256": INPUT_LEDGER_SHA,
        "prior_application_receipt_sha256": INPUT_RECEIPT_SHA,
        "accepted_base_point_ledger_sha256": BASE_LEDGER_SHA,
        "reviewed_seed_list_sha256": REVIEW_SEEDS_SHA,
        "independent_review_receipt_sha256": REVIEW_RECEIPT_SHA,
        "geonames_archive_file": str(zip_path),
        "geonames_archive_sha256": ZIP_SHA,
        "archive_member": "RU.txt",
        "raw_archive_lines_replayed": len(replays),
        "target_metadata_rows_reconciled": changed,
        "reconciled_path_fields": sorted(RECONCILED_FIELDS),
        "input_point_rows": count,
        "final_point_rows": pq.ParquetFile(result_path).metadata.num_rows,
        "original_baseline_rows_verified_unchanged": baseline_compared,
        "prior_ledger_rows_value_compared": compared,
        "only_metadata_fields_changed_on_exact_15_targets": True,
        "coordinate_values_changed": 0,
        "coordinate_status_values_changed": 0,
        "source_record_ids_changed": 0,
        "selected_population_or_identity_graph_changed": False,
        "review_packet_origin_label_preserved_in_coordinate_provenance": True,
        "archive_member_and_offsets_preserved_in_locators": True,
        "provider_identifier_binding_asserted": False,
        "elapsed_seconds_measured": round(elapsed, 6),
        "script_sha256": sha(Path(__file__)),
        "outputs": {
            "accepted_point_uses.parquet": {"sha256": sha(result_path), "bytes": result_path.stat().st_size},
            "origin_path_reconciliation.csv": {"sha256": sha(audit_path), "bytes": audit_path.stat().st_size},
        },
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, default=APPLIED_DIR)
    p.add_argument("--base-points", type=Path, default=BASE_POINTS)
    p.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    p.add_argument("--zip", dest="zip_path", type=Path, default=ZIP_PATH)
    p.add_argument("--output", type=Path, default=OUTPUT)
    args = p.parse_args()
    print(json.dumps(run(args.input_dir, args.base_points, args.review_dir, args.zip_path, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
