"""Prepare reviewed mass-extension manifests with source-write guards.

The only write targets are this package's explicit `ready_bundle/` and
`future_v2_ready_bundle/` directories. All source,
review, and base files are SHA-pinned, rehashed before/after preparation, and
never opened for writing. This script produces a manifest; it never applies it.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import pandas as pd


PACKAGE_ROOT = Path(__file__).resolve().parent
FOURTH_WORK_ROOT = Path(
    "/workspace/settlements-work/continuation_20261004/root/next_batch_manifest_preparation/fourth_20261004"
).resolve()
ALLOWED_OUTPUT_ROOTS = {
    (FOURTH_WORK_ROOT / "ready_bundle").resolve(),
    (FOURTH_WORK_ROOT / "future_v2_ready_bundle").resolve(),
}
OUTPUT_ROOT = (FOURTH_WORK_ROOT / "ready_bundle").resolve()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def output_path(relative_or_absolute: Path) -> Path:
    """Allow writes only to plain files below the single package output root."""
    requested = Path(relative_or_absolute)
    if not requested.is_absolute():
        requested = OUTPUT_ROOT / requested
    root = OUTPUT_ROOT.resolve()
    cursor = requested
    while cursor != cursor.parent:
        if cursor.exists() and cursor.is_symlink():
            raise ValueError(f"refusing symlink in output path: {cursor}")
        if cursor == root:
            break
        cursor = cursor.parent
    resolved = requested.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"write outside exact output allowlist refused: {requested}") from exc
    if not relative.parts:
        raise ValueError("refusing to write over output root")
    if requested.exists() and (requested.is_symlink() or not requested.is_file()):
        raise ValueError(f"output destination is not a regular file: {requested}")
    return resolved


def write_bytes_new(path: Path, content: bytes) -> None:
    target = output_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(content)


def write_json_new(path: Path, value: dict) -> None:
    write_bytes_new(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype="string", keep_default_na=False, engine="python")


def collect_inputs(inputs: dict) -> dict[str, str]:
    pins: dict[str, str] = {}
    for pin in inputs["pinned_inputs"]:
        path = str(Path(pin["path"]).resolve())
        expected = str(pin["sha256"])
        if path in pins and pins[path] != expected:
            raise ValueError(f"conflicting hashes supplied for pinned input {path}")
        pins[path] = expected
    return pins


def hash_snapshot(pins: dict[str, str], stage: str) -> dict[str, str]:
    snapshot = {}
    for path, expected in pins.items():
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"{stage}: pinned source missing: {source}")
        actual = file_sha(source)
        if actual != expected:
            raise ValueError(f"{stage}: pinned source hash mismatch {source}: {actual} != {expected}")
        snapshot[path] = actual
    return snapshot


def run_write_guard_regression(pins: dict[str, str]) -> dict:
    """Prove an actual review path and an outside-root path are refused."""
    before = hash_snapshot(pins, "write-guard regression before")
    protected_review = Path(next(iter(pins)))
    refused_review = False
    refused_escape = False
    try:
        output_path(protected_review)
    except ValueError:
        refused_review = True
    try:
        output_path(OUTPUT_ROOT.parent / "forbidden_fourth_manifest_escape.txt")
    except ValueError:
        refused_escape = True
    if not refused_review or not refused_escape:
        raise AssertionError("output allowlist regression failed to refuse unsafe destinations")
    after = hash_snapshot(pins, "write-guard regression after")
    if before != after:
        raise AssertionError("write-guard regression changed a source/review input")
    # Hash-mismatch detection is tested using a deliberately false expected hash;
    # it is read-only and does not touch the pinned file.
    false_pin = {str(protected_review): "0" * 64}
    mismatch_detected = False
    try:
        hash_snapshot(false_pin, "write-guard mismatch regression")
    except ValueError:
        mismatch_detected = True
    if not mismatch_detected:
        raise AssertionError("hash mismatch regression did not detect a false pin")
    return {"status": "passed", "review_destination_refused": refused_review,
            "outside_root_destination_refused": refused_escape,
            "false_hash_detected": mismatch_detected,
            "pinned_inputs_unchanged": True, "pinned_input_count": len(pins)}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp, dl = p2 - p1, math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def make_point_adapter_and_scoped_approval(inputs: dict, pins: dict[str, str], report: dict):
    spec = inputs["gnv7_point_source"]
    candidate_path = Path(spec["candidate"]["path"]).resolve()
    eligible_path = Path(spec["eligible"]["path"]).resolve()
    origin_path = Path(spec["origin"]["path"]).resolve()
    candidate = read_csv(candidate_path)
    eligible = read_csv(eligible_path)
    cc, ec = spec["candidate_columns"], spec["eligible_columns"]
    cids = candidate[cc["id"]].astype(str).str.strip()
    eids = eligible[ec["id"]].astype(str).str.strip()
    if cids.eq("").any() or cids.duplicated().any() or eids.eq("").any() or eids.duplicated().any():
        raise ValueError("GNv7 candidate/review IDs are blank or duplicated")
    candidate_rows = {str(row[cc["id"]]).strip(): row for row in candidate.to_dict("records")}
    eligible_rows = {str(row[ec["id"]]).strip(): row for row in eligible.to_dict("records")}
    if not set(eligible_rows).issubset(candidate_rows):
        raise ValueError("GNv7 reviewed point IDs are absent from the frozen candidate")
    if file_sha(origin_path) != spec["origin"]["sha256"]:
        raise ValueError("GNv7 raw origin bytes do not match the reviewed Parquet hash")

    required_candidate = [cc[k] for k in ("id", "target", "year", "latitude", "longitude", "origin_file",
                                          "origin_sha256", "source_row", "payload_sha256")]
    if set(required_candidate) - set(candidate.columns):
        raise ValueError(f"GNv7 candidate fields missing: {sorted(set(required_candidate)-set(candidate.columns))}")
    required_eligible = [ec[k] for k in ("id", "target", "year", "latitude", "longitude")]
    if set(required_eligible) - set(eligible.columns):
        raise ValueError(f"GNv7 eligible fields missing: {sorted(set(required_eligible)-set(eligible.columns))}")

    approved_rows = []
    all_reviewed_adapter_rows = []
    for decision_id, approved in eligible_rows.items():
        source = dict(candidate_rows[decision_id])
        target = str(source[cc["target"]]).strip()
        if target != str(approved[ec["target"]]).strip():
            raise ValueError(f"GNv7 target differs from reviewed point {decision_id}")
        for key in ("year", "latitude", "longitude"):
            lhs, rhs = str(source[cc[key]]).strip(), str(approved[ec[key]]).strip()
            try:
                same = int(lhs) == int(rhs) if key == "year" else float(lhs) == float(rhs)
            except (TypeError, ValueError):
                same = lhs == rhs
            if not same:
                raise ValueError(f"GNv7 {key} differs from review for {decision_id}")
        if Path(str(source[cc["origin_file"]])).resolve() != origin_path:
            raise ValueError(f"GNv7 source file mismatch for {decision_id}")
        if str(source[cc["origin_sha256"]]) != spec["origin"]["sha256"]:
            raise ValueError(f"GNv7 raw source hash mismatch for {decision_id}")
        raw_row = str(source[cc["source_row"]]).strip()
        payload_sha = str(source[cc["payload_sha256"]]).strip()
        if not raw_row.isdigit() or len(payload_sha) != 64:
            raise ValueError(f"GNv7 raw source locator invalid for {decision_id}")
        latitude, longitude = float(source[cc["latitude"]]), float(source[cc["longitude"]])
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise ValueError(f"GNv7 non-finite coordinates for {decision_id}")
        source["point_origin_file"] = str(origin_path)
        source["point_origin_sha256"] = spec["origin"]["sha256"]
        source["point_origin_locator"] = f"parquet_row_1based={raw_row};raw_payload_sha256={payload_sha}"
        source["coordinate_source_record_id"] = target
        source["coordinate_provider_id"] = ""
        source["coordinate_provider"] = "Tochno 2021 selected raw Parquet point"
        source["coordinate_quality"] = (
            "independently reviewed raw selected physical-settlement point; complete two-pass GeoNames alias "
            "inventory checked; no provider binding, measurement independence, date, or precision claim")
        source["coordinate_measurement_date_unknown"] = True
        source["boundary_comparability_asserted"] = False
        source["population_scope_comparability_asserted"] = False
        source["native_id_binding_asserted"] = False
        source["coordinate_application_family"] = "R_Geonames_two_pass_v7_reviewed_raw_source_point_20261004"
        source["coordinate_admission_rule_name"] = "R_GN_v7_complete_two_pass_ADM1_alias_inventory_raw_source_point_20261004"
        source["application_inference_kind"] = "direct reviewed source-row representative point only; no identity propagation"
        source["coordinate_use_interpretation"] = (
            "Literal selected 2021 raw source-row point, independently reviewed against the complete two-pass RU "
            "ADM1 PPL alias inventory. No GeoNames identifier binding, upstream measurement independence, "
            "census-date measurement, precision upgrade, temporal identity, or population-boundary comparability is asserted.")
        source["application_review_point_use_id"] = decision_id
        all_reviewed_adapter_rows.append(source)

    if len(all_reviewed_adapter_rows) != len(eligible):
        raise AssertionError("GNv7 source adapter row count differs from exact reviewed list")
    if len({row["target_source_record_id"] for row in all_reviewed_adapter_rows}) != len(eligible):
        raise ValueError("GNv7 review has duplicate target IDs")

    base_points_path = Path(inputs["base"]["points"]["path"])
    base_points = pd.read_parquet(base_points_path)
    required_base = {"target_source_record_id", "latitude", "longitude"}
    if required_base - set(base_points.columns):
        raise ValueError(f"current base point ledger lacks required columns: {sorted(required_base-set(base_points.columns))}")
    base_targets = base_points.target_source_record_id.astype(str).str.strip()
    if base_targets.duplicated().any():
        raise ValueError("pinned base point ledger contains duplicate target IDs")
    base_rows = {str(row["target_source_record_id"]).strip(): row for row in base_points.to_dict("records")}
    blocked_obj = json.loads(Path(inputs["blocked_targets"]["path"]).read_text(encoding="utf-8"))
    blocked = set(map(str, blocked_obj.get("blocked_target_source_record_ids", [])))

    overlap_rows, blocked_rows = [], []
    for source in all_reviewed_adapter_rows:
        target = str(source["target_source_record_id"])
        if target in base_rows:
            base = base_rows[target]
            distance = haversine_km(source["latitude"], source["longitude"], base["latitude"], base["longitude"])
            overlap_rows.append({"point_use_id": source["point_use_id"], "target_source_record_id": target,
                "candidate_latitude": source["latitude"], "candidate_longitude": source["longitude"],
                "base_latitude": base["latitude"], "base_longitude": base["longitude"],
                "distance_km_diagnostic": distance,
                "base_coordinate_application_family": base.get("coordinate_application_family", ""),
                "base_point_origin_file": base.get("point_origin_file", ""),
                "base_point_origin_locator": base.get("point_origin_locator", ""),
                "disposition": "existing accepted point retained; GNv7 alternate claim preserved, not submitted"})
        elif target in blocked:
            blocked_rows.append({"point_use_id": source["point_use_id"], "target_source_record_id": target,
                "disposition": "global blocked target; excluded from application list"})
        else:
            approved_rows.append({field: value for field, value in eligible_rows[source["application_review_point_use_id"]].items()})

    adapter_path = output_path(OUTPUT_ROOT / "geonames_two_pass_v7_reviewed_274_candidate_adapter.parquet")
    if adapter_path.exists():
        raise FileExistsError(adapter_path)
    pd.DataFrame(all_reviewed_adapter_rows).to_parquet(adapter_path, index=False)
    scoped_eligible_path = output_path(OUTPUT_ROOT / "geonames_two_pass_v7_current_base_disjoint_eligible.csv")
    if scoped_eligible_path.exists():
        raise FileExistsError(scoped_eligible_path)
    pd.DataFrame(approved_rows, columns=eligible.columns).to_csv(scoped_eligible_path, index=False, quoting=csv.QUOTE_MINIMAL)
    overlap_path = output_path(OUTPUT_ROOT / "geonames_two_pass_v7_existing_point_overlap_ledger.csv")
    if overlap_path.exists():
        raise FileExistsError(overlap_path)
    overlap_frame = pd.DataFrame(overlap_rows)
    overlap_frame.to_csv(overlap_path, index=False, quoting=csv.QUOTE_MINIMAL)
    blocked_path = output_path(OUTPUT_ROOT / "geonames_two_pass_v7_blocked_target_exclusions.csv")
    if blocked_path.exists():
        raise FileExistsError(blocked_path)
    pd.DataFrame(blocked_rows, columns=["point_use_id", "target_source_record_id", "disposition"]).to_csv(
        blocked_path, index=False, quoting=csv.QUOTE_MINIMAL)
    adapter_sha = file_sha(adapter_path)
    scoped_eligible_sha = file_sha(scoped_eligible_path)
    report["gnv7_application_scope"] = {"reviewed_eligible_rows": len(eligible),
        "current_base_overlaps_excluded": len(overlap_rows), "blocked_targets_excluded": len(blocked_rows),
        "application_eligible_after_current_base_gates": len(approved_rows),
        "adapter": {"path": str(adapter_path), "sha256": adapter_sha, "rows": len(all_reviewed_adapter_rows)},
        "scoped_eligible": {"path": str(scoped_eligible_path), "sha256": scoped_eligible_sha, "rows": len(approved_rows)},
        "overlap_ledger": {"path": str(overlap_path), "sha256": file_sha(overlap_path), "rows": len(overlap_rows)},
        "blocked_exclusions": {"path": str(blocked_path), "sha256": file_sha(blocked_path), "rows": len(blocked_rows)}}
    return adapter_path, scoped_eligible_path


def make_wk_v2_identity_adapter(inputs: dict, report: dict):
    """Filter the frozen WK candidate record list by its independent exact keys.

    This is an adapter only: eligible keys control admission, while candidate
    lineage and source context remain on every staged row. No identity decision
    is made here.
    """
    spec = inputs["wk_v2_identity_source"]
    candidate_path = Path(spec["candidate"]["path"]).resolve()
    eligible_path = Path(spec["eligible"]["path"]).resolve()
    candidate = read_csv(candidate_path)
    eligible = read_csv(eligible_path)
    cc, ec = spec["candidate_columns"], spec["eligible_columns"]
    required_candidate = {cc[k] for k in ("from", "to", "year", "status")}
    required_eligible = {ec[k] for k in ("from", "to", "year", "family")}
    if required_candidate - set(candidate.columns):
        raise ValueError(f"WK candidate columns missing: {sorted(required_candidate-set(candidate.columns))}")
    if required_eligible - set(eligible.columns):
        raise ValueError(f"WK eligible columns missing: {sorted(required_eligible-set(eligible.columns))}")

    family = str(spec["family"])
    keycols = ("from", "to", "year")
    cand_keys = list(zip(*(candidate[cc[k]].astype(str).str.strip() for k in keycols)))
    elig_keys = list(zip(*(eligible[ec[k]].astype(str).str.strip() for k in keycols)))
    if any(any(not part for part in key) for key in cand_keys + elig_keys):
        raise ValueError("WK source contains blank identity key components")
    if len(set(cand_keys)) != len(cand_keys) or len(set(elig_keys)) != len(elig_keys):
        raise ValueError("WK candidate/review keys must be unique")
    if any(str(v).strip() != family for v in eligible[ec["family"]]):
        raise ValueError("WK eligible list contains an unexpected rule family")
    candidate_index = {key: i for i, key in enumerate(cand_keys)}
    missing = set(elig_keys) - set(candidate_index)
    if missing:
        raise ValueError(f"WK reviewed keys absent from pinned candidate: {sorted(missing)[:5]}")
    eligible_set = set(elig_keys)
    chosen = candidate.iloc[[candidate_index[key] for key in elig_keys]].copy()
    selected_path = Path(inputs["frozen"]["selected"]["path"])
    selected_years = pd.read_parquet(selected_path, columns=["source_record_id", "census_year"])
    selected_years["source_record_id"] = selected_years.source_record_id.astype(str)
    if selected_years.source_record_id.duplicated().any():
        raise ValueError("frozen selected frame has duplicate source_record_id values")
    year_by_id = dict(zip(selected_years.source_record_id, selected_years.census_year))
    from_years, to_years = [], []
    for old_id, current_id, reviewed_year in elig_keys:
        if old_id not in year_by_id or current_id not in year_by_id:
            raise ValueError(f"WK reviewed endpoint absent from frozen selected frame: {(old_id, current_id)}")
        old_year = int(year_by_id[old_id])
        current_year = int(year_by_id[current_id])
        if old_year != int(reviewed_year) or current_year != 2021:
            raise ValueError(
                f"WK review year conflicts with selected endpoint years for {(old_id, current_id)}: "
                f"review={reviewed_year}, selected={old_year}->{current_year}"
            )
        from_years.append(old_year)
        to_years.append(current_year)
    chosen["from_source_record_id"] = [key[0] for key in elig_keys]
    chosen["to_source_record_id"] = [key[1] for key in elig_keys]
    chosen["from_year"] = from_years
    chosen["to_year"] = to_years
    chosen["integration_rule_family"] = family
    chosen["decision_id"] = [
        "wk-v2-" + hashlib.sha256("\x1f".join((family, *key)).encode("utf-8")).hexdigest()[:24]
        for key in elig_keys
    ]
    if chosen["decision_id"].duplicated().any():
        raise ValueError("WK generated canonical decision IDs collide")
    chosen["source_candidate_status"] = chosen[cc["status"]].astype(str)
    chosen["candidate_status"] = "wk_v2_independently_reviewed_eligible"
    chosen["integration_status"] = chosen["candidate_status"]
    chosen["source_secondary_possible_shared_origin"] = True
    chosen["application_raw_context_interpretation"] = (
        "District and observed type differences are retained as context flags; neither is treated as identity proof. "
        "The accepted edge is based on the independently reviewed year-scoped rule: whole-frame all-type name/province "
        "uniqueness, current physical-place/QID checks with an accepted point carrier, and an exact year-labelled raw "
        "P1082 population match (protected 2010 values remain a distinct bounded class). Wikidata evidence is secondary; "
        "possible shared source origin is retained, and no historical boundary or population-scope equivalence is asserted."
    )
    chosen["application_point_is_independent_historical_identity_evidence"] = False
    adapter_path = output_path(OUTPUT_ROOT / "wk_v2_reviewed_identity_candidate_adapter.csv")
    if adapter_path.exists():
        raise FileExistsError(adapter_path)
    chosen.to_csv(adapter_path, index=False, quoting=csv.QUOTE_MINIMAL)

    eligible_adapter_path = output_path(OUTPUT_ROOT / "wk_v2_exact_independently_eligible_keys.csv")
    if eligible_adapter_path.exists():
        raise FileExistsError(eligible_adapter_path)
    # Preserve the independent eligibility schema byte-for-byte as rows/columns;
    # only serialization is new and hash-pinned by the generated manifest.
    eligible.to_csv(eligible_adapter_path, index=False, quoting=csv.QUOTE_MINIMAL)
    report["wk_v2_application_scope"] = {
        "independently_eligible_rows": len(eligible),
        "candidate_rows": len(candidate),
        "staged_exactly_eligible_rows": len(chosen),
        "decision_id_scheme": "sha256(rule_family, from, to, year) prefix wk-v2-; source old_id is retained as evidence",
        "identity_interpretation": "reviewed year-scoped secondary corroboration; raw district/type variation retained as flags",
        "possible_shared_source_origin_preserved": True,
        "adapter": {"path": str(adapter_path), "sha256": file_sha(adapter_path), "rows": len(chosen)},
        "eligible_keys": {"path": str(eligible_adapter_path), "sha256": file_sha(eligible_adapter_path), "rows": len(eligible)},
    }
    return adapter_path, eligible_adapter_path


def make_type_correction_identity_adapter(inputs: dict, report: dict):
    """Adapt the separately reviewed 949 type/lineage identity edges."""
    spec = inputs["type_correction_identity_source"]
    candidate_path = Path(spec["candidate"]["path"]).resolve()
    eligible_path = Path(spec["eligible"]["path"]).resolve()
    candidate, eligible = read_csv(candidate_path), read_csv(eligible_path)
    cc, ec = spec["candidate_columns"], spec["eligible_columns"]
    required_candidate = {cc[k] for k in ("id", "from", "to", "from_year", "to_year", "family")}
    required_eligible = {ec[k] for k in ("id", "from", "to", "from_year", "to_year", "family")}
    if required_candidate - set(candidate.columns):
        raise ValueError(f"TYPE correction candidate columns missing: {sorted(required_candidate-set(candidate.columns))}")
    if required_eligible - set(eligible.columns):
        raise ValueError(f"TYPE correction eligible columns missing: {sorted(required_eligible-set(eligible.columns))}")
    ckeys = [cc[k] for k in ("id", "from", "to", "from_year", "to_year", "family")]
    ekeys = [ec[k] for k in ("id", "from", "to", "from_year", "to_year", "family")]
    if candidate[cc["id"]].astype(str).duplicated().any() or eligible[ec["id"]].astype(str).duplicated().any():
        raise ValueError("TYPE correction candidate/review edge IDs must be unique")
    cand_by_id = {str(row[cc["id"]]).strip(): row for row in candidate.to_dict("records")}
    elig_ids = [str(v).strip() for v in eligible[ec["id"]]]
    if not set(elig_ids).issubset(cand_by_id):
        raise ValueError("TYPE correction reviewed edge IDs are absent from the pinned candidate")
    selected = pd.read_parquet(Path(inputs["frozen"]["selected"]["path"]),
                               columns=["source_record_id", "census_year"])
    selected["source_record_id"] = selected.source_record_id.astype(str)
    if selected.source_record_id.duplicated().any():
        raise ValueError("frozen selected frame has duplicate source_record_id values")
    year_by_id = dict(zip(selected.source_record_id, selected.census_year))
    chosen_rows = []
    for row in eligible.to_dict("records"):
        edge_id = str(row[ec["id"]]).strip()
        source = dict(cand_by_id[edge_id])
        for key, candidate_col, eligible_col in zip(ckeys, ckeys, ekeys):
            if str(source[candidate_col]).strip() != str(row[eligible_col]).strip():
                raise ValueError(f"TYPE corrected review/source mismatch for {edge_id} ({key})")
        old_id, current_id = str(row[ec["from"]]).strip(), str(row[ec["to"]]).strip()
        old_year, current_year = int(row[ec["from_year"]]), int(row[ec["to_year"]])
        if old_id not in year_by_id or current_id not in year_by_id:
            raise ValueError(f"TYPE corrected endpoint absent from frozen selected frame: {edge_id}")
        if int(year_by_id[old_id]) != old_year or int(year_by_id[current_id]) != current_year:
            raise ValueError(f"TYPE corrected years conflict with selected endpoints: {edge_id}")
        source["decision_id"] = edge_id
        source["from_source_record_id"] = old_id
        source["to_source_record_id"] = current_id
        source["from_year"] = old_year
        source["to_year"] = current_year
        source["integration_rule_family"] = str(row[ec["family"]]).strip()
        source["source_candidate_only"] = source.get("candidate_only", "")
        source["candidate_status"] = "type_correction_independently_reviewed_eligible"
        source["application_historical_identity_interpretation"] = (
            "Independent full-predicate review approved this same-place identity edge. Observed type changes and their "
            "date intervals remain context only; no exact legal date, historic coordinate measurement, boundary "
            "comparability, or population-scope equivalence is asserted. Accepted current point evidence supports "
            "physical-place continuity within the reviewed distance gate only."
        )
        source["application_point_is_independent_historical_coordinate_evidence"] = False
        source["application_source_secondary_possible_shared_origin"] = True
        chosen_rows.append(source)
    chosen = pd.DataFrame(chosen_rows)
    if chosen.decision_id.duplicated().any():
        raise ValueError("TYPE correction canonical decision IDs are duplicated")
    adapter_path = output_path(OUTPUT_ROOT / "type_corrective_949_reviewed_identity_candidate_adapter.csv")
    if adapter_path.exists():
        raise FileExistsError(adapter_path)
    chosen.to_csv(adapter_path, index=False, quoting=csv.QUOTE_MINIMAL)
    eligible_adapter_path = output_path(OUTPUT_ROOT / "type_corrective_949_exact_eligible_edges.csv")
    if eligible_adapter_path.exists():
        raise FileExistsError(eligible_adapter_path)
    eligible.to_csv(eligible_adapter_path, index=False, quoting=csv.QUOTE_MINIMAL)
    report["type_correction_application_scope"] = {
        "independently_eligible_edges": len(eligible),
        "candidate_rows": len(candidate),
        "exact_reviewed_edges_staged": len(chosen),
        "identity_family_counts": chosen.integration_rule_family.value_counts().to_dict(),
        "no_exact_type_change_date_or_boundary_equivalence_claim": True,
        "adapter": {"path": str(adapter_path), "sha256": file_sha(adapter_path), "rows": len(chosen)},
        "eligible_edges": {"path": str(eligible_adapter_path), "sha256": file_sha(eligible_adapter_path), "rows": len(eligible)},
    }
    return adapter_path, eligible_adapter_path


def main() -> None:
    global OUTPUT_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    args = parser.parse_args()
    requested_root = Path(args.output_root).resolve()
    if requested_root not in ALLOWED_OUTPUT_ROOTS:
        raise ValueError(f"--output-root must be one of the explicit allowlisted roots: {sorted(map(str, ALLOWED_OUTPUT_ROOTS))}")
    OUTPUT_ROOT = requested_root
    input_path = Path(args.inputs).resolve()
    if input_path.is_relative_to(OUTPUT_ROOT):
        raise ValueError("read-only preparation input must be outside output root")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    inputs_hash_before = file_sha(input_path)
    inputs = json.loads(input_path.read_text(encoding="utf-8"))
    pins = collect_inputs(inputs)
    before = hash_snapshot(pins, "preparation before")
    guard_result = run_write_guard_regression(pins)
    report = {"status": "prepared_manifest_only_no_application", "inputs_path": str(input_path),
              "inputs_sha256": inputs_hash_before, "output_root_allowlist": str(OUTPUT_ROOT),
              "preparation_script": {"path": str(Path(__file__).resolve()),
                                     "sha256": file_sha(Path(__file__).resolve())},
              "input_hashes_before": before, "write_guard_regression": guard_result}
    adapter_path, approved_path = make_point_adapter_and_scoped_approval(inputs, pins, report)

    point_spec = inputs["gnv7_point_source"]
    candidate_columns = {"target": "target_source_record_id", "latitude": "latitude", "longitude": "longitude",
                         "origin_file": "point_origin_file", "origin_sha256": "point_origin_sha256",
                         "origin_locator": "point_origin_locator"}
    point_source = {"candidate": {"path": str(adapter_path), "sha256": file_sha(adapter_path)},
        "approved": {"path": str(approved_path), "sha256": file_sha(approved_path)},
        "review_receipt": point_spec["eligibility_receipt"],
        "candidate_columns": candidate_columns,
        "approved_columns": {"target": "target_source_record_id", "latitude": "latitude", "longitude": "longitude"},
        "origin": point_spec["origin"],
        "output_values": {"coordinate_application_family": "R_Geonames_two_pass_v7_reviewed_raw_source_point_20261004",
            "coordinate_admission_rule_name": "R_GN_v7_complete_two_pass_ADM1_alias_inventory_raw_source_point_20261004",
            "application_inference_kind": "direct reviewed source-row representative point only; no identity propagation",
            "coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False, "native_id_binding_asserted": False,
            "provider_binding_status": "raw source point only; GeoNames identity binding not asserted"}}
    identity_sources = []
    if "wk_v2_identity_source" in inputs:
        identity_candidate, identity_eligible = make_wk_v2_identity_adapter(inputs, report)
        wk = inputs["wk_v2_identity_source"]
        identity_sources.append({
            "candidate": {"path": str(identity_candidate), "sha256": file_sha(identity_candidate)},
            "eligible": {"path": str(identity_eligible), "sha256": file_sha(identity_eligible)},
            "review_receipt": wk["review_receipt"],
            "candidate_columns": {"from": "from_source_record_id", "to": "to_source_record_id",
                "family": "integration_rule_family", "id": "decision_id", "status": "candidate_status",
                "relation": "relation", "event": "explicit_successor_event_hold",
                "global_block": "explicit_federal_aggregate_hold"},
            "eligible_columns": {"from": "from_source_record_id", "to": "to_source_record_id",
                "family": "family", "year": "year"},
            "accepted_candidate_statuses": ["wk_v2_independently_reviewed_eligible"],
            "exclude_if_true": ["event", "global_block"],
            "canonical_columns": {"relation": "application_relation", "decision_class": "candidate_identity_rule",
                "source": "application_identity_evidence_class"}
        })
    if "type_correction_identity_source" in inputs:
        identity_candidate, identity_eligible = make_type_correction_identity_adapter(inputs, report)
        tc = inputs["type_correction_identity_source"]
        identity_sources.append({
            "candidate": {"path": str(identity_candidate), "sha256": file_sha(identity_candidate)},
            "eligible": {"path": str(identity_eligible), "sha256": file_sha(identity_eligible)},
            "review_receipt": tc["review_receipt"],
            "candidate_columns": {"from": "from_source_record_id", "to": "to_source_record_id",
                "family": "integration_rule_family", "id": "decision_id", "status": "candidate_status",
                "relation": "relation"},
            "eligible_columns": {"from": "from_source_record_id", "to": "to_source_record_id",
                "family": "review_family"},
            "accepted_candidate_statuses": ["type_correction_independently_reviewed_eligible"],
            "exclude_if_true": [],
            "canonical_columns": {"relation": "relation", "decision_class": "review_family",
                "source": "independent_review_status"}
        })
    manifest = {"manifest_version": "fourth_reviewed_mass_extensions_v2_20261004",
        "reviewed_at_utc": inputs["reviewed_at_utc"], "frozen": inputs["frozen"], "base": inputs["base"],
        "identity_sources": identity_sources, "point_sources": [point_source],
        "blocked_targets": inputs["blocked_targets"], "federal_points": inputs["federal_points"],
        "federal_chains": inputs["federal_chains"],
        "review_context_inputs": inputs["review_context_inputs"],
        "pending_review_cohorts": inputs["pending_review_cohorts"],
        "application_scope": report["gnv7_application_scope"] | {
            "wk_v2_identity": report.get("wk_v2_application_scope", "not included"),
            "type_corrective_949": report.get("type_correction_application_scope", "candidate-only; not included"),
            "type_axes_501": "candidate-only context; zero identity admissions in pinned receipt",
            "wk_v2_corridor": report.get("wk_v2_application_scope", "excluded pending independent eligible review")}}
    manifest_path = output_path(OUTPUT_ROOT / "fourth_application_manifest.json")
    write_json_new(manifest_path, manifest)
    report["manifest"] = {"path": str(manifest_path), "sha256": file_sha(manifest_path)}
    after = hash_snapshot(pins, "preparation after")
    if before != after:
        raise AssertionError("pinned source/review/base bytes changed during preparation")
    if file_sha(input_path) != inputs_hash_before:
        raise AssertionError("read-only preparation input JSON changed during preparation")
    report["input_hashes_after"] = after
    report["all_pinned_inputs_unchanged"] = True
    write_json_new(output_path(OUTPUT_ROOT / "preparation_receipt.json"), report)
    print(json.dumps({"manifest": report["manifest"], "gnv7_application_scope": report["gnv7_application_scope"],
        "receipt": {"path": str(OUTPUT_ROOT / "preparation_receipt.json"),
                    "sha256": file_sha(OUTPUT_ROOT / "preparation_receipt.json")},
        "write_guard_regression": guard_result, "all_pinned_inputs_unchanged": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
