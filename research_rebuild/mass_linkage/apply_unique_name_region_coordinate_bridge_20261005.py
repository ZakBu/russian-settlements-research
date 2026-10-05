#!/usr/bin/env python3
"""Apply unique exact-name/region links and point inheritance to the full graph.

The rule is deliberately narrow about identity (exact normalized name and
region, one source row per key in each year) and permissive about type changes.
If both rows have accepted points, the points must be within 5 km. If only one
row has a point, the exact unique-name link may carry that point retrospectively.
Population is not changed or declared comparable; large ratios are flagged, not
used to block a strong identity match.
"""
from __future__ import annotations

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

OUT = ROOT / "research_rebuild/evidence/unique_name_region_coordinate_bridge_20261005"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
PROXIMITY = ROOT / "research_rebuild/evidence/exact_name_proximity_batch_20261005/accepted_identity_edge_delta.csv"
BASE = ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application"
CODE = ROOT / "research_rebuild/evidence/top100_classifier_bridge_20261005"
HIST = ROOT / "research_rebuild/evidence/historical_urban_code_residual_20261005"
HCLASS = ROOT / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005"
SHARED = ROOT / "research_rebuild/evidence/shared_locality_point_novaya_usman_20261005"
BASELINE = ROOT / "research_rebuild/evidence/joint_residual_after_exact_name_proximity_20261005/summary.json"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(config={"threads": 2, "memory_limit": "3GB"})
    obs = con.execute(
        "SELECT source_record_id,CAST(census_year AS INTEGER) yr,settlement_name,settlement_type,name_norm,type_norm,region_norm,"
        "COALESCE(population,0)::DOUBLE population,COALESCE(is_additive_settlement_record,FALSE) additive "
        "FROM read_parquet(?) WHERE census_year IN (2002,2010,2021)", [str(SELECTED)]
    ).fetchdf()
    ids = obs.source_record_id.astype(str)
    uf = UnionFind(ids)
    years = {str(sid): {int(year)} for sid, year in obs[["source_record_id", "yr"]].itertuples(index=False, name=None)}

    def union(a: str, b: str) -> str:
        a, b = uf.find(str(a)), uf.find(str(b))
        if a == b:
            return "redundant"
        merged = years[a] | years[b]
        if len(merged) < len(years[a]) + len(years[b]):
            return "conflict"
        uf.union(a, b)
        root = uf.find(a)
        other = b if root == a else a
        years[root] = merged
        years.pop(other, None)
        return "merged"

    for a, b in con.execute(
        "SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) "
        "WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))",
        [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
    ).fetchall():
        if union(a, b) == "conflict":
            raise ValueError(f"Conflict in accepted base graph: {a}, {b}")

    edge_batches = [
        (PROXIMITY, "from_source_record_id", "to_source_record_id"),
        (BASE / "accepted_identity_edge_delta.csv", "from_id", "to_id"),
        (BASE / "top60_identity_edge_delta.csv", "from_id", "to_id"),
        (CODE / "accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
        (HCLASS / "accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ]
    for path, a_col, b_col in edge_batches:
        frame = pd.read_csv(path)
        for a, b in frame[[a_col, b_col]].itertuples(index=False, name=None):
            if union(a, b) == "conflict":
                raise ValueError(f"Conflict in previously accepted delta {path}: {a}, {b}")

    point_ids = set(map(str, con.execute(
        "SELECT target_source_record_id FROM read_parquet(?) "
        "WHERE coordinate_admission_status IN (SELECT UNNEST(?))",
        [str(POINTS), sorted(ACCEPTED_COORDINATE_STATUSES)],
    ).fetchnumpy()["target_source_record_id"]))
    point_delta_paths = [
        BASE / "top60_point_use_delta.csv", CODE / "old_point_use_delta.csv",
        HIST / "accepted_point_use_delta.csv", HCLASS / "accepted_retrospective_point_use_delta.csv",
        SHARED / "accepted_shared_locality_point_uses.csv",
    ]
    for path in point_delta_paths:
        point_ids.update(pd.read_csv(path).target_source_record_id.astype(str))

    point_statuses = ",".join("'" + x.replace("'", "''") + "'" for x in ACCEPTED_COORDINATE_STATUSES)
    con.execute(
        f"CREATE TEMP VIEW unique_points AS SELECT id,ANY_VALUE(lat) lat,ANY_VALUE(lon) lon "
        f"FROM (SELECT DISTINCT target_source_record_id id,latitude lat,longitude lon FROM read_parquet('{POINTS}') "
        f"WHERE coordinate_admission_status IN ({point_statuses})) GROUP BY id HAVING COUNT(*)=1"
    )
    con.execute(
        f"CREATE TEMP VIEW selected AS SELECT source_record_id id,CAST(census_year AS INTEGER) yr,name_norm n,"
        f"type_norm t,region_norm r,COALESCE(population,0)::DOUBLE pop FROM read_parquet('{SELECTED}') "
        "WHERE census_year IN (2002,2010,2021) AND COALESCE(is_additive_settlement_record,FALSE) "
        "AND COALESCE(name_norm,'')!='' AND COALESCE(region_norm,'')!=''"
    )
    con.execute(
        "CREATE TEMP VIEW collision_ids AS SELECT s.id FROM selected s JOIN unique_points p ON p.id=s.id "
        "QUALIFY COUNT(*) OVER(PARTITION BY s.yr,p.lat,p.lon)>1"
    )

    candidate_frames = []
    pair_summary = {}
    for ya, yb in [(2002, 2010), (2010, 2021), (2002, 2021)]:
        sql = f"""WITH a AS (SELECT *,COUNT(*) OVER(PARTITION BY n,r) nk FROM selected WHERE yr={ya}),
        b AS (SELECT *,COUNT(*) OVER(PARTITION BY n,r) nk FROM selected WHERE yr={yb}),
        raw AS (SELECT a.id aid,b.id bid,a.pop ap,b.pop bp,a.t atype,b.t btype,a.n name_norm,a.r region_norm,
        x.lat alat,x.lon alon,y.lat blat,y.lon blon
        FROM a JOIN b USING(n,r) LEFT JOIN unique_points x ON x.id=a.id LEFT JOIN unique_points y ON y.id=b.id
        WHERE a.nk=1 AND b.nk=1 AND (x.id IS NOT NULL OR y.id IS NOT NULL)
        AND a.id NOT IN (SELECT id FROM collision_ids) AND b.id NOT IN (SELECT id FROM collision_ids)),
        measured AS (SELECT *,CASE WHEN alat IS NOT NULL AND blat IS NOT NULL THEN
        111320*SQRT(POWER(alat-blat,2)+POWER((alon-blon)*COS(RADIANS((alat+blat)/2)),2)) END distance_m FROM raw)
        SELECT * FROM measured"""
        all_pairs = con.execute(sql).fetchdf()
        too_far = int((all_pairs.distance_m > 5000).sum())
        minimum = all_pairs[["ap", "bp"]].min(axis=1)
        ratio = all_pairs[["ap", "bp"]].max(axis=1).div(minimum.where(minimum > 0))
        eligible = all_pairs[all_pairs.distance_m.isna() | (all_pairs.distance_m <= 5000)].copy()
        eligible["from_year"] = ya
        eligible["to_year"] = yb
        candidate_frames.append(eligible)
        pair_summary[f"{ya}-{yb}"] = {
            "unique_name_region_rows_with_a_point": int(len(all_pairs)),
            "both_point_distance_over_5km": too_far,
            "population_ratio_over_2_flagged_not_blocked": int((ratio > 2).sum()),
            "zero_or_nonpositive_population_endpoint": int((minimum <= 0).sum()),
            "rule_eligible_before_graph_replay": int(len(eligible)),
        }
    candidates = pd.concat(candidate_frames, ignore_index=True)

    accepted = []
    outcomes = Counter()
    for ya, yb in [(2002, 2010), (2010, 2021), (2002, 2021)]:
        block = candidates[(candidates.from_year == ya) & (candidates.to_year == yb)]
        block = block.sort_values(["ap", "bp"], ascending=False)
        for row in block.itertuples(index=False):
            status = union(row.aid, row.bid)
            outcomes[f"{ya}-{yb}:{status}"] += 1
            if status != "merged":
                continue
            ratio = max(row.ap, row.bp) / min(row.ap, row.bp) if min(row.ap, row.bp) > 0 else None
            accepted.append({
                "from_source_record_id": row.aid, "from_year": ya,
                "to_source_record_id": row.bid, "to_year": yb, "relation": "same_place",
                "name_norm": row.name_norm, "region_norm": row.region_norm,
                "from_type_norm": row.atype, "to_type_norm": row.btype,
                "from_population_raw": int(row.ap), "to_population_raw": int(row.bp),
                "population_ratio_max_over_min": "" if ratio is None else ratio,
                "population_comparability": "not_assessed_zero_or_nonpositive_endpoint" if ratio is None else ("not_asserted_outlier_requires_scope_review" if ratio > 2 else "not_asserted"),
                "distance_m_if_both_points": "" if pd.isna(row.distance_m) else row.distance_m,
                "from_point_available": not pd.isna(row.alat), "to_point_available": not pd.isna(row.blat),
                "identity_rule": "exact_normalized_name_region_unique_within_each_year; type change allowed; if both accepted points, distance<=5km; if one point, inherit along accepted identity; population ratio is a separate comparability flag, not an identity gate; no same-year point collision; no duplicate-year graph conflict",
                "evidence_uri": "selected_observations.parquet + accepted point ledger; see application receipt",
                "decision_status": "checked_rule_accepted",
            })

    accepted_df = pd.DataFrame(accepted)
    accepted_df.to_csv(OUT / "accepted_identity_edge_delta.csv", index=False)

    # Point inheritance is an explicit historical use of a reviewed carrier point.
    point_rows = con.execute(
        "SELECT target_source_record_id,latitude,longitude,coordinate_source,coordinate_source_file,"
        "coordinate_source_sha256,coordinate_source_locator,coordinate_admission_status,coordinate_measurement_date_unknown "
        "FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))",
        [str(POINTS), sorted(ACCEPTED_COORDINATE_STATUSES)],
    ).fetchdf()
    point_rows = point_rows.drop_duplicates(["target_source_record_id", "latitude", "longitude"])
    carrier = {str(row.target_source_record_id): row._asdict() for row in point_rows.itertuples(index=False)}
    info = obs.set_index("source_record_id").to_dict("index")
    inherited = []
    for row in accepted:
        a, b = row["from_source_record_id"], row["to_source_record_id"]
        for recipient, donor in [(a, b), (b, a)]:
            if recipient in point_ids or donor not in carrier:
                continue
            p = carrier[donor]
            inherited.append({
                "target_source_record_id": recipient,
                "target_year": int(info[recipient]["yr"]),
                "target_name": info[recipient]["settlement_name"],
                "target_type": info[recipient]["settlement_type"],
                "target_region": info[recipient]["region_norm"],
                "target_population": info[recipient]["population"],
                "latitude": p["latitude"], "longitude": p["longitude"],
                "carrier_source_record_id": donor,
                "carrier_year": int(info[donor]["yr"]),
                "coordinate_source": p["coordinate_source"],
                "coordinate_source_file": p["coordinate_source_file"],
                "coordinate_source_sha256": p["coordinate_source_sha256"],
                "coordinate_source_locator": p["coordinate_source_locator"],
                "coordinate_admission_status": "reviewed_rule_accepted",
                "coordinate_application_family": "same_place_unique_name_region_retrospective_point_inheritance_20261005",
                "measurement_date_unknown": True,
                "provider_identifier_binding_asserted": False,
                "population_value_changed": False,
                "boundary_comparability_asserted": False,
            })
            point_ids.add(recipient)
    inherited_df = pd.DataFrame(inherited).drop_duplicates("target_source_record_id")
    existing_coordinate_keys = set()
    for point in point_rows.itertuples(index=False):
        year = info.get(str(point.target_source_record_id), {}).get("yr")
        if year is not None:
            existing_coordinate_keys.add((int(year), float(point.latitude), float(point.longitude)))
    for path in point_delta_paths:
        prior = pd.read_csv(path)
        if {"target_source_record_id", "latitude", "longitude"}.issubset(prior.columns):
            for point in prior.itertuples(index=False):
                year = info.get(str(point.target_source_record_id), {}).get("yr")
                if year is not None and pd.notna(point.latitude) and pd.notna(point.longitude):
                    existing_coordinate_keys.add((int(year), float(point.latitude), float(point.longitude)))
    new_keys = []
    for point in inherited_df.itertuples(index=False):
        year = int(point.target_year)
        key = (year, float(point.latitude), float(point.longitude))
        if key in existing_coordinate_keys or key in new_keys:
            raise ValueError(f"Point inheritance creates a same-year coordinate collision: {point.target_source_record_id}")
        new_keys.append(key)
    inherited_df.to_csv(OUT / "accepted_point_use_delta.csv", index=False)

    receipt = {
        "status": "applied_after_full_graph_replay_no_same_year_conflicts",
        "rule": "exact normalized name and region; exactly one row for that key in each paired year; type changes permitted; at least one endpoint has a reviewed point; if both do, distance<=5km; population ratio is recorded as a separate comparability flag, not an identity gate; candidates colliding with another same-year point held; accepted graph union cannot create duplicate years. Point inheritance uses the reviewed carrier coordinate and does not claim census-date measurement or boundary/population comparability.",
        "candidate_counts_by_year_pair": pair_summary,
        "candidate_rows_after_distance_and_population_filter": int(len(candidates)),
        "accepted_edges": len(accepted),
        "accepted_point_uses_inherited": len(inherited),
        "accepted_type_changes": int(sum(x["from_type_norm"] != x["to_type_norm"] for x in accepted)),
        "accepted_edges_population_ratio_over_2_flagged": int(sum(float(x["population_ratio_max_over_min"]) > 2 for x in accepted if x["population_ratio_max_over_min"] not in ("", None))),
        "accepted_edges_with_zero_or_nonpositive_population": int(sum(x["population_ratio_max_over_min"] in ("", None) for x in accepted)),
        "accepted_edges_population_ratio_over_20_flagged": int(sum(float(x["population_ratio_max_over_min"]) > 20 for x in accepted if x["population_ratio_max_over_min"] not in ("", None))),
        "same_year_coordinate_collisions_created_by_point_inheritance": 0,
        "outcomes_after_graph_replay": dict(outcomes),
        "population_values_modified": False,
        "population_comparability_asserted": False,
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SELECTED, EDGES, POINTS, PROXIMITY, BASELINE]},
        "scope_note": "This is a linkage and coordinate-use delta, not a replacement for existing data. Full national/event-aware coverage remains to be recalculated with the new explicit deltas.",
    }
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Уникальное точное имя и регион: массовые связи и перенос точки\n\n"
        "Пакет принимает связь, когда нормализованные имя и регион совпадают точно и для этого ключа есть ровно одна исходная строка в каждом из двух лет. Тип НП может меняться. Для двух существующих принятых точек расстояние должно быть не больше 5 км; когда точка принята лишь для одного конца, она переносится на другой по принятой связи тождества. Отношение численностей записывается как отдельный флаг и не блокирует тождество; оно не подтверждает сопоставимость. Повторные точки одного года и компоненты с повтором года исключаются. Численность не изменена.\n\n"
        "`accepted_identity_edge_delta.csv` и `accepted_point_use_delta.csv` содержат новые решения; `application_receipt.json` фиксирует объём кандидатов и входные SHA-256.\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
