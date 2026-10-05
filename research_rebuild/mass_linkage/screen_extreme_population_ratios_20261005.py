#!/usr/bin/env python3
"""Screen accepted ordinary identity components for >20x census changes."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_rebuild/mass_linkage"))
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind  # noqa: E402

OUT = ROOT / "research_rebuild/evidence/current_available_year_path_20261005"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
EVIDENCE = ROOT / "research_rebuild/evidence"
DELTAS = [
    (EVIDENCE / "exact_name_proximity_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    (EVIDENCE / "unique_name_region_coordinate_bridge_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    (EVIDENCE / "top60_and_proximity_review_20261005/simple_rule_application/accepted_identity_edge_delta.csv", "from_id", "to_id"),
    (EVIDENCE / "top60_and_proximity_review_20261005/simple_rule_application/top60_identity_edge_delta.csv", "from_id", "to_id"),
    (EVIDENCE / "top100_classifier_bridge_20261005/accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
    (EVIDENCE / "historical_classifier_bridge_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    obs = con.execute(
        "SELECT source_record_id,CAST(census_year AS INTEGER) yr,settlement_name,settlement_type,"
        "region_norm,population,population_value_quality,COALESCE(is_additive_settlement_record,FALSE) additive "
        "FROM read_parquet(?) WHERE census_year IN (2002,2010,2021)", [str(SELECTED)]
    ).fetchdf()
    uf = UnionFind(obs.source_record_id.astype(str))
    roots_years = {str(sid): {int(year)} for sid, year in obs[["source_record_id", "yr"]].itertuples(index=False, name=None)}

    def union(a: str, b: str) -> None:
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return
        merged = roots_years[a] | roots_years[b]
        if len(merged) < len(roots_years[a]) + len(roots_years[b]):
            raise ValueError(f"Repeated year in current graph: {a}, {b}")
        uf.union(a, b)
        root = uf.find(a)
        other = b if root == a else a
        roots_years[root] = merged
        roots_years.pop(other, None)

    for a, b in con.execute(
        "SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) "
        "WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))",
        [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
    ).fetchall():
        union(a, b)
    for path, a_col, b_col in DELTAS:
        frame = pd.read_csv(path)
        for a, b in frame[[a_col, b_col]].itertuples(index=False, name=None):
            union(a, b)

    obs["source_record_id"] = obs.source_record_id.astype(str)
    obs["root"] = obs.source_record_id.map(lambda sid: uf.find(sid))
    obs = obs[obs.additive & ~obs.region_norm.isin(["москва", "санкт петербург", "севастополь"])].copy()
    obs = obs[~((obs.yr == 2021) & obs.region_norm.eq("крым"))]
    rows = []
    zeros = []
    for root, group in obs.groupby("root"):
        per_year = {int(year): record for year, record in group.set_index("yr").iterrows()}
        years = sorted(per_year)
        for i, ya in enumerate(years):
            for yb in years[i + 1:]:
                a, b = per_year[ya], per_year[yb]
                p1, p2 = float(a.population or 0), float(b.population or 0)
                base = {
                    "component_root": root, "from_year": ya, "to_year": yb,
                    "from_id": a.source_record_id, "to_id": b.source_record_id,
                    "from_name": a.settlement_name, "to_name": b.settlement_name,
                    "from_type": a.settlement_type, "to_type": b.settlement_type,
                    "region_norm": a.region_norm, "from_population": p1, "to_population": p2,
                    "from_population_quality": a.population_value_quality,
                    "to_population_quality": b.population_value_quality,
                }
                if p1 <= 0 or p2 <= 0:
                    if p1 != p2:
                        zeros.append({**base, "screen_status": "zero_or_nonpositive_endpoint"})
                    continue
                ratio = max(p1, p2) / min(p1, p2)
                if ratio > 21:
                    rows.append({**base, "population_ratio_max_over_min": ratio,
                                 "change_direction": "increase" if p2 > p1 else "decrease",
                                 "screen_status": "review_flag_only_not_adjudicated"})
    flagged = pd.DataFrame(rows).sort_values("population_ratio_max_over_min", ascending=False) if rows else pd.DataFrame()
    flagged.to_csv(OUT / "extreme_population_ratio_over_2000pct.csv", index=False)
    pd.DataFrame(zeros).to_csv(OUT / "zero_endpoint_population_changes.csv", index=False)
    summary = {
        "status": "diagnostic_only_no_population_or_identity_changes",
        "screen": "positive population pair ratio >21 (more than 2,000% relative change in the larger direction); zero endpoints listed separately",
        "extreme_positive_pairs": int(len(rows)),
        "zero_or_nonpositive_endpoint_pairs": int(len(zeros)),
        "interpretation": "Flags are not errors. Boundary changes, actual growth/decline, protected or scope-affected values can explain them; no value was changed or excluded.",
        "top_20": flagged.head(20).to_dict("records") if rows else [],
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SELECTED, EDGES] + [p for p, _, _ in DELTAS]},
    }
    (OUT / "extreme_population_ratio_screen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["status", "extreme_positive_pairs", "zero_or_nonpositive_endpoint_pairs", "top_20"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
