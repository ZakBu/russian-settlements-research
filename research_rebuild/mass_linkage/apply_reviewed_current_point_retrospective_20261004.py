"""Append the exact 29 independently reviewed retrospective point uses.

This is a finite point-ledger application. It adds no identity edges or population
values. The historic coordinate is the already accepted 2021 carrier point, used
under an explicit continuity inference; source-provider identity, measurement date,
and historical boundary/population comparability remain unasserted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from decimal import Decimal
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from research_rebuild.mass_linkage.build_long_table import (
    ACCEPTED_COORDINATE_STATUSES,
    ACCEPTED_EDGE_STATUSES,
)


EXPECTED_REVIEW_STATUS = "independent_current_point_retrospective_review_complete_candidate_only"
EXPECTED_APPLICATION_FAMILY = "R_current_accepted_point_retrospective_same_place_component_20261004"
BLOCK_BASIS = "blocked_point_reuse_targets_v1: prior historic-point route remains blocked; this proposal uses only the distinct accepted 2021 carrier point"
EXPECTED_ELIGIBLE_COUNT = 29


def sha(path: str | Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def sql_path(path: str | Path) -> str:
    """Quote a local path as a DuckDB SQL string literal."""
    return "'" + str(path).replace("'", "''") + "'"


def require_pin(spec: dict[str, str], label: str) -> Path:
    path = Path(spec["path"])
    actual = sha(path)
    if actual != spec["sha256"]:
        raise ValueError(f"{label} SHA-256 mismatch: {path}")
    return path


def _bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "1", "yes"}


def _number(raw: Any, field: str) -> float:
    try:
        result = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Missing/invalid numeric {field}") from exc
    if not math.isfinite(result):
        raise ValueError(f"Non-finite numeric {field}")
    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def cast_addition_to_schema(row: dict[str, Any], schema: pa.Schema) -> dict[str, Any]:
    """Strictly adapt a new point-use row to the frozen ledger's physical types.

    Integer-valued numeric fields are accepted only when integral; strings are
    rendered explicitly, and no non-null scientific assertion is discarded.
    """
    result = {}
    for field in schema:
        value = row.get(field.name)
        if value is None:
            result[field.name] = None
        elif pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
            result[field.name] = str(value)
        elif pa.types.is_binary(field.type) or pa.types.is_large_binary(field.type):
            result[field.name] = value if isinstance(value, bytes) else str(value).encode("utf-8")
        elif pa.types.is_boolean(field.type):
            if isinstance(value, bool):
                result[field.name] = value
            elif isinstance(value, str) and value.lower() in {"true", "false"}:
                result[field.name] = value.lower() == "true"
            elif isinstance(value, int) and value in (0, 1):
                result[field.name] = bool(value)
            else:
                raise ValueError(f"Cannot strictly convert {field.name} to boolean: {value!r}")
        elif pa.types.is_integer(field.type):
            numeric = _number(value, field.name)
            if not numeric.is_integer():
                raise ValueError(f"Refusing non-integral {field.name}: {value!r}")
            result[field.name] = int(numeric)
        elif pa.types.is_floating(field.type):
            numeric = _number(value, field.name)
            result[field.name] = numeric
        elif pa.types.is_decimal(field.type):
            numeric = _number(value, field.name)
            result[field.name] = Decimal(str(numeric))
        else:
            raise TypeError(f"Unsupported pinned point-ledger type for {field.name}: {field.type}")
    return result


def _same_number(left: Any, right: Any, label: str) -> None:
    if _number(left, label) != _number(right, label):
        raise ValueError(f"{label} mismatch")


def _parse_json(raw: Any, label: str) -> Any:
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid JSON in {label}") from exc


def _assert_physical_source_flags(flags: dict[str, Any], label: str) -> None:
    if flags.get("is_additive_settlement_record") is not True:
        raise ValueError(f"{label} is not an additive settlement observation")
    if flags.get("is_federal_aggregate") is not False:
        raise ValueError(f"{label} is federal/aggregate or unknown")
    if flags.get("legacy_identity_conflict") is not False:
        raise ValueError(f"{label} has an unresolved legacy identity conflict")
    if flags.get("legacy_same_year_collision") is not False:
        raise ValueError(f"{label} has a same-year collision")
    if flags.get("legacy_verified_successor_settlement_id") not in (None, "", "null"):
        raise ValueError(f"{label} has a successor relation")
    if flags.get("population_scope") not in {"settlement", "settlement_population"}:
        raise ValueError(f"{label} has non-settlement/unknown population scope")


def validate_review_receipt(
    *, eligible_path: Path, eligible_sha: str, receipt_path: Path,
    receipt_sha: str, review_graph_sha: str, review_points_sha: str,
    selected_sha: str, source_evidence_sha: str, blocklist_sha: str,
    origin_replay_sha: str,
) -> dict[str, Any]:
    if sha(receipt_path) != receipt_sha:
        raise ValueError("Independent review receipt SHA-256 mismatch")
    review = json.loads(receipt_path.read_text(encoding="utf-8"))
    if review.get("status") != EXPECTED_REVIEW_STATUS:
        raise ValueError("Review receipt is not the completed candidate-only review")
    expected = {
        "eligible_coordinate_uses": EXPECTED_ELIGIBLE_COUNT,
    }
    if review.get("eligible_rows") != EXPECTED_ELIGIBLE_COUNT:
        raise ValueError("Review receipt does not approve exactly 29 uses")
    output = review.get("outputs", {}).get("eligible_retrospective_point_uses.csv", {})
    if output.get("sha256") != eligible_sha or sha(eligible_path) != eligible_sha:
        raise ValueError("Eligible CSV is not the file pinned by independent review")
    if output.get("rows") != EXPECTED_ELIGIBLE_COUNT:
        raise ValueError("Eligible CSV row count differs from independent review")
    raw_output = review.get("outputs", {}).get("raw_point_origin_replay.csv", {})
    if raw_output.get("sha256") != origin_replay_sha:
        raise ValueError("Raw point-origin replay is not pinned by independent review")
    pins = review.get("input_sha256", {})
    required_pins = {
        "selected_observations": selected_sha,
        "source_evidence": source_evidence_sha,
        "accepted_identity_edges": review_graph_sha,
        "accepted_point_uses": review_points_sha,
        "blocked_point_reuse_targets_v1": blocklist_sha,
    }
    for suffix, digest in required_pins.items():
        found = [value for path, value in pins.items() if path.endswith(suffix + ".parquet") or path.endswith(suffix + ".json")]
        if suffix == "blocked_point_reuse_targets_v1":
            found = [value for path, value in pins.items() if path.endswith("blocked_point_reuse_targets_v1.json")]
        if found != [digest]:
            raise ValueError(f"Review receipt does not pin the expected {suffix} input")
    if review.get("selected_source_mismatches") != 0:
        raise ValueError("Review found selected-source mismatches")
    if review.get("identity_path_edges_found_and_accepted") != 33:
        raise ValueError("Review did not validate all candidate identity paths")
    if review.get("exact_current_point_coordinate_origin_matches") != EXPECTED_ELIGIBLE_COUNT:
        raise ValueError("Review did not validate all 29 carrier origins/coordinates")
    if review.get("hard_source_flags_among_eligible") != 0:
        raise ValueError("Review found hard source flags among eligible uses")
    if review.get("global_point_block_list_mutated") is not False:
        raise ValueError("Review does not confirm the global point blocklist stayed intact")
    if review.get("old_global_point_block_targets_preserved") != 5:
        raise ValueError("Review did not preserve the five pre-existing global block targets")
    if eligible_path.resolve() != Path(review["outputs"]["eligible_retrospective_point_uses.csv"]["path"]).resolve():
        raise ValueError("Manifest eligible path differs from independently reviewed path")
    return review


def validate_blocklist_scope(rows: list[dict[str, str]], blocklist: dict[str, Any]) -> set[str]:
    blocked = set(blocklist.get("blocked_target_source_record_ids", []))
    eligible_ids = {row["historical_source_record_id"] for row in rows}
    intersect = blocked & eligible_ids
    marked = {
        row["historical_source_record_id"] for row in rows
        if _bool(row.get("original_global_point_reuse_block_preserved"))
    }
    if len(intersect) != 5 or marked != intersect:
        raise ValueError("Reviewed route is not an exact five-target exception to the unchanged global blocklist")
    for row in rows:
        target = row["historical_source_record_id"]
        if target in blocked:
            if row.get("original_global_point_reuse_block_basis") != BLOCK_BASIS:
                raise ValueError("Blocked target lacks the exact reviewed scoped-route basis")
            if not row.get("current_source_record_id") or not row.get("point_origin_file"):
                raise ValueError("Blocked target does not pin its exact carrier and point origin")
            _number(row.get("latitude"), "blocked target latitude")
            _number(row.get("longitude"), "blocked target longitude")
        elif _bool(row.get("original_global_point_reuse_block_preserved")):
            raise ValueError("A nonblocked target is marked as a global-block exception")
    return intersect


def assert_direct_targets_not_blocked(rows: list[dict[str, str]], blocklist: dict[str, Any]) -> None:
    blocked = set(blocklist.get("blocked_target_source_record_ids", []))
    overlap = {row["source_record_id"] for row in rows} & blocked
    if overlap:
        raise ValueError("Direct named-point route cannot waive any global point blocklist target")


def validate_reviewed_candidate(
    row: dict[str, str], *, selected: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]], carriers: dict[str, dict[str, Any]],
    origins: dict[str, dict[str, str]], graph_edges: dict[str, dict[str, Any]],
    existing_target_ids: set[str], blocked_targets: set[str],
) -> dict[str, Any]:
    target = row["historical_source_record_id"]
    carrier_id = row["current_source_record_id"]
    if target in existing_target_ids:
        raise ValueError(f"Retrospective target already has an accepted point use: {target}")
    if target not in selected or target not in evidence:
        raise ValueError("Historical source target is absent from selected/evidence inputs")
    if carrier_id not in selected or carrier_id not in evidence or carrier_id not in carriers:
        raise ValueError("Exact accepted current carrier is absent")
    historical = selected[target]
    current = selected[carrier_id]
    old_flags = evidence[target]
    current_flags = evidence[carrier_id]
    _assert_physical_source_flags(old_flags, "historical target")
    _assert_physical_source_flags(current_flags, "current carrier")

    year = int(row["historical_year"])
    if year not in {2002, 2010} or int(historical["census_year"]) != year:
        raise ValueError("Historical target year is not 2002/2010 or disagrees with selected row")
    if int(current["census_year"]) != 2021:
        raise ValueError("Retrospective carrier must be a selected 2021 record")
    for key, actual in [
        ("settlement_name", row["historical_name"]),
        ("settlement_type", row["historical_type"]),
        ("region_norm", row["historical_region_norm"]),
    ]:
        if str(historical.get(key) or "") != str(actual or ""):
            raise ValueError(f"Historical selected {key} mismatch")
    if str(current.get("settlement_name") or "") != row["current_name"]:
        raise ValueError("Current carrier name differs from reviewed candidate")
    if str(current.get("settlement_type") or "") != row["current_type"]:
        raise ValueError("Current carrier type differs from reviewed candidate")
    if str(current.get("region_norm") or "") != row["current_region_norm"]:
        raise ValueError("Current carrier region differs from reviewed candidate")
    _same_number(historical.get("population"), row["historical_population"], "historical population")

    point = carriers[carrier_id]
    if point.get("coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES:
        raise ValueError("Carrier point lacks a canonical accepted coordinate status")
    for field in ("latitude", "longitude"):
        _same_number(point.get(field), row[field], f"carrier {field}")
    for field in ("coordinate_source", "coordinate_provider", "coordinate_provider_id",
                  "point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind"):
        if str(point.get(field) or "") != str(row.get(field) or ""):
            raise ValueError(f"Carrier point {field} mismatch")
    origin = origins.get(target)
    if not origin or origin.get("current_carrier_source_record_id") != carrier_id:
        raise ValueError("No independent origin replay for the exact historical target/carrier pair")
    for candidate_field, origin_field in (
        ("point_origin_file", "source_file"),
        ("point_origin_sha256", "source_file_sha256"),
        ("point_origin_locator", "source_locator"),
    ):
        if str(row[candidate_field]) != str(origin[origin_field]):
            raise ValueError(f"Raw origin replay mismatch: {candidate_field}")
    for field in ("latitude", "longitude"):
        _same_number(row[field], origin[field], f"raw origin {field}")
    if origin.get("external_point_id") not in (None, "") and str(origin["external_point_id"]) != str(point.get("coordinate_provider_id") or ""):
        raise ValueError("Origin external point ID differs from exact accepted carrier claim")

    path = _parse_json(row.get("accepted_identity_path_json"), "accepted_identity_path_json")
    if not isinstance(path, list) or len(path) != int(row["accepted_identity_path_edge_count"]):
        raise ValueError("Reviewed identity path count/schema mismatch")
    if not path:
        raise ValueError("No reviewed same-place identity path")
    node = target
    decision_ids = []
    for edge in path:
        decision_id = str(edge.get("decision_id") or "")
        actual = graph_edges.get(decision_id)
        if not actual:
            raise ValueError("Reviewed identity edge is absent from application graph")
        if actual["decision_status"] not in ACCEPTED_EDGE_STATUSES or actual["relation"] != "same_place":
            raise ValueError("Identity path contains a nonaccepted/non-same-place edge")
        if edge.get("relation") != "same_place" or edge.get("decision_status") not in ACCEPTED_EDGE_STATUSES:
            raise ValueError("Review path itself does not mark an accepted same-place edge")
        a, b = actual["from_source_record_id"], actual["to_source_record_id"]
        if a == node:
            node = b
        elif b == node:
            node = a
        else:
            raise ValueError("Identity path edge does not continue from previous endpoint")
        decision_ids.append(decision_id)
    if node != carrier_id:
        raise ValueError("Reviewed accepted path does not terminate at exact carrier")

    flags_json = _parse_json(row.get("historical_source_evidence_flags_json"), "historical_source_evidence_flags_json")
    current_flags_json = _parse_json(row.get("current_source_evidence_flags_json"), "current_source_evidence_flags_json")
    for key in ("is_additive_settlement_record", "is_federal_aggregate", "legacy_identity_conflict",
                "legacy_same_year_collision", "legacy_verified_successor_settlement_id", "population_scope"):
        if flags_json.get(key) != old_flags.get(key):
            raise ValueError(f"Candidate historical source evidence flags disagree for {key}")
        if current_flags_json.get(key) != current_flags.get(key):
            raise ValueError(f"Candidate current source evidence flags disagree for {key}")

    is_blocked = target in blocked_targets
    if is_blocked != _bool(row.get("original_global_point_reuse_block_preserved")):
        raise ValueError("Global point blocklist status differs from reviewed row")
    return {
        "target_id": target,
        "carrier_id": carrier_id,
        "year": year,
        "latitude": _number(point["latitude"], "carrier latitude"),
        "longitude": _number(point["longitude"], "carrier longitude"),
        "decision_ids": decision_ids,
        "blocked_exception": is_blocked,
        "carrier": point,
        "selected_target": historical,
        "source_evidence": old_flags,
        "reviewed_candidate": row,
    }


def validate_direct_point_origin(row: dict[str, str], *, verify_assets: bool = True) -> dict[str, Any]:
    """Validate the actual coordinate literal attached to the six direct candidates."""
    if row.get("point_use_disposition") != "eligible_scoped_point_use_candidate_pending_root_application":
        raise ValueError("Direct point candidate is not independently eligible")
    if row.get("native_code_provider_binding") != "not_claimed":
        raise ValueError("Direct point candidate makes an unsupported provider-ID binding claim")
    if row.get("coordinate_measurement_date") != "unknown/not asserted":
        raise ValueError("Direct point candidate asserts an unsupported measurement date")
    if row.get("historical_boundary_equivalence") != "unknown/not asserted":
        raise ValueError("Direct point candidate asserts historical boundary equivalence")
    if row.get("population_value_changed") != "False" or row.get("source_row_mutated") != "False" or row.get("identity_graph_mutated") != "False" or row.get("point_ledger_mutated") != "False":
        raise ValueError("Direct point review packet reports a forbidden mutation")
    origin = _parse_json(row.get("point_origin_evidence_json"), "direct point origin evidence")
    point = (_number(row.get("point_latitude"), "direct point latitude"), _number(row.get("point_longitude"), "direct point longitude"))
    raw_path = origin.get("origin_path")
    raw_sha = origin.get("origin_sha256")
    if not raw_path or not raw_sha:
        raise ValueError("Direct point origin lacks a literal source path/hash")
    if verify_assets and sha(raw_path) != raw_sha:
        raise ValueError("Direct point origin asset SHA-256 mismatch")
    kind = origin.get("source_kind")
    if kind == "raw_named_typed_GeoKLADR_2011_DBf":
        raw = origin.get("raw_record", {})
        _same_number(raw.get("LAT"), point[0], "GeoKLADR raw latitude")
        _same_number(raw.get("LONG"), point[1], "GeoKLADR raw longitude")
        if raw.get("NAME1") != row.get("target_name") or not raw.get("SCOKATO"):
            raise ValueError("GeoKLADR point lacks exact raw name/type evidence")
        if int(origin.get("record_1based", 0)) <= 0 or int(origin.get("byte_offset_0based", -1)) < 0:
            raise ValueError("GeoKLADR origin locator is incomplete")
    elif kind == "cached_Wikidata_entity_P625":
        claim = origin.get("raw_claim", {}).get("value", {})
        _same_number(claim.get("latitude"), point[0], "Wikidata raw latitude")
        _same_number(claim.get("longitude"), point[1], "Wikidata raw longitude")
        label = origin.get("entity_label_ru", {}).get("value")
        if label != row.get("target_name"):
            raise ValueError("Wikidata raw Russian label differs from exact target name")
        if origin.get("provider_id_binding_claimed") is not False:
            raise ValueError("Wikidata source claims historical provider-ID binding")
        pop = origin.get("P1082_same_year_corroboration")
        if pop and pop.get("value") != int(float(row["source_population"])):
            raise ValueError("Wikidata population corroboration differs from selected count")
    else:
        raise ValueError(f"Unsupported direct coordinate-origin family: {kind}")
    return {"origin": origin, "lat": point[0], "lon": point[1], "origin_kind": kind,
            "origin_path": raw_path, "origin_sha256": raw_sha}


def validate_direct_packet(
    direct_spec: dict[str, str], direct_review_spec: dict[str, str],
    *, selected: dict[str, dict[str, Any]], evidence: dict[str, dict[str, Any]],
    graph_edges: dict[str, dict[str, Any]], existing_target_ids: set[str],
    verify_assets: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    candidate_path = require_pin(direct_spec, "direct point candidate CSV")
    review_path = require_pin(direct_review_spec, "direct point review receipt")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("status") != "independent_finite_point_use_review_candidates_only_no_admission":
        raise ValueError("Direct source packet does not have the expected independent review status")
    output = review.get("output", {})
    if output.get("sha256") != direct_spec["sha256"] or output.get("rows") != 6:
        raise ValueError("Direct candidate CSV hash/count is not pinned by independent review")
    if Path(output.get("path", "")).resolve() != candidate_path.resolve():
        raise ValueError("Direct candidate path differs from independent review receipt")
    if review.get("counts", {}).get("eligible_scoped_point_use_candidates_pending_root_application") != 6:
        raise ValueError("Direct review does not approve exactly six scoped point candidates")
    for source_path, digest in review.get("inputs", {}).items():
        if verify_assets and sha(source_path) != digest:
            raise ValueError(f"Direct review source input changed: {source_path}")
    rows = list(csv.DictReader(candidate_path.open(encoding="utf-8", newline="")))
    if len(rows) != 6 or len({r["source_record_id"] for r in rows}) != 6:
        raise ValueError("Direct point packet must contain six unique target observations")
    result, origin_pins = [], {}
    input_by_sha = {digest: path for path, digest in review.get("inputs", {}).items()}
    raw_cache: dict[tuple[str, int], dict[str, Any]] = {}
    raw_con = duckdb.connect(config={"threads": 1, "memory_limit": "1GB"})
    for row in rows:
        target = row["source_record_id"]
        if target in existing_target_ids:
            raise ValueError(f"Direct point target already has a point-use row: {target}")
        if target not in selected or target not in evidence:
            raise ValueError("Direct point target is missing from selected/source evidence")
        source = selected[target]
        flags = evidence[target]
        _assert_physical_source_flags(flags, "direct point target")
        year = int(row["year"])
        if int(source["census_year"]) != year or year not in {2002, 2010, 2021}:
            raise ValueError("Direct point target year does not match selected observation")
        if source.get("settlement_name") != row["target_name"]:
            raise ValueError("Direct target name does not match selected observation")
        _same_number(source.get("population"), row["source_population"], "direct target population")
        if source.get("population_scope") != row["source_population_scope"]:
            raise ValueError("Direct target population scope differs from selected observation")
        packet_flags = _parse_json(row["source_evidence_flags_preserved_json"], "direct source flags")
        for key in ("is_additive_settlement_record", "is_federal_aggregate", "legacy_identity_conflict",
                    "legacy_same_year_collision", "legacy_verified_successor_settlement_id", "population_scope"):
            if packet_flags.get(key) != flags.get(key):
                raise ValueError(f"Direct candidate source evidence differs for {key}")
        source_sha = row.get("source_sha256")
        if not source_sha or not row.get("source_file"):
            raise ValueError("Direct point packet lacks exact source-row file/hash")
        if verify_assets and sha(row["source_file"]) != source_sha:
            raise ValueError("Direct target source-row hash mismatch")
        point = validate_direct_point_origin(row, verify_assets=verify_assets)
        if point["origin_path"] in origin_pins and origin_pins[point["origin_path"]] != point["origin_sha256"]:
            raise ValueError("Inconsistent direct point origin hashes")
        origin_pins[point["origin_path"]] = point["origin_sha256"]
        endpoint = row["selected_2021_current_endpoint"]
        if endpoint not in selected or int(selected[endpoint]["census_year"]) != 2021:
            raise ValueError("Direct point packet lacks its exact selected 2021 endpoint")
        if year == 2021:
            if target != endpoint or row.get("accepted_identity_path_json") not in ("", "[]", None):
                raise ValueError("Direct 2021 point must be an exact self-target without a fabricated edge")
        else:
            path = _parse_json(row.get("accepted_identity_path_json"), "direct same-place path")
            if not isinstance(path, list) or not path:
                raise ValueError("Historical direct point use requires an accepted same-place path")
            node = target
            for edge in path:
                actual = graph_edges.get(str(edge.get("decision_id")))
                if not actual or actual.get("relation") != "same_place" or actual.get("decision_status") not in ACCEPTED_EDGE_STATUSES:
                    raise ValueError("Direct historical point route has a missing/unaccepted graph edge")
                a, b = actual["from_source_record_id"], actual["to_source_record_id"]
                if a == node:
                    node = b
                elif b == node:
                    node = a
                else:
                    raise ValueError("Direct point identity path is not continuous")
            if node != endpoint:
                raise ValueError("Direct point identity path does not end at exact 2021 endpoint")
        raw_current_sha = row.get("raw_current_source_sha256")
        raw_current_path = input_by_sha.get(raw_current_sha)
        if not raw_current_path:
            raise ValueError("Direct packet does not pin its exact current-source row asset")
        raw_row_number = int(float(row["raw_current_source_row"]))
        cache_key = (raw_current_path, raw_row_number)
        if cache_key not in raw_cache:
            if verify_assets and sha(raw_current_path) != raw_current_sha:
                raise ValueError("Raw current publisher asset hash mismatch")
            raw_cache[cache_key] = raw_con.execute(
                f"SELECT object_name,region,oktmo,latitude_dadata,longitude_dadata FROM read_parquet({sql_path(raw_current_path)}) LIMIT 1 OFFSET {raw_row_number - 1}"
            ).fetch_arrow_table().to_pylist()[0]
        raw_current = raw_cache[cache_key]
        if row["target_name"] not in str(raw_current.get("object_name") or ""):
            raise ValueError("Exact current publisher row name does not contain the reviewed target name")
        if not raw_current.get("latitude_dadata") or not raw_current.get("longitude_dadata"):
            raise ValueError("Exact current publisher row has no physical coordinate")
        current_distance = haversine_km(point["lat"], point["lon"], float(raw_current["latitude_dadata"]), float(raw_current["longitude_dadata"]))
        if abs(current_distance - float(row["point_to_raw_current_source_coordinate_km"])) > 0.002:
            raise ValueError("Direct point-to-current-source distance does not replay")
        native_code = row.get("current_native_OKTMO_raw")
        if native_code and native_code != raw_current.get("oktmo"):
            raise ValueError("Raw current OKTMO differs from the exact reviewed literal")
        result.append({"target_id": target, "year": year, "endpoint_id": endpoint,
                       "selected": source, "source_evidence": flags, "candidate": row,
                       "point": point})
    raw_con.close()
    if len(origin_pins) == 0:
        raise ValueError("No direct source-origin asset was verified")
    return result, origin_pins


def _load_manifest_table(con: duckdb.DuckDBPyConnection, spec: dict[str, str], view: str, query: str) -> list[dict[str, Any]]:
    path = require_pin(spec, view)
    con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet({sql_path(path)})")
    return con.execute(query).fetch_arrow_table().to_pylist()


def _load_selected_and_evidence(con: duckdb.DuckDBPyConnection, selected_spec: dict[str, str], evidence_spec: dict[str, str], ids: set[str]):
    selected_path = require_pin(selected_spec, "selected observations")
    evidence_path = require_pin(evidence_spec, "source evidence")
    con.execute(f"CREATE VIEW selected AS SELECT * FROM read_parquet({sql_path(selected_path)})")
    con.execute(f"CREATE VIEW source_evidence AS SELECT * FROM read_parquet({sql_path(evidence_path)})")
    con.register("wanted_ids", pa.table({"sid": sorted(ids)}))
    selected_rows = con.execute("SELECT * FROM selected s JOIN wanted_ids w ON s.source_record_id=w.sid").fetch_arrow_table().to_pylist()
    evidence_rows = con.execute("SELECT e.source_record_id,e.source_evidence_json FROM source_evidence e JOIN wanted_ids w ON e.source_record_id=w.sid").fetch_arrow_table().to_pylist()
    selected = {r["source_record_id"]: r for r in selected_rows}
    evidence = {r["source_record_id"]: json.loads(r["source_evidence_json"]) for r in evidence_rows}
    if len(selected) != len(ids) or len(evidence) != len(ids):
        raise ValueError("Not every candidate target/carrier is present exactly once in selected/source evidence")
    return selected, evidence


def validate_inputs(manifest: dict[str, Any]) -> dict[str, Any]:
    eligible_path = require_pin(manifest["eligible"], "eligible reviewed point uses")
    review_path = require_pin(manifest["review_receipt"], "independent review receipt")
    review_graph_path = require_pin(manifest["review_graph"], "review graph")
    review_points_path = require_pin(manifest["review_points"], "review point ledger")
    application_graph_path = require_pin(manifest["application_graph"], "application graph")
    application_points_path = require_pin(manifest["application_points"], "application point ledger")
    selected_path = require_pin(manifest["selected"], "selected observations")
    evidence_path = require_pin(manifest["source_evidence"], "source evidence")
    blocklist_path = require_pin(manifest["blocklist"], "global point blocklist")
    origin_path = require_pin(manifest["origin_replay"], "raw point-origin replay")

    rows = list(csv.DictReader(eligible_path.open(encoding="utf-8", newline="")))
    if len(rows) != EXPECTED_ELIGIBLE_COUNT:
        raise ValueError(f"Expected exactly {EXPECTED_ELIGIBLE_COUNT} reviewed point uses")
    targets = [r["historical_source_record_id"] for r in rows]
    if len(set(targets)) != len(targets):
        raise ValueError("Duplicate historical target in approved rows")
    carriers = [r["current_source_record_id"] for r in rows]
    if any(not c for c in carriers):
        raise ValueError("Missing exact 2021 carrier ID")

    review = validate_review_receipt(
        eligible_path=eligible_path, eligible_sha=manifest["eligible"]["sha256"],
        receipt_path=review_path, receipt_sha=manifest["review_receipt"]["sha256"],
        review_graph_sha=manifest["review_graph"]["sha256"],
        review_points_sha=manifest["review_points"]["sha256"],
        selected_sha=manifest["selected"]["sha256"],
        source_evidence_sha=manifest["source_evidence"]["sha256"],
        blocklist_sha=manifest["blocklist"]["sha256"],
        origin_replay_sha=manifest["origin_replay"]["sha256"],
    )
    # The independent packet reviewed a specific baseline. A later baseline may
    # contain additional accepted rows, but the packet inputs must stay pinned.
    if review["input_sha256"].get(str(review_graph_path)) != manifest["review_graph"]["sha256"]:
        raise ValueError("Review graph path/hash is not the independent packet baseline")
    if review["input_sha256"].get(str(review_points_path)) != manifest["review_points"]["sha256"]:
        raise ValueError("Review point-ledger path/hash is not the independent packet baseline")
    if review_graph_path == application_graph_path and review_points_path == application_points_path:
        pass

    blocklist = json.loads(blocklist_path.read_text(encoding="utf-8"))
    blocked_targets = validate_blocklist_scope(rows, blocklist)
    direct_spec = manifest.get("reviewed_direct_sources")
    direct_rows: list[dict[str, str]] = []
    direct_review_spec = None
    if direct_spec:
        direct_candidate_path = require_pin(direct_spec["candidates"], "direct point candidate CSV")
        direct_review_spec = direct_spec["review_receipt"]
        require_pin(direct_review_spec, "direct point review receipt")
        direct_rows = list(csv.DictReader(direct_candidate_path.open(encoding="utf-8", newline="")))
        if len(direct_rows) != 6:
            raise ValueError("This finite direct-source adapter accepts exactly six reviewed point uses")
        if {r["source_record_id"] for r in direct_rows} & set(targets):
            raise ValueError("Direct-source and retrospective-point target sets overlap")
        assert_direct_targets_not_blocked(direct_rows, blocklist)
    origin_rows = list(csv.DictReader(origin_path.open(encoding="utf-8", newline="")))
    origins = {r["historical_source_record_id"]: r for r in origin_rows}
    if len(origins) != EXPECTED_ELIGIBLE_COUNT or set(origins) != set(targets):
        raise ValueError("Origin replay must have exactly one row for every approved target")

    all_ids = set(targets) | set(carriers) | {r["source_record_id"] for r in direct_rows} | {r["selected_2021_current_endpoint"] for r in direct_rows}
    con = duckdb.connect(config={"threads": 1, "memory_limit": "2GB"})
    try:
        selected, evidence = _load_selected_and_evidence(con, manifest["selected"], manifest["source_evidence"], all_ids)
        con.execute(f"CREATE VIEW application_points AS SELECT * FROM read_parquet({sql_path(application_points_path)})")
        con.execute(f"CREATE VIEW application_graph AS SELECT * FROM read_parquet({sql_path(application_graph_path)})")
        con.register("target_ids", pa.table({"sid": sorted(set(targets) | {r["source_record_id"] for r in direct_rows})}))
        con.register("carrier_ids", pa.table({"sid": sorted(set(carriers))}))
        target_existing = {r["target_source_record_id"] for r in con.execute("SELECT p.target_source_record_id FROM application_points p JOIN target_ids t ON p.target_source_record_id=t.sid").fetch_arrow_table().to_pylist()}
        carrier_rows = con.execute("SELECT p.* FROM application_points p JOIN carrier_ids c ON p.target_source_record_id=c.sid").fetch_arrow_table().to_pylist()
        carrier_map = {r["target_source_record_id"]: r for r in carrier_rows}
        if len(carrier_map) != len(set(carriers)):
            raise ValueError("Every current carrier must have exactly one accepted point row")
        duplicate_carriers = con.execute("SELECT p.target_source_record_id,count(*) n FROM application_points p JOIN carrier_ids c ON p.target_source_record_id=c.sid GROUP BY 1 HAVING count(*)<>1").fetchall()
        if duplicate_carriers:
            raise ValueError("Carrier point ledger is ambiguous")
        graph_ids = set()
        for row in rows:
            graph_ids.update(str(e["decision_id"]) for e in _parse_json(row["accepted_identity_path_json"], "accepted identity path"))
        for row in direct_rows:
            if row.get("accepted_identity_path_json"):
                graph_ids.update(str(e["decision_id"]) for e in _parse_json(row["accepted_identity_path_json"], "direct accepted identity path"))
        con.register("decision_ids", pa.table({"did": sorted(graph_ids)}))
        graph_rows = con.execute("SELECT g.decision_id,g.from_source_record_id,g.to_source_record_id,g.from_year,g.to_year,g.relation,g.decision_status FROM application_graph g JOIN decision_ids d ON g.decision_id=d.did").fetch_arrow_table().to_pylist()
        graph_edges = {str(r["decision_id"]): r for r in graph_rows}
        if len(graph_edges) != len(graph_ids):
            raise ValueError("Application graph does not contain every reviewed accepted path edge")
    finally:
        con.close()

    # Validate origin assets directly from their reviewed source hashes, once each.
    origin_assets = {}
    for origin in origin_rows:
        path, digest = origin["source_file"], origin["source_file_sha256"]
        if path in origin_assets and origin_assets[path] != digest:
            raise ValueError("Origin source has inconsistent hashes in replay")
        origin_assets[path] = digest
    for path, digest in origin_assets.items():
        if sha(path) != digest:
            raise ValueError(f"Raw coordinate origin hash mismatch: {path}")

    validated = []
    for row in rows:
        validated.append(validate_reviewed_candidate(
            row, selected=selected, evidence=evidence, carriers=carrier_map,
            origins=origins, graph_edges=graph_edges, existing_target_ids=target_existing,
            blocked_targets=blocked_targets,
        ))
    direct_validated = []
    direct_origin_assets = {}
    if direct_spec:
        direct_validated, direct_origin_assets = validate_direct_packet(
            direct_spec["candidates"], direct_review_spec,
            selected=selected, evidence=evidence, graph_edges=graph_edges,
            existing_target_ids=target_existing,
        )
    return {
        "review": review,
        "rows": rows,
        "validated": validated,
        "blocked_targets": blocked_targets,
        "origin_assets": origin_assets,
        "direct_validated": direct_validated,
        "direct_origin_assets": direct_origin_assets,
        "paths": {
            "application_graph": application_graph_path,
            "application_points": application_points_path,
            "selected": selected_path,
            "source_evidence": evidence_path,
            "eligible": eligible_path,
            "review_receipt": review_path,
        },
    }


def make_addition(validated: dict[str, Any], schema: pa.Schema, review_sha: str, eligible_spec: dict[str, str], base_points_sha: str) -> dict[str, Any]:
    row = dict(validated["carrier"])
    selected = validated["selected_target"]
    target = validated["target_id"]
    carrier_id = validated["carrier_id"]
    candidate = validated["reviewed_candidate"]
    path_ids = validated["decision_ids"]
    # These fields describe the historic selected row. The coordinate source and
    # point origin below continue to name the exact accepted 2021 carrier claim.
    row.update({
        "target_source_record_id": target,
        "target_year": validated["year"],
        "coordinate_quality": "reviewed retrospective current representative point",
        "coordinate_admission_status": "reviewed_extension_rule_accepted",
        "coordinate_application_family": EXPECTED_APPLICATION_FAMILY,
        "admission_rule": "reviewed_existing_same_place_component_current_point_retrospective_use",
        "application_inference_kind": "modern_representative_point_retrospective_continuity_inference",
        "coordinate_measurement_date_unknown": True,
        "direct_historical_coordinate_measurement": False,
        "boundary_comparability_asserted": False,
        "population_scope_comparability_asserted": False,
        "coordinate_provider_id": None,
        "provider_binding_status": "historical_target_external_identifier_binding_not_asserted",
        "provider_fias_binding_status": "historical_target_external_identifier_binding_not_asserted",
        "provider_id_binding_asserted": False,
        "provider_identifier_binding_asserted": False,
        "native_id_binding_asserted": False,
        "fias_identifier_binding_claimed": False,
        "modern_provider_binding_claimed": False,
        "historical_provider_id_binding_claimed": False,
        "coordinate_source_record_id": carrier_id,
        "source_name": selected.get("settlement_name"),
        "source_type": selected.get("settlement_type"),
        "source_region": selected.get("region_raw"),
        "source_file": selected.get("source_file"),
        "source_row": selected.get("source_row"),
        "source_sha256": selected.get("source_sha256"),
        "source_locator": selected.get("source_locator"),
        "source_oktmo_raw": selected.get("oktmo"),
        "source_okato_raw": selected.get("okato"),
        "inference_modern_point_use_target_source_record_id": carrier_id,
        "inference_coordinate_origin_carrier_target_source_record_id": carrier_id,
        "inference_identity_path_decision_ids_json": json.dumps(path_ids, ensure_ascii=False),
        "inference_identity_path_from_source_record_id": target,
        "inference_identity_path_to_source_record_id": carrier_id,
        "inference_identity_path_edge_count": len(path_ids),
        "supporting_carrier_source_record_id": carrier_id,
        "supporting_carrier_admission_rule": validated["carrier"].get("admission_rule"),
        "supporting_carrier_coordinate_quality": validated["carrier"].get("coordinate_quality"),
        "supporting_carrier_coordinate_provenance": validated["carrier"].get("coordinate_provenance"),
        "supporting_carrier_provider_fias_binding_status": validated["carrier"].get("provider_fias_binding_status"),
        "supporting_carrier_point_origin_file": validated["carrier"].get("point_origin_file"),
        "supporting_carrier_point_origin_sha256": validated["carrier"].get("point_origin_sha256"),
        "supporting_carrier_point_origin_locator": validated["carrier"].get("point_origin_locator"),
        "supporting_carrier_point_origin_kind": validated["carrier"].get("point_origin_kind"),
        "coordinate_application_review_sha256": review_sha,
        "coordinate_provenance": json.dumps({
            "kind": "reviewed_current_point_retrospective_continuity",
            "review_receipt_sha256": review_sha,
            "eligible_csv_sha256": eligible_spec["sha256"],
            "base_point_ledger_sha256": base_points_sha,
            "historical_target_source_record_id": target,
            "accepted_2021_carrier_source_record_id": carrier_id,
            "accepted_identity_path_decision_ids": path_ids,
            "exact_point_origin_file": candidate["point_origin_file"],
            "exact_point_origin_sha256": candidate["point_origin_sha256"],
            "exact_point_origin_locator": candidate["point_origin_locator"],
            "coordinate_measurement_date_unknown": True,
            "historical_provider_id_binding_asserted": False,
            "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False,
        }, ensure_ascii=False, sort_keys=True),
        "candidate_only": False,
        "admission_allowed": True,
        "coordinate_admitted": True,
        "point_admitted": True,
        "historical_propagation_allowed": True,
        "application_gate_status": "accepted_after_independent_reviewed_current_point_retrospective_application",
        "application_candidate_source_path": eligible_spec["path"],
        "application_candidate_source_sha256": eligible_spec["sha256"],
        "point_use_id": f"retrospective:{target}:{carrier_id}",
        "source_record_id": target,
        "target_source_name_raw": selected.get("source_name_raw"),
        "target_population": selected.get("population"),
        "target_population_scope": selected.get("population_scope"),
        "target_population_value_quality": selected.get("population_value_quality"),
        "target_source_evidence_json": json.dumps(validated["source_evidence"], ensure_ascii=False, sort_keys=True),
        "target_source_record_json": json.dumps(selected, ensure_ascii=False, default=str, sort_keys=True),
        "point_only_assumption": "existing accepted same-place identity component; reuse current representative point retrospectively",
        "temporal_identity_admitted": False,
        "identity_edge_admitted": False,
        "population_value_changed": False,
        "provider_id_binding_claimed": False,
        "historical_measurement_claimed": False,
        "historical_measurement_claimed": False,
        "historical_boundary_comparability_claimed": False,
        "coordinate_use_interpretation": "retrospective current-point use; coordinate correctness assessed on carrier; historical external-provider identifier binding not asserted",
        "known_hold_reason": None,
        "legacy_identity_hold_reason": None,
        "blocked_conflict_resolution_approved": validated["blocked_exception"],
        "blocked_conflict_resolution_rationale": (
            "Exact target/carrier/origin/coordinate/path independently reviewed under the retrospective route; original global blocklist is unchanged and this exception applies only to this appended point-use row."
            if validated["blocked_exception"] else None
        ),
        "review_id": "independent_current_point_retrospective_review_20261004",
    })
    # Expose the exact source-record and source-flag assertions as provenance,
    # without writing census population values to any input artifact.
    if "target_source_record_json" in row:
        row["target_source_record_json"] = json.dumps(selected, ensure_ascii=False, default=str, sort_keys=True)
    allowed = set(schema.names)
    return {name: row.get(name) for name in schema.names if name in allowed}


def make_direct_addition(validated: dict[str, Any], schema: pa.Schema, review_sha: str,
                         candidate_spec: dict[str, str], base_points_sha: str) -> dict[str, Any]:
    candidate = validated["candidate"]
    selected = validated["selected"]
    target = validated["target_id"]
    endpoint = validated["endpoint_id"]
    point = validated["point"]
    origin = point["origin"]
    if point["origin_kind"] == "raw_named_typed_GeoKLADR_2011_DBf":
        coord_source = "raw_named_typed_GeoKLADR_2011_DBf"
        provider = "GeoKLADR 2011 named typed-place record"
        locator = f"record={origin['record_1based']};byte_offset_0based={origin['byte_offset_0based']};raw_OKATO={origin['computed_OKATO_from_raw_segments']}"
    else:
        coord_source = "wikidata_p625"
        provider = "Wikidata entity P625 claim"
        locator = f"entity={origin['raw_claim'].get('guid','').split('$',1)[0]};claim={origin.get('claim_guid')}"
    row = {name: None for name in schema.names}
    row.update({
        "target_source_record_id": target,
        "target_year": validated["year"],
        "latitude": point["lat"], "longitude": point["lon"],
        "coordinate_quality": "independently reviewed named physical-place representative point",
        "coordinate_source": coord_source,
        "coordinate_source_record_id": endpoint,
        "coordinate_provider": provider,
        "coordinate_provider_id": None,
        "source_name": selected.get("settlement_name"),
        "source_type": selected.get("settlement_type"),
        "source_region": selected.get("region_raw"),
        "source_file": selected.get("source_file"),
        "source_row": selected.get("source_row"),
        "source_sha256": selected.get("source_sha256"),
        "source_locator": selected.get("source_locator"),
        "coordinate_provenance": json.dumps({
            "kind": "independently_reviewed_named_physical_point",
            "review_receipt_sha256": review_sha,
            "candidate_csv_sha256": candidate_spec["sha256"],
            "historical_or_current_target_source_record_id": target,
            "selected_2021_current_endpoint": endpoint,
            "raw_point_origin": origin,
            "coordinate_measurement_date_unknown": True,
            "provider_identifier_binding_asserted": False,
            "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False,
            "same_year_population_claim_used_as_replacement": False,
        }, ensure_ascii=False, sort_keys=True),
        "admission_rule": "independent_reviewed_named_physical_point_direct_or_retrospective_same_place",
        "provider_binding_status": "point correctness independently reviewed; historical/current external-provider identifier binding not asserted",
        "provider_fias_binding_status": "external identifier binding not asserted",
        "coordinate_admission_status": "reviewed_extension_rule_accepted",
        "coordinate_measurement_date_unknown": True,
        "boundary_comparability_asserted": False,
        "coordinate_provider_family": "independently_reviewed_named_physical_place_source",
        "coordinate_application_family": "R_independent_named_physical_point_direct_review_20261004",
        "source_oktmo_raw": selected.get("oktmo"),
        "source_okato_raw": selected.get("okato"),
        "coordinate_source_file": point["origin_path"],
        "coordinate_source_sha256": point["origin_sha256"],
        "coordinate_source_locator": locator,
        "coordinate_source_origin": point["origin_kind"],
        "coordinate_source_input_artifact_sha256": point["origin_sha256"],
        "coordinate_source_latitude_raw": str(point["lat"]),
        "coordinate_source_longitude_raw": str(point["lon"]),
        "coordinate_measurement_date_claimed": False,
        "direct_historical_coordinate_measurement": False,
        "population_scope_comparability_asserted": False,
        "inference_modern_point_use_target_source_record_id": endpoint if validated["year"] < 2021 else None,
        "inference_identity_path_from_source_record_id": target if validated["year"] < 2021 else None,
        "inference_identity_path_to_source_record_id": endpoint if validated["year"] < 2021 else None,
        "inference_identity_path_edge_count": len(_parse_json(candidate["accepted_identity_path_json"], "direct path")) if candidate.get("accepted_identity_path_json") else 0,
        "inference_identity_path_decision_ids_json": json.dumps([edge["decision_id"] for edge in _parse_json(candidate["accepted_identity_path_json"], "direct path")], ensure_ascii=False) if candidate.get("accepted_identity_path_json") else "[]",
        "coordinate_application_review_sha256": review_sha,
        "candidate_only": False,
        "admission_allowed": True,
        "coordinate_admitted": True,
        "point_admitted": True,
        "application_gate_status": "accepted_after_independent_direct_point_review",
        "application_candidate_source_path": candidate_spec["path"],
        "application_candidate_source_sha256": candidate_spec["sha256"],
        "point_origin_file": point["origin_path"],
        "point_origin_sha256": point["origin_sha256"],
        "point_origin_locator": locator,
        "point_origin_kind": point["origin_kind"],
        "point_claim_artifact_file": point["origin_path"],
        "point_claim_artifact_sha256": point["origin_sha256"],
        "coordinate_source_record_id": endpoint,
        "coordinate_source": coord_source,
        "source_record_id": target,
        "point_use_id": f"named-point:{target}:{coord_source}",
        "target_source_name_raw": selected.get("source_name_raw"),
        "target_population": selected.get("population"),
        "target_population_scope": selected.get("population_scope"),
        "target_population_value_quality": selected.get("population_value_quality"),
        "target_source_evidence_json": json.dumps(validated["source_evidence"], ensure_ascii=False, sort_keys=True),
        "target_source_record_json": json.dumps(selected, ensure_ascii=False, default=str, sort_keys=True),
        "source_point_use_target_source_record_id": target,
        "source_point_use_target_year": validated["year"],
        "source_point_use_admission_rule": "independent_reviewed_named_physical_point_direct_or_retrospective_same_place",
        "source_point_use_status": "reviewed_extension_rule_accepted",
        "provider_id_binding_asserted": False,
        "provider_identifier_binding_asserted": False,
        "native_id_binding_asserted": False,
        "fias_identifier_binding_claimed": False,
        "historical_provider_id_binding_claimed": False,
        "historical_measurement_claimed": False,
        "historical_boundary_comparability_claimed": False,
        "temporal_identity_admitted": False,
        "identity_edge_admitted": False,
        "point_only_assumption": "independent named typed physical-place coordinate source; same-place route used only for historical targets",
        "known_hold_reason": None,
        "legacy_identity_hold_reason": None,
        "point_origin_record_json": json.dumps(origin, ensure_ascii=False, sort_keys=True),
        "point_source_to_current_distance_km_reviewed": candidate.get("point_to_raw_current_source_coordinate_km"),
        "point_population_value_replacement": False,
        "review_id": "independent_finite_point_use_review_20261004",
    })
    return {name: row.get(name) for name in schema.names}


def assert_baseline_prefix_exact(base_path: Path, result_path: Path, added_rows: int) -> int:
    """Read back every old field and verify the output begins with exact old rows."""
    base = pq.ParquetFile(base_path)
    result = pq.ParquetFile(result_path)
    if not base.schema_arrow.equals(result.schema_arrow, check_metadata=False):
        raise ValueError("Output point ledger schema differs from pinned baseline")
    if result.metadata.num_rows != base.metadata.num_rows + added_rows:
        raise ValueError("Output row count is not baseline plus exact reviewed additions")
    base_iter = iter(base.iter_batches(batch_size=8192))
    result_iter = iter(result.iter_batches(batch_size=8192))
    pending = None
    pending_offset = 0
    count = 0
    for old_batch in base_iter:
        needed = old_batch.num_rows
        parts = []
        while needed:
            if pending is None or pending_offset == pending.num_rows:
                try:
                    pending = next(result_iter)
                    pending_offset = 0
                except StopIteration as exc:
                    raise ValueError("Output ended before preserving the full baseline") from exc
            take = min(needed, pending.num_rows - pending_offset)
            parts.append(pending.slice(pending_offset, take))
            pending_offset += take
            needed -= take
        arrays = [pa.concat_arrays([part.column(index) for part in parts]) for index in range(old_batch.num_columns)]
        new_batch = pa.RecordBatch.from_arrays(arrays, schema=old_batch.schema)
        if not old_batch.equals(new_batch):
            raise ValueError("At least one original point-ledger value changed")
        count += old_batch.num_rows
    if count != base.metadata.num_rows:
        raise ValueError("Baseline prefix readback count mismatch")
    remaining = pending.num_rows - pending_offset if pending is not None else 0
    for batch in result_iter:
        remaining += batch.num_rows
    if remaining != added_rows:
        raise ValueError("Output suffix row count differs from exact reviewed addition count")
    return count


def apply(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"Immutable output path already exists: {output_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validated = validate_inputs(manifest)
    point_path = validated["paths"]["application_points"]
    schema = pq.read_schema(point_path)
    for required in ("target_source_record_id", "target_year", "latitude", "longitude", "coordinate_admission_status",
                     "point_origin_file", "point_origin_sha256", "point_origin_locator", "coordinate_source_record_id"):
        if required not in schema.names:
            raise ValueError(f"Application point schema lacks required field: {required}")
    retrospective_additions = [cast_addition_to_schema(make_addition(v, schema, manifest["review_receipt"]["sha256"], manifest["eligible"], manifest["application_points"]["sha256"]), schema) for v in validated["validated"]]
    direct_spec = manifest.get("reviewed_direct_sources")
    direct_review_sha = direct_spec["review_receipt"]["sha256"] if direct_spec else ""
    direct_additions = [cast_addition_to_schema(make_direct_addition(v, schema, direct_review_sha, direct_spec["candidates"], manifest["application_points"]["sha256"]), schema) for v in validated["direct_validated"]] if direct_spec else []
    additions = retrospective_additions + direct_additions
    additions_table = pa.Table.from_pylist(additions, schema=schema)
    retro_table = pa.Table.from_pylist(retrospective_additions, schema=schema)
    direct_table = pa.Table.from_pylist(direct_additions, schema=schema) if direct_additions else pa.Table.from_pylist([], schema=schema)
    output_path.mkdir(parents=True, exist_ok=False)
    result_points_path = output_path / "accepted_point_uses.parquet"
    additions_path = output_path / "point_use_additions.parquet"
    retro_path = output_path / "reviewed_current_point_retrospective_uses.parquet"
    direct_path = output_path / "reviewed_direct_named_physical_point_uses.parquet"
    source = pq.ParquetFile(point_path)
    with pq.ParquetWriter(result_points_path, schema, compression="zstd") as writer:
        for batch in source.iter_batches(batch_size=8192):
            writer.write_batch(batch)
        for batch in additions_table.to_batches(max_chunksize=8192):
            writer.write_batch(batch)
    preserved = assert_baseline_prefix_exact(point_path, result_points_path, len(additions))
    # Confirm the appended identity namespace is exact and every new coordinate
    # has the canonical accepted status. Existing target IDs were rejected in
    # validation; this readback catches a serialization/order mistake.
    pq.write_table(additions_table, additions_path, compression="zstd")
    pq.write_table(retro_table, retro_path, compression="zstd")
    if direct_additions:
        pq.write_table(direct_table, direct_path, compression="zstd")
    added_readback = pq.read_table(additions_path, columns=["target_source_record_id", "coordinate_admission_status"])
    expected_added_ids = {v["target_id"] for v in validated["validated"] + validated["direct_validated"]}
    if added_readback.num_rows != len(additions) or set(added_readback["target_source_record_id"].to_pylist()) != expected_added_ids:
        raise ValueError("Addition readback target set/count mismatch")
    if set(added_readback["coordinate_admission_status"].to_pylist()) != {"reviewed_extension_rule_accepted"}:
        raise ValueError("Addition readback has noncanonical coordinate-admission status")
    result = {
        "status": "reviewed_current_point_retrospective_uses_applied_no_identity_or_population_changes",
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha(manifest_path),
        "script_sha256": sha(Path(__file__).resolve()),
        "review_receipt_sha256": manifest["review_receipt"]["sha256"],
        "eligible_csv_sha256": manifest["eligible"]["sha256"],
        "uses_added": len(additions),
        "reviewed_retrospective_uses_added": len(retrospective_additions),
        "reviewed_direct_named_point_uses_added": len(direct_additions),
        "uses_by_year": {str(y): sum(v["year"] == y for v in validated["validated"]) + sum(v["year"] == y for v in validated["direct_validated"]) for y in (2002, 2010, 2021)},
        "historic_population_context_only_by_year": {str(y): sum(float(v["reviewed_candidate"]["historical_population"]) for v in validated["validated"] if int(v["year"]) == y) for y in (2002, 2010)},
        "scoped_global_block_exceptions": len(validated["blocked_targets"]),
        "global_point_blocklist_mutated": False,
        "identity_graph_changed": False,
        "population_values_changed": False,
        "coordinate_measurement_date_asserted": False,
        "historical_external_provider_id_binding_asserted": False,
        "boundary_comparability_asserted": False,
        "population_scope_comparability_asserted": False,
        "raw_origin_asset_pins": validated["origin_assets"],
        "direct_point_origin_asset_pins": validated["direct_origin_assets"],
        "inputs": {key: {"path": spec["path"], "sha256": spec["sha256"]}
                   for key, spec in manifest.items() if isinstance(spec, dict) and {"path", "sha256"}.issubset(spec)},
        "outputs": {
            result_points_path.name: {"path": str(result_points_path), "sha256": sha(result_points_path), "rows": pq.ParquetFile(result_points_path).metadata.num_rows},
            additions_path.name: {"path": str(additions_path), "sha256": sha(additions_path), "rows": pq.ParquetFile(additions_path).metadata.num_rows},
            retro_path.name: {"path": str(retro_path), "sha256": sha(retro_path), "rows": pq.ParquetFile(retro_path).metadata.num_rows},
        },
    }
    if direct_additions:
        result["outputs"][direct_path.name] = {"path": str(direct_path), "sha256": sha(direct_path), "rows": pq.ParquetFile(direct_path).metadata.num_rows}
    result["baseline_point_rows"] = source.metadata.num_rows
    result["baseline_point_rows_preserved_exactly"] = preserved == source.metadata.num_rows
    result["point_rows_after_append"] = source.metadata.num_rows + len(additions)
    (output_path / "application_receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true", help="Validate all 29 uses without writing a ledger")
    args = parser.parse_args()
    if args.validate_only:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validated = validate_inputs(manifest)
        years = {str(year): sum(v["year"] == year for v in validated["validated"] + validated["direct_validated"]) for year in (2002, 2010, 2021)}
        print(json.dumps({"status": "all_reviewed_uses_validated_no_output_written", "retrospective_uses": len(validated["validated"]), "direct_named_point_uses": len(validated["direct_validated"]), "uses_by_year": years, "blocked_exceptions": len(validated["blocked_targets"])}, ensure_ascii=False))
        return
    if args.output is None:
        parser.error("--output is required unless --validate-only is set")
    print(json.dumps(apply(args.manifest, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
