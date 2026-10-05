#!/usr/bin/env python3
"""Read-only Graph29 audit of coordinate uniqueness and proximity/name linkage.

The exact-name experiment profiles candidates, including graph circularity and
same-year competitors. It never admits points or edges. Source rows, accepted
point uses and graph components are distinct units throughout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import duckdb
import numpy as np
from scipy.spatial import cKDTree

from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind

REPO = Path(__file__).resolve().parents[2]
INPUTS = {
    "selected": Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet"),
    "points": Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet"),
    "edges": Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet"),
    "raw2021": Path("/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet"),
    "historical_objects": Path("/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet"),
    "anapa_reviewed_points": REPO / "research_rebuild/evidence/mass_joint_20261004/graph24_anapa_four_localities/approved_points.csv",
    "prior_current_point_review": REPO / "research_rebuild/evidence/mass_joint_20261004/graph16_points_and_large_paths/current_point_review_review_summary.json",
    "prior_current_point_eligible_rows": Path("/workspace/settlements-work/continuation_20261004/independent_review/current_point4984_review_v1/eligible_candidate_rows.csv"),
    "prior_current_point_review_code": Path("/workspace/settlements-work/continuation_20261004/independent_review/current_point4984_review_v1/independent_replay.py"),
}
EXPECTED = {
    "selected": "4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657",
    "points": "c4b6a79741c36bbc092d4f2390bd743dd55b982fc9c671f1d1ed6660b7f4f8e3",
    "edges": "583364c80cddc4fbed00dd06527f734242b1983c268f83a78a38946a811ede1d",
    "raw2021": "86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14",
}
R = 6371008.8


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def records(con, query):
    result = con.execute(query)
    fields = [x[0] for x in result.description]
    return [dict(zip(fields, row)) for row in result.fetchall()]


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def distance(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    v = math.sin((a - b) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon1 - lon2) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1, v)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        raise FileExistsError("Use a new output directory; reviewed outputs are immutable")
    started = time.monotonic()
    before = {key: {"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size} for key, p in INPUTS.items()}
    for key, expected in EXPECTED.items():
        if before[key]["sha256"] != expected:
            raise ValueError(f"Unexpected frozen input: {key}")
    out.mkdir(parents=True)
    con = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    for key in ("selected", "points", "edges", "raw2021", "historical_objects"):
        con.read_parquet(str(INPUTS[key])).create_view(key)
    point_sql = ",".join("'" + x + "'" for x in sorted(ACCEPTED_COORDINATE_STATUSES))
    edge_sql = ",".join("'" + x + "'" for x in sorted(ACCEPTED_EDGE_STATUSES))
    con.execute(f"CREATE VIEW allowed_points AS SELECT * FROM points WHERE coordinate_admission_status IN ({point_sql})")
    ids_years = con.execute("SELECT source_record_id,census_year FROM selected").fetchall()
    ids = [sid for sid, year in ids_years]
    if len(ids) != len(set(ids)):
        raise ValueError("Non-unique census source IDs")
    uf = UnionFind(ids)
    edges = con.execute(f"SELECT from_source_record_id,to_source_record_id FROM edges WHERE relation='same_place' AND decision_status IN ({edge_sql})").fetchall()
    for a, b in edges:
        if a not in uf.parent or b not in uf.parent:
            raise ValueError("Graph endpoint missing from selected source records")
        uf.union(a, b)
    roots = {sid: uf.find(sid) for sid in ids}
    root_years = defaultdict(list)
    for sid, year in ids_years:
        root_years[roots[sid]].append(year)
    masks = {root: sum(1 << (2002, 2010, 2021).index(y) for y in set(years)) for root, years in root_years.items()}
    # Register only narrow graph fields. The component join covers the full graph,
    # including intermediate endpoints outside a candidate subset.
    import pandas as pd
    components = pd.DataFrame({"source_record_id": ids, "component_root": [roots[s] for s in ids], "year_mask": [masks[roots[s]] for s in ids]})
    con.register("components", components)
    con.execute("""CREATE TEMP TABLE accepted AS
        SELECT s.source_record_id,s.census_year,s.settlement_name,s.settlement_type,
        s.name_norm,s.type_norm,s.region_norm,s.population,s.source_native_id,s.fias_id,
        s.population_scope,s.entity_grain_status,g.component_root,g.year_mask,
        p.latitude,p.longitude,p.coordinate_source,p.coordinate_provider,p.coordinate_admission_status,
        p.coordinate_application_family,p.application_inference_kind,p.coordinate_provenance,
        p.coordinate_measurement_date_unknown,p.direct_historical_coordinate_measurement,
        p.point_origin_file,p.point_origin_sha256,p.point_origin_locator,
        (coalesce(p.application_inference_kind,'') LIKE '%retrospective%'
          OR p.application_inference_kind='sourced_representative_point_reuse_across_accepted_observed_years') explicit_reuse
        FROM selected s JOIN allowed_points p ON p.target_source_record_id=s.source_record_id
        JOIN components g ON g.source_record_id=s.source_record_id""")
    cardinality = records(con, """SELECT (SELECT count(*) FROM selected) selected_rows,
        (SELECT count(*) FROM allowed_points) point_uses,
        (SELECT count(distinct target_source_record_id) FROM allowed_points) unique_point_targets,
        (SELECT count(*) FROM accepted) matched_point_uses,
        (SELECT count(*) FROM allowed_points WHERE NOT (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)) invalid_wgs84,
        (SELECT count(*) FROM selected s JOIN allowed_points p ON s.source_record_id=p.target_source_record_id WHERE try_cast(p.target_year AS INT)!=s.census_year) target_year_mismatches""")[0]
    if cardinality["matched_point_uses"] != cardinality["point_uses"] or cardinality["point_uses"] != cardinality["unique_point_targets"]:
        raise ValueError("Point targets are orphaned or repeated")
    year_profile = records(con, """SELECT census_year,count(*) accepted_point_rows,sum(population) selected_population,
        count(*) FILTER(WHERE coordinate_measurement_date_unknown) unknown_measurement_date,
        count(*) FILTER(WHERE direct_historical_coordinate_measurement) direct_historical_measurement,
        count(*) FILTER(WHERE explicit_reuse) explicit_retrospective_or_accepted_path_reuse_rows,
        sum(population) FILTER(WHERE explicit_reuse) explicit_reuse_population FROM accepted GROUP BY 1 ORDER BY 1""")
    origin_profile = records(con, "SELECT census_year,coordinate_source,coordinate_application_family,application_inference_kind,count(*) row_count,sum(population) selected_population FROM accepted GROUP BY ALL ORDER BY 1,5 DESC")
    write_csv(out / "accepted_point_origin_profile.csv", origin_profile)
    con.execute("""CREATE TEMP TABLE collisions AS SELECT census_year,latitude,longitude,count(*) record_count,
        sum(population) selected_population,count(*) FILTER(WHERE population>0) positive_records,
        count(distinct name_norm) distinct_names,count(distinct (name_norm,type_norm)) distinct_typed_names,
        count(distinct source_native_id) distinct_source_native_ids,count(distinct component_root) distinct_components
        FROM accepted GROUP BY 1,2,3 HAVING count(*)>1""")
    collision_summary = records(con, """SELECT census_year,count(*) collision_groups,sum(record_count) affected_rows,
        sum(selected_population) selected_population,max(record_count) max_group_size,
        count(*) FILTER(WHERE distinct_names>1) different_name_groups,
        count(*) FILTER(WHERE distinct_typed_names=1) identical_name_and_type_groups,
        count(*) FILTER(WHERE distinct_source_native_ids>1) different_source_native_id_groups,
        count(*) FILTER(WHERE positive_records>1) multiple_positive_population_groups,
        count(*) FILTER(WHERE distinct_components>1) different_graph_component_groups
        FROM collisions GROUP BY 1 ORDER BY 1""")
    collision_rows = records(con, """SELECT a.census_year,a.source_record_id,a.settlement_name,a.settlement_type,a.region_norm,
        a.source_native_id,a.fias_id,a.population,a.population_scope,a.entity_grain_status,a.latitude,a.longitude,
        a.coordinate_source,a.coordinate_admission_status,a.coordinate_application_family,a.coordinate_provenance,
        a.component_root,c.record_count,c.distinct_names,c.distinct_typed_names
        FROM accepted a JOIN collisions c USING(census_year,latitude,longitude)
        ORDER BY a.census_year,c.selected_population DESC,a.source_record_id""")
    write_csv(out / "accepted_same_year_collision_records.csv", collision_rows)
    # The prior replay compared new candidates to Graph15 accepted points, but
    # did not exclude coordinate sharing among candidates in the same batch.
    with INPUTS["prior_current_point_eligible_rows"].open(encoding="utf-8-sig",newline="") as f:
        prior_candidates = list(csv.DictReader(f))
    prior_groups = defaultdict(list)
    for row in prior_candidates:
        prior_groups[(float(row["candidate_latitude"]),float(row["candidate_longitude"]))].append(row)
    prior_shared = [g for g in prior_groups.values() if len(g)>1]
    prior_ids = {r["source_record_id"] for r in prior_candidates}
    current_from_prior = [r for r in collision_rows if r["census_year"]==2021 and r["source_record_id"] in prior_ids]
    prior_batch_summary = {"eligible_rows":len(prior_candidates),"internal_exact_point_collision_groups":len(prior_shared),
        "affected_rows":sum(map(len,prior_shared)),"affected_selected_population":sum(float(r["population"]) for g in prior_shared for r in g),
        "different_literal_name_groups":sum(len({r["settlement_name"] for r in g})>1 for g in prior_shared),
        "max_group_size":max(map(len,prior_shared)),"same_cohort_current_collision_rows":len(current_from_prior),
        "same_cohort_current_collision_population":sum(r["population"] or 0 for r in current_from_prior),
        "prior_review_compared_to_existing_graph15_points_only":True,
        "interpretation":"Internal batch sharing was omitted from the collision hold; source replay and FIAS level alone do not establish point accuracy."}
    # Independent Python grouping readback: includes same-year collisions only.
    point_rows = records(con, "SELECT * FROM accepted ORDER BY source_record_id")
    independent_groups = defaultdict(list)
    for row in point_rows:
        independent_groups[(row["census_year"], row["latitude"], row["longitude"])].append(row)
    for summary in collision_summary:
        groups = [g for k, g in independent_groups.items() if k[0] == summary["census_year"] and len(g) > 1]
        assert len(groups) == summary["collision_groups"]
        assert sum(map(len, groups)) == summary["affected_rows"]
        assert sum(r["population"] or 0 for g in groups for r in g) == summary["selected_population"]
    con.execute("CREATE TEMP TABLE raw_indexed AS SELECT row_number() OVER() raw_row_1based,* FROM raw2021")
    con.execute("""CREATE TEMP TABLE raw_selected AS SELECT s.source_record_id,s.settlement_name,s.settlement_type,
        s.name_norm,s.type_norm,s.region_norm,s.population selected_population,s.source_native_id,
        r.object_level,r.object_name,r.oktmo raw_oktmo,r.mun_upper,r.mun_lower,r.settlement_dadata,
        r.fias_level_dadata,r.settlement_fias_id_dadata,r.qc_geo_dadata,r.latitude_dadata latitude,r.longitude_dadata longitude,
        try_cast(r.population AS DOUBLE) raw_population,r.raw_row_1based
        FROM selected s JOIN raw_indexed r ON r.raw_row_1based=try_cast(regexp_extract(s.source_record_id,':parquet:([0-9]+)$',1) AS INT)
        WHERE s.census_year=2021""")
    raw_integrity = records(con, "SELECT count(*) selected_raw_rows,count(*) FILTER(WHERE selected_population IS DISTINCT FROM raw_population) population_mismatches,count(*) FILTER(WHERE latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180) valid_source_points FROM raw_selected")[0]
    if raw_integrity["selected_raw_rows"] != sum(y == 2021 for _, y in ids_years) or raw_integrity["population_mismatches"]:
        raise ValueError("Raw source row-index binding failed")
    con.execute("""CREATE TEMP TABLE raw_collisions AS SELECT latitude,longitude,count(*) record_count,
        sum(selected_population) selected_population,count(distinct name_norm) distinct_names,
        count(distinct (name_norm,type_norm)) distinct_typed_names,count(distinct source_native_id) distinct_native_codes
        FROM raw_selected WHERE latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180
        GROUP BY 1,2 HAVING count(*)>1""")
    raw_summary = records(con, """SELECT count(*) collision_groups,sum(record_count) affected_rows,
        sum(selected_population) selected_population,max(record_count) max_group_size,
        count(*) FILTER(WHERE distinct_names>1) different_name_groups,
        count(*) FILTER(WHERE distinct_typed_names=1) identical_name_and_type_groups,
        count(*) FILTER(WHERE distinct_native_codes>1) different_native_code_groups FROM raw_collisions""")[0]
    write_csv(out / "raw2021_same_point_records.csv", records(con, """SELECT r.*,c.record_count,c.distinct_names,c.distinct_typed_names,
        (p.target_source_record_id IS NOT NULL) current_point_use_exists,
        p.latitude accepted_latitude,p.longitude accepted_longitude,p.coordinate_source accepted_point_source,
        (r.latitude=p.latitude AND r.longitude=p.longitude) raw_point_equals_accepted_point
        FROM raw_selected r JOIN raw_collisions c USING(latitude,longitude)
        LEFT JOIN allowed_points p ON p.target_source_record_id=r.source_record_id
        ORDER BY c.record_count DESC,r.source_record_id"""))
    raw_qc = records(con, "SELECT qc_geo_dadata,fias_level_dadata,count(*) row_count,sum(r.selected_population) selected_population FROM raw_selected r JOIN raw_collisions c USING(latitude,longitude) GROUP BY 1,2 ORDER BY 3 DESC")
    historical_summary = records(con, """WITH h AS (SELECT * FROM historical_objects WHERE is_settlement_raw
        AND historical_name_exact AND historical_type_exact AND NOT coalesce(is_deleted,false)
        AND latitude_from_lat BETWEEN -90 AND 90 AND longitude_from_long BETWEEN -180 AND 180),
        g AS (SELECT latitude_from_lat,longitude_from_long,count(distinct historical_okato_2011_raw) code_count
        FROM h GROUP BY 1,2 HAVING count(distinct historical_okato_2011_raw)>1)
        SELECT (SELECT count(*) FROM h) historical_named_rows,(SELECT count(distinct historical_okato_2011_raw) FROM h) named_codes,
        (SELECT count(*) FROM g) collision_groups,(SELECT sum(code_count) FROM g) codes_in_collision,
        (SELECT max(code_count) FROM g) max_group_codes""")[0]
    # Exact normalized name+type+region is stronger than a generic fuzzy-name rule.
    # Reusing an accepted path's point cannot independently verify that path.
    con.execute(f"""CREATE TEMP TABLE candidate_pairs AS WITH d AS (
        SELECT a.census_year from_year,b.census_year to_year,a.source_record_id from_id,b.source_record_id to_id,
        a.settlement_name,a.settlement_type,a.region_norm,a.population from_population,b.population to_population,
        a.component_root=b.component_root already_connected,
        a.component_root!=b.component_root AND (a.year_mask & b.year_mask)>0 component_year_overlap,
        a.explicit_reuse OR b.explicit_reuse either_point_reused_by_continuity,
        a.point_origin_file IS NOT NULL AND a.point_origin_locator IS NOT NULL
        AND a.point_origin_file=b.point_origin_file AND a.point_origin_sha256=b.point_origin_sha256
        AND a.point_origin_locator=b.point_origin_locator same_recorded_coordinate_origin,
        {2*R}*asin(sqrt(least(1.0,pow(sin(radians(a.latitude-b.latitude)/2),2)
        +cos(radians(a.latitude))*cos(radians(b.latitude))*pow(sin(radians(a.longitude-b.longitude)/2),2)))) distance_m
        FROM accepted a JOIN accepted b ON a.census_year<b.census_year AND a.region_norm=b.region_norm
        AND a.name_norm=b.name_norm AND a.type_norm=b.type_norm
        WHERE coalesce(a.name_norm,'')!='' AND coalesce(a.type_norm,'')!='' AND abs(a.latitude-b.latitude)<0.046)
        SELECT * FROM d WHERE distance_m<=5000""")
    cross_year = []
    for radius in (0.001, 100, 1000, 5000):
        # One millimetre is a numerical-equality tolerance, not asserted accuracy.
        query = f"""WITH d AS (SELECT *,count(*) OVER(PARTITION BY from_year,to_year,from_id) left_degree,
            count(*) OVER(PARTITION BY from_year,to_year,to_id) right_degree FROM candidate_pairs WHERE distance_m<={radius})
            SELECT from_year,to_year,CAST({radius} AS DOUBLE) radius_m,count(*) candidate_pairs,
            count(*) FILTER(WHERE already_connected) already_connected_pairs,
            count(*) FILTER(WHERE component_year_overlap) ordinary_one_to_one_year_conflict_pairs,
            count(*) FILTER(WHERE NOT already_connected AND NOT component_year_overlap) new_component_compatible_candidates,
            count(*) FILTER(WHERE left_degree=1 AND right_degree=1) reciprocal_unique_pairs,
            count(*) FILTER(WHERE left_degree=1 AND right_degree=1 AND NOT already_connected AND NOT component_year_overlap) new_reciprocal_unique_compatible_candidates,
            count(*) FILTER(WHERE either_point_reused_by_continuity) continuity_dependent_pairs,
            count(*) FILTER(WHERE same_recorded_coordinate_origin) same_origin_pairs
            FROM d GROUP BY 1,2 ORDER BY 1,2"""
        cross_year.extend(records(con, query))
    write_csv(out / "exact_name_proximity_experiment.csv", cross_year)
    write_csv(out / "new_pair_candidates_top100.csv", records(con, """SELECT * FROM candidate_pairs WHERE NOT already_connected
        ORDER BY component_year_overlap,from_population+to_population DESC,from_id,to_id LIMIT 100"""))
    new_pairs = records(con, """SELECT d.*,
        a.latitude from_latitude,a.longitude from_longitude,a.coordinate_source from_point_source,
        b.latitude to_latitude,b.longitude to_longitude,b.coordinate_source to_point_source,
        ca.record_count IS NOT NULL from_same_year_point_collision,
        cb.record_count IS NOT NULL to_same_year_point_collision
        FROM candidate_pairs d JOIN accepted a ON a.source_record_id=d.from_id
        JOIN accepted b ON b.source_record_id=d.to_id
        LEFT JOIN collisions ca ON ca.census_year=a.census_year AND ca.latitude=a.latitude AND ca.longitude=a.longitude
        LEFT JOIN collisions cb ON cb.census_year=b.census_year AND cb.latitude=b.latitude AND cb.longitude=b.longitude
        WHERE distance_m<=1000 AND NOT already_connected AND NOT component_year_overlap
        ORDER BY from_year,to_year,from_id,to_id""")
    write_csv(out / "new_component_compatible_pairs_within1km.csv",new_pairs)
    new_endpoint_ids = {r[k] for r in new_pairs for k in ("from_id","to_id")}
    population_by_id = {r["source_record_id"]:(r["census_year"],r["population"] or 0) for r in point_rows}
    endpoint_summary = [{"year":year,"distinct_endpoint_records":sum(population_by_id[s][0]==year for s in new_endpoint_ids),
        "selected_endpoint_population_not_gain":sum(population_by_id[s][1] for s in new_endpoint_ids if population_by_id[s][0]==year)} for year in (2002,2010,2021)]
    simulation = UnionFind(set(roots.values()))
    for r in new_pairs:simulation.union(roots[r["from_id"]],roots[r["to_id"]])
    simulated_years=defaultdict(list)
    for root,years in root_years.items():simulated_years[simulation.find(root)].extend(years)
    batch_preflight = {"candidate_pairs":len(new_pairs),"ordinary_graph_components_with_duplicate_years_after_simulated_batch":sum(len(ys)!=len(set(ys)) for ys in simulated_years.values()),
        "pairs_with_same_year_coordinate_sharing_at_either_endpoint":sum(r["from_same_year_point_collision"] or r["to_same_year_point_collision"] for r in new_pairs),
        "unique_endpoint_summary":endpoint_summary,"admissions":0,"known_events_and_source_hold_review_performed":False}
    # Same-year examples show that unique points still permit close similar names.
    current = [r for r in point_rows if r["census_year"] == 2021]
    lat = np.radians([r["latitude"] for r in current]); lon = np.radians([r["longitude"] for r in current])
    xyz = np.column_stack((np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)))
    nearby = cKDTree(xyz).query_pairs(2*math.sin(3000/(2*R)), output_type="ndarray")
    counts = Counter(); fuzzy_examples = []; exact_name_examples = []
    qualifier_pairs = [("большой","малый"),("большая","малая"),("большие","малые"),("верхний","нижний"),
                       ("верхняя","нижняя"),("верхнее","нижнее"),("верхние","нижние"),("новый","старый"),
                       ("новая","старая"),("новое","старое"),("новые","старые")]
    for i, j in nearby:
        a, b = current[i], current[j]
        if a["region_norm"] != b["region_norm"] or a["type_norm"] != b["type_norm"]:
            continue
        dm = 2*R*math.asin(min(1,float(np.linalg.norm(xyz[i]-xyz[j]))/2))
        if a["name_norm"] == b["name_norm"]:
            counts["exact_name_same_type_pairs_within_3km"] += 1
            if dm<=0.001: counts["exact_name_same_type_pairs_same_point"] += 1
            elif dm<=1000: counts["exact_name_same_type_distinct_point_pairs_within_1km"] += 1
            if 0.001<dm<=1000:
                exact_name_examples.append({"from_id":a["source_record_id"],"to_id":b["source_record_id"],"region":a["region_norm"],
                    "name":a["settlement_name"],"type":a["settlement_type"],"from_native_code":a["source_native_id"],"to_native_code":b["source_native_id"],
                    "from_population":a["population"],"to_population":b["population"],"distance_m":round(dm,3),
                    "from_point_source":a["coordinate_source"],"to_point_source":b["coordinate_source"]})
            continue
        if dm<=0.001:
            counts["different_name_same_type_pairs_same_point"] += 1
            continue
        na, nb = a["name_norm"] or "", b["name_norm"] or ""
        ratio = SequenceMatcher(None,na,nb,autojunk=False).ratio()
        ta,tb=set(na.split()),set(nb.split())
        qualifier_conflict = any((x in ta and y in tb) or (y in ta and x in tb) for x,y in qualifier_pairs)
        if ratio>=0.85:
            counts["different_name_same_type_fuzzy85_distinct_point_pairs_within_3km"] += 1
            if dm<=1000:counts["different_name_same_type_fuzzy85_distinct_point_pairs_within_1km"] += 1
        if ratio>=0.85 or (qualifier_conflict and ratio>=0.65):
            counts["diagnostic_near_fuzzy_or_qualifier_pairs"] += 1
            fuzzy_examples.append({"from_id":a["source_record_id"],"to_id":b["source_record_id"],"region":a["region_norm"],
                "from_name":a["settlement_name"],"to_name":b["settlement_name"],"type":a["settlement_type"],
                "from_native_code":a["source_native_id"],"to_native_code":b["source_native_id"],
                "from_population":a["population"],"to_population":b["population"],"distance_m":round(dm,3),
                "name_sequence_ratio":round(ratio,4),"qualifier_conflict":qualifier_conflict,
                "from_point_source":a["coordinate_source"],"to_point_source":b["coordinate_source"]})
    fuzzy_examples.sort(key=lambda x:(not x["qualifier_conflict"], -min(x["from_population"] or 0,x["to_population"] or 0),x["distance_m"],x["from_id"]))
    qualifier_examples=[r for r in fuzzy_examples if r["qualifier_conflict"]][:50]
    strict_fuzzy_examples=sorted([r for r in fuzzy_examples if r["name_sequence_ratio"]>=0.85],key=lambda x:(x["distance_m"],-min(x["from_population"] or 0,x["to_population"] or 0)))[:50]
    example_by_pair={(r["from_id"],r["to_id"]):r for r in qualifier_examples+strict_fuzzy_examples}
    write_csv(out / "same_year_similar_name_distinct_point_examples.csv",list(example_by_pair.values()))
    exact_name_examples.sort(key=lambda x:(-min(x["from_population"] or 0,x["to_population"] or 0),x["distance_m"],x["from_id"]))
    write_csv(out / "same_year_identical_name_distinct_point_examples.csv",exact_name_examples[:50])
    # Four previously reviewed physical coordinates demonstrate a genuine city
    # fallback in the raw data, not merely a possible same-coordinate anomaly.
    selected_by_id = {r["source_record_id"]:r for r in records(con,"SELECT * FROM raw_selected")}
    anapa_examples = []
    with INPUTS["anapa_reviewed_points"].open(encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            original = selected_by_id[r["target_source_record_id"]]
            la,lo=float(r["latitude"]),float(r["longitude"])
            anapa_examples.append({"source_record_id":r["target_source_record_id"],"name":original["settlement_name"],
                "population":original["selected_population"],"raw_latitude":original["latitude"],"raw_longitude":original["longitude"],
                "reviewed_latitude":la,"reviewed_longitude":lo,"distance_from_raw_point_km":round(distance(original["latitude"],original["longitude"],la,lo)/1000,3),
                "reviewed_origin_locator":r["origin_locator"],"reviewed_origin_sha256":r["origin_sha256"]})
    write_csv(out / "anapa_verified_fallback_examples.csv", anapa_examples)
    for key,p in INPUTS.items():
        if sha(p)!=before[key]["sha256"]: raise ValueError(f"Input mutated during audit: {key}")
    output_hashes = {p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(out.glob("*.csv"))}
    receipt = {"status":"read_only_audit_no_point_or_identity_admissions", "input_files":before,
        "script_sha256":sha(__file__),"status_source_script_sha256":sha(REPO/"research_rebuild/mass_linkage/build_long_table.py"),
        "edge_status_allowlist":sorted(ACCEPTED_EDGE_STATUSES),"point_status_allowlist":sorted(ACCEPTED_COORDINATE_STATUSES),
        "cardinality":cardinality,"accepted_same_place_edges":len(edges),"graph_component_count":len(root_years),
        "graph_components_with_duplicate_years":sum(len(y)!=len(set(y)) for y in root_years.values()),
        "accepted_point_year_profile":year_profile,"accepted_same_year_collisions":collision_summary,
        "raw2021_selected_binding_integrity":raw_integrity,"raw2021_selected_point_collisions":raw_summary,
        "raw_collision_quality_labels":raw_qc,"historical_named_point_collisions":historical_summary,
        "prior_current_point_batch_internal_collision_review":prior_batch_summary,
        "new_pair_batch_preflight":batch_preflight,
        "exact_name_proximity_experiment":cross_year,"same_year_near_name_profile":dict(counts),
        "anapa_verified_examples":anapa_examples,"independent_sql_python_collision_counts_match":True,
        "all_inputs_unchanged":True,"output_files":output_hashes,"elapsed_seconds":round(time.monotonic()-started,3),
        "limitations":["Exact coordinate sharing is an anomaly, not proof that every participating point or identity is wrong.",
            "Affected populations are sums of selected observations, not numbers of incorrectly located people.",
            "Source-native codes are preserved literally; distinct codes alone do not prove distinct physical places.",
            "source_native_id for 2002/2010 can be an opaque publication row identifier, not an official geographic code; the raw 2021 field is native OKTMO.",
            "Exact-name proximity counts are candidate pairs, not accepted links or expected population gain.",
            "Previously accepted connectivity is a comparison baseline, not independent matching ground truth.",
            "Explicit reuse counts rely on recorded inference kinds and are not a complete source-lineage audit.",
            "Same-year nearby pairs are distinct source records, possibly source duplicates; their true identity is not resolved here.",
            "All adopted coordinates are representative-point uses; unknown measurement dates and zero historical-measurement flags preclude asserting exact census-date measurements.",
            "The old coordinate-availability layer is not used as if it contained coordinates."]}
    write_json(out / "receipt.json",receipt)
    print(json.dumps({"out":str(out),"cardinality":cardinality,"accepted_collisions":collision_summary,
                      "raw_collisions":raw_summary,"cross_year":cross_year,"near_name":dict(counts),
                      "elapsed_seconds":receipt["elapsed_seconds"]},ensure_ascii=False))


if __name__=="__main__":
    main()
