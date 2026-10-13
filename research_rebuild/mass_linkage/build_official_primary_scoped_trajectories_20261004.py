#!/usr/bin/env python3
"""Build an immutable, scoped display layer for three source-backed census trajectories.

This package does not edit selected observations, accepted identity edges, point uses,
or the national long table.  It projects reviewed source assertions and exact source
aliases into a small, inspectable trajectory view.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


STAGE = Path("/workspace/settlements-work/continuation_20261004/independent_review/large_current4_official_primary_staged_v2")
DEFAULT_SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
DEFAULT_OUT = Path("/workspace/settlements-work/continuation_20261004/R4/official_primary_scoped_trajectory_integration")

PLACE_ORDER = ["Кущевская", "Калининец", "Трудовое"]
YEARS = [2002, 2010, 2021]
EXPECTED_VALUES = {
    ("Кущевская", 2002): 29533,
    ("Кущевская", 2010): 28362,
    ("Кущевская", 2021): 30375,
    ("Калининец", 2002): 23873,
    ("Калининец", 2010): 21774,
    ("Калининец", 2021): 25082,
    ("Трудовое", 2002): 18935,
    ("Трудовое", 2010): 18522,
    ("Трудовое", 2021): 19543,
}
EXPECTED_IDS = {
    ("Кущевская", 2002): "ROSSTAT2002:T4:01-04:r4338",
    ("Кущевская", 2010): "ROSSTAT2010:T5:p79:l18",
    ("Кущевская", 2021): "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:45656",
    ("Калининец", 2002): "ROSSTAT2002:T4:01-04:r1212",
    ("Калининец", 2010): "ROSSTAT2010:T5:p36:l82",
    ("Калининец", 2021): "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:68255",
    ("Трудовое", 2002): "2002:1_TOM_01_04.xls:0:9927",
    ("Трудовое", 2010): "ROSSTAT2010:T5:p199:l277",
    ("Трудовое", 2021): "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:100072",
}
VLAS = "Власиха"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty output: {path}")
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _selected_index(path: Path, needed: set[str]) -> dict[str, dict[str, Any]]:
    cols = [
        "source_record_id", "census_year", "source_file", "source_sheet", "source_row",
        "source_native_id", "source_name_raw", "settlement_name", "settlement_type",
        "region_raw", "population", "latitude", "longitude", "population_scope",
        "population_value_quality", "source_path", "source_sha256", "source_locator",
        "source_population_raw", "men", "women", "identity_admission", "coordinate_admission",
    ]
    table = pq.read_table(path, columns=cols)
    found: dict[str, dict[str, Any]] = {}
    for row in table.to_pylist():
        sid = row["source_record_id"]
        if sid in needed:
            found[sid] = row
    missing = needed - found.keys()
    if missing:
        raise ValueError(f"selected observation IDs absent from pinned selected frame: {sorted(missing)}")
    return found


def _as_int(value: Any, where: str) -> int:
    if value is None or value == "":
        raise ValueError(f"missing population at {where}")
    n = int(float(value))
    if float(value) != n:
        raise ValueError(f"non-integral population at {where}: {value!r}")
    return n


def _validate_stage(stage: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    manifest_path = stage / "application_input_manifest.json"
    receipt_path = stage / "application_receipt.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen_application_inputs":
        raise ValueError("staging input manifest is not frozen")
    if receipt.get("status") != "root_approved_official_primary_source_assertion_layer_staged_for_integration":
        raise ValueError("staged official-primary layer is not root-approved")
    mapping = {
        "official": "official_primary_observations.csv",
        "edges": "scoped_continuity_links.csv",
        "mappings": "same_census_source_mappings.csv",
        "points": "accepted_current_point_uses.csv",
        "partition": "same_census_projection_policy.csv",
    }
    tables: dict[str, list[dict[str, str]]] = {}
    receipt_keys = {
        "official": "official_primary_observations_csv",
        "edges": "scoped_continuity_links_csv",
        "mappings": "same_census_source_mappings_csv",
        "points": "accepted_current_point_uses_csv",
        "partition": "same_census_projection_policy_csv",
    }
    for key, filename in mapping.items():
        p = stage / filename
        expected = receipt["outputs"][receipt_keys[key]]["sha256"]
        actual = sha256(p)
        if expected != actual:
            raise ValueError(f"staged file checksum mismatch: {filename}")
        tables[key] = read_csv(p)
    if len(tables["official"]) != 5 or len(tables["edges"]) != 7 or len(tables["mappings"]) != 7:
        raise ValueError("staged source layer counts differ from reviewed receipt")
    if len(tables["points"]) != 4 or len(tables["partition"]) != 2:
        raise ValueError("staged point or exclusive partition counts differ from reviewed receipt")
    return {"manifest": manifest, "receipt": receipt, "manifest_sha256": sha256(manifest_path), "receipt_sha256": sha256(receipt_path)}, tables


def _official_by_source(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["source_record_id"]: row for row in rows}


def _mapping_indexes(rows: list[dict[str, str]]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    alias_to_selected: dict[str, str] = {}
    by_candidate: dict[str, dict[str, str]] = {}
    for row in rows:
        by_candidate[row["candidate_from_id"]] = row
        by_candidate[row["candidate_to_id"]] = row
        for candidate_key, selected_key in (("candidate_from_id", "from_selected_id"), ("candidate_to_id", "to_selected_id")):
            candidate, selected = row[candidate_key], row[selected_key]
            if selected:
                prior = alias_to_selected.get(candidate)
                if prior and prior != selected:
                    raise ValueError(f"conflicting selected-source mappings for {candidate}")
                alias_to_selected[candidate] = selected
    return alias_to_selected, by_candidate


def _source_record(source_id: str, selected: dict[str, dict[str, Any]], official: dict[str, dict[str, str]]) -> dict[str, Any]:
    if source_id in official:
        r = official[source_id]
        return {
            "source_record_id": source_id,
            "observation_id": r["observation_id"],
            "source_layer": "reviewed_official_primary_source_assertion",
            "year": int(r["observation_year"]),
            "settlement_name": r["settlement_name"],
            "source_name_raw": r["source_name_raw"],
            "settlement_type": r["settlement_type"],
            "source_type_raw": r["source_type_raw"],
            "region_raw": r["region_raw"],
            "population_value": _as_int(r["population_value"], source_id),
            "population_raw": r["population_raw"],
            "population_male": r["population_male"],
            "population_female": r["population_female"],
            "population_unit": r["population_unit"],
            "population_scope": r["population_scope"],
            "population_value_quality": r["population_value_quality"],
            "source_publication_row_id": r["source_publication_row_id"],
            "source_path": r["source_path"],
            "source_sha256": r["source_sha256"],
            "source_raw_locator": r["source_raw_locator"],
            "source_sheet": r["source_sheet"],
            "source_page": r["source_page"],
            "source_row": r["source_row"],
            "source_review_receipt_sha256": r["source_review_receipt_sha256"],
        }
    if source_id not in selected:
        raise ValueError(f"source id is neither a reviewed official assertion nor selected observation: {source_id}")
    r = selected[source_id]
    return {
        "source_record_id": source_id,
        "observation_id": source_id,
        "source_layer": "existing_selected_observation_projection",
        "year": int(r["census_year"]),
        "settlement_name": r["settlement_name"],
        "source_name_raw": r["source_name_raw"],
        "settlement_type": r["settlement_type"],
        "source_type_raw": r["settlement_type"],
        "region_raw": r["region_raw"],
        "population_value": _as_int(r["population"], source_id),
        "population_raw": r["source_population_raw"] or str(_as_int(r["population"], source_id)),
        "population_male": "",
        "population_female": "",
        "population_unit": "persons",
        "population_scope": r["population_scope"],
        "population_value_quality": r["population_value_quality"],
        "source_publication_row_id": source_id,
        "source_path": r["source_path"],
        "source_sha256": r["source_sha256"],
        "source_raw_locator": r["source_locator"],
        "source_sheet": r["source_sheet"],
        "source_page": "",
        "source_row": r["source_row"],
        "source_review_receipt_sha256": "",
    }


def build_records(stage: Path, selected_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    stage_info, tables = _validate_stage(stage)
    manifest = stage_info["manifest"]
    selected_pin = manifest["inputs"]["selected"]
    if str(selected_path) != selected_pin["path"]:
        # A caller can explicitly supply an equivalent frozen input only if its hash matches.
        if sha256(selected_path) != selected_pin["sha256"]:
            raise ValueError("selected frame does not match the frozen stage input")
    if sha256(selected_path) != selected_pin["sha256"]:
        raise ValueError("selected frame checksum mismatch")

    official = _official_by_source(tables["official"])
    alias_to_selected, _ = _mapping_indexes(tables["mappings"])
    selected_ids = set(alias_to_selected.values())
    for row in tables["points"]:
        selected_ids.add(row["target_source_record_id"])
    selected = _selected_index(selected_path, selected_ids)

    source_specs: dict[tuple[str, int], str] = {
        ("Кущевская", 2002): "ROSSTAT2002:T4:01-04:r4338",
        ("Кущевская", 2010): "ROSSTAT2010:T5:p79:l18",
        ("Кущевская", 2021): "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:45656",
        ("Калининец", 2002): "ROSSTAT2002:T4:01-04:r1212",
        ("Калининец", 2010): "ROSSTAT2010:T5:p36:l82",
        ("Калининец", 2021): "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:68255",
        ("Трудовое", 2002): "2002:1_TOM_01_04.xls:0:9927",
        ("Трудовое", 2010): "ROSSTAT2010:T5:p199:l277",
        ("Трудовое", 2021): "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:100072",
    }
    projection: list[dict[str, Any]] = []
    node_id_by_key: dict[tuple[str, int], str] = {}
    for place in PLACE_ORDER:
        for year in YEARS:
            sid = source_specs[(place, year)]
            rec = _source_record(sid, selected, official)
            if rec["year"] != year or rec["settlement_name"] != place:
                raise ValueError(f"source/year/name mismatch for {(place, year)}: {sid}")
            if rec["population_scope"] not in ("settlement", "one official Rosstat locality row; historic administrative boundary comparability unknown"):
                raise ValueError(f"nonlocality grain blocks scoped trajectory: {sid}: {rec['population_scope']}")
            if rec["population_value"] != EXPECTED_VALUES[(place, year)]:
                raise ValueError(f"population differs from reviewed root accounting for {(place, year)}")
            if sid != EXPECTED_IDS[(place, year)]:
                raise ValueError(f"unexpected source ID for {(place, year)}: {sid}")
            counterpart = alias_to_selected.get(sid, sid)
            if counterpart not in selected:
                # Official-only primary rows may map through an alternate candidate id, not the row itself.
                counterpart = sid
            if counterpart in selected:
                sr = selected[counterpart]
                if place != sr["settlement_name"]:
                    raise ValueError(f"selected same-census counterpart name mismatch for {sid}")
                if year != int(sr["census_year"]):
                    raise ValueError(f"selected same-census counterpart year mismatch for {sid}")
            node_id = f"scoped-observation:{place}:{year}"
            node_id_by_key[(place, year)] = node_id
            projection.append({
                "trajectory_id": f"official-primary-scoped:{place}",
                "projection_row_id": node_id,
                "place": place,
                "year": year,
                "primary_source_record_id": sid,
                "selected_observation_counterpart_id": counterpart if counterpart in selected else "",
                **rec,
                "identity_scope_status": "root_approved_scoped_physical_continuity",
                "population_primary_status": "scoped_primary_source_assertion; selected frame unchanged",
                "population_boundary_comparability_asserted": False,
                "strict_national_2002_2010_2021_chain_claimed": False,
                "legal_status_date_claimed": False,
                "historical_coordinate_asserted": False,
                "historical_provider_binding_asserted": False,
            })

    if len(projection) != 9 or len({(r["place"], r["year"]) for r in projection}) != 9:
        raise ValueError("full trajectory projection must contain exactly nine distinct place/year rows")
    for key, expected_sid in EXPECTED_IDS.items():
        if next(r for r in projection if (r["place"], r["year"]) == key)["primary_source_record_id"] != expected_sid:
            raise AssertionError("projection source id regression")

    # Same physical-continuity links are kept with both their reviewed source row IDs
    # and trajectory-node IDs.  No graph endpoint is silently rewritten to an alias.
    links: list[dict[str, Any]] = []
    for edge in tables["edges"]:
        place = edge["place"]
        if place not in PLACE_ORDER:
            continue
        y0, y1 = int(edge["from_year"]), int(edge["to_year"])
        if (place, y0) not in node_id_by_key or (place, y1) not in node_id_by_key:
            continue
        links.append({
            **edge,
            "from_projection_row_id": node_id_by_key[(place, y0)],
            "to_projection_row_id": node_id_by_key[(place, y1)],
            "from_selected_observation_counterpart_id": alias_to_selected.get(edge["from_source_record_id"], edge["from_source_record_id"]),
            "to_selected_observation_counterpart_id": alias_to_selected.get(edge["to_source_record_id"], edge["to_source_record_id"]),
            "graph_mutation_performed": False,
            "scoped_layer_only": True,
        })
    if len(links) != 6 or {(r["place"], int(r["from_year"]), int(r["to_year"])) for r in links} != {
        (place, 2002, 2010) for place in PLACE_ORDER
    } | {(place, 2010, 2021) for place in PLACE_ORDER}:
        raise ValueError("expected exactly six adjacent-year links among the three full paths")

    # Vlasikha is purposefully an isolated two-year display, not a full trajectory.
    vlas_official = next(r for r in tables["official"] if r["settlement_name"] == VLAS)
    vlas_2021_id = vlas_official["current_2021_source_record_id"]
    vlas_rows = []
    for sid in (vlas_official["source_record_id"], vlas_2021_id):
        rec = _source_record(sid, selected, official)
        year = rec["year"]
        point = next(p for p in tables["points"] if p["place"] == VLAS)
        vlas_rows.append({
            "trajectory_id": "official-primary-scoped:Власиха:two-year-display-only",
            "projection_row_id": f"scoped-observation:{VLAS}:{year}",
            "place": VLAS,
            "year": year,
            "primary_source_record_id": sid,
            "selected_observation_counterpart_id": alias_to_selected.get(sid, sid) if alias_to_selected.get(sid, sid) in selected else "",
            **rec,
            "identity_scope_status": "root_approved_scoped_physical_continuity; two-year display only",
            "population_primary_status": "scoped primary source assertion; selected frame unchanged",
            "population_boundary_comparability_asserted": False,
            "strict_national_2002_2010_2021_chain_claimed": False,
            "legal_status_date_claimed": False,
            "historical_coordinate_asserted": False,
            "historical_provider_binding_asserted": False,
            "no_2002_observation_claimed": True,
            "current_point_use_id": point["point_use_id"],
        })
    if [r["year"] for r in vlas_rows] != [2010, 2021]:
        raise ValueError("Vlasikha display must contain 2010 and 2021 only")

    point_by_place = {r["place"]: r for r in tables["points"]}
    mapping_aliases_by_key: dict[tuple[str, int], set[str]] = {}
    for m in tables["mappings"]:
        for year_key, id_key in (("candidate_from_year", "candidate_from_id"), ("candidate_to_year", "candidate_to_id")):
            mapping_aliases_by_key.setdefault((m["place"], int(m[year_key])), set()).add(m[id_key])
    for row in projection:
        key = (row["place"], int(row["year"]))
        cp = point_by_place[row["place"]]
        row["census_year"] = row["year"]
        row["source_record_id"] = row["primary_source_record_id"]
        row["population"] = row["population_value"]
        row["latitude"] = cp["latitude"]
        row["longitude"] = cp["longitude"]
        row["current_2021_source_record_id"] = cp["target_source_record_id"]
        aliases = sorted(x for x in mapping_aliases_by_key.get(key, set()) if x != row["primary_source_record_id"])
        row["same_census_source_alias_record_ids"] = json.dumps(aliases, ensure_ascii=False)
        counterpart = row["selected_observation_counterpart_id"]
        if not counterpart:
            alias_counterparts = sorted({alias_to_selected[a] for a in aliases if a in alias_to_selected})
            if len(alias_counterparts) == 1:
                counterpart = alias_counterparts[0]
        row["preferred_same_census_alternate_selected_source_record_id"] = (
            counterpart if counterpart else ""
        )
    point_uses: list[dict[str, Any]] = []
    for place in PLACE_ORDER:
        current = point_by_place[place]
        for year in YEARS:
            point_uses.append({
                "point_use_id": f"scoped-current-point-context:{place}:{year}",
                "trajectory_id": f"official-primary-scoped:{place}",
                "projection_row_id": node_id_by_key[(place, year)],
                "place": place,
                "target_year": year,
                "target_source_record_id": source_specs[(place, year)],
                "latitude": current["latitude"],
                "longitude": current["longitude"],
                "coordinate_source": current["coordinate_source"],
                "coordinate_provider_id_context_only": current["coordinate_provider_id"],
                "coordinate_admission_status": current["coordinate_admission_status"],
                "point_origin_file": current["point_origin_file"],
                "point_origin_sha256": current["point_origin_sha256"],
                "point_origin_locator": current["point_origin_locator"],
                "point_origin_kind": current["point_origin_kind"],
                "coordinate_temporal_basis": "current 2021 representative point used as a scoped physical-place context; historical measurement date unknown" if year < 2021 else "accepted 2021 representative point",
                "direct_historical_coordinate_measurement": False,
                "historical_provider_binding_asserted": False,
                "population_boundary_comparability_asserted": False,
                "qid_native_identifier_binding_asserted": False,
                "point_use_admission_status": "root_approved_scoped_point_context",
            })
    if len(point_uses) != 9:
        raise ValueError("expected one explicit point context per full-trajectory projection row")

    # Keep the already reviewed source mappings and the mutually exclusive
    # whole-versus-parts policy as independent, verbatim source-mapping artifacts.
    mappings = [dict(r, scoped_layer_only=True) for r in tables["mappings"]]
    partitions = [dict(r, partition_role="exclusive_same_census_alternative", scoped_layer_only=True) for r in tables["partition"]]
    if sum(int(r["child_population_value"]) for r in partitions) != int(partitions[0]["parent_population_value"]):
        raise ValueError("Kushchevskaya parts do not reconcile to their whole; do not project")
    if any(r["child_counted_in_addition_to_parent"].lower() != "false" for r in partitions):
        raise ValueError("Kushchevskaya parts must remain excluded from the whole's additive count")

    summary = {
        "status": "root_approved_scoped_trajectory_projection_candidate_ready",
        "full_trajectory_places": PLACE_ORDER,
        "full_trajectory_years": YEARS,
        "full_trajectory_projection_rows": len(projection),
        "full_trajectory_links": len(links),
        "full_trajectory_population_sums": {
            str(year): sum(r["population_value"] for r in projection if r["year"] == year)
            for year in YEARS
        },
        "full_trajectory_population_total_by_place": {
            place: sum(r["population_value"] for r in projection if r["place"] == place)
            for place in PLACE_ORDER
        },
        "vlasikha_two_year_display_rows": len(vlas_rows),
        "vlasikha_2002_observation_claimed": False,
        "scoped_point_context_rows": len(point_uses),
        "source_mapping_rows": len(mappings),
        "exclusive_partition_rows": len(partitions),
        "selected_population_frame_mutated": False,
        "accepted_graph_mutated": False,
        "historical_coordinate_measurement_claimed": False,
        "historical_provider_binding_claimed": False,
        "boundary_comparability_claimed": False,
        "legal_status_date_claimed": False,
        "kalininets_qid_native_binding": "unresolved; no QID code-binding claim is made",
        "kushchevskaya_2002_parts_counted_additively": False,
        "excluded_partition_source_record_ids": sorted(r["child_source_record_id"] for r in partitions),
        "source_mapping_preserves_protected_alternates": True,
        "strict_national_joint_coverage_gain_claimed": False,
        "input_stage_manifest_sha256": stage_info["manifest_sha256"],
        "input_stage_receipt_sha256": stage_info["receipt_sha256"],
    }
    return summary, {
        "accepted_scoped_trajectory_projection.csv": projection,
        "accepted_scoped_continuity_links.csv": links,
        "vlasikha_two_year_display_only.csv": vlas_rows,
        "scoped_point_context_uses.csv": point_uses,
        "same_census_source_mappings.csv": mappings,
        "exclusive_partition_policy.csv": partitions,
    }


def run(stage: Path, selected: Path, out: Path) -> dict[str, Any]:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory already contains files (immutable): {out}")
    out.mkdir(parents=True, exist_ok=True)
    summary, tables = build_records(stage, selected)
    for filename, rows in tables.items():
        write_csv(out / filename, rows)
    artifacts: dict[str, Any] = {}
    for filename in tables:
        p = out / filename
        artifacts[filename] = {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size, "rows": len(tables[filename])}
    source_input_paths = {
        "stage_input_manifest": stage / "application_input_manifest.json",
        "stage_application_receipt": stage / "application_receipt.json",
        "selected_observations": selected,
    }
    summary["input_pins"] = {name: {"path": str(path), "sha256": sha256(path)} for name, path in source_input_paths.items()}
    summary["outputs"] = artifacts
    receipt_path = out / "integration_receipt.json"
    receipt_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The receipt deliberately does not contain its own hash; the caller pins it
    # after completion so the recorded digest is over the final bytes.
    summary.pop("receipt", None)
    receipt_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, default=STAGE)
    parser.add_argument("--selected", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.stage, args.selected, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
