#!/usr/bin/env python3
"""Apply the small collision-free historical classifier continuity batch."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import duckdb
import pandas as pd
from build_long_table import ACCEPTED_EDGE_STATUSES, UnionFind

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005"
SRC = OUT / "candidate_identity_edges_NOT_ADMITTED.csv"
PNT = OUT / "candidate_retrospective_point_uses_NOT_ADMITTED.csv"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
STATUSES = ["reviewed_rule_accepted", "frozen_r5b_reviewed_baseline_preserved", "reviewed_extension_rule_accepted", "reviewed_case_accepted"]
ACCEPTED_TYPE_TRANSITIONS = {("пгт", "поселок"), ("село", "деревня")}


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def norm(value: object) -> str:
    return " ".join(str(value).lower().replace("ё", "е").split())


def type_transition(old_type: object, new_type: object) -> str | None:
    old, new = norm(old_type), norm(new_type)
    if old == new:
        return "same_type"
    if (old, new) in ACCEPTED_TYPE_TRANSITIONS:
        return f"historical_status_transition:{old}->{new}"
    return None


def main() -> None:
    candidates = pd.read_csv(SRC)
    point_candidates = pd.read_csv(PNT)
    if len(candidates) != 13 or len(point_candidates) != 14:
        raise RuntimeError("frozen candidate package changed")
    if candidates.old_id.duplicated().any() or candidates.cur_id.duplicated().any() or point_candidates.old_id.duplicated().any() or point_candidates.cur_id.duplicated().any():
        raise RuntimeError("candidate endpoint keys are not unique")
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    selected = con.execute("select * from read_parquet(?)", [str(SELECTED)]).fetchdf()
    selected = selected.set_index("source_record_id", drop=False)
    uf = UnionFind(selected.index.astype(str))
    years = {str(s): {int(y)} for s, y in selected[["source_record_id", "census_year"]].itertuples(index=False, name=None)}

    def union(a: str, b: str) -> bool:
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return True
        if years[a] & years[b]:
            return False
        merged = years[a] | years[b]
        uf.union(a, b)
        root = uf.find(a)
        other = b if root == a else a
        years[root] = merged
        years.pop(other, None)
        return True

    for a, b in con.execute(
        "select from_source_record_id,to_source_record_id from read_parquet(?) "
        "where relation='same_place' and decision_status in (select unnest(?))",
        [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
    ).fetchall():
        union(a, b)
    prior_deltas = [
        (ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/accepted_identity_edge_delta.csv", "from_id", "to_id"),
        (ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/top60_identity_edge_delta.csv", "from_id", "to_id"),
        (ROOT / "research_rebuild/evidence/top100_classifier_bridge_20261005/accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
    ]
    for path, a_col, b_col in prior_deltas:
        if path.is_file():
            df = pd.read_csv(path)
            for a, b in df[[a_col, b_col]].itertuples(index=False, name=None):
                union(str(a), str(b))

    edge_rows = []
    held_edges = []
    for row in candidates.itertuples(index=False):
        old = selected.loc[str(row.old_id)]
        cur = selected.loc[str(row.cur_id)]
        if int(old.census_year) != int(row.old_year) or int(cur.census_year) != 2021:
            raise RuntimeError("candidate selected year mismatch")
        if not bool(old.is_additive_settlement_record) or not bool(cur.is_additive_settlement_record):
            raise RuntimeError("candidate endpoint is not an additive settlement row")
        for field, candidate_field in [("settlement_name", "old_name"), ("region_norm", "region_norm")]:
            if norm(old[field]) != norm(cur[field]) or norm(old[field]) != norm(getattr(row, candidate_field)):
                raise RuntimeError(f"exact name/regional key mismatch: {field}")
        transition = type_transition(old.settlement_type, cur.settlement_type)
        if transition is None:
            held_edges.append({**row._asdict(), "selected_old_type": old.settlement_type, "selected_current_type": cur.settlement_type, "hold_reason": "unreviewed_or_object_grain_type_transition"})
            continue
        if norm(old.settlement_type) != norm(row.old_type):
            raise RuntimeError("old type differs from candidate source row")
        if not math.isclose(float(old.population), float(row.old_pop), abs_tol=0.01) or not math.isclose(float(cur.population), float(row.cur_pop), abs_tol=0.01):
            raise RuntimeError("candidate population no longer matches selected row")
        if float(row.dist_m) > 5000 or float(row.ratio) > 2:
            raise RuntimeError("candidate violates proximity/population rule")
        if not union(str(row.old_id), str(row.cur_id)):
            raise RuntimeError("candidate batch creates repeated census year")
        edge_rows.append({
            "from_source_record_id": str(row.old_id), "to_source_record_id": str(row.cur_id),
            "relation": "same_place", "decision_status": "checked_rule_accepted",
            "decision_id": "HISTCLASS-" + hashlib.sha256((str(row.old_id) + "|" + str(row.cur_id)).encode()).hexdigest()[:16],
            "decision_rule": "Exact historical OKATO/GeoKLADR code path; exact name/type/region; unique eligible old and current typed key; historical classifier point within 5 km of accepted current point; positive population ratio <=2; full graph year-conflict check.",
            "from_year": int(row.old_year), "to_year": 2021,
            "from_type": old.settlement_type, "to_type": cur.settlement_type,
            "type_transition": transition,
            "from_population": int(old.population), "to_population": int(cur.population),
            "historical_okato_2009_raw": str(row.okato09), "geokladr_okato_2011_raw": str(row.okato11),
            "geo_2011_source_sha256": str(row.source_sha256_2011),
            "geo_2011_record_number_1based": int(row.record_number_1based),
            "geo_2011_record_byte_offset_0based": int(row.record_byte_offset_0based),
            "classifier_point_distance_m": float(row.dist_m), "population_ratio": float(row.ratio),
            "population_value_changed": False, "population_comparability_asserted": False,
            "boundary_comparability_asserted": False,
        })

    accepted_points = con.execute(
        "select target_source_record_id,target_year,latitude,longitude,coordinate_source,point_origin_file,point_origin_sha256,point_origin_locator "
        "from read_parquet(?) where coordinate_admission_status in (select unnest(?))",
        [str(POINTS), STATUSES],
    ).fetchdf()
    if accepted_points.target_source_record_id.duplicated().any():
        raise RuntimeError("duplicate point uses for one source record")
    current_lookup = accepted_points.set_index("target_source_record_id")
    existing_keys = {
        (int(float(r.target_year)), round(float(r.latitude), 7), round(float(r.longitude), 7))
        for r in accepted_points.itertuples(index=False)
        if pd.notna(r.target_year) and pd.notna(r.latitude) and pd.notna(r.longitude)
    }
    point_rows = []
    held_points = []
    for row in point_candidates.itertuples(index=False):
        old_id, cur_id = str(row.old_id), str(row.cur_id)
        if old_id in current_lookup.index:
            raise RuntimeError(f"point candidate already has accepted point: {old_id}")
        cur = current_lookup.loc[cur_id]
        old = selected.loc[old_id]
        if int(old.census_year) != int(row.old_year) or int(float(cur.target_year)) != 2021:
            raise RuntimeError("point carrier year mismatch")
        carrier_obs = selected.loc[cur_id]
        if not bool(old.is_additive_settlement_record) or not bool(carrier_obs.is_additive_settlement_record):
            raise RuntimeError("point candidate endpoint is not an additive settlement row")
        for field, candidate_field in [("settlement_name", "old_name"), ("region_norm", "region_norm")]:
            if norm(old[field]) != norm(carrier_obs[field]) or norm(old[field]) != norm(getattr(row, candidate_field)):
                raise RuntimeError(f"point carrier exact typed regional key mismatch: {field}")
        transition = type_transition(old.settlement_type, carrier_obs.settlement_type)
        if transition is None:
            held_points.append({**row._asdict(), "selected_old_type": old.settlement_type, "selected_current_type": carrier_obs.settlement_type, "hold_reason": "unreviewed_or_object_grain_type_transition"})
            continue
        if norm(old.settlement_type) != norm(row.old_type):
            raise RuntimeError("point old type differs from candidate source row")
        if not math.isclose(float(old.population), float(row.old_pop), abs_tol=0.01) or not math.isclose(float(carrier_obs.population), float(row.cur_pop), abs_tol=0.01):
            raise RuntimeError("point candidate population no longer matches selected row")
        key = (int(row.old_year), round(float(cur.latitude), 7), round(float(cur.longitude), 7))
        if key in existing_keys:
            raise RuntimeError(f"retrospective point collides with accepted same-year point: {old_id}")
        if float(row.dist_m) > 5000 or float(row.ratio) > 2:
            raise RuntimeError("retrospective point candidate violates proximity/population rule")
        existing_keys.add(key)
        point_rows.append({
            "target_source_record_id": old_id, "target_year": int(row.old_year),
            "target_name": old.settlement_name, "target_type": old.settlement_type,
            "target_region": old.region_norm, "target_population": int(old.population),
            "target_type_transition": transition,
            "latitude": float(cur.latitude), "longitude": float(cur.longitude),
            "carrier_source_record_id": cur_id, "carrier_year": 2021,
            "carrier_point_source": cur.coordinate_source,
            "carrier_point_origin_file": cur.point_origin_file,
            "carrier_point_origin_sha256": cur.point_origin_sha256,
            "carrier_point_origin_locator": cur.point_origin_locator,
            "historical_classifier_distance_m": float(row.dist_m),
            "coordinate_admission_status": "reviewed_case_accepted",
            "coordinate_application_family": "historical_classifier_unique_nearby_same_typed_name_continuity_20261005",
            "measurement_date_unknown": True, "provider_identifier_binding_asserted": False,
            "population_value_changed": False, "boundary_comparability_asserted": False,
        })

    pd.DataFrame(edge_rows).to_csv(OUT / "accepted_identity_edge_delta.csv", index=False)
    pd.DataFrame(point_rows).to_csv(OUT / "accepted_retrospective_point_use_delta.csv", index=False)
    pd.DataFrame(held_edges).to_csv(OUT / "held_identity_type_transition_candidates.csv", index=False)
    pd.DataFrame(held_points).to_csv(OUT / "held_point_type_transition_candidates.csv", index=False)
    summary = {
        "status": "accepted_collision_free_historical_classifier_batch_with_type_transition_holds",
        "candidate_identity_edges": len(candidates), "identity_edges_added": len(edge_rows), "identity_edges_held_for_type_transition": len(held_edges),
        "identity_endpoint_population_by_old_year": {str(int(y)): int(v) for y, v in pd.DataFrame(edge_rows).groupby("from_year").from_population.sum().items()},
        "held_identity_population_by_old_year": {str(int(y)): int(v) for y, v in pd.DataFrame(held_edges).groupby("old_year").old_pop.sum().items()},
        "candidate_point_uses": len(point_candidates), "point_uses_held_for_type_transition": len(held_points),
        "point_uses_added": len(point_rows),
        "point_endpoint_population_by_old_year": {str(int(y)): int(v) for y, v in pd.DataFrame(point_rows).groupby("target_year").target_population.sum().items()},
        "held_point_population_by_old_year": {str(int(y)): int(v) for y, v in pd.DataFrame(held_points).groupby("old_year").old_pop.sum().items()},
        "all_edges_passed_full_graph_year_conflict_check": True,
        "new_same_year_point_collisions": 0,
        "rule": "exact historical code route and name/region; type is unchanged or a documented pgt-to-settlement / village-to-derevnya transition; historical classifier point within 5 km of accepted current point; population ratio <=2; unique endpoints; no repeated census year in current graph",
        "population_values_changed": False,
        "boundary_comparability_asserted": False,
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SRC, PNT, SELECTED, EDGES, POINTS]},
        "limitations": ["The cohort is narrow and rule-specific; it does not establish census-boundary population comparability.", "Historical coordinate use is spatial continuity inference, not a historical point measurement."],
    }
    (OUT / "accepted_batch_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
