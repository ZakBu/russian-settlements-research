"""Apply the independently reviewed Afipsky point decision to one frozen ledger.

The reviewed 2010 recommendation is already present in the input ledger, so it
is verified and left byte-value-equivalent. Only the 2002 point is superseded;
its complete prior ledger row is archived. Populations and identity edges are
never written by this utility.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES


EXPECTED_REVIEW_STATUS = "independent_afipsky_point_review_complete_candidate_only"
TARGET_2002 = "2002:1_TOM_01_04.xls:0:4403"
TARGET_2010 = "ROSSTAT2010:T5:p80:l29"
CARRIER_2021 = "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46138"
NEW_LAT = 44.9034044
NEW_LON = 38.8411512
OLD_DBf_LAT = 44.598688
OLD_DBf_LON = 38.588292
DBF_SHA = "d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650"
TOCHNO_SHA = "86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14"


def sha(path: str | Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def pinned(spec: dict[str, str], label: str) -> Path:
    path = Path(spec["path"])
    if sha(path) != spec["sha256"]:
        raise ValueError(f"{label} SHA-256 mismatch")
    return path


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1"}


def validate_review_packet(rows: list[dict[str, str]], receipt: dict[str, Any], *,
                           eligible_sha: str, receipt_sha: str) -> tuple[dict[str, str], dict[str, str]]:
    if receipt.get("status") != EXPECTED_REVIEW_STATUS:
        raise ValueError("unexpected independent point-review status")
    if receipt.get("reviewed_recommendations") != 2 or receipt.get("identity_or_population_changes") != 0:
        raise ValueError("review receipt does not approve exactly two scoped point recommendations")
    output = receipt.get("outputs", {}).get("reviewed_point_supersession_candidates.csv", {})
    if output.get("sha256") != eligible_sha or output.get("rows") != 2:
        raise ValueError("review receipt does not pin the eligible two-row CSV")
    if receipt.get("candidate_point_packet", {}).get("sha256") != "09cd1e214c8ed398324956b8bf8127a8f4be66997022a6f38a276926bede6494":
        raise ValueError("review receipt does not pin the staged Afipsky candidate")
    if len(rows) != 2 or len({r.get("target_source_record_id") for r in rows}) != 2:
        raise ValueError("expected exactly two unique reviewed Afipsky target rows")
    by_id = {r["target_source_record_id"]: r for r in rows}
    if set(by_id) != {TARGET_2002, TARGET_2010}:
        raise ValueError("reviewed target IDs differ from the exact Afipsky pair")
    old, current = by_id[TARGET_2002], by_id[TARGET_2010]
    if old.get("review_status") != "preferred_modern_representative_point_supersession_scoped_candidate":
        raise ValueError("2002 point supersession is not independently recommended")
    if current.get("review_status") != "scoped_point_use_recommended_candidate":
        raise ValueError("2010 point use is not independently recommended")
    for row in rows:
        if int(row["target_year"]) != {TARGET_2002: 2002, TARGET_2010: 2010}[row["target_source_record_id"]]:
            raise ValueError("review target year mismatch")
        if float(row["reviewed_latitude"]) != NEW_LAT or float(row["reviewed_longitude"]) != NEW_LON:
            raise ValueError("reviewed coordinate does not match the exact approved modern representative point")
        if row["point_origin_sha256"] != TOCHNO_SHA:
            raise ValueError("reviewed point origin SHA differs")
        if CARRIER_2021 not in row["point_origin_locator"]:
            raise ValueError("point locator does not identify the accepted 2021 carrier")
    if old.get("old_point_treatment", "").find("archived disputed alternative") < 0:
        raise ValueError("review does not require retaining the old 2002 point as disputed evidence")
    if "not a 2010 measured point" not in current.get("measurement_or_boundary_claim", ""):
        raise ValueError("2010 recommendation must disclaim an exact census-date point")
    return old, current


def _field(row: dict[str, Any], name: str, value: Any) -> None:
    if name in row:
        row[name] = value


def reviewed_replacement(old: dict[str, Any], carrier: dict[str, Any], *,
                         review_sha: str, points_sha: str, path_ids: list[str],
                         eligible_sha: str) -> dict[str, Any]:
    if old["target_source_record_id"] != TARGET_2002 or carrier["target_source_record_id"] != CARRIER_2021:
        raise ValueError("unexpected source point supersession endpoints")
    if old.get("coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES:
        raise ValueError("old point is not an accepted predecessor")
    if carrier.get("coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES:
        raise ValueError("current carrier point is not accepted")
    if float(old["latitude"]) != OLD_DBf_LAT or float(old["longitude"]) != OLD_DBf_LON:
        raise ValueError("old disputed point does not match the reviewed predecessor")
    if old.get("point_origin_sha256") != DBF_SHA or "record_1based=2700" not in old.get("point_origin_locator", ""):
        raise ValueError("old disputed point origin does not match the reviewed DBF record")
    if float(carrier["latitude"]) != NEW_LAT or float(carrier["longitude"]) != NEW_LON:
        raise ValueError("accepted carrier coordinates differ from reviewed coordinates")
    if carrier.get("point_origin_sha256") != TOCHNO_SHA:
        raise ValueError("accepted carrier origin differs from reviewed raw source")
    if not path_ids:
        raise ValueError("reviewed continuity requires an accepted identity path")

    # Copy selected modern coordinate-origin fields. The historical target's
    # source identity/population/code fields remain untouched.
    origin_fields = [
        "latitude", "longitude", "coordinate_source", "coordinate_source_record_id",
        "coordinate_provider", "coordinate_provider_family", "point_origin_file",
        "point_origin_sha256", "point_origin_locator", "point_origin_kind",
        "point_claim_artifact_file", "point_claim_artifact_sha256",
        "coordinate_source_file", "coordinate_source_sha256", "coordinate_source_locator",
        "coordinate_source_origin", "coordinate_source_input_artifact_sha256",
        "coordinate_source_date", "coordinate_source_latitude_raw", "coordinate_source_longitude_raw",
    ]
    changes = {key: carrier.get(key) for key in origin_fields if key in old}
    old_provenance = old.get("coordinate_provenance")
    provenance = {
        "kind": "reviewed_Afipsky_modern_representative_point_supersession",
        "review_receipt_sha256": review_sha,
        "eligible_point_review_csv_sha256": eligible_sha,
        "carrier_source_record_id": CARRIER_2021,
        "accepted_identity_path_decision_ids": path_ids,
        "predecessor_point_ledger_sha256": points_sha,
        "predecessor_archive": "superseded_point_uses.parquet",
        "predecessor_point_provenance": old_provenance,
        "historical_external_identifier_binding_asserted": False,
        "census_date_measurement_asserted": False,
        "boundary_comparability_asserted": False,
        "population_changed": False,
    }
    changes.update({
        "coordinate_quality": "reviewed retrospective modern representative point",
        "coordinate_admission_status": "reviewed_extension_rule_accepted",
        "coordinate_application_family": "R_reviewed_Afipsky_point_supersession_20261004",
        "admission_rule": "independently_reviewed_same_place_modern_point_supersession_Afipsky",
        "application_inference_kind": "modern_representative_point_retrospective_continuity_inference",
        "coordinate_measurement_date_unknown": True,
        "direct_historical_coordinate_measurement": False,
        "boundary_comparability_asserted": False,
        "population_scope_comparability_asserted": False,
        "coordinate_provider_id": None,
        "provider_binding_status": "historical_target_external_identifier_binding_not_asserted",
        "provider_fias_binding_status": "historical_target_external_identifier_binding_not_asserted",
        "native_id_binding_asserted": "False",
        "fias_identifier_binding_claimed": False,
        "provider_id_binding_asserted": False,
        "provider_identifier_binding_asserted": "False",
        "modern_provider_binding_claimed": False,
        "inference_modern_point_use_target_source_record_id": CARRIER_2021,
        "inference_identity_path_decision_ids_json": json.dumps(path_ids, ensure_ascii=False),
        "inference_identity_path_from_source_record_id": TARGET_2002,
        "inference_identity_path_to_source_record_id": CARRIER_2021,
        "inference_identity_path_edge_count": len(path_ids),
        "coordinate_application_review_sha256": review_sha,
        "source_claim_independent_review_sha256": review_sha,
        "point_choice_review_id": "independent_afipsky_point_review_20261004",
        "point_choice_review_sha256": review_sha,
        "point_choice_review_decision": "preferred_modern_representative_point_supersession_scoped_candidate",
        "point_choice_review_resolution": "Retain the old 2011 DBF assertion in full archive as disputed; use the accepted current point as retrospective representative location under reviewed stable-place continuity; no historical measurement, provider-ID binding, or boundary comparison.",
        "point_supersession_kind": "reviewed_modern_representative_point_supersedes_disputed_DBf_point",
        "point_supersession_review_sha256": review_sha,
        "point_supersession_predecessor_ledger_sha256": points_sha,
        "point_supersession_old_latitude": float(old["latitude"]),
        "point_supersession_old_longitude": float(old["longitude"]),
        "point_supersession_old_origin_sha256": old["point_origin_sha256"],
        "point_supersession_old_origin_locator": old["point_origin_locator"],
        "point_supersession_carrier_provider_id": None,
        "coordinate_provenance": json.dumps(provenance, ensure_ascii=False, sort_keys=True),
        "coordinate_use_interpretation": "reviewed retrospective modern representative point; disputed historic DBF point retained in predecessor archive; no external identifier binding",
        "coordinate_admitted": True,
        "point_admitted": True,
        "admission_allowed": True,
        "candidate_only": False,
        "integration_review_status": "accepted_after_manifest_pinned_independent_point_review",
        "review_id": "independent_afipsky_point_review_20261004",
        "application_gate_status": "passed_scoped_reviewed_point_supersession",
        "modern_point_continuity_admitted": True,
        "historical_propagation_allowed": True,
        "historical_measurement_claimed": False,
        "census_date_point_measurement_proven": False,
        "blocked_conflict_resolution_approved": False,
    })
    flags = old.get("coordinate_uncertainty_flags_json")
    try:
        parsed = json.loads(flags) if flags else []
    except (TypeError, json.JSONDecodeError):
        parsed = [str(flags)]
    parsed = sorted(set(map(str, parsed)) | {"superseded_old_GeoKLADR_point_archived_as_disputed_alternative"})
    changes["coordinate_uncertainty_flags_json"] = json.dumps(parsed, ensure_ascii=False)
    return changes


def _sql_lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _cast_for_field(value: Any, field: pa.Field) -> Any:
    if value is None:
        return None
    typ = field.type
    if pa.types.is_string(typ) or pa.types.is_large_string(typ):
        return str(value)
    if pa.types.is_boolean(typ):
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "false"}:
            return str(value).lower() == "true"
        raise ValueError(f"strict boolean conversion failed for {field.name}")
    if pa.types.is_integer(typ):
        number = float(value)
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError(f"strict integer conversion failed for {field.name}")
        return int(number)
    if pa.types.is_floating(typ):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"non-finite value for {field.name}")
        return number
    raise TypeError(f"unsupported replacement field type {field.name}:{typ}")


def accepted_path(graph: Path, start: str, end: str) -> list[str]:
    con = duckdb.connect(config={"threads": 1, "memory_limit": "1GB"})
    edges = con.execute(
        "SELECT decision_id, from_source_record_id, to_source_record_id, relation, decision_status "
        "FROM read_parquet(?) WHERE from_source_record_id IN (?, ?, ?) OR to_source_record_id IN (?, ?, ?)",
        [str(graph), TARGET_2002, TARGET_2010, CARRIER_2021, TARGET_2002, TARGET_2010, CARRIER_2021],
    ).fetchall()
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for did, a, b, relation, status in edges:
        if relation != "same_place" or status != "checked_rule_accepted":
            continue
        adj[str(a)].append((str(b), str(did)))
        adj[str(b)].append((str(a), str(did)))
    parents: dict[str, tuple[str, str] | None] = {start: None}
    queue = deque([start])
    while queue and end not in parents:
        node = queue.popleft()
        for nxt, did in adj[node]:
            if nxt not in parents:
                parents[nxt] = (node, did)
                queue.append(nxt)
    if end not in parents:
        raise ValueError("no accepted same_place path connects supersession target to current carrier")
    path, node = [], end
    while node != start:
        previous, did = parents[node]
        path.append(did)
        node = previous
    return list(reversed(path))


def apply(manifest_path: Path, output: Path) -> dict[str, Any]:
    manifest_path, output = Path(manifest_path), Path(output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    graph = pinned(manifest["graph"], "accepted graph")
    points = pinned(manifest["points"], "accepted points")
    selected = pinned(manifest["selected"], "selected observations")
    evidence = pinned(manifest["source_evidence"], "source evidence")
    eligible_path = pinned(manifest["eligible"], "eligible recommendations")
    review_path = pinned(manifest["review"], "independent review receipt")
    origin_paths = [pinned(spec, f"raw point origin {i}") for i, spec in enumerate(manifest["origins"])]
    receipt = json.loads(review_path.read_text(encoding="utf-8"))
    with eligible_path.open(encoding="utf-8", newline="") as handle:
        approved = list(csv.DictReader(handle))
    validate_review_packet(
        approved, receipt, eligible_sha=manifest["eligible"]["sha256"], receipt_sha=manifest["review"]["sha256"]
    )
    # Cross-check all independent receipt input pins, including the original
    # review baseline and frozen source evidence.
    required_inputs = {
        str(selected): manifest["selected"]["sha256"],
        str(evidence): manifest["source_evidence"]["sha256"],
        str(graph): manifest["graph"]["sha256"],
        str(manifest["review_baseline_points"]["path"]): manifest["review_baseline_points"]["sha256"],
    }
    for path, digest in required_inputs.items():
        pin = receipt.get("inputs", {}).get(path, {}).get("sha256")
        if pin != digest:
            raise ValueError(f"independent receipt does not pin required input: {path}")
    if output.exists():
        raise FileExistsError(f"output must not exist: {output}")

    con = duckdb.connect(config={"threads": 1, "memory_limit": "2GB"})
    point_rows = con.execute(
        "SELECT * FROM read_parquet(?) WHERE target_source_record_id IN (?, ?, ?)",
        [str(points), TARGET_2002, TARGET_2010, CARRIER_2021],
    ).fetch_arrow_table()
    records = {r["target_source_record_id"]: r for r in point_rows.to_pylist()}
    if set(records) != {TARGET_2002, TARGET_2010, CARRIER_2021}:
        raise ValueError("expected one predecessor, already-applied 2010 point, and current carrier")
    if len(records) != point_rows.num_rows:
        raise ValueError("duplicate point target in relevant base rows")
    old, already_2010, carrier = records[TARGET_2002], records[TARGET_2010], records[CARRIER_2021]
    if float(already_2010["latitude"]) != NEW_LAT or float(already_2010["longitude"]) != NEW_LON:
        raise ValueError("2010 reviewed point recommendation is already present with different coordinates")
    if already_2010.get("point_origin_sha256") != TOCHNO_SHA or already_2010.get("coordinate_source_record_id") != CARRIER_2021:
        raise ValueError("2010 point is not already attached to the reviewed current carrier")
    if already_2010.get("coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES:
        raise ValueError("existing 2010 point is not accepted under the canonical status")
    if float(old["latitude"]) != OLD_DBf_LAT or float(old["longitude"]) != OLD_DBf_LON:
        raise ValueError("2002 point differs from independently reviewed predecessor")
    path_ids = accepted_path(graph, TARGET_2002, CARRIER_2021)
    changes = reviewed_replacement(old, carrier, review_sha=sha(review_path), points_sha=sha(points),
                                   path_ids=path_ids, eligible_sha=sha(eligible_path))
    schema = pq.read_schema(points)
    changes = {k: _cast_for_field(v, schema.field(k)) for k, v in changes.items() if k in schema.names}
    if "point_supersession_review_sha256" not in changes or "point_supersession_old_origin_locator" not in changes:
        raise ValueError("base ledger lacks supersession provenance fields")
    if {str(p) for p in origin_paths} != {
        "/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet",
        "/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf",
    }:
        raise ValueError("raw point origin pins must be exactly the modern carrier and archived predecessor source")

    # Verify the authoritative selected/population/source assertions before
    # touching the point ledger. No population is copied into the updated row.
    selected_rows = con.execute(
        "SELECT source_record_id, census_year, population, settlement_name, settlement_type, region_norm "
        "FROM read_parquet(?) WHERE source_record_id IN (?, ?, ?)",
        [str(selected), TARGET_2002, TARGET_2010, CARRIER_2021],
    ).fetchall()
    srows = {r[0]: r for r in selected_rows}
    if set(srows) != {TARGET_2002, TARGET_2010, CARRIER_2021}:
        raise ValueError("selected observation endpoints are incomplete")
    expected_year_pop = {TARGET_2002: (2002, 17977), TARGET_2010: (2010, 18969), CARRIER_2021: (2021, 23592)}
    for sid, expected in expected_year_pop.items():
        if (int(srows[sid][1]), int(srows[sid][2])) != expected:
            raise ValueError("Afipsky selected population/year assertions differ from reviewed primary values")
    source_flags = con.execute(
        "SELECT source_record_id, source_evidence_json FROM read_parquet(?) WHERE source_record_id IN (?, ?, ?)",
        [str(evidence), TARGET_2002, TARGET_2010, CARRIER_2021],
    ).fetchall()
    for sid, raw in source_flags:
        f = json.loads(raw)
        if f.get("is_additive_settlement_record") is not True or f.get("is_federal_aggregate") is not False:
            raise ValueError(f"source grain hard hold for {sid}")
        if f.get("legacy_identity_conflict") is not False or f.get("legacy_same_year_collision") is not False:
            raise ValueError(f"identity hard hold for {sid}")
        if f.get("legacy_verified_successor_settlement_id") not in (None, "", "null"):
            raise ValueError(f"successor event hold for {sid}")

    output.mkdir(parents=True)
    archive_path = output / "superseded_point_uses.parquet"
    pq.write_table(point_rows.filter(pc.equal(point_rows["target_source_record_id"], pa.scalar(TARGET_2002))), archive_path, compression="zstd")
    out_points = output / "accepted_point_uses.parquet"
    source = pq.ParquetFile(points)
    count = changed = 0
    with pq.ParquetWriter(out_points, schema, compression="zstd") as writer:
        for batch in source.iter_batches(batch_size=8192):
            ids = batch.column(batch.schema.get_field_index("target_source_record_id")).to_pylist()
            affected = [i for i, sid in enumerate(ids) if sid == TARGET_2002]
            if len(affected) > 1:
                raise ValueError("duplicate 2002 target encountered during streaming write")
            arrays = list(batch.columns)
            if affected:
                index = affected[0]
                for col_i, field in enumerate(batch.schema):
                    if field.name in changes:
                        values = arrays[col_i].to_pylist()
                        values[index] = changes[field.name]
                        arrays[col_i] = pa.array(values, type=field.type)
                changed += 1
            corrected = pa.RecordBatch.from_arrays(arrays, schema=schema)
            corrected.validate(full=True)
            writer.write_batch(corrected)
            count += len(batch)
    if changed != 1 or count != source.metadata.num_rows:
        raise ValueError("streaming application did not replace exactly one point row")

    # Exact full-row equality for every untouched target, including arbitrary
    # optional proof columns. The output preserves source batch order, allowing
    # low-memory Arrow batch comparison rather than a huge wide DuckDB join.
    output_source = pq.ParquetFile(out_points)
    id_index = schema.get_field_index("target_source_record_id")
    compared = 0
    for left, right in zip(source.iter_batches(batch_size=4096), output_source.iter_batches(batch_size=4096)):
        if left.num_rows != right.num_rows or left.schema != right.schema:
            raise ValueError("output batch boundaries/schema differ from the pinned input")
        ids = left.column(id_index).to_pylist()
        if ids != right.column(id_index).to_pylist():
            raise ValueError("output target order differs from the pinned input")
        keep = pc.not_equal(left.column(id_index), pa.scalar(TARGET_2002))
        if not left.filter(keep).equals(right.filter(keep)):
            raise ValueError("an unrelated base point row changed in the full-column comparison")
        compared += len(ids) - ids.count(TARGET_2002)
    if compared != source.metadata.num_rows - 1:
        raise ValueError("full-column validation did not cover every untouched point row")
    post = con.execute(
        "SELECT count(*), count(DISTINCT target_source_record_id), "
        "sum(CASE WHEN target_source_record_id=? THEN 1 ELSE 0 END), "
        "sum(CASE WHEN target_source_record_id=? THEN 1 ELSE 0 END), "
        "sum(CASE WHEN target_source_record_id=? THEN 1 ELSE 0 END) "
        "FROM read_parquet(?)",
        [TARGET_2002, TARGET_2010, CARRIER_2021, str(out_points)],
    ).fetchone()
    if post[0] != source.metadata.num_rows or post[1] != source.metadata.num_rows or tuple(post[2:]) != (1, 1, 1):
        raise ValueError("output target uniqueness/count verification failed")
    replacement = con.execute(
        "SELECT latitude, longitude, target_population, point_origin_sha256, coordinate_source_record_id, "
        "target_source_record_json FROM read_parquet(?) WHERE target_source_record_id=?",
        [str(out_points), TARGET_2002],
    ).fetchone()
    if replacement[0] != NEW_LAT or replacement[1] != NEW_LON or replacement[2] != 17977.0 or replacement[3] != TOCHNO_SHA or replacement[4] != CARRIER_2021:
        raise ValueError("superseded target readback differs from approved point or population")

    result = {
        "status": "reviewed_Afipsky_point_supersession_applied_no_identity_or_population_changes",
        "manifest_sha256": sha(manifest_path),
        "script_sha256": sha(__file__),
        "review_receipt_sha256": sha(review_path),
        "eligible_csv_sha256": sha(eligible_path),
        "input_points_sha256": sha(points),
        "accepted_graph_sha256": sha(graph),
        "raw_point_origin_pins": {str(p): sha(p) for p in origin_paths},
        "output_rows": int(post[0]),
        "2010_recommendation_preexisting_exact_and_unchanged": True,
        "2002_target_rows_superseded": changed,
        "complete_predecessor_rows_archived": 1,
        "unrelated_point_rows_full_column_equal": True,
        "unrelated_point_rows_compared": compared,
        "identity_edges_changed": False,
        "population_values_changed": False,
        "population_assertions_retained": {"2002": 17977, "2010": 18969, "2021": 23592},
        "external_provider_identifier_binding_asserted": False,
        "historical_measurement_or_boundary_comparability_asserted": False,
        "outputs": {p.name: sha(p) for p in (out_points, archive_path)},
    }
    (output / "application_receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    print(json.dumps(apply(Path(args.manifest), Path(args.output)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
