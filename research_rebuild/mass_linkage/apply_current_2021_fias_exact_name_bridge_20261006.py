#!/usr/bin/env python3
"""Mass-link current FIAS6 points to unique exact census name/type/region rows."""
from __future__ import annotations

import hashlib, json, math, sys
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_rebuild/mass_linkage"))
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind

OUT = ROOT / "research_rebuild/evidence/current_2021_fias_exact_name_bridge_20261006"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
GRAPH = Path("/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_identity_edges.parquet")
BASE_POINTS = Path("/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet")
CANDIDATES = Path("/workspace/settlements-work/continuation_20261004/regions/current_residual_own_locality_points_v1/current_point_candidates.csv")
CURRENT_POINT_DELTA = ROOT / "research_rebuild/evidence/current_residual_ownlocality_points_20261005/accepted_point_use_delta.csv.gz"
EVIDENCE = ROOT / "research_rebuild/evidence"
OLD_EDGE_DELTAS = [
    ("exact_name_proximity_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ("unique_name_region_coordinate_bridge_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ("top60_and_proximity_review_20261005/simple_rule_application/accepted_identity_edge_delta.csv", "from_id", "to_id"),
    ("top60_and_proximity_review_20261005/simple_rule_application/top60_identity_edge_delta.csv", "from_id", "to_id"),
    ("top100_classifier_bridge_20261005/accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
    ("historical_classifier_bridge_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ("unique_exact_historical_code_point_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ("kudryashovsky_three_census_chain_20261006/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
]

def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def norm(value) -> str:
    return str(value or "").strip().casefold().replace("ё", "е")

def km(a_lat, a_lon, b_lat, b_lon) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))

def main() -> None:
    if OUT.exists():
        raise FileExistsError(OUT)
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    selected = pd.read_parquet(SELECTED)
    selected = selected[selected.census_year.isin([2002, 2010, 2021]) & selected.is_additive_settlement_record.fillna(False)].copy()
    selected["year"] = selected.census_year.astype(int)
    selected["key"] = [(norm(n), norm(t), norm(r)) for n, t, r in zip(selected.name_norm, selected.type_norm, selected.region_norm)]

    candidates = pd.read_csv(CANDIDATES, dtype={"source_record_id": str})
    points = pd.read_csv(CURRENT_POINT_DELTA, dtype={"target_source_record_id": str})
    point_ids = set(points.target_source_record_id)
    candidates = candidates[candidates.source_record_id.isin(point_ids)].copy()
    candidates["key"] = [(norm(n), norm(t), norm(r)) for n, t, r in zip(candidates.settlement_name, candidates.settlement_type, candidates.region_norm)]
    # Exact normalized name/type/region and one endpoint per key in each year.
    cand_by_id = candidates.set_index("source_record_id", drop=False)
    point_by_id = points.set_index("target_source_record_id", drop=False)
    proposals = []
    selected_by_year_key = {y: {k: g for k, g in selected[selected.year.eq(y)].groupby("key")} for y in (2002, 2010, 2021)}
    for year in (2002, 2010):
        for candidate in candidates.itertuples(index=False):
            if len(selected_by_year_key[2021].get(candidate.key, ())) != 1:
                continue
            old_group = selected_by_year_key[year].get(candidate.key)
            if old_group is None or len(old_group) != 1:
                continue
            old = old_group.iloc[0]
            current = selected_by_year_key[2021][candidate.key].iloc[0]
            old_pop = max(0, int(old.population or 0)); new_pop = max(0, int(current.population or 0))
            ratio = max(old_pop, new_pop) / max(1, min(old_pop, new_pop))
            if ratio > 2:
                continue
            pp = point_by_id.loc[str(candidate.source_record_id)]
            proposals.append({"old_id": str(old.source_record_id), "new_id": str(current.source_record_id), "year": year,
                              "old_pop": old_pop, "new_pop": new_pop, "ratio": ratio, "key": candidate.key,
                              "lat": float(pp.latitude), "lon": float(pp.longitude)})

    # Rebuild all already accepted components, then admit only nonconflicting edges.
    ids = selected.source_record_id.astype(str)
    uf = UnionFind(ids)
    year_sets = {str(sid): {int(y)} for sid, y in zip(selected.source_record_id, selected.year)}
    def union(a, b):
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return "redundant"
        if year_sets[a] & year_sets[b]:
            return "conflict"
        merged = year_sets[a] | year_sets[b]
        uf.union(a, b)
        root = uf.find(a); other = b if root == a else a
        year_sets[root] = merged; year_sets.pop(other, None)
        return "merged"
    for a, b in con.execute("SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))", [str(GRAPH), sorted(ACCEPTED_EDGE_STATUSES)]).fetchall():
        if union(a, b) == "conflict":
            raise ValueError("accepted base graph contains a duplicate-year component")
    for rel, left, right in OLD_EDGE_DELTAS:
        frame = pd.read_csv(EVIDENCE / rel, dtype=str)
        for a, b in frame[[left, right]].itertuples(index=False, name=None):
            if union(a, b) == "conflict":
                raise ValueError(f"prior accepted delta conflicts: {rel}")

    # Retain a point-distance guard where the historical endpoint already has a point.
    accepted_statuses = list(ACCEPTED_COORDINATE_STATUSES)
    core_points = con.execute("SELECT target_source_record_id,latitude,longitude FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))", [str(BASE_POINTS), accepted_statuses]).fetchdf()
    point_map = {}
    for r in core_points.itertuples(index=False):
        point_map.setdefault(str(r.target_source_record_id), set()).add((float(r.latitude), float(r.longitude)))
    point_delta_files = [
        "top60_and_proximity_review_20261005/simple_rule_application/top60_point_use_delta.csv",
        "top100_classifier_bridge_20261005/old_point_use_delta.csv",
        "historical_urban_code_residual_20261005/accepted_point_use_delta.csv",
        "historical_classifier_bridge_batch_20261005/accepted_retrospective_point_use_delta.csv",
        "shared_locality_point_novaya_usman_20261005/accepted_shared_locality_point_uses.csv",
        "unique_name_region_coordinate_bridge_20261005/accepted_point_use_delta.csv",
        "unique_exact_historical_code_point_batch_20261005/accepted_point_use_delta.csv",
        "current_residual_ownlocality_points_20261005/accepted_point_use_delta.csv.gz",
        "kudryashovsky_three_census_chain_20261006/accepted_point_use_delta.csv",
    ]
    for rel in point_delta_files:
        frame = pd.read_csv(EVIDENCE / rel)
        if {"target_source_record_id", "latitude", "longitude"}.issubset(frame.columns):
            for r in frame[["target_source_record_id", "latitude", "longitude"]].dropna().itertuples(index=False):
                point_map.setdefault(str(r.target_source_record_id), set()).add((float(r.latitude), float(r.longitude)))
    owners = {}
    selected_year_by_id = selected.set_index("source_record_id").year.to_dict()
    for sid, locations in point_map.items():
        year = selected_year_by_id.get(sid)
        if year is None:
            continue
        for lat, lon in locations:
            owners.setdefault((year, round(lat, 6), round(lon, 6)), set()).add(sid)

    accepted, held = [], []
    # Extend 2010 paths first, then 2002 paths; larger populations first within each year.
    proposals.sort(key=lambda x: (x["year"] == 2002, x["old_pop"] + x["new_pop"]), reverse=True)
    for p in proposals:
        old_points = point_map.get(p["old_id"], set())
        if len(old_points) > 1:
            held.append({**p, "hold_reason": "historical_endpoint_has_conflicting_accepted_points"}); continue
        if old_points:
            op = next(iter(old_points))
            if len(owners.get((p["year"], round(op[0], 6), round(op[1], 6)), set())) > 1:
                held.append({**p, "hold_reason": "historical_coordinate_is_shared_by_multiple_selected_rows"}); continue
            if km(op[0], op[1], p["lat"], p["lon"]) > 5:
                held.append({**p, "hold_reason": "historical_point_more_than_5km_from_current_FIAS6_point"}); continue
        status = union(p["old_id"], p["new_id"])
        if status != "merged":
            held.append({**p, "hold_reason": "already_connected" if status == "redundant" else "same_year_graph_conflict"}); continue
        old = selected.loc[selected.source_record_id.eq(p["old_id"])].iloc[0]
        current_point = point_by_id.loc[p["new_id"]]
        accepted.append({
            "from_source_record_id": p["old_id"], "from_year": p["year"], "to_source_record_id": p["new_id"], "to_year": 2021,
            "relation": "same_place", "decision_status": "checked_rule_accepted",
            "from_population": p["old_pop"], "to_population": p["new_pop"], "population_ratio_max_over_min": p["ratio"],
            "identity_rule": "exact_normalized_name_type_region_unique_per_year_plus_current_FIAS6_level6_point; population_change_not_over_2x; full_accepted_graph_no_repeated_year; existing points within 5km",
            "coordinate_measurement_date_unknown": True, "population_comparability_asserted": False,
            "boundary_comparability_asserted": False,
        })
        if not old_points:
            accepted_point = current_point
            point_map[p["old_id"]] = {(p["lat"], p["lon"])}
            # Make retrospective spatial continuity explicit; preserve the 2021 FIAS point provenance.
            accepted.append({"_point_for": p["old_id"], "_carrier": p["new_id"], "_year": p["year"],
                             "_lat": p["lat"], "_lon": p["lon"], "_source": accepted_point.coordinate_source,
                             "_provider_id": accepted_point.coordinate_provider_id})

    edge_rows = [x for x in accepted if "from_source_record_id" in x]
    point_rows = []
    for x in accepted:
        if "_point_for" not in x: continue
        old = selected.loc[selected.source_record_id.eq(x["_point_for"])].iloc[0]
        carrier = point_by_id.loc[x["_carrier"]]
        point_rows.append({
            "target_source_record_id": x["_point_for"], "target_year": x["_year"], "latitude": x["_lat"], "longitude": x["_lon"],
            "coordinate_quality": "retrospective_spatial_continuity_from_current_FIAS6_point",
            "coordinate_source": f"2021 exact selected-row FIAS6 point inherited from {x['_carrier']}",
            "coordinate_source_record_id": carrier.coordinate_source_record_id,
            "coordinate_provider": carrier.coordinate_provider, "coordinate_provider_id": carrier.coordinate_provider_id,
            "source_name": old.settlement_name, "source_type": old.settlement_type, "source_region": old.region_raw,
            "source_file": old.source_file, "source_row": old.source_row, "source_sha256": old.source_sha256,
            "source_locator": old.source_locator,
            "coordinate_provenance": "Exact normalized name/type/region unique across selected year layers; current point is a directly admitted FIAS level-6 locality point; full accepted graph has no repeated year; historical point is retrospective spatial continuity, not a census-date observation.",
            "admission_rule": "current_FIAS6_point_exact_name_type_region_unique_ratio_le_2_no_graph_conflict_v1",
            "coordinate_admission_status": "reviewed_extension_rule_accepted", "coordinate_measurement_date_unknown": True,
            "boundary_comparability_asserted": False, "coordinate_application_family": "current_FIAS6_exact_name_type_region_bridge_20261006",
            "application_inference_kind": "retrospective_spatial_continuity", "direct_historical_coordinate_measurement": False,
            "population_scope_comparability_asserted": False, "admission_allowed": True,
            "point_origin_file": carrier.point_origin_file, "point_origin_sha256": carrier.point_origin_sha256,
            "point_origin_locator": carrier.point_origin_locator, "point_origin_kind": carrier.point_origin_kind,
            "point_claim_artifact_file": carrier.point_claim_artifact_file, "point_claim_artifact_sha256": carrier.point_claim_artifact_sha256,
        })
    OUT.mkdir(parents=True)
    edge_path = OUT / "accepted_identity_edge_delta.csv"
    point_path = OUT / "accepted_retrospective_point_use_delta.csv"
    held_path = OUT / "held_candidates.csv"
    pd.DataFrame(edge_rows).to_csv(edge_path, index=False)
    pd.DataFrame(point_rows).to_csv(point_path, index=False)
    pd.DataFrame(held).to_csv(held_path, index=False)
    receipt = {
        "status": "applied_exact_name_type_region_bridge_from_current_fias6_point",
        "rule": "Exact normalized name/type/region; unique in each compared year; population ratio <=2; target's current direct point is FIAS level 6; accepted graph replay has no repeated-year conflict; any existing historical point is unique and within 5km. Historical coordinates are inherited as representative-point continuity only.",
        "input_candidate_rows": len(proposals), "accepted_edge_rows": len(edge_rows), "already_connected_or_conflicting_or_spatially_held": len(held),
        "accepted_retrospective_points": len(point_rows), "accepted_old_year_population_by_year": {str(y): int(sum(x['from_population'] for x in edge_rows if x['from_year']==y)) for y in (2002,2010)},
        "accepted_2021_population_by_link_year": {str(y): int(sum(x['to_population'] for x in edge_rows if x['from_year']==y)) for y in (2002,2010)},
        "outputs": {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in (edge_path, point_path, held_path)},
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in (SELECTED, GRAPH, BASE_POINTS, CANDIDATES, CURRENT_POINT_DELTA)},
        "limitations": ["No population values are changed.", "Population comparability and census-date coordinate accuracy are not asserted.", "2010 confidentiality-protected population flags remain unchanged."],
    }
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (OUT / "README.md").write_text("# Mass exact identity bridge from current FIAS6 points\n\nApplied exact normalized name, type and region joins from the newly admitted 2021 FIAS level-6 points to unique earlier census rows. Links were accepted only when population changed by no more than 2x, existing earlier points were unique and within 5 km, and full graph replay did not create a repeated census year. Older coordinates are inherited as representative-place points; census-date measurement and population/boundary comparability are not claimed. Population values were not modified.\n\nSee the receipt, accepted identity delta, retrospective point delta, and held candidate list.\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("input_candidate_rows","accepted_edge_rows","already_connected_or_conflicting_or_spatially_held","accepted_retrospective_points","accepted_old_year_population_by_year","accepted_2021_population_by_link_year")}, ensure_ascii=False))

if __name__ == "__main__": main()
