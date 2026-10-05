#!/usr/bin/env python3
"""Admit only the remaining collision-free points in the audited urban code bridge."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
from build_long_table import ACCEPTED_EDGE_STATUSES, UnionFind

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "research_rebuild/evidence/historical_urban_code_residual_20261005"
COHORT = Path("/workspace/settlements-work/continuation_20261004/independent_review/historical_urban_code_bridge_1258_audit_v1/cohort.csv")
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
RAW_ROOT = Path("/workspace/settlements-raw")
STATUSES = ["reviewed_rule_accepted", "frozen_r5b_reviewed_baseline_preserved", "reviewed_extension_rule_accepted", "reviewed_case_accepted"]


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main() -> None:
    cohort = pd.read_csv(COHORT)
    eligible = cohort[(cohort.source_file_resolved == True) & (cohort.shared_point_n == 1)].copy()
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    selected = con.execute(
        "select source_record_id,census_year,population,is_additive_settlement_record from read_parquet(?)",
        [str(SELECTED)],
    ).fetchdf()
    if selected.source_record_id.duplicated().any():
        raise RuntimeError("selected observation IDs are not unique")
    selected = selected.set_index("source_record_id")
    points = con.execute(
        "select target_source_record_id,target_year,latitude,longitude from read_parquet(?) "
        "where coordinate_admission_status in (select unnest(?))",
        [str(POINTS), STATUSES],
    ).fetchdf()
    if points.target_source_record_id.duplicated().any():
        raise RuntimeError("Graph29 has multiple accepted point uses per target")
    point_ids = set(points.target_source_record_id.astype(str))
    residual = eligible[~eligible.source_record_id.astype(str).isin(point_ids)].copy()
    if len(residual) != 18 or set(residual.year.astype(int)) != {2002}:
        raise RuntimeError(f"audited unpointed residual changed: {len(residual)} rows")
    # Ensure every point candidate still refers to one selected additive census row.
    uses = []
    for row in residual.itertuples(index=False):
        sid = str(row.source_record_id)
        if sid not in selected.index:
            raise RuntimeError(f"candidate absent from selected observations: {sid}")
        obs = selected.loc[sid]
        if int(obs.census_year) != int(row.year) or not bool(obs.is_additive_settlement_record):
            raise RuntimeError(f"selected-row year/grain mismatch: {sid}")
        if pd.isna(row.point_lat) or pd.isna(row.point_lon) or not (-90 <= row.point_lat <= 90 and -180 <= row.point_lon <= 180):
            raise RuntimeError(f"invalid coordinate: {sid}")
        rel = str(row.source_file)
        raw = RAW_ROOT / rel
        if not raw.is_file():
            raise RuntimeError(f"raw source file is unavailable: {raw}")
        uses.append({
            "target_source_record_id": sid,
            "target_year": int(row.year),
            "target_name": row.settlement_name,
            "target_type": row.settlement_type,
            "target_region": row.region_norm,
            "target_population": int(row.population),
            "latitude": float(row.point_lat),
            "longitude": float(row.point_lon),
            "coordinate_source": "GeoKLADR 2011 point joined by exact 8-char OKATO prefix + literal KOD3=000",
            "source_file": rel,
            "source_file_sha256": sha(raw),
            "source_locator": row.source_locator,
            "okato_2009_raw": str(row.classifier_okato_2009_raw),
            "okato_2011_raw": str(row.geokladr_okato_2011_raw),
            "kod3_raw": str(row.KOD3_raw),
            "point_record_1based": int(row.point_record),
            "source_row_exact": bool(row.source_row_exact),
            "region_name_type_key_count": int(row.region_name_type_key_count),
            "within_year_shared_point_candidates": int(row.shared_point_n),
            "coordinate_admission_status": "reviewed_rule_accepted",
            "coordinate_application_family": "historical_urban_8_to_11_okato_prefix_kod3_000_residual_20261005",
            "point_is_retrospective_inference": True,
            "measurement_date_unknown": True,
            "provider_identifier_binding_asserted": False,
            "population_value_changed": False,
            "population_comparability_asserted": False,
        })
    use_frame = pd.DataFrame(uses)
    if use_frame.target_source_record_id.duplicated().any():
        raise RuntimeError("duplicate point targets in residual")
    # Reject exact same-year coordinate collisions with the accepted point ledger.
    existing = points.dropna(subset=["target_year", "latitude", "longitude"]).copy()
    existing["coord_key"] = list(zip(existing.latitude.round(7), existing.longitude.round(7)))
    existing_keys = {(int(float(y)), key) for y, key in zip(existing.target_year, existing.coord_key)}
    collisions = [
        (int(y), (round(float(lat), 7), round(float(lon), 7))) in existing_keys
        for y, lat, lon in zip(use_frame.target_year, use_frame.latitude, use_frame.longitude)
    ]
    if any(collisions):
        raise RuntimeError("new point matches an accepted same-year coordinate")
    use_frame.to_csv(OUT / "accepted_point_use_delta.csv", index=False)

    # The matched current 2021 endpoint route is measured separately. It may
    # produce corroboration, but cannot be counted as new if already in graph.
    current = con.execute(
        "select source_record_id,settlement_name,settlement_type,region_norm,population "
        "from read_parquet(?) where census_year=2021 and is_additive_settlement_record=true",
        [str(SELECTED)],
    ).fetchdf()
    current_points = points.dropna(subset=["latitude", "longitude"])
    current = current.merge(current_points, left_on="source_record_id", right_on="target_source_record_id", how="inner")
    def norm(v: object) -> str:
        return " ".join(str(v).lower().replace("ё", "е").split())
    for col in ["settlement_name", "settlement_type", "region_norm"]:
        eligible[col + "_norm"] = eligible[col].map(norm)
        current[col + "_norm"] = current[col].map(norm)
    groups = {key: group for key, group in current.groupby(["settlement_name_norm", "settlement_type_norm", "region_norm_norm"])}
    candidate_rows = []
    for row in eligible.itertuples(index=False):
        key = (row.settlement_name_norm, row.settlement_type_norm, row.region_norm_norm)
        group = groups.get(key)
        if group is None:
            continue
        for target in group.itertuples(index=False):
            lat1, lat2 = float(row.point_lat), float(target.latitude)
            dlat = __import__("math").radians(lat1 - lat2)
            dlon = __import__("math").radians(float(row.point_lon) - float(target.longitude))
            a = __import__("math").sin(dlat / 2) ** 2 + __import__("math").cos(__import__("math").radians(lat1)) * __import__("math").cos(__import__("math").radians(lat2)) * __import__("math").sin(dlon / 2) ** 2
            distance_km = 12742 * __import__("math").asin(min(1, __import__("math").sqrt(a)))
            old_pop, current_pop = float(row.population), float(target.population)
            ratio = max(old_pop, current_pop) / min(old_pop, current_pop) if min(old_pop, current_pop) > 0 else float("inf")
            if distance_km <= 5 and ratio <= 2:
                candidate_rows.append({"old_id": str(row.source_record_id), "old_year": int(row.year), "current_2021_id": target.source_record_id, "old_population": int(old_pop), "current_population": int(current_pop), "distance_km": distance_km, "population_ratio": ratio})
    match_frame = pd.DataFrame(candidate_rows)
    if match_frame.empty:
        pd.DataFrame(columns=["old_id", "old_year", "current_2021_id", "old_population", "current_population", "distance_km", "population_ratio"]).to_csv(OUT / "historical_code_same_name_current_2021_candidates.csv", index=False)
        graph_connected_edges = 0
    else:
        match_frame.to_csv(OUT / "historical_code_same_name_current_2021_candidates.csv", index=False)
        uf = UnionFind(selected.index.astype(str))
        for a, b in con.execute(
            "select from_source_record_id,to_source_record_id from read_parquet(?) "
            "where relation='same_place' and decision_status in (select unnest(?))",
            [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
        ).fetchall():
            uf.union(str(a), str(b))
        prior_paths = [
            (REPO / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/accepted_identity_edge_delta.csv", "from_id", "to_id"),
            (REPO / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/top60_identity_edge_delta.csv", "from_id", "to_id"),
            (REPO / "research_rebuild/evidence/top100_classifier_bridge_20261005/accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
            (REPO / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
        ]
        for path, a_col, b_col in prior_paths:
            if path.is_file():
                df = pd.read_csv(path)
                for a, b in df[[a_col, b_col]].itertuples(index=False, name=None):
                    uf.union(str(a), str(b))
        graph_connected_edges = int(sum(uf.find(a) == uf.find(b) for a, b in match_frame[["old_id", "current_2021_id"]].itertuples(index=False, name=None)))

    summary = {
        "status": "accepted_point_extension_delta_for_residual_only",
        "rule": "Exact historical 8-char OKATO to live 11-char GeoKLADR code prefix with literal KOD3=000; exact selected source row; exact typed regional key unique; source file present; GeoKLADR point not shared by another historical named candidate or an already accepted same-year point.",
        "historical_code_cohort": {"rows": int(len(cohort)), "population": int(cohort.population.sum())},
        "source_resolved_noncollision_cohort": {"rows": int(len(eligible)), "population": int(eligible.population.sum())},
        "already_accepted_points_in_eligible_cohort": {"rows": int(len(eligible) - len(residual)), "population": int(eligible.loc[eligible.source_record_id.astype(str).isin(point_ids), "population"].sum())},
        "new_point_uses": {"rows": int(len(use_frame)), "population": int(use_frame.target_population.sum()), "by_year": {str(int(y)): {"rows": int(n), "population": int(use_frame.loc[use_frame.target_year.eq(y), "target_population"].sum())} for y, n in use_frame.groupby("target_year").size().items()}},
        "same_year_accepted_coordinate_collisions": 0,
        "current_2021_exact_name_type_region_point_candidates_le_5km_population_ratio_le_2": {"edges": int(len(match_frame)), "old_ids": int(match_frame.old_id.nunique()) if not match_frame.empty else 0, "old_population": int(match_frame.old_population.sum()) if not match_frame.empty else 0, "already_connected_in_current_identity_graph": graph_connected_edges, "new_identity_edges_available": int(len(match_frame) - graph_connected_edges)},
        "population_values_changed": False,
        "historical_point_is_representative_inference": True,
        "identity_and_population_comparability_asserted": False,
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [COHORT, SELECTED, POINTS, EDGES]},
        "raw_source_files": {str(RAW_ROOT / x): {"sha256": sha(RAW_ROOT / x), "bytes": (RAW_ROOT / x).stat().st_size} for x in sorted(use_frame.source_file.unique())},
        "known_holds": {"shared_point_collision_rows": int((cohort.shared_point_n > 1).sum()), "source_file_unavailable_rows": int((cohort.source_file_resolved != True).sum())},
        "limitation": "All 18 residual point rows are not members of an accepted cross-census identity component; adding these points raises coordinate-only coverage but not the strict point-plus-complete-chain axis.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Остаток исторических городских точек по мосту ОКАТО\n\n"
        "Из аудированной когорты 1 258 строк повторно проверены текущий Graph29 и selected-слой. "
        "Из 1 167 строк с доступным первоисточником и уникальной точкой 1 149 уже имеют принятую точку. "
        "Оставшиеся 18 записей 2002 года добавлены отдельной координатной дельтой после проверки выбранной строки, исходного файла и хеша, точного кода 8→11, уникальности имени/типа/региона, допустимости WGS84 и отсутствия точного совпадения с принятой точкой того же года.\n\n"
        "Этот шаг не создаёт межгодовых связей и не меняет численность. Поэтому он увеличивает только точечное покрытие; строгую ось «координата + полная цепочка 2002→2010→2021» пересчитывать с приростом от него нельзя. Сводка и входные хеши — в `summary.json`.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main()
