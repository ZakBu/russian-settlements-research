"""Reproducible descriptive tables for the national report; no source mutations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(base: Path, allow_pending_places: bool = False) -> None:
    root = base / "national_integration_20261019"
    out = root / "report_tables"
    inputs = [
        root / "core/feature_master.parquet",
        root / "screening/support_point_profiles.parquet",
        root / "core/MASTER_AUDIT.json",
        root / "screening/SCREENING_AUDIT.json",
        root / "documented_evidence/documentary_vs_mass_sources.csv",
        root / "documented_evidence/AUDIT.json",
    ]
    initial_hashes = {str(p.relative_to(base)): sha(p) for p in inputs}
    source_audit = json.loads(inputs[3].read_text())
    declared_master = source_audit["inputs"]["national_integration_20261019/core/feature_master.parquet"]
    assert declared_master["sha256"] == sha(inputs[0]), "Screening belongs to another master version; rebuild screening first"
    places_loaded = bool(source_audit["places_loaded"])
    if not places_loaded and not allow_pending_places:
        raise RuntimeError("Final report requires a completed Places layer and refreshed screening")
    master = pd.read_parquet(inputs[0])
    profiles = pd.read_parquet(inputs[1])
    if places_loaded:
        primary_groups = [c for c in profiles if c.startswith("baseline_function_") and c.endswith("_witness")]
        assert len(primary_groups) == 11 and "baseline_function_trade_access_witness" in primary_groups, "Await the final 11-group construct; do not publish the superseded retail/pickup split"
    assert len(master) == len(profiles) == 142570
    assert master.id.notna().all() and master.id.is_unique
    assert profiles.id.notna().all() and profiles.id.is_unique
    assert set(master.id) == set(profiles.id)
    profiles = profiles.set_index("id").loc[master.id].reset_index()
    assert np.array_equal(master.id.to_numpy(), profiles.id.to_numpy())
    population = pd.to_numeric(master.population_2021, errors="coerce")
    assert population.dropna().ge(0).all()
    n = len(master)
    total_population = float(population.sum(min_count=1))

    legal_years = [f"econ_native_{y}_legal_entities" for y in range(2011, 2026)]
    signals = {
        "organization_any_year_2011_2025": master[legal_years].gt(0).any(axis=1),
        "organization_2025": master.econ_native_2025_legal_entities.gt(0),
        "consumer_legal_2025": profiles.legal_native_function_diversity.gt(0),
        "consumer_legal_conditional_2025": profiles.legal_conditional_function_diversity.gt(0),
        "places_baseline_snapshot": profiles.physical_baseline_function_diversity.gt(0),
        "places_conditional_snapshot": profiles.physical_conditional_function_diversity.gt(0),
        "wb_strict_all_types_snapshot": master.wb_strict_all_types_locations.gt(0),
        "wb_strict_focus_types_snapshot": profiles.wb_strict_focus_published_locations.gt(0),
        "municipal_agricultural_series": master.agri_municipality_series_matched,
        "municipal_agricultural_valid_profile_2021": master.agri_profile2021_covered,
        "baseline_any_function": profiles.baseline_function_diversity.gt(0),
        "baseline_multiple_functions": profiles.baseline_function_diversity.ge(2),
        "conditional_any_function": profiles.conditional_function_diversity.gt(0),
        "conditional_multiple_functions": profiles.conditional_function_diversity.ge(2),
    }
    signals = {k: pd.Series(v, dtype="boolean") for k, v in signals.items()}
    # Entire missing sources remain unknown even if a dependency uses float NaN comparisons.
    if not places_loaded:
        for k in ["places_baseline_snapshot", "places_conditional_snapshot"]:
            signals[k] = pd.Series(pd.NA, index=master.index, dtype="boolean")

    def fraction(num: float, den: float) -> float:
        return float(num / den * 100) if den else np.nan

    def summarize(index, group_kind, group_name):
        population_group = population.loc[index]
        pop_sum = float(population_group.sum(min_count=1))
        result = []
        for layer, signal in signals.items():
            q = signal.loc[index]
            positive = q.fillna(False)
            count = int(positive.sum())
            covered_pop = float(population_group.loc[positive].sum())
            observed_source = bool(q.notna().any())
            result.append({
                "group_kind": group_kind, "group": str(group_name), "layer": layer,
                "n_axis": len(index), "n_status_known": int(q.notna().sum()),
                "n_source_positive": count if observed_source else np.nan,
                "n_source_unknown": int(q.isna().sum()),
                "axis_share_percent": fraction(count, len(index)) if observed_source else np.nan,
                "population_2021_known_sum": pop_sum,
                "population_2021_in_positive_points": covered_pop if observed_source else np.nan,
                "population_2021_share_percent": fraction(covered_pop, pop_sum) if observed_source else np.nan,
                "denominator_kind": "frozen_axis_points_or_known_census2021_population",
                "source_zero_is_not_real_world_absence": True,
            })
        return result

    national = pd.DataFrame(summarize(master.index, "national", "all_frozen_axis"))
    regional = []
    for region, indices in master.groupby("region", dropna=False).groups.items():
        regional.extend(summarize(indices, "region", region))

    labels = ["0", "1-99", "100-499", "500-1999", "2000-9999", "10000+", "unknown"]
    size = pd.Series("unknown", index=master.index, dtype="object")
    size.loc[population.eq(0)] = "0"
    for lo, hi, label in [(1, 99, "1-99"), (100, 499, "100-499"),
                           (500, 1999, "500-1999"), (2000, 9999, "2000-9999")]:
        size.loc[population.between(lo, hi)] = label
    size.loc[population.ge(10000)] = "10000+"
    by_size, diversity = [], []
    for label in labels:
        indices = master.index[size.eq(label)]
        by_size.extend(summarize(indices, "census_population_size", label))
        q = profiles.loc[indices, "baseline_function_diversity"]
        diversity.append({"population_size": label, "n_axis": len(indices),
                          "baseline_diversity_known_n": int(q.notna().sum()),
                          "baseline_diversity_mean": q.mean(),
                          "baseline_diversity_median": q.median(),
                          "baseline_diversity_ge2_n": int(q.ge(2).sum()),
                          "baseline_diversity_ge2_percent": fraction(int(q.ge(2).sum()), len(indices))})
    assert sum(x["n_axis"] for x in diversity) == n

    source_pattern = pd.DataFrame({
        "legal_native": signals["consumer_legal_2025"],
        "physical_baseline": signals["places_baseline_snapshot"],
        "wb_strict_focus": signals["wb_strict_focus_types_snapshot"],
        "population_2021": population,
    })
    agreement = source_pattern.groupby(["legal_native", "physical_baseline", "wb_strict_focus"],
                                       dropna=False).agg(n_axis=("population_2021", "size"),
                                                        population_2021=("population_2021", "sum")).reset_index()
    agreement["axis_share_percent"] = agreement.n_axis / n * 100
    assert agreement.n_axis.sum() == n

    functions = []
    for c in profiles.columns:
        if c.startswith("baseline_function_") and c.endswith("_witness"):
            mask = profiles[c].astype("boolean").fillna(False)
            functions.append({"function": c[len("baseline_function_"):-len("_witness")],
                              "n_source_positive": int(mask.sum()),
                              "axis_share_percent": int(mask.sum()) / n * 100,
                              "population_2021_in_positive_points": float(population.loc[mask].sum())})
    pairs = {
        "organization_any_year_and_wb_all_types_and_agri2021":
            signals["organization_any_year_2011_2025"] & signals["wb_strict_all_types_snapshot"]
            & signals["municipal_agricultural_valid_profile_2021"],
        "consumer_legal2025_and_wb_focus":
            signals["consumer_legal_2025"] & signals["wb_strict_focus_types_snapshot"],
        "consumer_legal2025_and_physical_baseline":
            signals["consumer_legal_2025"] & signals["places_baseline_snapshot"],
    }
    joint = pd.DataFrame([{"combination": k, "n_axis": n, "n_positive": int(v.fillna(False).sum()),
                           "percent": int(v.fillna(False).sum()) / n * 100,
                           "unknown_n": int(v.isna().sum())} for k, v in pairs.items()])
    iterations = []
    initial = root / "screening/INITIAL_WITHOUT_PLACES_SCREENING_AUDIT.json"
    if initial.exists():
        old = json.loads(initial.read_text())
        for source in ["baseline", "conditional", "physical_baseline", "legal_native", "wb_strict"]:
            before = old["profile_counts"].get(source, {})
            after = source_audit["profile_counts"].get(source, {})
            for status in sorted(set(before) | set(after)):
                iterations.append({"source": source, "status": status,
                                   "initial_n": before.get(status, 0), "current_n": after.get(status, 0),
                                   "difference": after.get(status, 0) - before.get(status, 0),
                                   "comparison": "source_and_construct_iteration_not_historical_change",
                                   "classification_definition_changed": True})

    documented = pd.read_csv(inputs[4])
    documentary_control = []
    for function, legal_column in [("education", "econ_native_2025_education85_legal_entities"),
                                    ("health", "econ_native_2025_health86_legal_entities")]:
        q = documented[documented[f"documentary_{function}_external_witness"]]
        documentary_control.append({
            "function": function, "documented_provider_UID": len(q),
            "baseline_POI_positive_UID": int(q[f"published_POI_baseline_{function}_witness"].sum()),
            "conditional_POI_positive_UID": int(q[f"published_POI_conditional_{function}_witness"].sum()),
            "native_legal_positive_UID_2025": int(q[legal_column].gt(0).sum()),
            "sample_kind": "previous_selected_nonblind_documentary_corpus_not_national_accuracy",
            "observation_dates_are_mixed": True,
        })
    assert len(documented) == documented.id.nunique() == 17
    assert documentary_control[0]["documented_provider_UID"] == 16
    assert documentary_control[1]["documented_provider_UID"] == 2
    case_uid = "np3:p-LhnKirDV_v-5toCw1SuLxV_fTVDKu7egUwIhwNkT0"
    case_columns = ["id", "name", "region", "population_2021", "baseline_function_diversity",
                    "conditional_function_diversity", "baseline_profile_signature", "conditional_profile_signature"]
    illustrative_cases = profiles.loc[profiles.id.eq(case_uid), case_columns].copy()
    assert len(illustrative_cases) == 1
    illustrative_cases["selection_scope"] = "selected_illustrative_case_not_blind_validation"

    assert int(national.set_index("layer").loc["consumer_legal_2025", "n_source_positive"]) == 12097
    observed_multiple = int(profiles.baseline_function_diversity.ge(2).sum())
    assert observed_multiple == source_audit["profile_counts"]["baseline"].get("multiple_observed_functions", 0)
    assert all(initial_hashes[str(p.relative_to(base))] == sha(p) for p in inputs), "Input changed during report calculation"
    out.mkdir(exist_ok=True)
    frames = {
        "source_coverage.csv": national, "coverage_by_region.csv": pd.DataFrame(regional),
        "coverage_by_population_size.csv": pd.DataFrame(by_size),
        "diversity_by_population_size.csv": pd.DataFrame(diversity),
        "source_agreement.csv": agreement, "function_group_counts.csv": pd.DataFrame(functions),
        "joint_layer_coverage.csv": joint, "change_between_iterations.csv": pd.DataFrame(iterations),
        "documentary_control.csv": pd.DataFrame(documentary_control),
        "illustrative_cases.csv": illustrative_cases,
    }
    for name, frame in frames.items():
        frame.to_csv(out / name, index=False)
    audit = {
        "status": "FINAL_INPUT_TABLES_COMPUTED" if places_loaded else "PRELIMINARY_PLACES_PENDING",
        "axis_rows": n, "master_columns": len(master.columns), "profile_columns": len(profiles.columns),
        "places_loaded": places_loaded, "population_2021_denominator": total_population,
        "regions_observed": int(master.region.nunique()), "one_point_weight": True,
        "p_values_or_causal_effects_computed": False, "sources": initial_hashes,
        "code_sha256": sha(Path(__file__)),
        "output": {name: {"rows": len(frame), "sha256": sha(out / name)} for name, frame in frames.items()},
        "interpretation": "Descriptive source coverage; population shares refer to residents of source-positive points, not service users or catchments",
    }
    (out / "AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k not in ["sources", "output"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--allow-pending-places", action="store_true")
    args = parser.parse_args()
    run(args.base.resolve(), args.allow_pending_places)
