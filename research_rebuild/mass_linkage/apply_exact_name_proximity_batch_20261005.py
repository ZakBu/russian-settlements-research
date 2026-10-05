#!/usr/bin/env python3
"""Apply a bounded exact-name/region/type/point rule to residual year pairs."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_rebuild/mass_linkage"))
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind  # noqa: E402

OUT = ROOT / "research_rebuild/evidence/exact_name_proximity_batch_20261005"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
CANDIDATES = ROOT / "research_rebuild/evidence/coordinate_proximity_audit_20261005/new_component_compatible_pairs_within1km.csv"
CURRENT_SUMMARY = ROOT / "research_rebuild/evidence/current_joint_residual_priority_20261005/summary.json"
BASE = ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application"
CODE = ROOT / "research_rebuild/evidence/top100_classifier_bridge_20261005"
HIST = ROOT / "research_rebuild/evidence/historical_urban_code_residual_20261005"
HCLASS = ROOT / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005"
SHARED = ROOT / "research_rebuild/evidence/shared_locality_point_novaya_usman_20261005"


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    obs = c.execute(
        "SELECT source_record_id,CAST(census_year AS INTEGER) yr,settlement_name,name_norm,settlement_type,type_norm,region_norm,"
        "COALESCE(population,0)::DOUBLE population,COALESCE(is_additive_settlement_record,FALSE) additive "
        "FROM read_parquet(?) WHERE census_year IN (2002,2010,2021)", [str(SELECTED)]
    ).fetchdf()
    if obs.source_record_id.duplicated().any():
        raise ValueError("Selected source_record_id is not unique")
    info = obs.set_index("source_record_id").to_dict("index")
    uf = UnionFind(obs.source_record_id.astype(str))
    year_sets = {str(row.source_record_id): {int(row.yr)} for row in obs.itertuples(index=False)}

    def union(a: str, b: str) -> str:
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return "redundant"
        merged = year_sets[a] | year_sets[b]
        if len(merged) < len(year_sets[a]) + len(year_sets[b]):
            return "conflict"
        uf.union(a, b)
        root = uf.find(a)
        other = b if root == a else a
        year_sets[root] = merged
        year_sets.pop(other, None)
        return "merged"

    base_edge_n = 0
    for a, b in c.execute(
        "SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) "
        "WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))",
        [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
    ).fetchall():
        status = union(a, b)
        if status == "conflict":
            raise ValueError(f"Existing accepted graph already has a duplicate-year conflict: {a}, {b}")
        base_edge_n += 1

    prior_edge_batches = [
        (BASE / "accepted_identity_edge_delta.csv", "from_id", "to_id"),
        (BASE / "top60_identity_edge_delta.csv", "from_id", "to_id"),
        (CODE / "accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
        (HCLASS / "accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ]
    prior_edge_n = 0
    for path, a_col, b_col in prior_edge_batches:
        frame = pd.read_csv(path)
        for a, b in frame[[a_col, b_col]].itertuples(index=False, name=None):
            status = union(a, b)
            if status == "conflict":
                raise ValueError(f"Existing accepted delta has duplicate-year conflict: {a}, {b}")
            prior_edge_n += 1

    point_ids = set(map(str, c.execute(
        "SELECT target_source_record_id FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))",
        [str(POINTS), sorted(ACCEPTED_COORDINATE_STATUSES)],
    ).fetchnumpy()["target_source_record_id"]))
    for path in [BASE / "top60_point_use_delta.csv", CODE / "old_point_use_delta.csv", HIST / "accepted_point_use_delta.csv", HCLASS / "accepted_retrospective_point_use_delta.csv", SHARED / "accepted_shared_locality_point_uses.csv"]:
        point_ids.update(pd.read_csv(path).target_source_record_id.astype(str))

    def coverage() -> dict[int, dict[str, int]]:
        out = {}
        special = {"москва", "санкт петербург", "севастополь"}
        obs["_root"] = obs.source_record_id.map(lambda sid: uf.find(str(sid)))
        roots_by_year = obs.groupby("_root").yr.agg(lambda ys: set(map(int, ys)))
        complete_roots = set(roots_by_year[roots_by_year.map(lambda ys: {2002, 2010, 2021}.issubset(ys))].index)
        for year in (2002, 2010, 2021):
            d = obs[(obs.yr == year) & obs.additive & ~obs.region_norm.isin(special)].copy()
            if year == 2021:
                d = d[d.region_norm.ne("крым")]
            d["accepted_point"] = d.source_record_id.isin(point_ids)
            d["full_chain"] = d._root.isin(complete_roots)
            d["joint"] = d.accepted_point & d.full_chain
            out[year] = {
                "rows": int(len(d)),
                "population": int(d.population.sum()),
                "joint_rows": int(d.joint.sum()),
                "joint_population": int(d.loc[d.joint, "population"].sum()),
            }
        obs.drop(columns=["_root"], inplace=True)
        return out

    before = coverage()
    baseline = json.loads(CURRENT_SUMMARY.read_text(encoding="utf-8"))
    for year in (2002, 2010, 2021):
        expected = int(baseline["by_year"][str(year)]["joint_covered_population"])
        if before[year]["joint_population"] != expected:
            raise ValueError(f"Baseline replay differs for {year}: {before[year]['joint_population']} != {expected}")

    with CANDIDATES.open(encoding="utf-8", newline="") as f:
        candidates = list(csv.DictReader(f))
    accepted, held, outcomes = [], [], Counter()
    def candidate_norm(value: str) -> str:
        return " ".join(str(value).casefold().replace("ё", "е").split())
    from_counts, to_counts = Counter(), Counter()
    for r in candidates:
        pair = (r["from_year"], r["to_year"])
        from_counts[(*pair, r["from_id"])] += 1
        to_counts[(*pair, r["to_id"])] += 1
    if any(n != 1 for n in from_counts.values()) or any(n != 1 for n in to_counts.values()):
        raise ValueError("Candidate set is not one-to-one within each year-pair")

    for r in candidates:
        a, b = r["from_id"], r["to_id"]
        ya, yb = int(r["from_year"]), int(r["to_year"])
        if a not in info or b not in info or info[a]["yr"] != ya or info[b]["yr"] != yb:
            raise ValueError(f"Candidate endpoint missing or census year mismatch: {a}, {b}")
        ia, ib = info[a], info[b]
        if (ia["name_norm"], ia["type_norm"], ia["region_norm"]) != (ib["name_norm"], ib["type_norm"], ib["region_norm"]):
            raise ValueError(f"Exact name/type/region condition failed: {a}, {b}")
        if (candidate_norm(r["settlement_name"]) not in {candidate_norm(ia["settlement_name"]), candidate_norm(ib["settlement_name"]), candidate_norm(ia["name_norm"])}
                or candidate_norm(r["settlement_type"]) not in {candidate_norm(ia["settlement_type"]), candidate_norm(ib["settlement_type"]), candidate_norm(ia["type_norm"])}
                or r["region_norm"] != ia["region_norm"]):
            raise ValueError(f"Candidate evidence does not match selected endpoints: {a}, {b}")
        distance = float(r["distance_m"])
        if distance > 1000 or r["from_same_year_point_collision"].lower() == "true" or r["to_same_year_point_collision"].lower() == "true":
            raise ValueError(f"Distance/collision guard failed: {a}, {b}")
        p1, p2 = float(ia["population"]), float(ib["population"])
        ratio = max(p1, p2) / min(p1, p2) if p1 > 0 and p2 > 0 else None
        exact_origin = r["same_recorded_coordinate_origin"].lower() == "true"
        if p1 > 0 and p2 > 0 and (ratio < .5 or ratio > 2):
            held.append({**r, "decision": "hold_population_change_over_2x", "population_ratio_max_over_min": ratio})
            continue
        if (p1 == 0 or p2 == 0) and not exact_origin:
            held.append({**r, "decision": "hold_zero_or_unknown_population_without_exact_shared_point_origin", "population_ratio_max_over_min": ""})
            continue
        if not exact_origin and (ratio is None or not .5 <= ratio <= 2):
            held.append({**r, "decision": "hold_population_ratio_not_computable", "population_ratio_max_over_min": ""})
            continue
        status = union(a, b)
        if status == "conflict":
            held.append({**r, "decision": "hold_component_year_conflict", "population_ratio_max_over_min": ratio or ""})
            continue
        if status == "redundant":
            outcomes["already_connected_by_transitive_path"] += 1
            continue
        outcomes["merged"] += 1
        edge = {
            "from_source_record_id": a, "from_year": ya, "to_source_record_id": b, "to_year": yb,
            "relation": "same_place", "settlement_name": ia["settlement_name"],
            "settlement_type": ia["settlement_type"], "region_norm": ia["region_norm"],
            "from_population_raw": p1, "to_population_raw": p2,
            "population_ratio_max_over_min": ratio if ratio is not None else "",
            "population_comparability": "not_assessed_by_identity_rule" if ratio is None or (ratio is not None and ratio > 1) else "not_asserted",
            "distance_m": distance, "same_recorded_coordinate_origin": exact_origin,
            "identity_rule": "exact_name_type_region_unique_pair_accepted_points_le_1km_no_collision_no_duplicate_year; shared exact GeoKLADR source may support identity with zero count but outlier ratios held",
            "evidence_uri": "research_rebuild/evidence/coordinate_proximity_audit_20261005/new_component_compatible_pairs_within1km.csv",
            "decision_status": "checked_rule_accepted",
        }
        accepted.append(edge)

    after = coverage()
    gain = {y: after[y]["joint_population"] - before[y]["joint_population"] for y in before}
    if any(v < 0 for v in gain.values()):
        raise ValueError(f"Candidate graph reduced joint chain coverage: {gain}")

    for filename, rows in [("accepted_identity_edge_delta.csv", accepted), ("held_candidates.csv", held)]:
        if rows:
            with (OUT / filename).open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
    result = {
        "status": "applied_after_full_graph_replay; no duplicate-year conflicts",
        "rule": "Exact normalized name/type/region, unique one-to-one year-pair, accepted coordinates within 1 km, no same-year point collision, no duplicate census year after union; positive population ratios above 2x held, exact shared coordinate origins may connect zero-value rows with population comparability unasserted.",
        "input_candidate_rows": len(candidates), "accepted_identity_edges": len(accepted), "held_candidates": len(held),
        "already_connected_redundant_candidates": outcomes["already_connected_by_transitive_path"],
        "edge_pairs_by_year": dict(Counter(f"{r['from_year']}-{r['to_year']}" for r in accepted)),
        "held_by_reason": dict(Counter(r["decision"] for r in held)),
        "accepted_positive_population_ratio_gt_2x": sum(1 for r in accepted if r["population_ratio_max_over_min"] not in ("", None) and float(r["population_ratio_max_over_min"]) > 2),
        "identity_conflicts": 0,
        "population_values_modified": False,
        "coverage_before": before, "coverage_after": after,
        "joint_chain_population_gain_by_year": gain,
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SELECTED, EDGES, POINTS, CANDIDATES, CURRENT_SUMMARY]},
        "status_scope_note": "This batch adds identity edges to the separate graph delta. It does not adjust census counts or claim boundary/population comparability; 2x population outliers stay held."
    }
    (OUT / "application_receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
