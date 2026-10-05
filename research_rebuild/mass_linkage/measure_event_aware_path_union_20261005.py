#!/usr/bin/env python3
"""Measure selected census rows supported by accepted scoped multi-year paths."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
BASE = EVIDENCE / "current_available_year_path_20261005"
OUT = EVIDENCE / "event_aware_path_union_20261005"
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
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
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "research_rebuild/mass_linkage"))
    from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind
    con = duckdb.connect(config={"threads": 2, "memory_limit": "3GB"})
    selected = con.execute("SELECT source_record_id,CAST(census_year AS INTEGER) yr,population,is_additive_settlement_record,region_norm FROM read_parquet(?) WHERE census_year IN (2002,2010,2021)", [str(SELECTED)]).fetchdf()
    selected["source_record_id"] = selected.source_record_id.astype(str)
    selected["yr"] = selected.yr.astype(int)
    if selected.source_record_id.duplicated().any():
        raise ValueError("Selected census source_record_id is not unique")
    # Reconstruct only the in-memory coverage ID set. Avoid writing a large
    # temporary all-record CSV to a nearly full workspace.
    all_ids = selected.source_record_id
    uf = UnionFind(all_ids)
    years_by_root = {sid: {int(y)} for sid, y in selected[["source_record_id", "yr"]].itertuples(index=False, name=None)}
    def union(a: str, b: str) -> None:
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return
        merged = years_by_root[a] | years_by_root[b]
        if len(merged) < len(years_by_root[a]) + len(years_by_root[b]):
            raise ValueError("Accepted path reconstruction found a repeated year")
        uf.union(a, b)
        root = uf.find(a)
        other = b if root == a else a
        years_by_root[root] = merged
        years_by_root.pop(other, None)
    for a, b in con.execute("SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))", [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)]).fetchall():
        union(a, b)
    for path, a_col, b_col in EDGE_DELTAS:
        delta = pd.read_csv(path, dtype=str)
        for a, b in delta[[a_col, b_col]].itertuples(index=False, name=None):
            union(a, b)
    point_ids = set(map(str, con.execute("SELECT target_source_record_id FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))", [str(POINTS), sorted(ACCEPTED_COORDINATE_STATUSES)]).fetchnumpy()["target_source_record_id"]))
    for path in POINT_DELTAS:
        point_ids.update(pd.read_csv(path, dtype=str).target_source_record_id.dropna().astype(str))
    ordinary_cov = {sid for sid in all_ids if sid in point_ids and len(years_by_root[uf.find(sid)]) >= 2}
    selected["population"] = pd.to_numeric(selected.population, errors="coerce")
    selected["additive"] = selected.is_additive_settlement_record.fillna(False).astype(bool)
    selected = selected[selected.additive & ~selected.region_norm.isin(["москва", "санкт петербург", "севастополь"])]
    selected = selected[~((selected.yr == 2021) & selected.region_norm.eq("крым"))]
    selected_index = selected.set_index("source_record_id")

    accepted = []
    rejected = []
    input_files = []
    for folder in sorted(EVIDENCE.glob("*20261005")):
        series = folder / "accepted_series.csv"
        manifest = folder / "event_aware_coverage.json"
        if not (series.exists() and manifest.exists()):
            continue
        frame = pd.read_csv(series, dtype=str, keep_default_na=False)
        year_col = next((c for c in ("year", "observation_year") if c in frame.columns), None)
        id_col = "source_record_id" if "source_record_id" in frame.columns else None
        pop_col = next((c for c in ("population_used", "population") if c in frame.columns), None)
        name_col = "place" if "place" in frame.columns else None
        point_col = next((c for c in ("coordinate_status", "point_status") if c in frame.columns), None)
        if not all((year_col, id_col, pop_col, name_col, point_col)):
            continue
        frame["_year"] = pd.to_numeric(frame[year_col], errors="coerce")
        frame["_population"] = pd.to_numeric(frame[pop_col], errors="coerce")
        for place, group in frame.groupby(name_col, dropna=False):
            valid_rows = []
            years = set()
            for row in group.to_dict("records"):
                sid = str(row[id_col]).strip()
                if not sid or sid not in selected_index.index:
                    continue
                yr = int(row["_year"]) if pd.notna(row["_year"]) else None
                if yr is None:
                    continue
                selected_row = selected_index.loc[sid]
                # Do not count context-only / secondary population rows that were not selected.
                if int(selected_row.yr) != yr or pd.isna(row["_population"]) or float(selected_row.population) != float(row["_population"]):
                    continue
                point_status = str(row[point_col]).lower()
                if not ("accepted" in point_status or "reviewed" in point_status or "approved" in point_status):
                    continue
                valid_rows.append({
                    "source_record_id": sid,
                    "year": yr,
                    "population": int(selected_row.population),
                    "place": str(place),
                    "event_folder": folder.name,
                    "point_status": str(row[point_col]),
                    "ordinary_path_point_covered": sid in ordinary_cov,
                })
                years.add(yr)
            # Require two independently selected census records at distinct dates.
            if len(years) < 2 or len({x["source_record_id"] for x in valid_rows}) < 2:
                rejected.extend(valid_rows)
                continue
            accepted.extend(valid_rows)
        input_files.extend([series, manifest])

    # Reject conflicting event assignments for a record, retain ordinary coverage priority.
    by_id: dict[str, list[dict]] = {}
    for row in accepted:
        by_id.setdefault(row["source_record_id"], []).append(row)
    conflict_ids = {sid for sid, rows in by_id.items() if len({(r["place"], r["year"]) for r in rows}) > 1}
    eligible = []
    for sid, rows in by_id.items():
        if sid in conflict_ids:
            continue
        eligible.append(rows[0])
    df = pd.DataFrame(eligible)
    if df.empty:
        df = pd.DataFrame(columns=["source_record_id", "year", "population", "place", "event_folder", "point_status", "ordinary_path_point_covered"])
    df.to_csv(OUT / "accepted_event_path_selected_rows.csv", index=False)
    new = df[~df.source_record_id.isin(ordinary_cov)].copy()
    new.to_csv(OUT / "event_path_rows_added_over_ordinary.csv", index=False)
    fed = json.loads((EVIDENCE / "federal_territory_spatial_overlay_20261005/coverage_overlay.json").read_text(encoding="utf-8"))
    summary = {
        "status": "diagnostic_union_of_current_ordinary_path_and_accepted_scoped_event_paths",
        "definition": "Rows added only when an accepted_series artifact contains at least two selected, distinct-year source records for a place, each population exactly matches the selected observation and each point status is marked accepted/reviewed/approved. Ordinary covered rows are not counted twice. This remains a mixed scope-aware spatial coverage axis, not a canonical same_place graph or proof of population boundary comparability.",
        "event_series_artifacts": len(input_files) // 2,
        "selected_event_path_rows_before_dedup": len(accepted),
        "selected_event_path_unique_rows_after_conflict_removal": len(df),
        "event_record_assignment_conflicts_excluded": sorted(conflict_ids),
        "event_rows_overlapping_ordinary_coverage": int(df.source_record_id.isin(ordinary_cov).sum()),
        "additional_event_rows": len(new),
        "by_year": {},
        "limitations": [
            "Event paths remain their own scope and are not inserted into the ordinary identity graph.",
            "This may include exact selected population values carrying secondary source quality; source quality remains as in the selected layer.",
            "Full chain (all three census years), actual-year path (at least two years), and historical event path are distinct metrics.",
            "No 2010 census total discrepancy is repaired by this spatial union.",
            "Federal territory rows are added separately; ordinary NP rows are excluded from these federal subjects to avoid double-counting.",
        ],
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SELECTED, EDGES, POINTS, EVIDENCE / "federal_territory_spatial_overlay_20261005/coverage_overlay.json", *[x for x, _, _ in EDGE_DELTAS], *POINT_DELTAS, *input_files]},
    }
    for year in (2002, 2010, 2021):
        src = selected[selected.yr == year]
        base = src[src.source_record_id.isin(ordinary_cov)]
        extra = new[new.year == year]
        if year == 2021:
            denominator = int(fed["by_year"][str(year)]["available_three_census_chain_denominator"])
            territorial = int(fed["by_year"][str(year)]["territory_full_chain_population_added"])
        else:
            denominator = int(fed["by_year"][str(year)]["official_control"])
            territorial = int(fed["by_year"][str(year)]["territory_population_represented"])
        ordinary_pop = int(base.population.sum())
        added_pop = int(extra.population.sum())
        total = ordinary_pop + added_pop + territorial
        summary["by_year"][str(year)] = {
            "ordinary_available_year_path_population": ordinary_pop,
            "new_accepted_event_path_population": added_pop,
            "separate_federal_territory_population": territorial,
            "combined_spatial_population": total,
            "denominator": denominator,
            "coverage_percent": 100 * total / denominator,
            "gap_to_99_percent": max(0, int(__import__("math").ceil(.99 * denominator - total))),
            "new_event_rows": len(extra),
            "population_quality_caveat": "Selected population quality preserved row-by-row; no source values are overwritten.",
        }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Сверка массового показателя с принятыми событийными цепочками\n\n"
        "Отчёт добавляет к текущему показателю только выбранные исходные записи из принятых scoped/event-aware серий с точным совпадением source_record_id и численности. В одной серии должны быть не менее двух выбранных переписных записей разных лет с принятыми точками. Уже покрытая обычным графом запись считается один раз. Событийные связи остаются отдельным типом доказательства и не меняют ordinary same_place граф.\n\n"
        "См. `summary.json`, `accepted_event_path_selected_rows.csv` и `event_path_rows_added_over_ordinary.csv`. Это не утверждение о полной сопоставимости численности при изменении границ.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
