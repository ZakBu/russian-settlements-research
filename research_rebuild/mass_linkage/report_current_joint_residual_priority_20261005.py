#!/usr/bin/env python3
"""Rank the current ordinary-settlement strict point+three-census-chain residual."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/current_joint_residual_priority_20261005"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
BASE = ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application"
CODE = ROOT / "research_rebuild/evidence/top100_classifier_bridge_20261005"
HIST = ROOT / "research_rebuild/evidence/historical_urban_code_residual_20261005"
HCLASS = ROOT / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005"
SHARED = ROOT / "research_rebuild/evidence/shared_locality_point_novaya_usman_20261005"
STATUSES = sorted(ACCEPTED_COORDINATE_STATUSES)


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main() -> None:
    c = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    obs = c.execute(
        "select source_record_id,census_year,source_file,source_row,source_name_raw,settlement_name,settlement_type,"
        "region_raw,region_norm,district_raw,population,population_value_quality,population_quality_limitation,source_sha256,"
        "source_locator,is_additive_settlement_record,population_scope from read_parquet(?)",
        [str(SELECTED)],
    ).fetchdf()
    uf = UnionFind(obs.source_record_id.astype(str))
    year_sets = {str(sid): {int(year)} for sid, year in obs[["source_record_id", "census_year"]].itertuples(index=False, name=None)}

    def union(a: str, b: str) -> None:
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return
        merged = year_sets[a] | year_sets[b]
        uf.union(a, b)
        root = uf.find(a)
        other = b if root == a else a
        year_sets[root] = merged
        year_sets.pop(other, None)

    for a, b in c.execute(
        "select from_source_record_id,to_source_record_id from read_parquet(?) "
        "where relation='same_place' and decision_status in (select unnest(?))",
        [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
    ).fetchall():
        union(a, b)
    edge_deltas = [
        (BASE / "accepted_identity_edge_delta.csv", "from_id", "to_id"),
        (BASE / "top60_identity_edge_delta.csv", "from_id", "to_id"),
        (CODE / "accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
        (HCLASS / "accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ]
    for path, a_col, b_col in edge_deltas:
        d = pd.read_csv(path)
        for a, b in d[[a_col, b_col]].itertuples(index=False, name=None):
            union(a, b)
    point_ids = set(map(str, c.execute(
        "select target_source_record_id from read_parquet(?) where coordinate_admission_status in (select unnest(?))",
        [str(POINTS), STATUSES],
    ).fetchnumpy()["target_source_record_id"]))
    for path in [BASE / "top60_point_use_delta.csv", CODE / "old_point_use_delta.csv", HIST / "accepted_point_use_delta.csv", HCLASS / "accepted_retrospective_point_use_delta.csv", SHARED / "accepted_shared_locality_point_uses.csv"]:
        point_ids.update(pd.read_csv(path).target_source_record_id.astype(str))
    obs["source_record_id"] = obs.source_record_id.astype(str)
    obs["component_years"] = obs.source_record_id.map(lambda sid: ",".join(map(str, sorted(year_sets[uf.find(sid)]))))
    obs["full_chain"] = obs.source_record_id.map(lambda sid: {2002, 2010, 2021}.issubset(year_sets[uf.find(sid)]))
    obs["accepted_point"] = obs.source_record_id.isin(point_ids)
    obs["joint_covered"] = obs.full_chain & obs.accepted_point
    additive = obs.is_additive_settlement_record.fillna(False)
    special_federal_regions = {"москва", "санкт петербург", "севастополь"}
    summary = {"scope": "individual additive settlement rows eligible for a 2002-2010-2021 chain; federal-city regional aggregates are handled in a separate territory layer; Crimea/Sevastopol 2021 are out of scope because no 2002/2010 Russian census endpoint", "by_year": {}}
    for year in [2002, 2010, 2021]:
        d = obs[(obs.census_year == year) & additive & ~obs.region_norm.isin(special_federal_regions)].copy()
        if year == 2021:
            d = d[~d.region_norm.eq("крым")]
        residual = d[~d.joint_covered].copy()
        residual["residual_reason"] = residual.apply(lambda r: "missing_point_and_chain" if not r.accepted_point and not r.full_chain else ("missing_point" if not r.accepted_point else "missing_full_chain"), axis=1)
        residual.sort_values(["population", "source_record_id"], ascending=[False, True]).head(100).to_csv(OUT / f"top100_uncovered_{year}.csv", index=False)
        parts = residual.groupby("residual_reason").population.agg(["size", "sum"]).to_dict("index")
        summary["by_year"][str(year)] = {"selected_additive_rows_in_chain_scope": int(len(d)), "selected_additive_population_in_chain_scope": int(d.population.sum()), "joint_covered_population": int(d.loc[d.joint_covered, "population"].sum()), "uncovered_rows": int(len(residual)), "uncovered_population": int(residual.population.sum()), "uncovered_by_reason": parts}
    summary["inputs"] = {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SELECTED, EDGES, POINTS] + [p for p, _, _ in edge_deltas] + [BASE / "top60_point_use_delta.csv", CODE / "old_point_use_delta.csv", HIST / "accepted_point_use_delta.csv", HCLASS / "accepted_retrospective_point_use_delta.csv", SHARED / "accepted_shared_locality_point_uses.csv"]}
    summary["limitation"] = "This additive settlement residual excludes the separate federal-territory spatial overlay and does not imply every uncovered record existed in all three census years."
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Текущий крупнейший остаток строгой цепочки\n\n"
        "Список ранжирует по численности записи НП, которым не хватает либо принятой координаты, либо компоненты со всеми тремя переписями. Московская, Санкт-Петербургская и Севастопольская территории рассчитываются отдельно и не смешиваются с отдельными НП; Крым и Севастополь 2021 исключены из доступного трёхпереписного знаменателя, поскольку они отсутствовали в российской переписной географии 2002/2010. На запись сохраняются source locator и population quality. Это список приоритетов, не новые решения.\n\n"
        "`top100_uncovered_<year>.csv` содержит наибольшие строки для следующего прохода; `summary.json` закрепляет численность остатка и входные SHA.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main()
