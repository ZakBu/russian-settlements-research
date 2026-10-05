#!/usr/bin/env python3
"""Measure point-plus-link coverage for the census years each place has."""
from __future__ import annotations

import hashlib
import json
import math
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
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
FEDERAL = ROOT / "research_rebuild/evidence/federal_territory_spatial_overlay_20261005/coverage_overlay.json"
EVIDENCE = ROOT / "research_rebuild/evidence"
EDGE_DELTAS = [
    (EVIDENCE / "exact_name_proximity_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    (EVIDENCE / "unique_name_region_coordinate_bridge_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    (EVIDENCE / "top60_and_proximity_review_20261005/simple_rule_application/accepted_identity_edge_delta.csv", "from_id", "to_id"),
    (EVIDENCE / "top60_and_proximity_review_20261005/simple_rule_application/top60_identity_edge_delta.csv", "from_id", "to_id"),
    (EVIDENCE / "top100_classifier_bridge_20261005/accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
    (EVIDENCE / "historical_classifier_bridge_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
]
POINT_DELTAS = [
    EVIDENCE / "top60_and_proximity_review_20261005/simple_rule_application/top60_point_use_delta.csv",
    EVIDENCE / "top100_classifier_bridge_20261005/old_point_use_delta.csv",
    EVIDENCE / "historical_urban_code_residual_20261005/accepted_point_use_delta.csv",
    EVIDENCE / "historical_classifier_bridge_batch_20261005/accepted_retrospective_point_use_delta.csv",
    EVIDENCE / "shared_locality_point_novaya_usman_20261005/accepted_shared_locality_point_uses.csv",
    EVIDENCE / "unique_name_region_coordinate_bridge_20261005/accepted_point_use_delta.csv",
]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(config={"threads": 2, "memory_limit": "3GB"})
    selected = con.execute(
        "SELECT source_record_id,CAST(census_year AS INTEGER) yr,settlement_name,settlement_type,"
        "region_norm,population,COALESCE(is_additive_settlement_record,FALSE) additive "
        "FROM read_parquet(?) WHERE census_year IN (2002,2010,2021)", [str(SELECTED)]
    ).fetchdf()
    if selected.source_record_id.isna().any() or selected.source_record_id.astype(str).duplicated().any():
        raise ValueError("Selected census record IDs must be unique and nonnull")
    uf = UnionFind(selected.source_record_id.astype(str))
    years = {str(sid): {int(year)} for sid, year in selected[["source_record_id", "yr"]].itertuples(index=False, name=None)}

    def union(a: str, b: str) -> None:
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return
        merged = years[a] | years[b]
        if len(merged) < len(years[a]) + len(years[b]):
            raise ValueError(f"Accepted graph has repeated census year after union: {a}, {b}")
        uf.union(a, b)
        root = uf.find(a)
        other = b if root == a else a
        years[root] = merged
        years.pop(other, None)

    for a, b in con.execute(
        "SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) "
        "WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))",
        [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
    ).fetchall():
        union(a, b)
    for path, a_col, b_col in EDGE_DELTAS:
        frame = pd.read_csv(path)
        for a, b in frame[[a_col, b_col]].itertuples(index=False, name=None):
            union(a, b)

    point_ids = set(map(str, con.execute(
        "SELECT target_source_record_id FROM read_parquet(?) "
        "WHERE coordinate_admission_status IN (SELECT UNNEST(?))",
        [str(POINTS), sorted(ACCEPTED_COORDINATE_STATUSES)],
    ).fetchnumpy()["target_source_record_id"]))
    for path in POINT_DELTAS:
        frame = pd.read_csv(path)
        if "target_source_record_id" not in frame:
            raise ValueError(f"Point delta lacks target_source_record_id: {path}")
        point_ids.update(frame.target_source_record_id.dropna().astype(str))

    selected["source_record_id"] = selected.source_record_id.astype(str)
    selected["root"] = selected.source_record_id.map(lambda sid: uf.find(sid))
    selected["component_years"] = selected.root.map(lambda root: ",".join(map(str, sorted(years[uf.find(root)]))))
    selected["accepted_point"] = selected.source_record_id.isin(point_ids)
    selected["available_year_path"] = selected.root.map(lambda root: len(years[uf.find(root)]) >= 2)
    special = {"москва", "санкт петербург", "севастополь"}
    selected_years = selected[(selected.additive) & ~selected.region_norm.isin(special)].copy()
    selected_years = selected_years[~((selected_years.yr == 2021) & selected_years.region_norm.eq("крым"))]
    selected_years["covered"] = selected_years.accepted_point & selected_years.available_year_path
    selected_years["residual_reason"] = selected_years.apply(
        lambda row: "missing_point_and_path" if not row.accepted_point and not row.available_year_path else
        ("missing_point" if not row.accepted_point else "missing_available_year_path"), axis=1
    )
    fed = json.loads(FEDERAL.read_text(encoding="utf-8"))
    summary = {
        "status": "current_exact_observed_year_path_plus_federal_territory_point_measurement",
        "definition": "An ordinary selected additive record counts when it has its own accepted point use and belongs to an accepted same_place component containing at least two distinct selected census years. No missing year is imputed. Federal cities are represented separately by the accepted territory-point overlay and are not double-counted as ordinary settlements. The 2021 comparison excludes Crimea and Sevastopol because these were outside the Russian 2002/2010 census geography.",
        "ordinary_identity_components": int(selected.root.nunique()),
        "accepted_edge_count_core": int(con.execute("SELECT COUNT(*) FROM read_parquet(?) WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))", [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)]).fetchone()[0]),
        "accepted_edge_delta_rows": int(sum(len(pd.read_csv(path)) for path, _, _ in EDGE_DELTAS)),
        "accepted_point_count_core": len(set(map(str, con.execute("SELECT target_source_record_id FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))", [str(POINTS), sorted(ACCEPTED_COORDINATE_STATUSES)]).fetchnumpy()["target_source_record_id"]))),
        "accepted_point_delta_rows": int(sum(len(pd.read_csv(path)) for path in POINT_DELTAS)),
        "by_year": {},
        "limitations": [
            "This is an axis for the census years actually present on a connected identity component, not necessarily a full 2002-2010-2021 chain.",
            "Historical inclusion / merge scopes remain separately marked and are not ordinary same_place links.",
            "A point inherited under the new rule is representative-point continuity, not a census-date measurement.",
            "Population values are unchanged; exact comparability after boundary change is not asserted.",
            "The 2010 selected sum remains below the national official control; coordinates and identity do not repair source-value coverage.",
            "The ±5% Student-t statement is not a confidence interval for a complete census total; no sampling design was used here.",
        ],
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SELECTED, EDGES, POINTS, FEDERAL] + [x for x, _, _ in EDGE_DELTAS] + POINT_DELTAS},
    }
    for year in (2002, 2010, 2021):
        d = selected_years[selected_years.yr == year].copy()
        ordinary_pop = int(d.loc[d.covered, "population"].sum())
        ordinary_known = int(d.population.sum())
        territory = fed["by_year"][str(year)]
        if year == 2021:
            denominator = int(territory["available_three_census_chain_denominator"])
            territorial_pop = int(territory["territory_full_chain_population_added"])
        else:
            denominator = int(territory["official_control"])
            territorial_pop = int(territory["territory_population_represented"])
        total = ordinary_pop + territorial_pop
        gap = max(0, math.ceil(0.99 * denominator) - total)
        summary["by_year"][str(year)] = {
            "ordinary_selected_population": ordinary_known,
            "ordinary_coordinate_plus_actual_year_path_population": ordinary_pop,
            "ordinary_percent_of_selected_population": 100 * ordinary_pop / ordinary_known if ordinary_known else None,
            "territory_layer_population_added_separately": territorial_pop,
            "population_coordinate_plus_available_year_path": total,
            "denominator": denominator,
            "coverage_percent": 100 * total / denominator,
            "gap_to_99_percent": gap,
            "ordinary_rows_covered": int(d.covered.sum()),
            "ordinary_rows_residual": int((~d.covered).sum()),
            "ordinary_residual_population": int(d.loc[~d.covered, "population"].sum()),
            "residual_by_reason": d.loc[~d.covered].groupby("residual_reason").population.agg(["size", "sum"]).to_dict("index"),
        }
        d.loc[~d.covered].sort_values(["population", "source_record_id"], ascending=[False, True]).head(100).to_csv(
            OUT / f"top100_residual_{year}.csv", index=False
        )
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Текущая привязка по фактически доступным годам и координатам\n\n"
        "Для обычного НП запись считается покрытой, если у неё есть принятая точка и она лежит в принятом компоненте `same_place` минимум с двумя переписными годами. Отдельные ряды федеральных городов представлены слоем территорий без двойного счёта с НП. Для 2021 сравнивается доступная территория без Крыма и Севастополя; это не пропуски matching. Полная трёхпереписная цепочка остаётся отдельным показателем.\n\n"
        "`summary.json` содержит измерение и входные SHA; `top100_residual_<year>.csv` ранжирует оставшиеся строки. Точки, унаследованные по новой связи, отмечены как ретроспективное пространственное представление. Численность не изменена, сопоставимость границ не заявлена.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
