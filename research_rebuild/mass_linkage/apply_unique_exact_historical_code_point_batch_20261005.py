#!/usr/bin/env python3
"""Apply the small exact-code/no-collision historical point stratum."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_rebuild/mass_linkage"))
from build_long_table import ACCEPTED_EDGE_STATUSES, UnionFind
OUT = ROOT / "research_rebuild/evidence/unique_exact_historical_code_point_batch_20261005"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
CANDIDATES = Path("/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
GRAPH = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
GEO = Path("/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf")
EDGE_DELTAS = [
    (ROOT / "research_rebuild/evidence/exact_name_proximity_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    (ROOT / "research_rebuild/evidence/unique_name_region_coordinate_bridge_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    (ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/accepted_identity_edge_delta.csv", "from_id", "to_id"),
    (ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/top60_identity_edge_delta.csv", "from_id", "to_id"),
    (ROOT / "research_rebuild/evidence/top100_classifier_bridge_20261005/accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
    (ROOT / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
]
EXPECTED_IDS = {
    "2002:038_218ac665d8_02c_Astraxanskaja.xls:Sheet1:395",
    "2002:022_862ad8a69d_02c_Vologodskaya.xls:2C:5142",
    "2002:045_9dc3ed048e_02c__Udmurtia.xls:Sheet1:1916",
    "2002:070_48ec6f4a77_Irkut_obl_new.xls:Sheet1:1623",
    "2010:008_342f3c208b_16._20Сиб_ФО_2010.xls:Sib:4924",
}
POINT_STATUSES = ["reviewed_rule_accepted", "frozen_r5b_reviewed_baseline_preserved", "reviewed_extension_rule_accepted", "reviewed_case_accepted"]


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Immutable evidence folder already exists: {OUT}")
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    selected = c.execute('SELECT source_record_id,CAST(census_year AS INTEGER) AS "year",settlement_name,settlement_type,region_norm,source_file,source_row,source_sha256,source_locator,okato,population FROM read_parquet(?) WHERE census_year IN (2002,2010)', [str(SELECTED)]).fetchdf()
    current = c.execute("SELECT target_source_record_id FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))", [str(POINTS), POINT_STATUSES]).fetchdf().target_source_record_id.astype(str)
    raw = c.execute("SELECT * FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))", [str(CANDIDATES), sorted(EXPECTED_IDS)]).fetchdf()
    if set(raw.source_record_id.astype(str)) != EXPECTED_IDS:
        raise ValueError("The frozen candidate set is incomplete")
    if set(raw.code_join_basis) != {"exact_raw_code"}:
        raise ValueError("Every candidate must have an exact raw historical-code join")
    raw = raw[(raw.historical_named_point_candidate == True) & (raw.historical_name_exact == True) & (raw.historical_type_exact == True) & (raw.is_additive_settlement_record == True)]
    if set(raw.source_record_id.astype(str)) != EXPECTED_IDS:
        raise ValueError("Candidate stratum includes an ineligible source record")
    if raw.source_record_id.astype(str).duplicated().any():
        raise ValueError("A source ID maps to multiple candidate objects")
    if raw.possible_unlocated_historical_competitor.fillna(False).any():
        raise ValueError("Candidate has an unlocated historical competitor")
    if not raw.latitude_from_lat.between(-90, 90).all() or not raw.longitude_from_long.between(-180, 180).all():
        raise ValueError("Candidate coordinates are outside WGS84 bounds")
    if not raw.historical_okato_2011_raw.astype(str).str.fullmatch(r"\d{11}").all():
        raise ValueError("Expected 11-digit GeoKLADR OKATO values")
    # Reproduce the collision screen across every exact historical named point.
    coll = c.execute("SELECT census_year,latitude_from_lat,longitude_from_long,count(DISTINCT historical_okato_2011_raw) n FROM read_parquet(?) WHERE historical_name_exact AND historical_type_exact AND is_additive_settlement_record AND latitude_from_lat IS NOT NULL AND longitude_from_long IS NOT NULL GROUP BY ALL", [str(CANDIDATES)]).fetchdf()
    collision_map = {(int(r.census_year), float(r.latitude_from_lat), float(r.longitude_from_long)): int(r.n) for r in coll.itertuples(index=False)}
    for r in raw.itertuples(index=False):
        if collision_map.get((int(r.census_year), float(r.latitude_from_lat), float(r.longitude_from_long)), 0) != 1:
            raise ValueError(f"Point collision for {r.source_record_id}")
    selected = selected[selected.source_record_id.isin(EXPECTED_IDS)].copy()
    if len(selected) != len(EXPECTED_IDS) or selected.source_record_id.astype(str).duplicated().any():
        raise ValueError("Selected source row bind is not one-to-one")
    frame = raw.merge(selected, on="source_record_id", suffixes=("_geo", "_selected"), validate="one_to_one")
    if not (frame.census_year.astype(int) == frame.year.astype(int)).all():
        raise ValueError("Selected year does not match historical candidate year")
    if not (frame.name_raw_2011.str.replace(r"^(г|с|пгт|п|д|ст|х|аул)\.?\s+", "", regex=True, case=False).str.strip().str.casefold() == frame.settlement_name_selected.str.strip().str.casefold()).all():
        raise ValueError("Exact historical name did not match the selected row")
    # Pin every census source file and the historical point file at the rows used.
    def resolve_source_file(value: str) -> Path:
        path = Path(value)
        return path if path.is_file() else Path("/workspace/settlements-raw") / path
    files = sorted(set(resolve_source_file(x) for x in frame.source_file_selected))
    if sha(GEO) != str(raw.source_sha256_2011.iloc[0]):
        raise ValueError("Historical GeoKLADR checksum differs from the candidate evidence")
    selected_source_hashes = {}
    for source_path, expected in zip(frame.source_file_selected, frame.source_sha256):
        path = resolve_source_file(source_path)
        actual = sha(path)
        if pd.notna(expected) and actual != str(expected):
            raise ValueError(f"Census source checksum differs: {path}")
        selected_source_hashes[str(source_path)] = actual

    # Compare against the complete already-accepted point ledger, not just this candidate subset.
    ledger = c.execute(
        "SELECT target_source_record_id,CAST(target_year AS INTEGER) target_year,latitude,longitude "
        "FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))",
        [str(POINTS), POINT_STATUSES],
    ).fetchdf()
    occupied: dict[tuple[int, float, float], set[str]] = {}
    for q in ledger.itertuples(index=False):
        if pd.notna(q.target_year) and pd.notna(q.latitude) and pd.notna(q.longitude):
            occupied.setdefault((int(q.target_year), float(q.latitude), float(q.longitude)), set()).add(str(q.target_source_record_id))
    frame["point_hold_reason"] = ""
    for ix, q in frame.iterrows():
        key = (int(q.year), float(q.latitude_from_lat), float(q.longitude_from_long))
        if any(other != str(q.source_record_id) for other in occupied.get(key, set())):
            frame.at[ix, "point_hold_reason"] = "same-year point is already accepted for a different source record"

    # Permit a cross-year edge only for the same exact unique code/name/type/region/object.
    taezh = frame[frame.historical_okato_2011_raw.eq("25255553005")]
    edges = []
    if len(taezh) == 2:
        a, b = taezh.sort_values("year").to_dict("records")
        if (a["year"], b["year"]) != (2002, 2010):
            raise ValueError("Unexpected Taezhny census-year pair")
        keycols = ["settlement_name_selected", "settlement_type_selected", "region_norm_selected", "historical_okato_2011_raw", "latitude_from_lat", "longitude_from_long"]
        if any(str(a[k]).strip().casefold() != str(b[k]).strip().casefold() for k in keycols[:4]) or any(float(a[k]) != float(b[k]) for k in keycols[4:]):
            raise ValueError("Taezhny observations do not share an exact historical place key/point")
        all_years = c.execute("SELECT source_record_id,CAST(census_year AS INTEGER) FROM read_parquet(?)", [str(SELECTED)]).fetchall()
        uf = UnionFind(str(x[0]) for x in all_years)
        year_set = {str(x[0]): {int(x[1])} for x in all_years}
        def union(a_id: str, b_id: str) -> None:
            ra, rb = uf.find(str(a_id)), uf.find(str(b_id))
            if ra == rb:
                return
            merged = year_set[ra] | year_set[rb]
            if len(merged) < len(year_set[ra]) + len(year_set[rb]):
                raise ValueError("Existing accepted graph has a repeated-year conflict")
            uf.union(ra, rb)
            root = uf.find(ra)
            other = rb if root == ra else ra
            year_set[root] = merged
            year_set.pop(other, None)
        core_edges = c.execute("SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))", [str(GRAPH), sorted(ACCEPTED_EDGE_STATUSES)]).fetchall()
        for x, y in core_edges:
            union(x, y)
        for path, left, right in EDGE_DELTAS:
            for x, y in pd.read_csv(path, dtype=str)[[left, right]].itertuples(index=False, name=None):
                union(x, y)
        ra, rb = uf.find(a["source_record_id"]), uf.find(b["source_record_id"])
        if ra != rb:
            if year_set[ra] & year_set[rb]:
                raise ValueError("Taezhny bridge would duplicate a census year in its identity component")
            edges.append({"from_source_record_id": a["source_record_id"], "to_source_record_id": b["source_record_id"], "from_year": 2002, "to_year": 2010, "relation": "same_place", "decision_status": "checked_rule_accepted", "selection_projection_status": "active_endpoints_selected", "evidence_rule": "exact_raw_historical_code_plus_unique_name_type_region_and_same_valid_named_point"})

    points = []
    point_frame = frame[frame.point_hold_reason.eq("")]
    for r in point_frame.to_dict("records"):
        points.append({
            "target_source_record_id": r["source_record_id"], "target_year": int(r["year"]),
            "latitude": float(r["latitude_from_lat"]), "longitude": float(r["longitude_from_long"]),
            "coordinate_quality": "reviewed_historical_named_point_retrospective",
            "coordinate_source": "GeoKLADR OKATO 2011 named typed object", "coordinate_source_record_id": r["historical_okato_2011_raw"],
            "coordinate_provider": "GeoKLADR 2011", "coordinate_provider_id": "OKATO2011:" + str(r["historical_okato_2011_raw"]),
            "source_name": r["settlement_name_selected"], "source_type": r["settlement_type_selected"], "source_region": r["region_norm_selected"],
            "source_file": r["source_file_selected"], "source_row": r["source_row_selected"], "source_sha256": selected_source_hashes[str(r["source_file_selected"])], "source_locator": r["source_locator"],
            "coordinate_provenance": "Exact raw historical OKATO object; unique exact typed name/code and valid point, no same-year object collision or unlocated competitor. Used retrospectively as representative place point, not as a census-date measurement.",
            "admission_rule": "exact_raw_historical_code_unique_named_point_no_collision_v1",
            "coordinate_admission_status": "reviewed_case_accepted",
            "coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False, "coordinate_application_family": "H_historical_exact_code_named_point",
            "application_inference_kind": "retrospective_spatial_continuity_from_historical_named_point",
            "direct_historical_coordinate_measurement": False, "admission_allowed": True,
            "point_origin_file": str(GEO), "point_origin_sha256": str(r["source_sha256_2011"]),
            "point_origin_locator": f"DBF_record_1based={int(r['record_number_1based'])};byte_offset_0based={int(r['record_byte_offset_0based'])};OKATO2011_raw={r['historical_okato_2011_raw']}",
            "point_origin_kind": "raw_named_typed_geokladr2011_object",
            "point_claim_artifact_file": str(CANDIDATES), "point_claim_artifact_sha256": sha(CANDIDATES),
            "population": int(r["population_selected"]) if pd.notna(r["population_selected"]) else None,
            "population_value_quality": r["population_value_quality"], "review_note": "Exact historical code/name/type candidate checked against accepted same-year point ledger; no coordinate or population value inferred by distribution.",
        })
    OUT.mkdir(parents=True)
    pd.DataFrame(points).to_csv(OUT / "accepted_point_use_delta.csv", index=False)
    frame[frame.point_hold_reason.ne("")][["source_record_id", "year", "settlement_name_selected", "settlement_type_selected", "region_norm_selected", "population_selected", "historical_okato_2011_raw", "latitude_from_lat", "longitude_from_long", "point_hold_reason"]].to_csv(OUT / "held_coordinate_collisions.csv", index=False)
    pd.DataFrame(edges, columns=["from_source_record_id","to_source_record_id","from_year","to_year","relation","decision_status","selection_projection_status","evidence_rule"]).to_csv(OUT / "accepted_identity_edge_delta.csv", index=False)
    frame[["source_record_id","year","settlement_name_selected","settlement_type_selected","region_norm_selected","population_selected","population_value_quality","historical_okato_2011_raw","latitude_from_lat","longitude_from_long","name_raw_2011","source_file_selected","source_locator","record_number_1based","record_byte_offset_0based"]].to_csv(OUT / "reviewed_candidates.csv", index=False)
    inputs = [SELECTED, CANDIDATES, POINTS, GEO, *files]
    receipt = {
        "status": "exact_historical_code_unique_named_point_case_batch_applied",
        "rule": "Exact raw 2009/2011 historical code mapping; exact name/type; additive row; unique selected source key; valid WGS84 named-point coordinate; no shared point for distinct coded objects in that census year; no unlocated competitor. Coordinate is retrospective representative point. Population and boundary comparability are not inferred.",
        "candidate_rows": len(frame), "accepted_point_rows": len(points), "held_point_rows": int(frame.point_hold_reason.ne("").sum()), "accepted_edge_rows": len(edges),
        "population_by_year": {str(y): int(point_frame.loc[point_frame.year.eq(y), "population_selected"].fillna(0).sum()) for y in (2002,2010)},
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in inputs},
        "selected_source_file_hashes": selected_source_hashes,
        "outputs": {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in OUT.iterdir() if p.is_file()},
        "limitations": ["Five-row candidate stratum only; do not extrapolate to route-available rows with unknown provider/object provenance.", "Three point collisions are held; Taezhny pair has zero population in both selected rows; its edge adds continuity but no resident coverage.", "No population values changed; no census-date coordinate measurement is claimed."],
    }
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text("# Exact historical-code point batch\n\nThe five candidates pass exact code, exact name/type, additive census row, valid GeoKLADR point, and no historical unlocated competitor. The final application additionally checks every already-accepted same-year point. Three candidates are held because their point is already assigned to a different source record. Only the two Taezhny zero-population rows receive point uses. Their exact code/name/type/region/point key supports a 2002–2010 same-place edge; no population values or boundaries were changed.\n\nSee the receipt, candidate table, point-use delta, held collisions, and identity-edge delta.\n", encoding="utf-8")
    print(json.dumps({"candidate_rows": len(frame), "accepted_point_rows": len(points), "held_point_rows": int(frame.point_hold_reason.ne("").sum()), "accepted_edge_rows": len(edges), "population_by_year": receipt["population_by_year"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
