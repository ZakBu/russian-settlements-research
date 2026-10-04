"""Build the origin-corrected point-source replacement bundle; never apply it."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


WORK_ROOT = Path("/workspace/settlements-work/continuation_20261004")
V3_ROOT = WORK_ROOT / "root/next_batch_manifest_preparation/fourth_20261004/future_v3_ready_bundle"
OUTPUT_ROOT = WORK_ROOT / "root/next_batch_manifest_preparation/fourth_origin_corrected_20261004/ready_bundle"
ALLOWED_OUTPUT_ROOTS = {OUTPUT_ROOT.resolve()}
V3_MANIFEST = V3_ROOT / "fourth_application_manifest.json"
APPROVED_107 = V3_ROOT / "geonames_two_pass_v7_current_base_disjoint_eligible.csv"
V7_CANDIDATES = WORK_ROOT / "R4/wikidata_points/extensions/geonames_two_pass_v7/staged_point_uses.csv"
V7_ELIGIBLE_274 = WORK_ROOT / "independent_review/geonames_two_pass_v7_independent_eligible_274.csv"
V7_ELIGIBILITY_RECEIPT = WORK_ROOT / "independent_review/geonames_two_pass_v7_independent_eligibility_receipt.json"
V7_REVIEW_RECEIPT = WORK_ROOT / "independent_review/geonames_two_pass_v7_independent_review_receipt.json"
TOCHNO_ORIGIN = Path("/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet")
GEONAMES_ORIGIN = Path("/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip")
GEONAMES_MEMBER = "RU.txt"
GEONAMES_MEMBER_SHA256 = "3ef8f69d9c6b8adbd53afc35f6dc774b1d01b04f566622e1892a6d2f00d2f4d0"
TOCHNO_SHA256 = "86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14"
GEONAMES_ZIP_SHA256 = "9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4"
TOCHNO_FIELDS = ["object_level", "object_name", "oktmo", "region", "mun_upper", "mun_lower", "settlement",
    "population", "settlement_with_type_dadata", "settlement_type_dadata", "settlement_type_full_dadata",
    "settlement_dadata", "fias_level_dadata", "latitude_dadata", "longitude_dadata"]
SELECTED_RELATIVE_SOURCE = "data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def output_path(path: Path) -> Path:
    path = Path(path)
    root = OUTPUT_ROOT.resolve()
    if not path.is_absolute():
        path = root / path
    cursor = path
    while cursor != cursor.parent:
        if cursor.exists() and cursor.is_symlink():
            raise ValueError(f"symlink output path refused: {cursor}")
        if cursor == root:
            break
        cursor = cursor.parent
    resolved = path.resolve(strict=False)
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError(f"output outside exact origin-correction root refused: {path}")
    if resolved == root:
        raise ValueError("cannot overwrite the origin-correction output root")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError(f"output must be a new regular file: {path}")
    return resolved


def write_new(path: Path, body: bytes) -> None:
    target = output_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as f:
        f.write(body)


def write_json(path: Path, obj: dict) -> None:
    write_new(path, (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype="string", keep_default_na=False, engine="python")


def file_snapshot(paths: dict[str, Path]) -> dict[str, str]:
    result = {}
    for label, path in paths.items():
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"{label}: {path}")
        result[label] = sha256_file(path)
    return result


def _row_payload(row: pd.Series) -> dict:
    return {key: (None if pd.isna(row[key]) else (row[key].item() if hasattr(row[key], "item") else row[key]))
            for key in TOCHNO_FIELDS}


def _serialize_payload(row: pd.Series) -> str:
    return json.dumps(_row_payload(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def verify_tochno_rows(rows: pd.DataFrame, selected: pd.DataFrame) -> dict[str, dict]:
    if sha256_file(TOCHNO_ORIGIN) != TOCHNO_SHA256:
        raise ValueError("raw Tochno Parquet bytes differ from the approved origin pin")
    raw = pd.read_parquet(TOCHNO_ORIGIN, columns=TOCHNO_FIELDS)
    selected = selected.set_index("source_record_id", drop=False)
    results = {}
    for row in rows.to_dict("records"):
        use_id, target = row["point_use_id"], row["target_source_record_id"]
        raw_index = int(row["source_raw_row_1based"])
        if raw_index < 1 or raw_index > len(raw):
            raise ValueError(f"Tochno row locator outside Parquet: {use_id}")
        if target not in selected.index:
            raise ValueError(f"Tochno point target missing from selected frame: {target}")
        selected_row = selected.loc[target]
        if selected_row.source_file != SELECTED_RELATIVE_SOURCE or int(selected_row.source_row) != raw_index:
            raise ValueError(f"selected source identity does not point to this Parquet row: {use_id}")
        raw_row = raw.iloc[raw_index - 1]
        payload = _serialize_payload(raw_row)
        payload_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if payload_sha != row["source_raw_payload_sha256"]:
            raise ValueError(f"Tochno raw payload hash mismatch: {use_id}")
        if row["source_raw_file_sha256"] != TOCHNO_SHA256 or Path(row["source_raw_file"]).resolve() != TOCHNO_ORIGIN.resolve():
            raise ValueError(f"Tochno raw file provenance mismatch: {use_id}")
        lat, lon = float(raw_row.latitude_dadata), float(raw_row.longitude_dadata)
        if not math.isfinite(lat) or not math.isfinite(lon):
            raise ValueError(f"Tochno row has nonfinite coordinates: {use_id}")
        if lat != float(row["latitude"]) or lon != float(row["longitude"]):
            raise ValueError(f"approved Tochno coordinates differ from the raw Parquet row: {use_id}")
        results[use_id] = {"point_origin_file": str(TOCHNO_ORIGIN), "point_origin_sha256": TOCHNO_SHA256,
            "point_origin_locator": f"parquet_row_1based={raw_index};raw_payload_sha256={payload_sha}",
            "origin_family": "actual raw selected source point", "native_join_source_row_1based": raw_index,
            "native_join_payload_sha256": payload_sha, "native_join_latitude": lat, "native_join_longitude": lon,
            "origin_record_locator_verified": True}
    return results


def verify_geonames_rows(rows: pd.DataFrame) -> dict[str, dict]:
    if sha256_file(GEONAMES_ORIGIN) != GEONAMES_ZIP_SHA256:
        raise ValueError("GeoNames archive bytes differ from the approved raw origin pin")
    desired = {}
    for row in rows.to_dict("records"):
        witnesses = json.loads(row["geo_names_whole_ADM1_witnesses_json"])
        matching = [w for w in witnesses if float(w["latitude"]) == float(row["latitude"])
                    and float(w["longitude"]) == float(row["longitude"])
                    and str(w.get("feature_class")) == "P" and str(w.get("feature_code", "")).startswith("PPL")]
        if len(matching) != 1:
            raise ValueError(f"GeoNames actual coordinate does not identify one literal PPL witness: {row['point_use_id']}")
        witness = matching[0]
        line_no = int(witness["source_line_1based"])
        if line_no in desired and desired[line_no][1] != witness:
            raise ValueError(f"conflicting GeoNames witness metadata for RU.txt line {line_no}")
        desired[line_no] = (row["point_use_id"], witness)
    found, member_hash = {}, hashlib.sha256()
    with zipfile.ZipFile(GEONAMES_ORIGIN) as zf:
        if GEONAMES_MEMBER not in zf.namelist():
            raise ValueError(f"GeoNames archive lacks expected member {GEONAMES_MEMBER}")
        with zf.open(GEONAMES_MEMBER) as stream:
            offset = 0
            for line_no, line in enumerate(stream, start=1):
                member_hash.update(line)
                start, end = offset, offset + len(line)
                offset = end
                if line_no not in desired:
                    continue
                use_id, w = desired[line_no]
                if start != int(w["byte_start"]) or end != int(w["byte_end"]):
                    raise ValueError(f"GeoNames raw byte offsets differ from witness: {use_id}")
                line_sha = hashlib.sha256(line).hexdigest()
                if line_sha != w["line_sha256"]:
                    raise ValueError(f"GeoNames raw line SHA differs from witness: {use_id}")
                fields = line.rstrip(b"\r\n").decode("utf-8").split("\t")
                if len(fields) < 9:
                    raise ValueError(f"GeoNames RU.txt line is malformed: {line_no}")
                geonameid, latitude, longitude = fields[0], float(fields[4]), float(fields[5])
                if (geonameid != str(w["geonameid"]) or latitude != float(w["latitude"])
                        or longitude != float(w["longitude"]) or fields[6] != "P"
                        or not fields[7].startswith("PPL") or fields[8] != "RU"):
                    raise ValueError(f"GeoNames raw row content differs from reviewed witness: {use_id}")
                found[line_no] = {"point_origin_file": str(GEONAMES_ORIGIN), "point_origin_sha256": GEONAMES_ZIP_SHA256,
                    "point_origin_locator": (f"zip_member={GEONAMES_MEMBER};member_sha256={GEONAMES_MEMBER_SHA256};"
                        f"line_1based={line_no};byte_start={start};byte_end={end};geonameid={geonameid};line_sha256={line_sha}"),
                    "origin_family": "actual GeoNames RU PPL-family point", "geonameid": geonameid,
                    "source_line_1based": line_no, "source_line_byte_start": start, "source_line_byte_end": end,
                    "source_line_sha256": line_sha, "member_sha256": GEONAMES_MEMBER_SHA256,
                    "native_join_latitude": latitude, "native_join_longitude": longitude,
                    "origin_record_locator_verified": True}
    if member_hash.hexdigest() != GEONAMES_MEMBER_SHA256:
        raise ValueError(f"GeoNames RU.txt member SHA mismatch: {member_hash.hexdigest()}")
    if set(found) != set(desired):
        raise ValueError(f"GeoNames raw witness rows not found: {sorted(set(desired)-set(found))[:10]}")
    by_use = {use_id: found[line_no] for line_no, (use_id, _) in desired.items()}
    return by_use


def make_origin_row(row: dict, actual: dict, family: str) -> dict:
    output = dict(row)
    output.update(actual)
    output["point_origin_geonameid"] = actual.get("geonameid", "")
    output["point_origin_line_1based"] = actual.get("source_line_1based", "")
    output["point_origin_line_sha256"] = actual.get("source_line_sha256", "")
    if family == "actual raw selected source point":
        output.update({"coordinate_source_record_id": row["target_source_record_id"], "coordinate_provider_id": "",
            "coordinate_provider": "Tochno 2021 selected raw Parquet source point",
            "coordinate_quality": "literal selected 2021 raw source-row coordinates; raw payload and coordinate values reopened",
            "coordinate_application_family": "R_GN_v7_actual_Tochno_2021_source_point_origin_corrected_20261004",
            "coordinate_admission_rule_name": "R_GN_v7_Tochno_raw_row_origin_corrected_20261004"})
    else:
        output.update({"coordinate_source_record_id": "", "coordinate_provider_id": "",
            "coordinate_provider": "GeoNames RU 2026-09-07 raw PPL-family coordinate; geonameid is a raw-row locator only",
            "coordinate_quality": "literal GeoNames RU.txt PPL-family row coordinate verified by line bytes, offsets, geonameid, and line SHA",
            "coordinate_application_family": "R_GN_v7_actual_GeoNames_PPL_origin_corrected_20261004",
            "coordinate_admission_rule_name": "R_GN_v7_literal_GN_PPL_record_origin_corrected_20261004"})
    output.update({"coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False,
        "population_scope_comparability_asserted": False, "native_id_binding_asserted": False,
        "application_inference_kind": "direct reviewed coordinate use from its verified raw origin; no identity propagation",
        "coordinate_use_interpretation": ("Actual point origin is recorded per use. The GeoNames identifier is only a line locator, "
            "not a provider binding; measurement date, upstream independence, precision upgrade, historic boundary, and population-scope equivalence are not asserted."),
        "application_review_point_use_id": row["point_use_id"]})
    return output


def main() -> None:
    global OUTPUT_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    args = parser.parse_args()
    requested = Path(args.output_root).resolve()
    if requested not in ALLOWED_OUTPUT_ROOTS:
        raise ValueError(f"output root must be the exact allowlisted location {OUTPUT_ROOT}")
    OUTPUT_ROOT = requested
    if OUTPUT_ROOT.exists():
        raise FileExistsError(f"origin-corrected bundle path must be new: {OUTPUT_ROOT}")

    v3 = json.loads(V3_MANIFEST.read_text(encoding="utf-8"))
    if sha256_file(V3_MANIFEST) != "0cb35e52bc77f0301b8249f73166e3e63e7c3b35075effd238fd03369d67f8a9":
        raise ValueError("frozen v3 manifest hash differs from the root-reviewed bundle")
    before_paths = {"v3_manifest": V3_MANIFEST, "approved_107": APPROVED_107, "v7_candidates": V7_CANDIDATES,
        "v7_eligible_274": V7_ELIGIBLE_274, "v7_eligibility_receipt": V7_ELIGIBILITY_RECEIPT,
        "v7_review_receipt": V7_REVIEW_RECEIPT, "tochno_parquet": TOCHNO_ORIGIN, "geonames_zip": GEONAMES_ORIGIN}
    for n, spec in enumerate(v3["frozen"].values()): before_paths[f"frozen_{n}"] = Path(spec["path"])
    for n, spec in enumerate(v3["base"].values()): before_paths[f"base_{n}"] = Path(spec["path"])
    for n, source_spec in enumerate(v3["identity_sources"]):
        for key in ("candidate", "eligible", "review_receipt"):
            before_paths[f"identity_{n}_{key}"] = Path(source_spec[key]["path"])
        for j, extra in enumerate(source_spec.get("additional_review_receipts", [])):
            before_paths[f"identity_{n}_additional_receipt_{j}"] = Path(extra["path"])
    for key in ("blocked_targets", "federal_points", "federal_chains"):
        before_paths[key] = Path(v3[key]["path"])
    for n, context in enumerate(v3.get("review_context_inputs", [])):
        before_paths[f"review_context_{n}"] = Path(context["path"])
    before = file_snapshot(before_paths)
    context_hashes = {str(Path(item["path"]).resolve()): item["sha256"] for item in v3.get("review_context_inputs", [])}
    for label, path in [("v7_candidates", V7_CANDIDATES), ("v7_eligible_274", V7_ELIGIBLE_274),
                        ("v7_eligibility_receipt", V7_ELIGIBILITY_RECEIPT), ("v7_review_receipt", V7_REVIEW_RECEIPT)]:
        expected = context_hashes.get(str(path.resolve()))
        if not expected or before[label] != expected:
            raise ValueError(f"V7 input lacks a matching frozen v3 context pin: {label}")
    if before["approved_107"] != v3["point_sources"][0]["approved"]["sha256"]:
        raise ValueError("107-target approved list bytes differ from the provisional V3 manifest pin")
    for i, spec in enumerate(v3["frozen"].values()):
        if before[f"frozen_{i}"] != spec["sha256"]:
            raise ValueError(f"frozen input hash mismatch: {spec['path']}")
    for i, spec in enumerate(v3["base"].values()):
        if before[f"base_{i}"] != spec["sha256"]:
            raise ValueError(f"THIRD base hash mismatch: {spec['path']}")
    for i, spec in enumerate(v3["identity_sources"]):
        for key in ("candidate", "eligible", "review_receipt"):
            if before[f"identity_{i}_{key}"] != spec[key]["sha256"]:
                raise ValueError(f"V3 identity-source pin mismatch: {key}")
        for j, extra in enumerate(spec.get("additional_review_receipts", [])):
            if before[f"identity_{i}_additional_receipt_{j}"] != extra["sha256"]:
                raise ValueError("V3 additional identity review receipt hash mismatch")
    for key in ("blocked_targets", "federal_points", "federal_chains"):
        if before[key] != v3[key]["sha256"]:
            raise ValueError(f"V3 fixed application input hash mismatch: {key}")
    for i, context in enumerate(v3.get("review_context_inputs", [])):
        if before[f"review_context_{i}"] != context["sha256"]:
            raise ValueError(f"V3 review-context hash mismatch: {context['role']}")
    if before["tochno_parquet"] != TOCHNO_SHA256 or before["geonames_zip"] != GEONAMES_ZIP_SHA256:
        raise ValueError("coordinate-origin raw bytes differ from the explicit source pins")
    candidates = read_csv(V7_CANDIDATES)
    reviewed_274 = read_csv(V7_ELIGIBLE_274)
    approved_107 = read_csv(APPROVED_107)
    for name, frame, column in [("candidate", candidates, "point_use_id"), ("reviewed", reviewed_274, "point_use_id"),
                                ("application eligible", approved_107, "point_use_id")]:
        if frame[column].astype(str).duplicated().any():
            raise ValueError(f"{name} has duplicate point-use IDs")
    candidate_index = {str(r["point_use_id"]): r for r in candidates.to_dict("records")}
    if not set(reviewed_274.point_use_id) <= set(candidate_index):
        raise ValueError("independent 274 list contains missing source-candidate point IDs")
    source_rows = [candidate_index[str(pid)] for pid in reviewed_274.point_use_id]
    all_274 = pd.DataFrame(source_rows)
    if set(all_274.coordinate_source) != {"actual raw selected source point", "actual GeoNames RU PPL-family point"}:
        raise ValueError("V7 point source families changed unexpectedly")
    base_points = pd.read_parquet(v3["base"]["points"]["path"], columns=["target_source_record_id"])
    if base_points.target_source_record_id.astype(str).duplicated().any():
        raise ValueError("THIRD base point targets are not unique")
    base_ids = set(base_points.target_source_record_id.astype(str))
    if any(str(r.target_source_record_id) in base_ids for r in approved_107.itertuples(index=False)):
        raise ValueError("approved new point list overlaps the pinned THIRD base")
    if len(approved_107) != 107:
        raise ValueError(f"expected 107 new reviewed targets, got {len(approved_107)}")
    app_by_id = {str(r["point_use_id"]): r for r in approved_107.to_dict("records")}
    candidate_by_id = {str(r["point_use_id"]): r for r in all_274.to_dict("records")}
    if set(app_by_id) - set(candidate_by_id):
        raise ValueError("new target list is not a subset of the 274 reviewed source candidates")
    for point_id, eligible in app_by_id.items():
        candidate = candidate_by_id[point_id]
        if str(candidate["target_source_record_id"]) != str(eligible["target_source_record_id"]):
            raise ValueError(f"point target differs from V7 review for {point_id}")
        if float(candidate["latitude"]) != float(eligible["latitude"]) or float(candidate["longitude"]) != float(eligible["longitude"]):
            raise ValueError(f"point coordinates differ from V7 review for {point_id}")
    selected = pd.read_parquet(v3["frozen"]["selected"]["path"],
        columns=["source_record_id", "census_year", "source_file", "source_row", "latitude", "longitude"])
    selected["source_record_id"] = selected.source_record_id.astype(str)
    if selected.source_record_id.duplicated().any():
        raise ValueError("selected observations have duplicate source IDs")

    raw_rows = all_274[all_274.coordinate_source == "actual raw selected source point"]
    gn_rows = all_274[all_274.coordinate_source == "actual GeoNames RU PPL-family point"]
    if (len(raw_rows), len(gn_rows)) != (207, 67):
        raise ValueError(f"expected all-274 provenance split 207/67, got {len(raw_rows)}/{len(gn_rows)}")
    raw_checks = verify_tochno_rows(raw_rows, selected)
    gn_checks = verify_geonames_rows(gn_rows)
    if (sum(1 for x in raw_checks.values() if x["point_origin_file"] == str(TOCHNO_ORIGIN)),
        sum(1 for x in gn_checks.values() if x["point_origin_file"] == str(GEONAMES_ORIGIN))) != (207, 67):
        raise AssertionError("native origin validation counts do not match the candidate families")

    all_checks = raw_checks | gn_checks
    raw_candidates = pd.DataFrame([make_origin_row(r, all_checks[str(r["point_use_id"])], "actual raw selected source point")
        for r in raw_rows.to_dict("records")])
    gn_candidates = pd.DataFrame([make_origin_row(r, all_checks[str(r["point_use_id"])], "actual GeoNames RU PPL-family point")
        for r in gn_rows.to_dict("records")])
    raw_new_ids = set(approved_107.loc[approved_107.point_use_id.isin(raw_candidates.point_use_id), "point_use_id"].astype(str))
    gn_new_ids = set(approved_107.loc[approved_107.point_use_id.isin(gn_candidates.point_use_id), "point_use_id"].astype(str))
    if (len(raw_new_ids), len(gn_new_ids)) != (79, 28) or raw_new_ids | gn_new_ids != set(app_by_id):
        raise ValueError(f"application source-origin split differs from reviewed 79/28 target: {len(raw_new_ids)}/{len(gn_new_ids)}")

    raw_approved = pd.DataFrame([{"point_use_id": pid, "target_source_record_id": candidate_by_id[pid]["target_source_record_id"],
        "latitude": candidate_by_id[pid]["latitude"], "longitude": candidate_by_id[pid]["longitude"],
        "origin_file": all_checks[pid]["point_origin_file"], "origin_sha256": all_checks[pid]["point_origin_sha256"],
        "origin_locator": all_checks[pid]["point_origin_locator"]} for pid in sorted(raw_new_ids)])
    gn_approved = pd.DataFrame([{"point_use_id": pid, "target_source_record_id": candidate_by_id[pid]["target_source_record_id"],
        "latitude": candidate_by_id[pid]["latitude"], "longitude": candidate_by_id[pid]["longitude"],
        "origin_file": all_checks[pid]["point_origin_file"], "origin_sha256": all_checks[pid]["point_origin_sha256"],
        "origin_locator": all_checks[pid]["point_origin_locator"], "geonameid": all_checks[pid]["geonameid"],
        "source_line_1based": all_checks[pid]["source_line_1based"], "source_line_sha256": all_checks[pid]["source_line_sha256"]}
        for pid in sorted(gn_new_ids)])
    validation_rows = []
    for row in all_274.to_dict("records"):
        pid = str(row["point_use_id"]); validation = all_checks[pid]
        validation_rows.append({"point_use_id": pid, "target_source_record_id": row["target_source_record_id"],
            "candidate_coordinate_source": row["coordinate_source"], "candidate_rule_family": row["candidate_rule_family"],
            "application_new_target": pid in app_by_id, "latitude": row["latitude"], "longitude": row["longitude"],
            **validation})
    validation_frame = pd.DataFrame(validation_rows)
    if validation_frame.origin_record_locator_verified.astype(bool).sum() != 274:
        raise AssertionError("not every V7 source coordinate has an origin-locator verification")

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    outroot = OUTPUT_ROOT.resolve()
    outroot.mkdir(parents=True, exist_ok=False)
    raw_candidate_out = outroot / "tochno_207_origin_corrected_candidate_points.csv"
    gn_candidate_out = outroot / "geonames_67_origin_corrected_candidate_points.csv"
    raw_approved_out = outroot / "tochno_79_origin_corrected_approved_points.csv"
    gn_approved_out = outroot / "geonames_28_origin_corrected_approved_points.csv"
    checks_out = outroot / "v7_point_origin_native_join_checks_274.csv"
    for frame, path in [(raw_candidates, raw_candidate_out), (gn_candidates, gn_candidate_out),
                        (raw_approved, raw_approved_out), (gn_approved, gn_approved_out), (validation_frame, checks_out)]:
        output_path(path)
        frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)

    origin_receipt = {"status": "origin_corrected_application_adapters_ready_no_application",
        "created_at_utc": now, "prior_manifest": {"path": str(V3_MANIFEST), "sha256": before["v3_manifest"],
            "status": "superseded point provenance mapping; identity rows/base pins reused, point_sources replaced"},
        "approved_target_counts": {"total": 107, "actual_raw_tochno": len(raw_approved), "actual_geonames_ppl": len(gn_approved)},
        "all_274_reviewed_point_claims_origin_verified": {"raw_tochno_rows": len(raw_candidates), "actual_geonames_ppl_rows": len(gn_candidates)},
        "origin_files": {"tochno": {"path": str(TOCHNO_ORIGIN), "sha256": before["tochno_parquet"]},
            "geonames_zip": {"path": str(GEONAMES_ORIGIN), "sha256": before["geonames_zip"],
                "member": GEONAMES_MEMBER, "member_sha256": GEONAMES_MEMBER_SHA256}},
        "raw_source_review": {"candidate_path": str(V7_CANDIDATES), "candidate_sha256": before["v7_candidates"],
            "eligible_274_path": str(V7_ELIGIBLE_274), "eligible_274_sha256": before["v7_eligible_274"],
            "eligibility_receipt_sha256": before["v7_eligibility_receipt"], "independent_review_receipt_sha256": before["v7_review_receipt"]},
        "coordinate_origins": {"Tochno": "all 207 candidate rows have selected-record to raw Parquet source-row joins, payload-SHA matches and exact coordinate matches",
            "GeoNames": "all 67 candidate rows have unique reviewed PPL witness joins to exact RU.txt line number, byte offsets, line SHA, geonameid, feature code, and exact coordinates"},
        "application_eligible_outputs": {"tochno_candidate": {"path": str(raw_candidate_out), "sha256": sha256_file(raw_candidate_out), "rows": len(raw_candidates)},
            "geonames_candidate": {"path": str(gn_candidate_out), "sha256": sha256_file(gn_candidate_out), "rows": len(gn_candidates)},
            "tochno_approved": {"path": str(raw_approved_out), "sha256": sha256_file(raw_approved_out), "rows": len(raw_approved)},
            "geonames_approved": {"path": str(gn_approved_out), "sha256": sha256_file(gn_approved_out), "rows": len(gn_approved)}},
        "all_274_origin_validation_rows": {"path": str(checks_out), "sha256": sha256_file(checks_out), "rows": len(validation_frame)}}
    origin_receipt_out = outroot / "point_origin_reconciliation_receipt.json"
    write_json(origin_receipt_out, origin_receipt)

    common_values = {"coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False,
        "population_scope_comparability_asserted": False, "native_id_binding_asserted": False,
        "coordinate_provider_id": "", "application_inference_kind": "direct reviewed actual-origin point use; no identity propagation"}
    point_specs = []
    for family, candidate_path, approved_path, origin_path, origin_sha, family_name, rule_name, provider, quality in [
        ("raw", raw_candidate_out, raw_approved_out, TOCHNO_ORIGIN, TOCHNO_SHA256,
            "R_GN_v7_actual_Tochno_2021_source_point_origin_corrected_20261004", "R_GN_v7_Tochno_raw_row_origin_corrected_20261004",
            "Tochno 2021 selected raw Parquet source point", "literal selected source row coordinates; raw payload and coordinates reopened"),
        ("geonames", gn_candidate_out, gn_approved_out, GEONAMES_ORIGIN, GEONAMES_ZIP_SHA256,
            "R_GN_v7_actual_GeoNames_PPL_origin_corrected_20261004", "R_GN_v7_literal_GN_PPL_record_origin_corrected_20261004",
            "GeoNames RU 2026-09-07 raw PPL-family coordinate; geonameid is a raw-row locator only",
            "literal RU.txt PPL-family coordinates verified by member, line bytes, offsets, geonameid and line SHA"),
    ]:
        point_specs.append({"candidate": {"path": str(candidate_path), "sha256": sha256_file(candidate_path)},
            "approved": {"path": str(approved_path), "sha256": sha256_file(approved_path)},
            "review_receipt": {"path": str(origin_receipt_out), "sha256": sha256_file(origin_receipt_out)},
            "candidate_columns": {"target": "target_source_record_id", "latitude": "latitude", "longitude": "longitude",
                "origin_file": "point_origin_file", "origin_sha256": "point_origin_sha256", "origin_locator": "point_origin_locator"},
            "approved_columns": {"target": "target_source_record_id", "latitude": "latitude", "longitude": "longitude",
                "origin_file": "origin_file", "origin_sha256": "origin_sha256", "origin_locator": "origin_locator"},
            "origin": {"path": str(origin_path), "sha256": origin_sha},
            "output_values": common_values | {"coordinate_provider": provider, "coordinate_quality": quality,
                "coordinate_application_family": family_name, "coordinate_admission_rule_name": rule_name,
                "coordinate_use_interpretation": ("Actual coordinate origin and raw locator are recorded per point. GeoNames geonameid is used only for byte-level row location, not a provider-ID binding. Measurement date, upstream independence, precision upgrade, historical boundary or population-scope equivalence are not asserted."),
                "provider_binding_status": "not asserted"}})

    pins = file_snapshot(before_paths)
    if pins != before:
        raise AssertionError("source files changed before manifest finalization")
    review_context = list(v3.get("review_context_inputs", []))
    review_context.extend([
        {"role": "superseded_v3_manifest_origin_metadata_defect_context", "path": str(V3_MANIFEST), "sha256": before["v3_manifest"]},
        {"role": "origin_reconciliation_receipt", "path": str(origin_receipt_out), "sha256": sha256_file(origin_receipt_out)},
        {"role": "v7_staged_candidates_raw", "path": str(V7_CANDIDATES), "sha256": before["v7_candidates"]},
        {"role": "v7_full_eligible_274", "path": str(V7_ELIGIBLE_274), "sha256": before["v7_eligible_274"]},
        {"role": "v7_independent_eligibility_receipt", "path": str(V7_ELIGIBILITY_RECEIPT), "sha256": before["v7_eligibility_receipt"]},
        {"role": "v7_independent_review_receipt", "path": str(V7_REVIEW_RECEIPT), "sha256": before["v7_review_receipt"]},
        {"role": "actual_tochno_raw_coordinate_origin", "path": str(TOCHNO_ORIGIN), "sha256": before["tochno_parquet"]},
        {"role": "actual_geonames_raw_zip_coordinate_origin", "path": str(GEONAMES_ORIGIN), "sha256": before["geonames_zip"]},
    ])
    manifest = {"manifest_version": "mass_rule_extensions_origin_corrected_20261004",
        "reviewed_at_utc": now, "frozen": v3["frozen"], "base": v3["base"],
        "identity_sources": v3["identity_sources"], "point_sources": point_specs,
        "blocked_targets": v3["blocked_targets"], "federal_points": v3["federal_points"], "federal_chains": v3["federal_chains"],
        "review_context_inputs": review_context, "pending_review_cohorts": v3.get("pending_review_cohorts", []),
        "application_scope": {"identity_edge_count": 3650,
            "direct_new_point_targets": 107, "direct_new_point_origin_split": {"tochno": 79, "geonames_ppl": 28},
            "all_274_reviewed_candidate_origin_split": {"tochno": 207, "geonames_ppl": 67},
            "candidate_overlap_targets_preserved_as_unapplied_evidence": 167,
            "point_provenance_correction": "per-row origin verified against the true source; no blanket Tochno origin for GeoNames coordinates"}}
    manifest_out = outroot / "origin_corrected_application_manifest.json"
    write_new(manifest_out, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    after = file_snapshot(before_paths)
    if after != before:
        raise AssertionError("one or more pinned source files changed during bundle preparation")
    prep_receipt = {"status": "origin_corrected_manifest_ready_no_application", "created_at_utc": now,
        "preparation_script": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "manifest": {"path": str(manifest_out), "sha256": sha256_file(manifest_out)},
        "origin_receipt": {"path": str(origin_receipt_out), "sha256": sha256_file(origin_receipt_out)},
        "pinned_inputs_before": before, "pinned_inputs_after": after, "all_pinned_inputs_unchanged": True,
        "validated_counts": {"reviewed_candidates": 274, "raw_tochno_origin": 207, "geonames_ppl_origin": 67,
            "new_approved_tochno_points": 79, "new_approved_geonames_points": 28, "identity_edges": 3650},
        "no_application_performed": True}
    receipt_out = outroot / "origin_corrected_preparation_receipt.json"
    write_json(receipt_out, prep_receipt)
    print(json.dumps({"manifest": prep_receipt["manifest"], "origin_receipt": prep_receipt["origin_receipt"],
        "preparation_receipt": {"path": str(receipt_out), "sha256": sha256_file(receipt_out)},
        "counts": prep_receipt["validated_counts"], "inputs_unchanged": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
