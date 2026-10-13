#!/usr/bin/env python3
"""Append five independently reviewed 2021 GeoNames point seeds and safe graph continuations.

Only the accepted point-use ledger is projected. Selected observations and the
accepted identity graph are pinned read-only inputs and are never modified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pyarrow as pa
import pyarrow.parquet as pq

from research_rebuild.mass_linkage.build_long_table import (
    ACCEPTED_COORDINATE_STATUSES,
    ACCEPTED_EDGE_STATUSES,
)
from research_rebuild.mass_linkage.propagate_continuation_points import (
    load_source_evidence,
    read_blocked_targets,
    stage_point_use,
)
from research_rebuild.mass_linkage.apply_reviewed_current_point_retrospective_20261004 import (
    cast_addition_to_schema,
)


REVIEW_DIR = Path("/workspace/settlements-work/continuation_20261004/independent_review/point_gap_five_2021_review")
BASE_DIR = Path("/workspace/settlements-work/continuation_20261004/accepted_mass_ninth_reviewed_legacy202")
FROZEN_DIR = Path("/workspace/settlements-delivery/continuation-consolidated-20261003")
BLOCKLIST = Path("/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json")
OUTPUT = Path("/workspace/settlements-work/continuation_20261004/root/accepted_point_gap_five_reviewed")

REVIEW_RECEIPT_SHA = "30deddc0e41a86680f243724783124275a9cd902d875ea987fa240327312ca35"
ELIGIBLE_SHA = "7a51b0244cf06cd946a81b01f1cce41a3ce1daa3b4af90c19543f311972603a9"
BASE_GRAPH_SHA = "a9fec4648d24afc7345ae23fca9f45058c0962e8fd41d9124deaf01839ef58b6"
BASE_POINTS_SHA = "264812092d0bc1df17929d945609d6f12f096ab28d085a85bb26dee09cc17d5b"
SELECTED_SHA = "4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657"
EVIDENCE_SHA = "e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327"
RAW_PUBLISHER_SHA = "86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14"
GEONAMES_SHA = "9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4"
BLOCKLIST_SHA = "7a715254f965d996541001d08d3422828299f5c300dfae4cbe78b79f9a5b0e70"

SELECTED_COLUMNS = [
    "source_record_id", "census_year", "settlement_name", "settlement_type",
    "source_name_raw", "source_file", "source_sheet", "source_row", "source_sha256",
    "source_locator", "source_native_id", "source_path", "population", "population_scope",
    "population_value_quality", "is_additive_settlement_record", "entity_grain_status",
    "region_raw", "region_norm", "district_raw", "municipality_raw", "okato", "oktmo",
]
GRAPH_COLUMNS = ["from_source_record_id", "to_source_record_id", "from_year", "to_year", "relation", "decision_status", "decision_id"]
POINT_COLUMNS = ["target_source_record_id", "target_year", "latitude", "longitude", "coordinate_admission_status"]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def truth(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric {label}: {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"non-finite {label}: {value!r}")
    return result


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    rad = math.pi / 180.0
    p1, p2 = a_lat * rad, b_lat * rad
    dp, dl = (b_lat - a_lat) * rad, (b_lon - a_lon) * rad
    q = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(q))


def validate_review(review_dir: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    receipt_path = review_dir / "review_receipt.json"
    summary_path = review_dir / "review_summary.json"
    eligible_path = review_dir / "eligible_point_seeds.csv"
    replay_path = review_dir / "fixed_raw_replay.csv"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if sha(eligible_path) != ELIGIBLE_SHA or sha(replay_path) != ELIGIBLE_SHA:
        raise ValueError("the fixed reviewed point seed bytes do not match their receipt pin")
    if receipt.get("status") != "independent_point_gap_five_review_complete_candidate_only":
        raise ValueError("point review receipt is not the expected complete candidate-only review")
    if receipt.get("eligible_point_seed_csv_sha256") != ELIGIBLE_SHA:
        raise ValueError("review receipt does not pin exact eligible point seed bytes")
    if summary.get("eligible_point_seed_count") != 5 or summary.get("all_five_raw_replays_pass") is not True:
        raise ValueError("review summary does not approve exactly five fully replayed seeds")
    if summary.get("global_blocklist_targets_found") != 0 or summary.get("hard_flags_found") != 0:
        raise ValueError("reviewed seed packet reports source hard flags or a blocklist target")
    if summary.get("decision") != "approve exact five current-point seeds only; no global blocklist clearance and no identity admission or publisher/provider-ID binding":
        raise ValueError("review decision wording changed or grants broader authority")
    rows = csv_rows(eligible_path)
    expected = set(receipt["eligible_target_source_record_ids"])
    if len(rows) != 5 or {r["target_source_record_id"] for r in rows} != expected:
        raise ValueError("eligible seed rows differ from the five exact receipt targets")
    for row in rows:
        if row["review_status"] != "eligible_exact_2021_point_seed_candidate_only":
            raise ValueError(f"unexpected point candidate state for {row['target_source_record_id']}")
        if row["target_year"] != "2021" or row["proposed_point_feature_code"] != "PPL":
            raise ValueError("only reviewed 2021 physical PPL points may be applied")
        if row["global_blocklist_target"] != "False" or row["existing_accepted_current_point"] != "False":
            raise ValueError("reviewed seed is blocked or already has a current accepted point")
        if row["unique_alias_within_1km"] != "True":
            raise ValueError("reviewed physical-point rule no longer passes")
    return {"receipt": receipt, "summary": summary, "receipt_path": receipt_path,
            "summary_path": summary_path, "eligible_path": eligible_path}, rows


def hard_source_flags(ev: dict[str, Any] | None) -> list[str]:
    if not ev:
        return ["source_evidence_missing"]
    holds = []
    if truth(ev.get("is_federal_aggregate")):
        holds.append("source_federal_aggregate")
    if truth(ev.get("legacy_same_year_collision")):
        holds.append("source_same_year_collision")
    if ev.get("legacy_verified_successor_settlement_id") not in (None, "", "null"):
        holds.append("source_verified_successor_event")
    if ev.get("is_additive_settlement_record") is not True:
        holds.append("source_not_additive_atomic_settlement")
    grain = str(ev.get("entity_grain_status") or "").lower()
    if any(x in grain for x in ("aggregate", "municipal_total", "shared_okato", "parent_row")):
        holds.append("source_aggregate_or_shared_grain")
    if not str(ev.get("settlement_name") or "").strip() or not str(ev.get("settlement_type") or "").strip():
        holds.append("source_name_or_type_missing")
    # legacy_identity_conflict is retained in source evidence, but is not by
    # itself a physical-object veto after an independently accepted graph path.
    return holds


def graph_components(graph_path: Path) -> tuple[dict[str, list[tuple[str, str]]], dict[str, int], set[str]]:
    table = pq.read_table(graph_path, columns=GRAPH_COLUMNS)
    statuses = set(table.column("decision_status").to_pylist()) - ACCEPTED_EDGE_STATUSES
    if statuses:
        raise ValueError(f"graph has noncanonical decision statuses: {sorted(statuses)}")
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    years: dict[str, int] = {}
    accepted_same_place = set()
    for e in table.to_pylist():
        if e["relation"] != "same_place" or e["decision_status"] not in ACCEPTED_EDGE_STATUSES:
            continue
        a, b = str(e["from_source_record_id"]), str(e["to_source_record_id"])
        ay, by = int(e["from_year"]), int(e["to_year"])
        for sid, year in ((a, ay), (b, by)):
            old = years.setdefault(sid, year)
            if old != year:
                raise ValueError(f"source record has contradictory endpoint years in graph: {sid}")
        adjacency[a].append((b, str(e["decision_id"])))
        adjacency[b].append((a, str(e["decision_id"])))
        accepted_same_place.add(str(e["decision_id"]))
    for sid in adjacency:
        adjacency[sid].sort(key=lambda x: (x[0], x[1]))
    return adjacency, years, accepted_same_place


def component_and_paths(seed_id: str, adjacency: dict[str, list[tuple[str, str]]]) -> tuple[set[str], dict[str, list[str]]]:
    if seed_id not in adjacency:
        return {seed_id}, {seed_id: []}
    paths = {seed_id: []}
    q = deque([seed_id])
    while q:
        node = q.popleft()
        for neighbor, decision in adjacency[node]:
            if neighbor not in paths:
                paths[neighbor] = paths[node] + [decision]
                q.append(neighbor)
    return set(paths), paths


def unique_three_year_component(component: set[str], years: dict[str, int]) -> bool:
    component_years = [years[sid] for sid in component if sid in years]
    return len(component) == 3 and len(component_years) == 3 and set(component_years) == {2002, 2010, 2021}


def point_spread_conflicts(seed_lat: float, seed_lon: float, existing_rows: list[dict[str, Any]], threshold_km: float = 5.0) -> list[tuple[str, float]]:
    conflicts = []
    for row in existing_rows:
        distance = haversine_km(seed_lat, seed_lon, float(row["latitude"]), float(row["longitude"]))
        if distance > threshold_km:
            conflicts.append((str(row["target_source_record_id"]), distance))
    return conflicts


def load_selected(path: Path, needed: set[str]) -> dict[str, dict[str, Any]]:
    table = pq.read_table(path, columns=SELECTED_COLUMNS, filters=[("source_record_id", "in", sorted(needed))])
    rows = {str(r["source_record_id"]): r for r in table.to_pylist()}
    if rows.keys() != needed:
        raise ValueError(f"selected source rows missing for accepted component: {sorted(needed - rows.keys())}")
    return rows


def load_existing_points(path: Path, needed: set[str]) -> dict[str, dict[str, Any]]:
    if not needed:
        return {}
    table = pq.read_table(path, columns=POINT_COLUMNS, filters=[("target_source_record_id", "in", sorted(needed))])
    result: dict[str, dict[str, Any]] = {}
    for r in table.to_pylist():
        sid = str(r["target_source_record_id"])
        status = r["coordinate_admission_status"]
        if status not in ACCEPTED_COORDINATE_STATUSES:
            continue
        if sid in result:
            raise ValueError(f"duplicate accepted point target in baseline: {sid}")
        result[sid] = r
    return result


def make_seed_carrier(row: dict[str, str], review_sha: str) -> dict[str, Any]:
    lat = number(row["proposed_point_latitude"], "GeoNames latitude")
    lon = number(row["proposed_point_longitude"], "GeoNames longitude")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("reviewed GeoNames coordinate is outside WGS84 bounds")
    locator = (
        f"member=RU.txt;line={row['proposed_point_line_1based']};"
        f"byte_start={row['proposed_point_byte_start_0based']};"
        f"byte_end={row['proposed_point_byte_end_0based']};"
        f"raw_line_sha256={row['proposed_point_line_sha256']}"
    )
    return {
        "target_source_record_id": row["target_source_record_id"],
        "target_year": 2021,
        "latitude": lat,
        "longitude": lon,
        "coordinate_quality": "independently_reviewed_named_physical_place_point",
        "coordinate_source": "GeoNames RU PPL row; literal point use only",
        "coordinate_source_record_id": None,
        "coordinate_provider": "GeoNames",
        "coordinate_provider_id": None,
        "coordinate_provider_family": "gazetteer",
        "coordinate_provenance": (
            f"Independent review {review_sha}; exact current publisher source row and one matching GeoNames RU physical PPL alias within 1 km; "
            "GeoNames identifier is retained only as an internal raw-row locator, not as provider identity binding."
        ),
        "admission_rule": "point_gap_five_exact_current_physical_ppl_seed_20261004",
        "provider_binding_status": "GeoNames external identifier binding not asserted",
        "provider_fias_binding_status": "not_asserted",
        "coordinate_admission_status": "reviewed_extension_rule_accepted",
        "coordinate_measurement_date_unknown": True,
        "boundary_comparability_asserted": False,
        "coordinate_provider_family": "GeoNames RU gazetteer point; provider identity not bound",
        "provider_query_receipt_missing": True,
        "coordinate_uncertainty_flags_json": json.dumps({
            "measurement_date_unknown": True,
            "coordinate_accuracy_claimed": False,
            "census_geometry_equivalence_claimed": False,
            "geonames_identifier_binding_claimed": False,
            "retrospective_historic_use_requires_accepted_same_place_path": True,
        }, sort_keys=True),
        "coordinate_application_family": "point_gap_five_reviewed_current_point_seed_20261004",
        "review_id": "independent_point_gap_five_2021_review",
        "application_inference_kind": "direct_reviewed_current_point_seed",
        "direct_historical_coordinate_measurement": False,
        "population_scope_comparability_asserted": False,
        "coordinate_source_sha256": row["proposed_point_source_sha256"],
        "coordinate_source_locator": locator,
        "coordinate_source_file": row["proposed_point_source_path"],
        "coordinate_source_origin": "GeoNames RU physical place point row",
        "coordinate_source_input_artifact_sha256": row["proposed_point_source_sha256"],
        "coordinate_source_date": None,
        "coordinate_source_latitude_raw": row["proposed_point_latitude"],
        "coordinate_source_longitude_raw": row["proposed_point_longitude"],
        "point_origin_file": row["proposed_point_source_path"],
        "point_origin_sha256": row["proposed_point_source_sha256"],
        "point_origin_locator": locator,
        "point_origin_kind": "geonames_RU_literal_physical_PPL_row",
        "point_claim_artifact_file": row["proposed_point_source_path"],
        "point_claim_artifact_sha256": row["proposed_point_source_sha256"],
        "coordinate_application_review_sha256": review_sha,
        "geonames_source_file": row["proposed_point_source_path"],
        "geonames_source_sha256": row["proposed_point_source_sha256"],
        "geonames_geonameid": row["proposed_point_geonameid"],
        "geonames_record_locator": locator,
        "geonames_source_name_raw": row["proposed_point_raw_name"],
        "geonames_ascii_name_raw": row["proposed_point_raw_name"],
        "geonames_feature_class": "P",
        "geonames_feature_code": row["proposed_point_feature_code"],
        "geonames_country_code": "RU",
        "geonames_admin1_raw": row["proposed_point_admin1"],
        "geonames_raw_line_sha256": row["proposed_point_line_sha256"],
        "geonames_alias_literal_in_raw_member": True,
        "provider_id_binding_asserted": False,
        "fias_identifier_binding_claimed": False,
        "native_id_binding_asserted": False,
        "modern_provider_binding_claimed": False,
        "historical_measurement_claimed": False,
        "candidate_only": False,
    }


def direct_review_checks(row: dict[str, str], selected: dict[str, Any], evidence: dict[str, Any], blocked: set[str], existing: dict[str, Any]) -> list[str]:
    sid = row["target_source_record_id"]
    holds = []
    if sid in blocked:
        holds.append("global_blocklist_exact_target")
    if sid in existing:
        holds.append("already_has_accepted_point")
    if int(selected["census_year"]) != 2021 or row["target_year"] != "2021":
        holds.append("not_current_2021_source_row")
    if str(selected["settlement_name"]) != row["settlement_name"] or str(selected["settlement_type"]) != row["settlement_type"]:
        holds.append("selected_name_or_type_mismatch")
    if str(selected["region_raw"]) != row["region_raw"]:
        holds.append("selected_region_mismatch")
    if str(selected["oktmo"]) != row["native_oktmo_raw"]:
        holds.append("selected_native_oktmo_mismatch")
    if int(round(float(selected["population"]))) != int(round(float(row["population"]))):
        holds.append("selected_population_mismatch")
    if str(selected["is_additive_settlement_record"]).lower() != "true":
        holds.append("selected_row_not_additive")
    holds.extend(hard_source_flags(evidence))
    raw_flags = json.loads(row["current_source_evidence_hardflags_json"] or "{}")
    if raw_flags:
        holds.append("reviewed_packet_reports_hard_source_flags")
    if row["source_parquet_sha256"] != RAW_PUBLISHER_SHA:
        holds.append("reviewed_raw_publisher_pin_mismatch")
    if row["proposed_point_source_sha256"] != GEONAMES_SHA:
        holds.append("reviewed_geonames_pin_mismatch")
    return holds


def build_additions(rows: list[dict[str, str]], selected: dict[str, dict[str, Any]], evidence: dict[tuple[str, int], dict],
                    point_rows: dict[str, dict[str, Any]], components: dict[str, set[str]],
                    paths_by_seed: dict[str, dict[str, list[str]]], adjacency: dict[str, list[tuple[str, str]]],
                    year_by_id: dict[str, int], blocked: set[str], review_sha: str):
    additions: list[dict[str, Any]] = []
    holds: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    used_targets: set[str] = set()
    seed_rows = {r["target_source_record_id"]: r for r in rows}
    component_key_by_seed = {}
    for seed_id, comp in components.items():
        key = tuple(sorted(comp))
        component_key_by_seed[seed_id] = key

    # Distinct reviewed current seeds may not be in the same identity component.
    by_component: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for seed_id, key in component_key_by_seed.items():
        by_component[key].append(seed_id)
    if any(len(v) > 1 for v in by_component.values()):
        raise ValueError("two reviewed current point seeds resolve to one accepted identity component")

    for seed_id in sorted(seed_rows):
        seed = seed_rows[seed_id]
        seed_ev = evidence.get((seed_id, 2021))
        seed_sel = selected[seed_id]
        if seed_id in blocked or seed_id in point_rows:
            holds.append({"target_source_record_id": seed_id, "hold_reason": "global_blocklist_or_existing_point", "scope": "direct_seed_and_propagation"})
            continue
        if direct_review_checks(seed, seed_sel, seed_ev or {}, blocked, point_rows):
            reasons = direct_review_checks(seed, seed_sel, seed_ev or {}, blocked, point_rows)
            holds.append({"target_source_record_id": seed_id, "hold_reason": ";".join(reasons), "scope": "direct_seed_and_propagation"})
            continue

        carrier = make_seed_carrier(seed, review_sha)
        seed_target = SimpleNamespace(**seed_sel)
        direct = stage_point_use(seed_target, seed_ev, carrier, seed_id, seed_ev, [])
        direct.update({
            "coordinate_admission_status": "reviewed_extension_rule_accepted",
            "coordinate_quality": "independently_reviewed_named_physical_place_point",
            "coordinate_source_record_id": None,
            "coordinate_provider_id": None,
            "coordinate_measurement_date_unknown": True,
            "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False,
            "direct_historical_coordinate_measurement": False,
            "application_inference_kind": "direct_reviewed_current_point_seed",
            "coordinate_application_family": "point_gap_five_reviewed_current_point_seed_20261004",
            "coordinate_application_review_sha256": review_sha,
            "admission_rule": "point_gap_five_exact_current_physical_ppl_seed_20261004",
            "admission_allowed": True,
            "application_gate_status": "reviewed_current_point_seed_accepted; no provider identifier binding",
            "coordinate_admitted": True,
            "point_admitted": True,
            "historical_propagation_allowed": True,
            "identity_edge_admitted": False,
            "historical_measurement_claimed": False,
            "modern_provider_binding_claimed": False,
            "provider_binding_status": "GeoNames external identifier binding not asserted",
            "provider_fias_binding_status": "not_asserted",
            "coordinate_provenance": carrier["coordinate_provenance"],
            "review_id": "independent_point_gap_five_2021_review",
            "point_use_id": f"point-gap-five-seed:{seed_id}",
            "target_source_record_id": seed_id,
            "target_year": 2021,
        })
        additions.append(direct)
        used_targets.add(seed_id)

        comp = components[seed_id]
        all_years = [year_by_id[sid] for sid in comp if sid in year_by_id]
        year_unique = unique_three_year_component(comp, year_by_id)
        seed_path = paths_by_seed[seed_id]
        context = {"seed_source_record_id": seed_id, "component_source_record_ids": sorted(comp),
                   "component_census_years": sorted(all_years), "three_year_unique_component": year_unique,
                   "historical_propagation_status": "pending"}
        contexts.append(context)
        if not year_unique:
            context["historical_propagation_status"] = "held_component_not_exact_unique_2002_2010_2021"
            holds.append({"target_source_record_id": seed_id, "hold_reason": "component_not_unique_three_census_years", "scope": "historical_propagation"})
            continue

        # Do not reuse the new seed if a pre-existing accepted point in this
        # component puts the component's current representative points >5 km apart.
        component_existing = [point_rows[sid] for sid in comp if sid in point_rows]
        seed_lat, seed_lon = float(carrier["latitude"]), float(carrier["longitude"])
        conflicts = point_spread_conflicts(seed_lat, seed_lon, component_existing)
        if conflicts:
            context["historical_propagation_status"] = "held_existing_component_point_spread_over_5km"
            context["point_spread_conflicts_json"] = json.dumps([{"source_record_id": sid, "distance_km": round(dist, 6)} for sid, dist in conflicts])
            holds.append({"target_source_record_id": seed_id, "hold_reason": "existing_accepted_point_spread_over_5km", "scope": "historical_propagation", "conflicts_json": context["point_spread_conflicts_json"]})
            continue

        blocked_old = []
        added_old = []
        for target_id in sorted(comp, key=lambda sid: year_by_id[sid]):
            year = year_by_id[target_id]
            if year == 2021:
                continue
            if target_id in blocked:
                blocked_old.append(target_id)
                holds.append({"target_source_record_id": target_id, "hold_reason": "global_blocklist_exact_target", "scope": "historical_propagation"})
                continue
            if target_id in point_rows:
                continue
            target_ev = evidence.get((target_id, year))
            hard = hard_source_flags(target_ev)
            if hard:
                holds.append({"target_source_record_id": target_id, "hold_reason": ";".join(hard), "scope": "historical_propagation"})
                continue
            sel = selected.get(target_id)
            if not sel:
                holds.append({"target_source_record_id": target_id, "hold_reason": "selected_endpoint_missing", "scope": "historical_propagation"})
                continue
            path_ids = seed_path.get(target_id)
            if not path_ids:
                # Same source node cannot have two years; this catches a path
                # omission instead of accidentally claiming an unsupported use.
                holds.append({"target_source_record_id": target_id, "hold_reason": "accepted_same_place_path_missing", "scope": "historical_propagation"})
                continue
            target = SimpleNamespace(**sel)
            use = stage_point_use(target, target_ev, carrier, seed_id, seed_ev, path_ids)
            use.update({
                "coordinate_admission_status": "reviewed_extension_rule_accepted",
                "coordinate_quality": "independently_reviewed_named_physical_place_point",
                "coordinate_source_record_id": None,
                "coordinate_provider_id": None,
                "coordinate_measurement_date_unknown": True,
                "boundary_comparability_asserted": False,
                "population_scope_comparability_asserted": False,
                "direct_historical_coordinate_measurement": False,
                "application_inference_kind": "modern_representative_point_retrospective_continuity_inference",
                "coordinate_application_family": "point_gap_five_reviewed_current_point_graph_continuity_20261004",
                "coordinate_application_review_sha256": review_sha,
                "admission_rule": "reviewed_exact_2021_seed_plus_accepted_unique_three_year_same_place_path",
                "admission_allowed": True,
                "application_gate_status": "reviewed_current_point_seed and canonical accepted graph path passed; physical source flags checked",
                "coordinate_admitted": True,
                "point_admitted": True,
                "historical_propagation_allowed": True,
                "identity_edge_admitted": False,
                "historical_measurement_claimed": False,
                "modern_provider_binding_claimed": False,
                "provider_binding_status": "GeoNames external identifier binding not asserted",
                "provider_fias_binding_status": "not_asserted_for_historical_target_by_graph_continuity",
                "coordinate_provenance": carrier["coordinate_provenance"] + "; applied retrospectively through canonical accepted same_place graph path; historical point measurement and source identifier binding not claimed",
                "review_id": "independent_point_gap_five_2021_review",
                "point_use_id": f"point-gap-five-retrospective:{target_id}",
                "target_source_record_id": target_id,
                "target_year": year,
                "supporting_carrier_source_record_id": seed_id,
                "inference_modern_point_use_target_source_record_id": seed_id,
                "inference_identity_path_from_source_record_id": target_id,
                "inference_identity_path_to_source_record_id": seed_id,
                "inference_identity_path_decision_ids_json": json.dumps(path_ids),
                "inference_identity_path_edge_count": len(path_ids),
                "coordinate_uncertainty_flags_json": json.dumps({
                    "measurement_date_unknown": True,
                    "historical_provider_binding_not_asserted": True,
                    "population_boundary_comparability_not_asserted": True,
                    "retrospective_same_place_path_decision_ids": path_ids,
                }, ensure_ascii=False, sort_keys=True),
            })
            additions.append(use)
            used_targets.add(target_id)
            added_old.append(target_id)
        context["historical_propagation_status"] = "applied_to_missing_unblocked_source_rows"
        context["added_historical_source_record_ids"] = added_old
        context["blocked_historical_source_record_ids"] = blocked_old
    if len(used_targets) != len(set(used_targets)):
        raise ValueError("two reviewed seeds attempted to write a point use to the same source record")
    return additions, holds, contexts


def run(review_dir: Path, base_dir: Path, frozen_dir: Path, blocklist_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output is nonempty and immutable: {output}")
    review_info, seeds = validate_review(review_dir)
    graph_path, points_path = base_dir / "accepted_identity_edges.parquet", base_dir / "accepted_point_uses.parquet"
    selected_path, evidence_path = frozen_dir / "selected_observations.parquet", frozen_dir / "source_evidence.parquet"
    raw_path = Path("/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet")
    gn_zip = Path("/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip")
    pins = {
        "review_receipt": (review_info["receipt_path"], None),
        "review_summary": (review_info["summary_path"], review_info["summary"].get("summary_sha256")),
        "eligible_seeds": (review_info["eligible_path"], ELIGIBLE_SHA),
        "base_identity_graph": (graph_path, BASE_GRAPH_SHA),
        "base_point_uses": (points_path, BASE_POINTS_SHA),
        "selected_observations": (selected_path, SELECTED_SHA),
        "source_evidence": (evidence_path, EVIDENCE_SHA),
        "raw_current_publisher": (raw_path, RAW_PUBLISHER_SHA),
        "geonames_source_zip": (gn_zip, GEONAMES_SHA),
        "global_blocklist": (blocklist_path, BLOCKLIST_SHA),
    }
    input_pins = {}
    for label, (path, expected) in pins.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing pinned {label}: {path}")
        actual = sha(path)
        if expected and actual != expected:
            raise ValueError(f"checksum mismatch for {label}: {actual}")
        if label == "review_receipt" and actual != REVIEW_RECEIPT_SHA:
            raise ValueError(f"independent review receipt hash mismatch: {actual}")
        input_pins[label] = {"path": str(path), "sha256": actual}
    # The review receipt hash is content-based and is stored in its parent run log.
    review_sha = input_pins["review_receipt"]["sha256"]
    blocked = read_blocked_targets(blocklist_path)
    graph_edges, years, _ = graph_components(graph_path)
    seeds_for_components = {r["target_source_record_id"]: component_and_paths(r["target_source_record_id"], graph_edges) for r in seeds}
    components = {sid: val[0] for sid, val in seeds_for_components.items()}
    paths_by_seed = {sid: val[1] for sid, val in seeds_for_components.items()}
    component_ids = set().union(*components.values())
    selected = load_selected(selected_path, component_ids)
    evidence = load_source_evidence(evidence_path, component_ids)
    points = load_existing_points(points_path, component_ids)
    # Every existing component point must be a canonical accepted ledger row.
    for sid, row in points.items():
        if row["coordinate_admission_status"] not in ACCEPTED_COORDINATE_STATUSES:
            raise ValueError(f"noncanonical accepted coordinate status: {sid}")
    # Validate that the staged targets remain point-empty before producing any rows.
    if set(components) & set(points):
        raise ValueError("reviewed current point seeds are already present in the ninth point ledger")
    additions, holds, component_context = build_additions(
        seeds, selected, evidence, points, components, paths_by_seed, graph_edges, years, blocked, review_sha
    )
    schema = pq.read_schema(points_path)
    if len(additions) < 5:
        raise ValueError(f"expected all five independent direct seeds to pass; only {len(additions)} point rows staged")
    casted = [cast_addition_to_schema(r, schema) for r in additions]
    add_table = pa.Table.from_pylist(casted, schema=schema)
    add_table.validate(full=True)
    target_ids = [str(r["target_source_record_id"]) for r in casted]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("duplicate addition target_source_record_id")
    if set(target_ids) & set(points):
        raise ValueError("addition would replace an existing accepted point use")
    if any(r.get("coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES for r in casted):
        raise ValueError("addition status is not in canonical accepted coordinate status set")
    if any(r.get("coordinate_provider_id") not in (None, "") for r in casted):
        raise ValueError("GeoNames provider identifier may not be asserted")
    if any(r.get("coordinate_measurement_date_unknown") is not True or r.get("boundary_comparability_asserted") is not False for r in casted):
        raise ValueError("point-use limitation flags were lost")

    output.mkdir(parents=True, exist_ok=False)
    accepted_out = output / "accepted_point_uses.parquet"
    source = pq.ParquetFile(points_path)
    with pq.ParquetWriter(accepted_out, schema, compression="zstd") as writer:
        for batch in source.iter_batches(batch_size=8192):
            writer.write_batch(batch)
        writer.write_table(add_table, row_group_size=max(1, len(casted)))
    # Read back and prove the baseline prefix is byte-value-identical by Arrow batch.
    out_parquet = pq.ParquetFile(accepted_out)
    out_iter = iter(out_parquet.iter_batches(batch_size=8192))
    out_batch = next(out_iter, None)
    out_offset = 0
    rows_equal = 0
    for old_batch in source.iter_batches(batch_size=8192):
        remaining = old_batch.num_rows
        slices = []
        while remaining:
            if out_batch is None:
                raise ValueError("output point ledger ended before the input baseline prefix")
            take = min(remaining, out_batch.num_rows - out_offset)
            slices.append(out_batch.slice(out_offset, take))
            out_offset += take
            remaining -= take
            if out_offset == out_batch.num_rows:
                out_batch = next(out_iter, None)
                out_offset = 0
        new_table = pa.Table.from_batches(slices, schema=schema)
        old_table = pa.Table.from_batches([old_batch], schema=schema)
        if not old_table.equals(new_table):
            raise ValueError("an existing point-ledger row changed in the streamed output prefix")
        rows_equal += old_batch.num_rows
    tail_slices = []
    if out_batch is not None and out_offset < out_batch.num_rows:
        tail_slices.append(out_batch.slice(out_offset))
    for rest in out_iter:
        tail_slices.append(rest)
    appended = pa.Table.from_batches(tail_slices, schema=schema) if tail_slices else pa.Table.from_batches([], schema=schema)
    if not appended.equals(add_table):
        raise ValueError("appended point rows differ from the validated additions table")
    expected_rows = source.metadata.num_rows + len(casted)
    if rows_equal != source.metadata.num_rows or out_parquet.metadata.num_rows != expected_rows:
        raise ValueError("baseline prefix row count or final ledger row count mismatch")

    # Human-review CSV retains source IDs, point origin, graph paths, and population context.
    write_rows = []
    seed_by_id = {r["target_source_record_id"]: r for r in seeds}
    for added in additions:
        sid = str(added["target_source_record_id"])
        seed_id = sid if sid in seed_by_id else added.get("supporting_carrier_source_record_id")
        seed = seed_by_id[str(seed_id)]
        sel = selected[sid]
        write_rows.append({
            "target_source_record_id": sid,
            "target_year": int(years.get(sid, 2021)),
            "population": sel["population"],
            "settlement_name": sel["settlement_name"],
            "settlement_type": sel["settlement_type"],
            "region_raw": sel["region_raw"],
            "point_latitude": added["latitude"],
            "point_longitude": added["longitude"],
            "point_origin_sha256": added["point_origin_sha256"],
            "point_origin_locator": added["point_origin_locator"],
            "geonames_geonameid_locator_only": added.get("geonames_geonameid"),
            "reviewed_current_seed_source_record_id": seed_id,
            "review_receipt_sha256": review_sha,
            "identity_path_decision_ids_json": added.get("inference_identity_path_decision_ids_json") or "[]",
            "application_inference_kind": added["application_inference_kind"],
            "coordinate_provider_id_binding_asserted": False,
            "historical_measurement_claimed": False,
            "population_boundary_comparability_asserted": False,
            "legacy_identity_conflict_preserved": bool((evidence.get((sid, int(sel["census_year"]))) or {}).get("legacy_identity_conflict")),
        })
    if write_rows:
        with (output / "point_use_additions.csv").open("w", encoding="utf-8", newline="") as f:
            fields = list(write_rows[0])
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(write_rows)
    with (output / "component_holds.csv").open("w", encoding="utf-8", newline="") as f:
        fields = sorted({k for r in holds for k in r}) or ["target_source_record_id", "hold_reason", "scope"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(holds)
    context_rows = [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in r.items()} for r in component_context]
    with (output / "component_context.csv").open("w", encoding="utf-8", newline="") as f:
        fields = sorted({k for r in context_rows for k in r})
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(context_rows)
    receipt = {
        "status": "reviewed_five_current_point_seeds_and_scoped_graph_continuity_applied",
        "review_status": review_info["receipt"]["status"],
        "direct_reviewed_seed_rows": len(seeds),
        "point_use_rows_appended": len(casted),
        "historical_point_continuity_rows_appended": sum(1 for r in additions if int(r["target_year"]) < 2021),
        "direct_current_seed_population_sum": sum(float(r["population"]) for r in seeds),
        "total_population_of_appended_point_targets_by_year": {
            str(year): sum(float(selected[str(r["target_source_record_id"])]["population"]) for r in additions if int(r["target_year"]) == year)
            for year in (2002, 2010, 2021)
        },
        "component_count": len(components),
        "historical_propagation_holds": len(holds),
        "global_blocklist_targets_added_or_removed": 0,
        "accepted_identity_graph_mutated": False,
        "selected_population_frame_mutated": False,
        "existing_point_rows_changed": 0,
        "baseline_point_rows": source.metadata.num_rows,
        "final_point_rows": out_parquet.metadata.num_rows,
        "baseline_prefix_value_identical_rows": rows_equal,
        "coordinate_measurement_date_claimed": False,
        "historical_provider_id_binding_claimed": False,
        "population_boundary_comparability_claimed": False,
        "coordinate_accuracy_claimed": False,
        "verified_successor_edges_used_as_same_place": False,
        "source_evidence_legacy_identity_flags_overwritten": False,
        "input_pins": input_pins,
        "script_sha256": sha(Path(__file__)),
        "outputs": {},
    }
    for path in sorted(output.iterdir()):
        if path.is_file():
            receipt["outputs"][path.name] = {"sha256": sha(path), "bytes": path.stat().st_size}
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    p.add_argument("--base-dir", type=Path, default=BASE_DIR)
    p.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    p.add_argument("--blocklist", type=Path, default=BLOCKLIST)
    p.add_argument("--output", type=Path, default=OUTPUT)
    args = p.parse_args()
    print(json.dumps(run(args.review_dir, args.base_dir, args.frozen_dir, args.blocklist, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
