#!/usr/bin/env python3
"""Apply the prepared exact-row/current-own-locality point rule to its frozen cohort."""
from __future__ import annotations

import hashlib
import json
import ast
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/current_residual_ownlocality_points_20261005"
CANDIDATES = Path("/workspace/settlements-work/continuation_20261004/regions/current_residual_own_locality_points_v1/current_point_candidates.csv")
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
ACCEPTED = {"reviewed_rule_accepted", "frozen_r5b_reviewed_baseline_preserved", "reviewed_extension_rule_accepted", "reviewed_case_accepted"}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    if OUT.exists():
        raise FileExistsError(OUT)
    d = pd.read_csv(CANDIDATES, low_memory=False)
    expected_gates = [
        "source_record_suffix_matches_row", "native_oktmo_selected_raw_exact",
        "raw_source_name_matches_selected_label", "typed_name_and_type_match",
        "region_matches", "population_exact", "named_FIAS_level6_same_id",
        "point_valid", "selected_point_consistent_if_present",
        "native_code_unique_in_full_selected_2021", "not_street_district_or_SNT_label",
        "selected_row_additive_locality",
    ]
    for column in expected_gates:
        if not d.raw_gate_evidence.map(lambda x: ast.literal_eval(x).get(column) is True).all():
            raise ValueError(f"Prepared candidate failed frozen source gate: {column}")
    if d.source_record_id.astype(str).duplicated().any() or set(d.year.astype(int)) != {2021}:
        raise ValueError("Expected unique 2021 source rows only")
    if not d.current_point_latitude.between(-90, 90).all() or not d.current_point_longitude.between(-180, 180).all():
        raise ValueError("Invalid WGS84 coordinate")

    # Keep the fixed cohort, but hold any point duplicated by another NP in 2021.
    keys = list(zip(d.year.astype(int), d.current_point_latitude.astype(float), d.current_point_longitude.astype(float)))
    candidate_counts = pd.Series(keys).value_counts()
    d["hold_reason"] = ""
    d.loc[[candidate_counts[k] > 1 for k in keys], "hold_reason"] = "same coordinate assigned to multiple candidates in this year"
    core = pd.read_parquet(POINTS, columns=["target_source_record_id", "target_year", "latitude", "longitude", "coordinate_admission_status"])
    core = core[core.coordinate_admission_status.isin(ACCEPTED)]
    core["target_year"] = pd.to_numeric(core.target_year, errors="coerce")
    core_ids_by_key: dict[tuple[int, float, float], set[str]] = {}
    for r in core.itertuples(index=False):
        if pd.isna(r.target_year) or pd.isna(r.latitude) or pd.isna(r.longitude):
            continue
        key = (int(r.target_year), float(r.latitude), float(r.longitude))
        core_ids_by_key.setdefault(key, set()).add(str(r.target_source_record_id))
    for i, r in d.iterrows():
        if r.hold_reason:
            continue
        key = (int(r.year), float(r.current_point_latitude), float(r.current_point_longitude))
        if any(sid != str(r.source_record_id) for sid in core_ids_by_key.get(key, set())):
            d.at[i, "hold_reason"] = "same coordinate already accepted for a different 2021 source row"

    selected = pd.read_parquet(SELECTED, columns=["source_record_id", "census_year", "source_file", "source_sha256", "source_row", "source_locator", "settlement_name", "settlement_type", "region_raw", "oktmo", "population"])
    sel = selected.set_index("source_record_id", drop=False)
    if not set(d.source_record_id.astype(str)).issubset(set(sel.index.astype(str))):
        raise ValueError("Candidate source IDs are absent from frozen selected census rows")

    good = d[d.hold_reason.eq("")].copy()
    rows = []
    for r in good.itertuples(index=False):
        s = sel.loc[str(r.source_record_id)]
        rows.append({
            "target_source_record_id": str(r.source_record_id), "target_year": 2021,
            "latitude": float(r.current_point_latitude), "longitude": float(r.current_point_longitude),
            "coordinate_quality": "reviewed_rule_accepted_current_source_locality_point",
            "coordinate_source": "Tochno 2021 raw row; DaData settlement point at FIAS level 6",
            "coordinate_source_record_id": str(r.source_raw_fias_id), "coordinate_provider": "DaData as embedded in Tochno 2021",
            "coordinate_provider_id": str(r.source_raw_fias_id), "source_name": str(s.settlement_name),
            "source_type": str(s.settlement_type), "source_region": str(s.region_raw),
            "source_file": str(s.source_file), "source_row": int(s.source_row), "source_sha256": str(s.source_sha256),
            "source_locator": str(s.source_locator),
            "coordinate_provenance": "Exact selected-row/native OKTMO/raw-name/type/region/population match; FIAS level 6 ID is identical in both provider fields; raw point equals selected point; additive locality row.",
            "admission_rule": "current_residual_own_FIAS6_exact_source_row_v1",
            "coordinate_admission_status": "reviewed_extension_rule_accepted",
            "coordinate_measurement_date_unknown": True, "boundary_comparability_asserted": False,
            "coordinate_application_family": "current_own_locality_point_exact_row_FIAS6",
            "application_inference_kind": "direct_current_source_point", "direct_historical_coordinate_measurement": False,
            "population_scope_comparability_asserted": False, "admission_allowed": True,
            "point_origin_file": str(r.point_origin_file), "point_origin_sha256": str(r.point_origin_sha256),
            "point_origin_locator": f"parquet row 1-based={int(r.point_origin_row_1based)}; raw row sha256={r.point_origin_raw_payload_sha256}",
            "point_origin_kind": "exact_row_current_FIAS_level6_locality", "point_claim_artifact_file": str(CANDIDATES),
            "point_claim_artifact_sha256": sha(CANDIDATES), "coordinate_source_latitude_raw": float(r.current_point_latitude),
            "coordinate_source_longitude_raw": float(r.current_point_longitude), "source_native_id": str(s.oktmo),
            "population_context_only": int(s.population), "raw_source_row_payload_sha256": str(r.point_origin_raw_payload_sha256),
            "application_gate_status": "passed_all_frozen_exact_row_and_locality_gates",
        })
    held = d[d.hold_reason.ne("")].copy()
    OUT.mkdir(parents=True)
    point_path = OUT / "accepted_point_use_delta.csv.gz"
    hold_path = OUT / "held_coordinate_collisions.csv.gz"
    pd.DataFrame(rows).to_csv(point_path, index=False, compression="gzip")
    held.to_csv(hold_path, index=False, compression="gzip")
    selected_year = selected[selected.census_year.eq(2021)]
    summary = {
        "status": "applied_exact_source_row_current_FIAS6_points_with_same_year_coordinate_collision_holds",
        "rule": "A selected 2021 additive settlement row's own current point is accepted where its exact native OKTMO, source ordinal, name, type, region, population, FIAS level-6 identity, raw point and selected point agree. Retrospective dates and cross-year identity are not asserted.",
        "candidate_rows": int(len(d)), "candidate_population": int(d.population.sum()),
        "accepted_rows": int(len(rows)), "accepted_population": int(good.population.sum()),
        "held_rows": int(len(held)), "held_population": int(held.population.sum()),
        "same_year_coordinate_collisions_in_candidate_batch": int(pd.Series(keys).duplicated(keep=False).sum()),
        "selected_2021_population_denominator": int(selected_year.population.sum()),
        "selected_2021_population_after_direct_points": int(selected_year.loc[selected_year.source_record_id.astype(str).isin(set(good.source_record_id.astype(str))), "population"].sum()),
        "joint_axis_gain_only_for_existing_identity_path": int(good.loc[good.missing_joint_axis.eq("point"), "population"].sum()),
        "point_only_marginal_population": int(good.loc[good.missing_joint_axis.eq("identity_and_point"), "population"].sum()),
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in (CANDIDATES, SELECTED, POINTS)},
        "outputs": {str(p.name): {"sha256": sha(p), "bytes": p.stat().st_size} for p in (point_path, hold_path)},
        "limitations": ["This is 2021 coordinate-axis gain; it does not add same_place edges or census population values.", "Population/boundary comparability is not inferred.", "Any same-year coordinate shared with another candidate or accepted source row is held."],
    }
    (OUT / "application_receipt.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text("# Точки собственных записей 2021 года\n\nПрименено готовое правило точной исходной строки и локалитета ФИАС уровня 6 к подготовленной когорте текущих записей. Дубли одной точки в пределах переписного года удержаны. Пакет добавляет только координатную ось; он не создаёт межгодовых связей и не меняет население. У 23 строк уже есть межгодовая идентичность, поэтому для них координата одновременно закрывает совместную ось; остальные строки дают только пространственное покрытие.\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("candidate_rows", "candidate_population", "accepted_rows", "accepted_population", "held_rows", "held_population", "joint_axis_gain_only_for_existing_identity_path", "point_only_marginal_population")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
