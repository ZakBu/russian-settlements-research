#!/usr/bin/env python3
"""Reproduce top-60 unpointed-record review and graph-wide <=5 km candidates.

This is an evidence builder, not an acceptance job: no coordinate or identity
ledger is modified. It preserves raw point claims separately from accepted
point uses and emits collision/uniqueness/graph gates for downstream review.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd

from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind

REPO = Path(__file__).resolve().parents[2]
INPUTS = {
    "selected": Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet"),
    "points": Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet"),
    "edges": Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet"),
    "historical": Path("/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet"),
    "wikidata": Path("/workspace/settlements-work/wikidata/point_bindings.parquet"),
    "wikidata_wide": Path("/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet"),
    "coordinate_screen": Path("/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet"),
    "raw2021": Path("/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet"),
}
TOP_FILES = {y: REPO / f"research_rebuild/evidence/unpointed_top20_20261005/top20_{y}_direct_point_missing.csv" for y in (2002, 2010, 2021)}
R = 6371008.8


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def csv_write(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    out = args.out
    if out.exists():
        raise FileExistsError(f"Output exists; choose a new directory: {out}")
    sources = {k: {"path": str(v), "sha256": sha(v), "bytes": v.stat().st_size} for k, v in INPUTS.items()}
    top = pd.concat([pd.read_csv(TOP_FILES[y]) for y in (2002, 2010, 2021)], ignore_index=True)
    top_hashes = {str(y): {"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size} for y, p in TOP_FILES.items()}
    if len(top) != 60 or top.source_record_id.nunique() != 60:
        raise ValueError("Expected exactly 60 distinct top-20 source records")
    out.mkdir(parents=True)
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    con.register("top", top)
    for key, path in INPUTS.items():
        con.read_parquet(str(path)).create_view(key)
    point_statuses = ",".join("'" + x.replace("'", "''") + "'" for x in sorted(ACCEPTED_COORDINATE_STATUSES))
    edge_statuses = ",".join("'" + x.replace("'", "''") + "'" for x in sorted(ACCEPTED_EDGE_STATUSES))
    con.execute(f"CREATE VIEW accepted_points AS SELECT * FROM points WHERE coordinate_admission_status IN ({point_statuses})")

    # Join source identifiers to candidate evidence; do not coalesce candidate
    # values into the accepted-coordinate columns.
    con.execute("""CREATE TEMP TABLE raw2021_indexed AS SELECT row_number() OVER () raw_row_1based,* FROM raw2021""")
    top_evidence = con.execute("""SELECT t.source_record_id,t.census_year,t.settlement_name,t.settlement_type,t.region_raw,
        t.population,t.population_value_quality,t.source_native_id,t.okato,t.oktmo,t.in_frozen_scope_residual,
        p.target_source_record_id IS NOT NULL accepted_point_exists,p.latitude accepted_latitude,
        p.longitude accepted_longitude,p.coordinate_source accepted_coordinate_source,
        h.historical_okato_2009_raw,h.historical_okato_2011_raw,h.oktmo_2011_raw historical_oktmo,
        h.source_line_1based historical_classifier_line,h.record_number_1based historical_geo_record,
        h.source_sha256_2009 historical_classifier_sha256,h.source_sha256_2011 historical_geo_sha256,
        h.latitude_from_lat historical_candidate_latitude,h.longitude_from_long historical_candidate_longitude,
        h.historical_key_region_name_type_count historical_region_name_type_count,
        h.code_join_basis historical_code_join_basis,h.historical_name_exact,h.historical_type_exact,
        h.is_deleted historical_deleted,h.decision_status historical_candidate_status,
        h.population_boundary_comparability_admitted historical_population_comparability,
        w.wikidata_qid,w.coordinate_decision wikidata_coordinate_decision,w.identity_decision wikidata_identity_decision,
        w.source_latitude wikidata_source_latitude,w.source_longitude wikidata_source_longitude,
        w.p625_points_json wikidata_points_json,w.review_flags_json wikidata_review_flags,
        ww.wikidata_qid wide_wikidata_qid,ww.coordinate_admission wide_wikidata_coordinate_admission,
        ww.identity_admission wide_wikidata_identity_admission,ww.candidate_status wide_wikidata_candidate_status,
        ww.points_json wide_wikidata_points_json,ww.wikidata_truthy_p625_claims_json wide_wikidata_truthy_p625_claims,
        ww.tsv_distinct_point_count wide_wikidata_tsv_point_count,ww.truthy_p625_point_count wide_wikidata_truthy_p625_point_count,
        r.latitude_dadata raw_provider_latitude,r.longitude_dadata raw_provider_longitude,
        r.fias_level_dadata raw_provider_fias_level,r.qc_geo_dadata raw_provider_qc_geo,
        r.object_level raw_provider_object_level,r.object_name raw_provider_object_name,
        r.settlement_dadata raw_provider_settlement_name,r.settlement_fias_id_dadata raw_provider_fias_id,
        r.oktmo raw_provider_oktmo,r.mun_upper raw_provider_municipality,r.mun_lower raw_provider_locality,
        cs.provider_point_available screen_provider_point_available,cs.provider_latitude screen_provider_latitude,
        cs.provider_longitude screen_provider_longitude,cs.provider_fias_level screen_provider_fias_level,
        cs.provider_settlement_name screen_provider_name,cs.provider_settlement_type_full screen_provider_type,
        cs.provider_coordinate_duplicate_count screen_provider_coordinate_duplicate_count,
        cs.provider_settlement_fias_duplicate_count screen_provider_fias_duplicate_count,
        cs.candidate_status screen_provider_candidate_status,cs.admission_allowed screen_provider_admission_allowed,
        cs.baseline_coordinate_quality_class screen_baseline_coordinate_quality,
        cs.baseline_coordinate_review_required screen_baseline_review_required,
        cs.gate_provider_name_exact_selected_name screen_gate_exact_name,
        cs.gate_provider_full_type_exact_selected_type screen_gate_exact_type,
        cs.gate_provider_coordinate_unique_in_selected_rows screen_gate_unique_coordinate,
        cs.gate_provider_primary_fias_id_unique_in_selected_rows screen_gate_unique_fias,
        cs.provider_query_receipt_missing screen_provider_query_receipt_missing
        FROM top t LEFT JOIN accepted_points p ON p.target_source_record_id=t.source_record_id
        LEFT JOIN historical h ON h.source_record_id=t.source_record_id
        LEFT JOIN wikidata w ON w.source_record_id=t.source_record_id
        LEFT JOIN wikidata_wide ww ON ww.source_record_id=t.source_record_id
        LEFT JOIN coordinate_screen cs ON cs.source_record_id=t.source_record_id
        LEFT JOIN raw2021_indexed r ON t.census_year=2021 AND r.raw_row_1based=try_cast(regexp_extract(t.source_record_id,':parquet:([0-9]+)$',1) AS INT)
        ORDER BY t.census_year,t.population DESC,t.source_record_id""").fetchdf()
    top_evidence.to_csv(out / "top60_coordinate_and_identity_candidates.csv", index=False)

    # For each unpointed top-60 observation, enumerate exactly normalized
    # same-name/type/region observations in other censuses that already have an
    # accepted point. These are potential carriers; alias and event review is
    # deliberately outside the automatic join.
    carrier_rows = con.execute("""WITH keys AS (SELECT census_year,name_norm,type_norm,region_norm,count(*) key_count
        FROM selected GROUP BY ALL), target AS (SELECT t.source_record_id,t.census_year,t.settlement_name,t.settlement_type,
        t.population,t.population_value_quality,t.source_native_id,ss.name_norm,ss.type_norm,ss.region_norm
        FROM top t JOIN selected ss USING(source_record_id))
        SELECT t.census_year target_year,t.source_record_id target_source_record_id,t.settlement_name target_name,
        t.settlement_type target_type,t.population target_population,t.population_value_quality target_population_quality,
        t.source_native_id target_native_id,k1.key_count target_full_year_key_count,
        c.census_year carrier_year,c.source_record_id carrier_source_record_id,c.settlement_name carrier_name,
        c.settlement_type carrier_type,c.population carrier_population,c.population_value_quality carrier_population_quality,
        c.source_native_id carrier_native_id,k2.key_count carrier_full_year_key_count,
        p.latitude carrier_latitude,p.longitude carrier_longitude,p.coordinate_source carrier_coordinate_source,
        p.coordinate_admission_status carrier_coordinate_admission_status,p.coordinate_provider_id carrier_provider_id,
        c.okato carrier_okato,c.oktmo carrier_oktmo,c.source_file carrier_source_file,c.source_sheet carrier_source_sheet,
        c.source_row carrier_source_row,
        'candidate_exact_name_type_region_existing_point_no_identity_admission' candidate_status
        FROM target t JOIN selected c ON c.census_year!=t.census_year AND c.name_norm=t.name_norm
          AND c.type_norm=t.type_norm AND c.region_norm=t.region_norm
        JOIN keys k1 ON k1.census_year=t.census_year AND k1.name_norm=t.name_norm AND k1.type_norm=t.type_norm AND k1.region_norm=t.region_norm
        JOIN keys k2 ON k2.census_year=c.census_year AND k2.name_norm=c.name_norm AND k2.type_norm=c.type_norm AND k2.region_norm=c.region_norm
        JOIN accepted_points p ON p.target_source_record_id=c.source_record_id
        ORDER BY t.census_year,t.population DESC,c.census_year,c.source_record_id""").fetchdf()
    carrier_rows.to_csv(out / "top60_existing_point_carrier_candidates.csv", index=False)

    # Detect exact accepted-coordinate collisions at the census-record grain.
    con.execute("""CREATE TEMP TABLE collision_groups AS SELECT s.census_year,p.latitude,p.longitude,
        count(*) record_count,count(distinct s.source_record_id) source_record_count,
        count(distinct s.name_norm) name_count,count(distinct s.type_norm) typed_name_count,
        count(distinct s.settlement_id) legacy_settlement_id_count,sum(s.population) selected_population
        FROM selected s JOIN accepted_points p ON p.target_source_record_id=s.source_record_id
        GROUP BY 1,2,3 HAVING count(*)>1""")
    collisions = con.execute("""SELECT s.census_year,s.source_record_id,s.settlement_name,s.settlement_type,s.region_norm,
        s.source_native_id,s.fias_id,s.population,s.population_scope,s.entity_grain_status,
        p.latitude,p.longitude,p.coordinate_source,p.coordinate_provider,p.coordinate_provider_id,
        p.coordinate_admission_status,p.coordinate_application_family,p.application_inference_kind,
        p.point_origin_file,p.point_origin_sha256,p.point_origin_locator,
        c.record_count,c.name_count,c.typed_name_count,c.selected_population
        FROM selected s JOIN accepted_points p ON p.target_source_record_id=s.source_record_id
        JOIN collision_groups c ON c.census_year=s.census_year AND c.latitude=p.latitude AND c.longitude=p.longitude
        ORDER BY s.census_year,c.selected_population DESC,s.source_record_id""").fetchdf()
    collisions.to_csv(out / "accepted_same_year_coordinate_collisions.csv", index=False)

    # Build graph components and exact-name/region pairs with accepted
    # points. 5 km is a candidate-generation radius, not a geocoding accuracy.
    ids_years = con.execute("SELECT source_record_id,census_year FROM selected").fetchall()
    if len(ids_years) != len({x[0] for x in ids_years}):
        raise ValueError("Selected source record IDs are not unique")
    uf = UnionFind([x[0] for x in ids_years])
    for a, b in con.execute(f"SELECT from_source_record_id,to_source_record_id FROM edges WHERE relation='same_place' AND decision_status IN ({edge_statuses})").fetchall():
        if a not in uf.parent or b not in uf.parent:
            raise ValueError("Accepted edge endpoint missing from selected observations")
        uf.union(a, b)
    years_by_root: dict[str, set[int]] = defaultdict(set)
    for sid, year in ids_years:
        years_by_root[uf.find(sid)].add(year)
    roots = {sid: uf.find(sid) for sid, _ in ids_years}
    con.register("components", pd.DataFrame({"source_record_id": list(roots), "component_root": list(roots.values())}))
    con.execute("""CREATE TEMP TABLE accepted AS SELECT s.source_record_id,s.census_year,s.settlement_name,
        s.settlement_type,s.name_norm,s.type_norm,s.region_norm,s.population,s.population_scope,
        s.population_value_quality,s.entity_grain_status,s.is_additive_settlement_record,
        p.latitude,p.longitude,p.coordinate_source,p.coordinate_provider,p.coordinate_provider_id,
        p.coordinate_application_family,p.application_inference_kind,p.point_origin_file,p.point_origin_sha256,
        p.point_origin_locator,p.provider_binding_status,p.provider_fias_binding_status,
        c.component_root
        FROM selected s JOIN accepted_points p ON p.target_source_record_id=s.source_record_id
        JOIN components c ON c.source_record_id=s.source_record_id""")
    con.execute(f"""CREATE TEMP TABLE pairs AS WITH d AS (
        SELECT a.census_year from_year,b.census_year to_year,a.source_record_id from_id,b.source_record_id to_id,
        a.settlement_name,a.settlement_type from_type,b.settlement_type to_type,a.type_norm from_type_norm,b.type_norm to_type_norm,
        a.region_norm,a.population from_population,b.population to_population,
        a.population_scope from_population_scope,b.population_scope to_population_scope,
        a.entity_grain_status from_grain,b.entity_grain_status to_grain,
        a.is_additive_settlement_record from_additive,b.is_additive_settlement_record to_additive,
        a.component_root from_component,b.component_root to_component,
        a.component_root=b.component_root already_connected,
        a.component_root!=b.component_root component_compatible,
        a.point_origin_file=b.point_origin_file AND a.point_origin_sha256=b.point_origin_sha256
          AND a.point_origin_locator=b.point_origin_locator same_point_origin,
        (coalesce(a.application_inference_kind,'') LIKE '%reuse%' OR coalesce(a.application_inference_kind,'') LIKE '%continuity%'
          OR coalesce(b.application_inference_kind,'') LIKE '%reuse%' OR coalesce(b.application_inference_kind,'') LIKE '%continuity%') continuity_dependent,
        2*6371008.8*asin(sqrt(least(1.0,pow(sin(radians(a.latitude-b.latitude)/2),2)
          +cos(radians(a.latitude))*cos(radians(b.latitude))*pow(sin(radians(a.longitude-b.longitude)/2),2)))) distance_m,
        a.latitude from_latitude,a.longitude from_longitude,a.coordinate_source from_coordinate_source,
        b.latitude to_latitude,b.longitude to_longitude,b.coordinate_source to_coordinate_source,
        a.coordinate_provider_id from_provider_id,b.coordinate_provider_id to_provider_id
        FROM accepted a JOIN accepted b ON a.census_year<b.census_year
          AND a.name_norm=b.name_norm AND a.region_norm=b.region_norm
        WHERE coalesce(a.name_norm,'')!='' AND coalesce(a.region_norm,'')!=''
          AND abs(a.latitude-b.latitude)<0.046)
        SELECT * FROM d WHERE distance_m<=5000""")
    con.execute("""CREATE TEMP TABLE candidate_pairs AS SELECT *,
        count(*) OVER(PARTITION BY from_year,to_year,from_id) from_degree,
        count(*) OVER(PARTITION BY from_year,to_year,to_id) to_degree
        FROM pairs""")
    # any different-year pair whose roots collectively already contain the
    # same census year is held; compute complete year sets in Python below.
    pair_rows = con.execute("SELECT * FROM candidate_pairs ORDER BY from_year,to_year,from_id,to_id").fetchdf().to_dict("records")
    collision_keys = set(zip(collisions.census_year, collisions.latitude, collisions.longitude))
    by_point = {(r.census_year, r.source_record_id): (r.latitude, r.longitude) for r in con.execute("SELECT s.census_year,s.source_record_id,p.latitude,p.longitude FROM selected s JOIN accepted_points p ON p.target_source_record_id=s.source_record_id").fetchdf().itertuples(index=False)}
    normalized = []
    for row in pair_rows:
        component_year_overlap = bool(years_by_root[row["from_component"]] & years_by_root[row["to_component"]]) if row["from_component"] != row["to_component"] else False
        left_coll = (row["from_year"], row["from_latitude"], row["from_longitude"]) in collision_keys
        right_coll = (row["to_year"], row["to_latitude"], row["to_longitude"]) in collision_keys
        row["component_year_overlap"] = component_year_overlap
        row["same_year_collision_at_either_endpoint"] = left_coll or right_coll
        row["reciprocal_unique"] = row["from_degree"] == 1 and row["to_degree"] == 1
        row["candidate_only"] = True
        # Avoid converting the proposal into a claim: event/status holds are
        # not yet included, so even apparently clean rows await review.
        row["admission_status"] = "candidate_event_and_source_hold_review_required"
        normalized.append(row)
    csv_write(out / "new_component_compatible_candidates_within5km.csv",
        [r for r in normalized if not r["already_connected"] and not r["component_year_overlap"]])

    # Compact by cohort/radius and gate to make the output actionable.
    summary = con.execute("""SELECT from_year,to_year,count(*) candidate_pairs,
        count(*) FILTER(WHERE already_connected) already_connected,
        count(*) FILTER(WHERE component_compatible AND NOT already_connected) component_disjoint_new,
        count(*) FILTER(WHERE NOT reciprocal_unique) non_reciprocal_unique
        FROM (SELECT *,from_degree=1 AND to_degree=1 reciprocal_unique FROM candidate_pairs)
        GROUP BY 1,2 ORDER BY 1,2""").fetchall()
    # Replace the quick count's component gate with explicit year-overlap gate.
    gate_summary = []
    for a, b in ((2002, 2010), (2002, 2021), (2010, 2021)):
        rows = [r for r in normalized if r["from_year"] == a and r["to_year"] == b]
        gate_summary.append({"from_year": a, "to_year": b, "candidate_pairs": len(rows),
            "already_connected": sum(bool(r["already_connected"]) for r in rows),
            "new_component_compatible": sum(not r["already_connected"] and not r["component_year_overlap"] for r in rows),
            "reciprocal_unique_new_component_compatible": sum(not r["already_connected"] and not r["component_year_overlap"] and r["reciprocal_unique"] for r in rows),
            "same_year_point_collision_endpoint": sum(r["same_year_collision_at_either_endpoint"] for r in rows),
            "new_pair_same_year_point_collision_endpoint": sum(not r["already_connected"] and not r["component_year_overlap"] and r["same_year_collision_at_either_endpoint"] for r in rows),
            "same_recorded_point_origin": sum(bool(r["same_point_origin"]) for r in rows),
            "new_pair_same_recorded_point_origin": sum(not r["already_connected"] and not r["component_year_overlap"] and bool(r["same_point_origin"]) for r in rows),
            "continuity_dependent": sum(bool(r["continuity_dependent"]) for r in rows),
            "new_pairs_pop_scope_or_event_reviewed": 0})

    collision_summary = con.execute("""SELECT census_year,count(*) collision_groups,
        sum(record_count) affected_rows,sum(selected_population) collision_population,
        count(*) FILTER(WHERE name_count>1) different_name_groups,
        count(*) FILTER(WHERE typed_name_count>1) different_typed_name_groups
        FROM collision_groups GROUP BY 1 ORDER BY 1""").fetchdf().to_dict("records")
    top_summary = top_evidence.groupby("census_year").agg(record_count=("source_record_id", "count"),
        population=("population", "sum"),raw_provider_point_rows=("screen_provider_point_available", lambda x: int(x.fillna(False).sum())),
        historical_candidate_rows=("historical_candidate_latitude", lambda x: int(x.notna().sum())),
        accepted_point_rows=("accepted_point_exists", "sum")).reset_index().to_dict("records")
    carrier_summary = []
    for year, group in carrier_rows.groupby("target_year"):
        carrier_summary.append({"year": int(year), "candidate_carrier_pairs": int(len(group)),
            "target_records_with_carrier": int(group.target_source_record_id.nunique()),
            "target_and_carrier_full_key_unique_pairs": int(((group.target_full_year_key_count == 1) & (group.carrier_full_year_key_count == 1)).sum()),
            "target_population_not_gain": float(group.drop_duplicates("target_source_record_id").target_population.sum())})

    manifest = {"purpose": "candidate and collision review only; no ledger mutation",
        "source_hashes": {**sources, "top20_csvs": top_hashes},
        "top60": {"distinct_rows": 60, "by_year": top_summary},
        "top60_existing_accepted_point_carriers": carrier_summary,
        "accepted_coordinate_collisions": collision_summary,
        "exact_name_region_5km_pairs": gate_summary,
        "limitations": [
            "Exact normalized name and region within 5 km is candidate generation; settlement-type changes are retained as metadata and do not imply boundary/population comparability.",
            "Shared point origins and continuity-derived points are dependent evidence.",
            "The graph-year gate excludes duplicate-year components but does not by itself resolve event, split/merge, source-scope, or source-hold questions.",
            "Raw provider coordinates and historical/Wikidata claims remain candidate fields, not accepted point uses.",
            "Exact-name/type/region rows with existing point carriers are candidate pairs only; full-year key uniqueness does not resolve population scope, events, or alternate spellings.",
            "No automatic admissions were made by this script."]}
    (out / "summary.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text("""# Топ-60, совпадающие точки и 5-км связи\n\nЭтот выпуск инвентаризирует 60 крупнейших записей без принятой прямой точки, координатные коллизии всего принятого графа и межгодовые кандидаты точного нормализованного имени/региона в радиусе 5 км. Тип записи остаётся отдельным признаком: смена типа может быть реальным событием и сама по себе не доказывает сопоставимость населения. Скрипт не меняет принятые реестры.\n\n`top60_coordinate_and_identity_candidates.csv` отделяет принятые точки от сырых точек поставщика, GeoKLADR и Wikidata; `top60_existing_point_carrier_candidates.csv` перечисляет совпавшие по точному имени/типу/региону записи с уже принятой точкой. Это кандидаты, а не связи. `accepted_same_year_coordinate_collisions.csv` перечисляет записи с одинаковой принятой точкой внутри года. `new_component_compatible_candidates_within5km.csv` содержит новые пары с точками, совместимые по текущему графу; все строки требуют проверки событий, охвата и исходных ограничений.\n\n5 км — радиус поиска, а не точность координат. Полные SHA-256, counts и ограничения — в `summary.json`.\n""", encoding="utf-8")
    after = {k: sha(p) for k, p in INPUTS.items()}
    if any(after[k] != sources[k]["sha256"] for k in INPUTS):
        raise RuntimeError("An input changed during the run")
    print(json.dumps({"output": str(out), "summary": manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
