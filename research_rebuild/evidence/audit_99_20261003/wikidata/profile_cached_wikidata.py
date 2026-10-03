#!/usr/bin/env python3
"""Reproduce the cached-Wikidata profile for unpointed 2021 settlement targets.

This is a diagnostic only. It never writes candidate decisions to release data.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

F = Path("/workspace/settlements-delivery/continuation-consolidated-20261003")
W = Path("/workspace/settlements-work/wikidata/wide_v5")
OUT = Path(__file__).resolve().parent
KNOWN_CURRENT_CITY_HOLDS = {
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:149473": "Mezhgorye: unresolved city point-choice conflict",
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:25288": "Ust-Kut: unresolved city point-choice conflict",
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:155218": "Pokachi: multiple distinct eligible P625 coordinates",
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:50511": "Feodosia: multiple distinct eligible P625 coordinates",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def js(value):
    if value is None or pd.isna(value) or value == "":
        return []
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []


def ids(obj):
    return {str(x.get("value_qid")) for x in obj if x.get("value_qid")}


def haversine_km(lat1, lon1, lat2, lon2):
    import math
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def main():
    selected = pd.read_parquet(F / "selected_observations.parquet")
    selected = selected.loc[
        selected.census_year.eq(2021)
        & selected.is_additive_settlement_record.fillna(False)
        & selected.population_scope.eq("settlement")
    ].copy()
    uses = pd.read_parquet(F / "accepted_point_uses.parquet", columns=["target_year", "target_source_record_id"])
    accepted = set(uses.loc[uses.target_year.eq(2021), "target_source_record_id"].astype(str))
    targets = selected.loc[~selected.source_record_id.astype(str).isin(accepted)].copy()
    targets["source_record_id"] = targets.source_record_id.astype(str)
    source_physical = pd.read_parquet(W / "provider_code_candidate_screen.parquet", columns=["source_record_id", "source_is_physical_np"])
    targets = targets.merge(source_physical, on="source_record_id", how="left", validate="one_to_one")
    if targets.source_is_physical_np.isna().any() or not targets.source_is_physical_np.astype(bool).all():
        raise ValueError("the scoped current unpointed target universe contains missing/nonphysical source rows")

    wide = pd.read_parquet(W / "wide_point_bindings.parquet")
    wide = wide.loc[wide.source_record_id.astype(str).isin(set(targets.source_record_id))].copy()
    wide["p31"] = wide.wikidata_truthy_p31_claims_json.map(js)
    wide["p625"] = wide.wikidata_truthy_p625_claims_json.map(js)
    wide["p17"] = wide.wikidata_truthy_p17_claims_json.map(js)
    wide["p131"] = wide.wikidata_truthy_p131_claims_json.map(js)
    wide["p31ids"] = wide.p31.map(ids)
    sys.path.insert(0, "/workspace/russian-settlements-research")
    from research_rebuild.mass_linkage.coordinate_validation_packet import wikidata_type_lineage
    from research_rebuild.mass_linkage.coordinate_validation_packet import _load_region_geometries, _point_inside_source_region
    ancestry = json.loads(Path("/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json").read_text())
    profiles = wikidata_type_lineage(ancestry)
    geometries, region_iso = _load_region_geometries()
    region_screen = pd.read_parquet("/workspace/settlements-work/coordinates/region_screen_v1/region_point_screen.parquet", columns=["source_record_id", "geometry_iso"])
    geometry_by_source = region_screen.set_index("source_record_id").geometry_iso.to_dict()
    wide["physical_lineage"] = wide.p31ids.map(lambda qs: any(profiles.get(q, {}).get("physical_settlement_lineage") for q in qs))
    wide["admin_only_lineage"] = wide.p31ids.map(lambda qs: any(profiles.get(q, {}).get("admin_only_lineage_without_physical_settlement") for q in qs))
    wide["mixed_p31_lineage"] = wide.physical_lineage & wide.admin_only_lineage
    wide["p625coords"] = wide.p625.map(lambda xs: {
        (float(x["latitude"]), float(x["longitude"])) for x in xs
        if x.get("wgs84_valid") and x.get("latitude") is not None and x.get("longitude") is not None
    })
    wide["exact_code"] = wide.wikidata_truthy_exact_p764_match.fillna(False).astype(bool)
    wide["exact_name"] = wide.wikidata_name_exact_label.fillna(False).astype(bool)
    wide["physical_known"] = wide.physical_lineage
    wide["admin_known"] = wide.admin_only_lineage
    wide["p17_russia"] = wide.p17.map(lambda x: "Q159" in ids(x))
    wide["has_valid_point"] = wide.p625coords.map(bool)
    wide["multi_distinct_point"] = wide.p625coords.map(lambda x: len(x) > 1)
    target_coords = targets.set_index("source_record_id")[["latitude", "longitude"]].to_dict("index")
    wide["p625_nearest_source_point_km"] = wide.apply(
        lambda r: min((haversine_km(lat, lon,
                                      target_coords.get(str(r.source_record_id), {}).get("latitude"),
                                      target_coords.get(str(r.source_record_id), {}).get("longitude"))
                       for lat, lon in r.p625coords), default=None), axis=1
    )
    wide["has_admin_context"] = wide.p131.map(bool)
    target_region = {sid: geometry_by_source.get(sid) for sid in targets.source_record_id.astype(str)}
    wide["single_point_inside_expected_adm1"] = wide.apply(
        lambda r: len(r.p625coords) == 1 and _point_inside_source_region(
            next(iter(r.p625coords))[0], next(iter(r.p625coords))[1],
            target_region.get(str(r.source_record_id)), geometries, region_iso
        )[0], axis=1
    )
    wide["source_row_name_type_region_exact"] = (
        wide.source_name.fillna("").astype(str).str.casefold().eq(
            targets.set_index("source_record_id").reindex(wide.source_record_id.astype(str)).settlement_name.fillna("").astype(str).str.casefold().to_numpy()
        )
        & wide.source_type.fillna("").astype(str).str.casefold().eq(
            targets.set_index("source_record_id").reindex(wide.source_record_id.astype(str)).settlement_type.fillna("").astype(str).str.casefold().to_numpy()
        )
        & wide.source_region.fillna("").astype(str).str.casefold().eq(
            targets.set_index("source_record_id").reindex(wide.source_record_id.astype(str)).region_raw.fillna("").astype(str).str.casefold().to_numpy()
        )
    )

    # Candidate gates are target-level ORs over exact-code-linked QIDs. Keep target-level
    # code and point checks separate from candidate-QID counts so duplicates are visible.
    target_flags = wide.groupby("source_record_id", sort=False).agg(
        exact_code=("exact_code", "max"), exact_name=("exact_name", "max"),
        valid_point=("has_valid_point", "max"), physical_known=("physical_known", "max"),
        admin_known=("admin_known", "max"), p17_russia=("p17_russia", "max"),
        mixed_p31_lineage=("mixed_p31_lineage", "max"),
        single_point_inside_expected_adm1=("single_point_inside_expected_adm1", "max"),
        nearest_p625_source_point_km=("p625_nearest_source_point_km", "min"),
        has_admin_context=("has_admin_context", "max"),
        source_row_name_type_region_exact=("source_row_name_type_region_exact", "max"),
        qids=("wikidata_qid", "nunique"), multi_qid=("wikidata_qid", lambda x: x.nunique() > 1),
        competing_qid=("entity_competition_across_tsv_or_truthy", "max"),
        source_code_competition=("source_observation_competition_for_exact_oktmo", "max"),
        multi_point_qid=("multi_distinct_point", "max"),
        physical_and_admin_known=("mixed_p31_lineage", "max"),
    ).reset_index()
    targets = targets.merge(target_flags, on="source_record_id", how="left", validate="one_to_one")
    boolcols = [c for c in target_flags.columns if c not in {"source_record_id", "qids", "nearest_p625_source_point_km"}]
    targets[boolcols] = targets[boolcols].fillna(False).astype(bool)
    targets["qids"] = targets.qids.fillna(0).astype(int)

    def measure(mask):
        rows = targets.loc[mask]
        return {"rows": int(len(rows)), "population": int(rows.population.fillna(0).sum())}

    masks = {
        "unpointed_target_universe": pd.Series(True, index=targets.index),
        "any_exact_p764": targets.exact_code,
        "exact_p764_plus_valid_p625": targets.exact_code & targets.valid_point,
        "exact_ru_label_plus_valid_p625": targets.exact_name & targets.valid_point,
        "exact_code_name_and_valid_p625": targets.exact_code & targets.exact_name & targets.valid_point,
        "exact_code_name_point_and_known_physical_p31": targets.exact_code & targets.exact_name & targets.valid_point & targets.physical_known,
        "same_plus_no_multi_qid_and_no_entity_competition": targets.exact_code & targets.exact_name & targets.valid_point & targets.physical_known & ~targets.multi_qid & ~targets.competing_qid & ~targets.source_code_competition,
        "same_plus_single_distinct_p625": targets.exact_code & targets.exact_name & targets.valid_point & targets.physical_known & ~targets.multi_qid & ~targets.competing_qid & ~targets.source_code_competition & ~targets.multi_point_qid,
        "scoped_wikidata_core_plus_single_point_inside_adm1": targets.exact_code & targets.exact_name & targets.valid_point & targets.physical_known & ~targets.multi_qid & ~targets.competing_qid & ~targets.source_code_competition & ~targets.multi_point_qid & targets.single_point_inside_expected_adm1,
    }
    metrics = {name: measure(mask) for name, mask in masks.items()}
    metrics["unpointed_target_universe"]["population"] = int(targets.population.fillna(0).sum())
    metrics["wide_binding_coverage"] = {"targets_with_any_cached_wide_row": int(targets.source_record_id.isin(wide.source_record_id).sum()), "wide_rows_including_qid_duplicates": int(len(wide)), "target_ids_with_duplicate_qid_rows": int(target_flags.multi_qid.sum())}
    metrics["gate_marginals_within_exact_code_name_point"] = {
        col: measure((targets.exact_code & targets.exact_name & targets.valid_point) & targets[col])
        for col in ["physical_known", "admin_known", "p17_russia", "has_admin_context", "multi_qid", "competing_qid", "source_code_competition", "multi_point_qid", "physical_and_admin_known", "mixed_p31_lineage", "single_point_inside_expected_adm1"]
    }
    pilot = (targets.exact_code & targets.exact_name & targets.valid_point & targets.physical_known
             & ~targets.multi_qid & ~targets.competing_qid & ~targets.source_code_competition
             & ~targets.multi_point_qid & targets.single_point_inside_expected_adm1)
    targets["known_current_city_hold_reason"] = targets.source_record_id.map(KNOWN_CURRENT_CITY_HOLDS)
    known_hold_rows = targets.loc[targets.known_current_city_hold_reason.notna()].copy()
    known_hold_overlap = known_hold_rows.loc[pilot.reindex(known_hold_rows.index)]
    pilot_after_city_holds = pilot & targets.known_current_city_hold_reason.isna()
    metrics["known_current_city_holds"] = {
        "all_four_hold_rows_in_current_unpointed_universe": int(len(known_hold_rows)),
        "all_four_hold_population": int(known_hold_rows.population.fillna(0).sum()),
        "hold_detail": [
            {"source_record_id": r.source_record_id, "name": r.settlement_name,
             "population": int(r.population or 0), "reason": r.known_current_city_hold_reason,
             "overlaps_pre_review_scoped_core": bool(str(r.source_record_id) in set(known_hold_overlap.source_record_id.astype(str)))}
            for r in known_hold_rows.itertuples(index=False)
        ],
        "overlap_scoped_core_rows": int(len(known_hold_overlap)),
        "overlap_scoped_core_population": int(known_hold_overlap.population.fillna(0).sum()),
        "scoped_core_after_quarantining_these_known_holds": {
            "rows": int(pilot_after_city_holds.sum()),
            "population": int(targets.loc[pilot_after_city_holds, "population"].fillna(0).sum()),
        },
        "status": "candidate_only_no_new_admission",
    }
    metrics["provider_distance_review_flags_within_scoped_core"] = {
        "distance_available_rows": int((pilot & targets.nearest_p625_source_point_km.notna()).sum()),
        "exact_same_coordinate_rows": int((pilot & targets.nearest_p625_source_point_km.fillna(float("inf")).eq(0)).sum()),
        "nearest_p625_to_selected_source_point_over_1km_rows": int((pilot & targets.nearest_p625_source_point_km.gt(1)).sum()),
        "nearest_p625_to_selected_source_point_over_5km_rows": int((pilot & targets.nearest_p625_source_point_km.gt(5)).sum()),
        "nearest_p625_to_selected_source_point_over_10km_rows": int((pilot & targets.nearest_p625_source_point_km.gt(10)).sum()),
        "distance_quantiles_km": {str(q): float(targets.loc[pilot, "nearest_p625_source_point_km"].dropna().quantile(q)) for q in [0.5, 0.9, 0.99, 1.0]},
        "interpretation": "contextual review flags only; selected source points may be unaccepted or share lineage and distance does not decide point validity by itself",
    }
    metrics["full_geo_names_probe_context"] = {
        "probe_rows": 2819, "probe_population": 3298376,
        "strict_candidate_rows": 1047, "strict_candidate_population": 1034555,
        "already_accepted_point_overlap_rows": 289,
        "new_candidate_rows": 758, "new_candidate_population": 929241,
        "note": "Strict GeoNames witness set is candidate-only; 1 km agreement and exact source-row region equality are extra witness constraints, not prerequisites for using a uniquely identified Wikidata P625 point."
    }
    metrics["source_hashes_sha256"] = {
        str(path): sha(path) for path in [
            F / "selected_observations.parquet", F / "accepted_point_uses.parquet",
            W / "wide_point_bindings.parquet", W / "provider_code_candidate_screen.parquet",
            W / "manifest.json", W / "run_summary.json",
            Path("/workspace/settlements-work/coordinates/region_screen_v1/region_point_screen.parquet"),
            Path("/workspace/settlements-work/coordinates/region_screen_v1/receipt.json"),
            Path("/workspace/settlements-work/sources/region_geometry/RUS_ADM1_simplified.geojson"),
            Path("/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json"),
            Path("/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv"),
            Path("/workspace/settlements-work/coordinates/validation_packet/run_20261002_06/manifest.json"),
            Path("/workspace/settlements-work/coordinates/validation_packet/run_20261002_07/manifest.json"),
            Path("/workspace/settlements-work/coordinates/independent_review_v1/review.json"),
            Path("/workspace/settlements-work/continuation_20261003/geonames_wikidata_full_witness_probe_v2/full_2819_witness_evidence.csv"),
            Path("/workspace/settlements-work/continuation_20261003/geonames_wikidata_full_witness_probe_v2/summary.json"),
            Path("/workspace/settlements-work/continuation_20261003/geonames_wikidata_full_witness_probe_v2/build_probe.py"),
            Path("/workspace/russian-settlements-research/research_rebuild/mass_linkage/coordinate_validation_packet.py"),
            Path("/workspace/russian-settlements-research/research_rebuild/mass_linkage/admit_coordinates.py"),
        ]
    }
    metrics["source_manifest_extract"] = {
        "wide_manifest": str(W / "manifest.json"),
        "manifest_sha256": sha(W / "manifest.json"),
        "raw_wikimedia_oktmo_tsv_sha256": "580e20042d6dfdcc6dd29d5d7fbde59593145b97abbb37e7760e89b567b36d36",
        "truthy_claim_retrieval": "2026-08-31 snapshot; 141 cached files; export omits statement IDs, rank/qualifiers/references",
        "existing_review": "/workspace/settlements-work/coordinates/independent_review_v1/review.json; C city rule accepted with row-specific holds: 903/910 after holds; fixed C sample 100/100 gates, 98 point eligible after holds",
        "existing_application_barrier": "coordinate_validation_packet + admit_coordinates retain new points as candidates; admit_coordinates manifest requires independent coordinate review and reports coordinate_admissions_new=0",
        "limitations": ["P764 source/reference lineage unavailable in truthy export", "OKATO projection is marked non-independent", "Wikimedia TSV/module/truthy/P279 metadata are one Wikidata evidence family, not independent providers", "current-source region copied through exact source_record_id join is not independent WD administrative-region evidence", "ADM1 membership is regional context, not locality identity/extent; for rural/PGT this new audit profile is availability only and not a reviewed rule result"],
    }
    (OUT / "profile.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "source_hashes_sha256"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
