#!/usr/bin/env python3
"""Apply the scoped 8-digit typed-city OKATO to GeoKLADR point bridge."""
from __future__ import annotations

import hashlib, json, re
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/typed_city_geokladr_code_width_points_20261006"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
GRAPH_POINTS = Path("/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet")
HIST = Path("/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet")
PRIORITIES = Path("/workspace/settlements-work/continuation_20261003/audit_99_20261003/older_years/current_candidate_priorities.csv")
MANIFEST_ASSETS = Path("/workspace/settlements-work/continuation_20261003/audit_99_20261003/older_years/selected_source_manifest_assets.csv")
EVIDENCE = ROOT / "research_rebuild/evidence"
POINT_DELTAS = [
    "top60_and_proximity_review_20261005/simple_rule_application/top60_point_use_delta.csv",
    "top100_classifier_bridge_20261005/old_point_use_delta.csv",
    "historical_urban_code_residual_20261005/accepted_point_use_delta.csv",
    "historical_classifier_bridge_batch_20261005/accepted_retrospective_point_use_delta.csv",
    "shared_locality_point_novaya_usman_20261005/accepted_shared_locality_point_uses.csv",
    "unique_name_region_coordinate_bridge_20261005/accepted_point_use_delta.csv",
    "unique_exact_historical_code_point_batch_20261005/accepted_point_use_delta.csv",
    "current_residual_ownlocality_points_20261005/accepted_point_use_delta.csv.gz",
    "kudryashovsky_three_census_chain_20261006/accepted_point_use_delta.csv",
    "current_2021_fias_exact_name_bridge_20261006/accepted_retrospective_point_use_delta.csv",
]

def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def main() -> None:
    if OUT.exists():
        raise FileExistsError(OUT)
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    selected = pd.read_parquet(SELECTED)
    selected = selected[selected.census_year.isin([2002, 2010])].copy()
    selected["census_year"] = selected.census_year.astype(int)
    pr = pd.read_csv(PRIORITIES, low_memory=False)
    pr = pr[
        pr.historical_named_point_candidate.astype(str).str.lower().eq("true")
        & pr.code_join_basis.eq("typed_urban_8digit_plus_zero_third_geo_group")
    ].copy()
    if pr.source_record_id.astype(str).duplicated().any():
        raise ValueError("Historical candidate priority IDs are not unique")
    hist = con.execute(
        "SELECT * FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))",
        [str(HIST), pr.source_record_id.astype(str).tolist()],
    ).fetchdf()
    if len(hist) != len(pr):
        raise ValueError("Historical point candidate rows do not map one-to-one")
    x = pr.merge(hist, on="source_record_id", suffixes=("_priority", "_hist"), validate="one_to_one")
    x = x.merge(selected, on="source_record_id", suffixes=("", "_selected"), validate="one_to_one")
    assets = pd.read_csv(MANIFEST_ASSETS)
    x = x.merge(assets[["path", "input_manifest_sha256", "local_asset_exists", "local_sha256_matches_manifest"]],
                left_on="source_file", right_on="path", how="left", validate="many_to_one")

    # This is a documented field-grain bridge: 8-digit typed urban 2009 OKATO
    # to the 11-digit 2011 GeoKLADR object when KOD3 is exactly "000".
    c2009 = x.historical_okato_2009_raw_hist
    c2011 = x.historical_okato_2011_raw_hist
    gates = (
        x.code_join_basis_priority.eq("typed_urban_8digit_plus_zero_third_geo_group")
        & x.historical_name_exact_hist.fillna(False) & x.historical_type_exact_hist.fillna(False)
        & x.historical_code_structure_compatible_hist.fillna(False)
        & x.is_additive_settlement_record.fillna(False)
        & x.historical_key_region_name_type_count_hist.eq(1)
        & ~x.possible_unlocated_historical_competitor_hist.fillna(False)
        & c2009.fillna("").str.fullmatch(r"\d{8}")
        & c2011.fillna("").str.fullmatch(r"\d{11}")
        & c2011.fillna("").str[:8].eq(c2009.fillna(""))
        & x.kod3_raw_text.eq("000")
        & x.source_updated_at.eq("2011/06/20")
        & x.latitude_from_lat.between(-90, 90) & x.longitude_from_long.between(-180, 180)
        & (x.local_sha256_matches_manifest.fillna(False) | x.source_sha256.notna())
    )
    if not gates.all():
        raise ValueError(f"Scoped typed-city candidate gate failed for {int((~gates).sum())} rows")

    # Hold exact coordinate collisions between distinct raw historical objects.
    hist_all = con.execute(
        "SELECT census_year,latitude_from_lat,longitude_from_long,count(DISTINCT historical_okato_2011_raw) n "
        "FROM read_parquet(?) WHERE historical_named_point_candidate AND latitude_from_lat IS NOT NULL "
        "AND longitude_from_long IS NOT NULL GROUP BY ALL", [str(HIST)]
    ).fetchdf()
    x = x.merge(hist_all, on=["census_year", "latitude_from_lat", "longitude_from_long"], how="left", validate="many_to_one")
    raw_collision = x.n.fillna(0).gt(1)
    collision_free = x[~raw_collision].copy()

    # Also hold a point already assigned to another selected object in the same year.
    statuses = ["reviewed_rule_accepted", "frozen_r5b_reviewed_baseline_preserved", "reviewed_extension_rule_accepted", "reviewed_case_accepted"]
    base_points = con.execute(
        "SELECT target_source_record_id,latitude,longitude FROM read_parquet(?) "
        "WHERE coordinate_admission_status IN (SELECT UNNEST(?))", [str(GRAPH_POINTS), statuses]
    ).fetchdf()
    point_frames = [base_points.rename(columns={"target_source_record_id":"source_record_id"})]
    for rel in POINT_DELTAS:
        d = pd.read_csv(EVIDENCE / rel)
        if {"target_source_record_id", "latitude", "longitude"}.issubset(d.columns):
            point_frames.append(d[["target_source_record_id", "latitude", "longitude"]].dropna().rename(columns={"target_source_record_id":"source_record_id"}))
    existing = pd.concat(point_frames, ignore_index=True).drop_duplicates()
    id_year = selected[["source_record_id", "census_year"]]
    existing = existing.merge(id_year, on="source_record_id", how="inner")
    existing["point_key"] = list(zip(existing.census_year, existing.latitude.round(6), existing.longitude.round(6)))
    owners_by_point = existing.groupby("point_key").source_record_id.agg(lambda s: set(map(str, s))).to_dict()
    points_by_target = existing.groupby("source_record_id").apply(
        lambda g: set(zip(g.latitude.round(6), g.longitude.round(6))), include_groups=False
    ).to_dict()
    collision_free["candidate_point_key"] = list(zip(collision_free.census_year, collision_free.latitude_from_lat.round(6), collision_free.longitude_from_long.round(6)))
    collision_free["already_same_target"] = collision_free.apply(
        lambda r: (round(r.latitude_from_lat, 6), round(r.longitude_from_long, 6)) in points_by_target.get(str(r.source_record_id), set()), axis=1
    )
    collision_free["target_has_other_point"] = collision_free.source_record_id.astype(str).map(
        lambda sid: bool(points_by_target.get(sid, set()))
    ) & ~collision_free.already_same_target
    collision_free["other_target_collision"] = collision_free.apply(
        lambda r: bool(owners_by_point.get(r.candidate_point_key, set()) - {str(r.source_record_id)}), axis=1
    )
    already = collision_free[collision_free.already_same_target].copy()
    ledger_collision = collision_free[collision_free.other_target_collision | collision_free.target_has_other_point].copy()
    accepted = collision_free[~collision_free.already_same_target & ~collision_free.other_target_collision & ~collision_free.target_has_other_point].copy()
    held = pd.concat([
        x[raw_collision].assign(hold_reason="same_year_coordinate_collision_between_distinct_historical_objects"),
        ledger_collision.assign(hold_reason="coordinate_already_assigned_to_another_selected_same_year_record_or_target_point_conflict"),
    ], ignore_index=True)

    point_rows = []
    for r in accepted.itertuples(index=False):
        point_rows.append({
            "target_source_record_id": r.source_record_id, "target_year": int(r.census_year),
            "latitude": float(r.latitude_from_lat), "longitude": float(r.longitude_from_long),
            "coordinate_quality": "reviewed_historical_typed_city_geokladr_named_point",
            "coordinate_source": "GeoKLADR OKATO 2011 named typed city object",
            "coordinate_source_record_id": str(r.historical_okato_2011_raw_hist),
            "coordinate_provider": "GeoKLADR 2011", "coordinate_provider_id": "OKATO2011:" + str(r.historical_okato_2011_raw_hist),
            "source_name": r.settlement_name, "source_type": r.settlement_type, "source_region": r.region_raw,
            "source_file": r.source_file, "source_row": r.source_row, "source_sha256": r.source_sha256,
            "source_locator": r.source_locator,
            "coordinate_provenance": "Scoped typed-city field-grain bridge: literal 8-digit 2009 typed-city OKATO equals the first eight digits of the unique 11-digit 2011 GeoKLADR OKATO and raw KOD3 is 000; exact selected name/type and historical raw object; unique same-year raw point; source file pinned by input manifest or selected row hash. Point updated 2011-06-20, not a census-date measurement.",
            "admission_rule": "typed_city_8digit_to_11digit_geokladr_KOD3_000_unique_named_point_v1",
            "coordinate_admission_status": "reviewed_extension_rule_accepted",
            "coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False,
            "coordinate_application_family": "historical_typed_city_okato_width_bridge_20261006",
            "application_inference_kind": "historical_named_point_code_grain_compatibility",
            "direct_historical_coordinate_measurement": False, "admission_allowed": True,
            "point_origin_file": str(HIST), "point_origin_sha256": sha(HIST),
            "point_origin_locator": f"GeoKLADR DBF record={int(r.record_number_1based)}; byte_offset={int(r.record_byte_offset_0based)}; OKATO2011={r.historical_okato_2011_raw_hist}; OKATO2009={r.historical_okato_2009_raw_hist}; KOD3={r.kod3_raw_text}",
            "point_origin_kind": "raw_named_typed_geokladr2011_object",
            "point_claim_artifact_file": str(PRIORITIES), "point_claim_artifact_sha256": sha(PRIORITIES),
            "historical_okato_2009_raw": str(r.historical_okato_2009_raw_hist),
            "historical_okato_2011_raw": str(r.historical_okato_2011_raw_hist),
            "historical_kod3_raw": str(r.kod3_raw_text), "input_manifest_sha256": r.input_manifest_sha256,
            "population": int(r.population) if pd.notna(r.population) else None,
            "population_value_quality": r.population_value_quality,
            "review_note": "Coordinate point only; this code-width association does not create a census-to-census identity edge or population/boundary comparability claim.",
        })
    OUT.mkdir(parents=True)
    point_path = OUT / "accepted_point_use_delta.csv"
    held_path = OUT / "held_coordinate_collisions.csv"
    candidate_path = OUT / "reviewed_candidates.csv"
    pd.DataFrame(point_rows).to_csv(point_path, index=False)
    held.to_csv(held_path, index=False)
    x.to_csv(candidate_path, index=False)
    receipt = {
        "status": "applied_scoped_typed_city_code_width_point_bridge",
        "rule": "Accept only 2002/2010 additive typed-city candidates with exact selected and historical names/types, unique region/name/type key, no unlocated competitor, literal 8-digit 2009 code matching the first eight characters of literal 11-digit GeoKLADR 2011 code, raw KOD3=000, valid WGS84 point, date 2011-06-20, and source pinned by verified input-manifest asset or selected source hash. Hold raw same-year candidate coordinate collisions and collisions with any already accepted selected point. No identity edge or population/boundary comparability is inferred.",
        "input_candidates": len(x), "accepted_point_rows": len(point_rows), "already_accepted_same_target_rows": len(already), "held_coordinate_collision_rows": len(held),
        "population_by_year": {str(y): int(accepted.loc[accepted.census_year.eq(y), "population"].fillna(0).sum()) for y in (2002, 2010)},
        "collision_free_raw_code_candidates": len(collision_free), "manifest_hash_pinned_rows": int(accepted.local_sha256_matches_manifest.fillna(False).sum()),
        "selected_row_hash_pinned_rows": int(accepted.source_sha256.notna().sum()),
        "point_updated_at_values": accepted.source_updated_at.value_counts(dropna=False).to_dict(),
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in (SELECTED, GRAPH_POINTS, HIST, PRIORITIES, MANIFEST_ASSETS)},
        "outputs": {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in (point_path, held_path, candidate_path)},
        "limitations": ["2009/2011 classifier codes are not asserted as native census OKATO/OKTMO values.", "GeoKLADR coordinates date to 2011-06-20, not the census dates.", "No identity links, census population values, legal boundaries, or population comparability were changed.", "Point collisions remain explicit and held."],
    }
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (OUT / "README.md").write_text("# Typed-city GeoKLADR code-width point batch\n\nApplied the scoped compatibility bridge for typed urban classifier codes: literal 8-digit 2009 OKATO maps to a unique 11-digit 2011 GeoKLADR city object when the first eight digits agree and raw KOD3 is exactly `000`. Exact historical name/type and a unique selected region/name/type key are required. Raw same-year point collisions and collisions with already accepted selected points are held. This adds a historical named point to a census row; it does not add inter-census identity or change population/boundary comparability. GeoKLADR point data are dated 2011-06-20.\n\nSee the receipt, accepted point delta, held collisions, and candidate ledger.\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("input_candidates", "accepted_point_rows", "already_accepted_same_target_rows", "held_coordinate_collision_rows", "population_by_year", "manifest_hash_pinned_rows", "selected_row_hash_pinned_rows")}, ensure_ascii=False))

if __name__ == "__main__": main()
