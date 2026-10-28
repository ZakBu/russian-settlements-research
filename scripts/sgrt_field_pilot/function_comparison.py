"""Compare settlement-only population fields with published local service evidence.

Known presence, model choice and unknown local stock remain separate. No field
maximum changes a published centre or allocates municipal workers to settlements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


FAMILIES = ("school", "medical_basic", "grocery")
EVIDENCE_COLUMNS = (
    "provider_settlement_id", "provider_site_id", "provider_name", "cost_minutes", "known_local_supply",
    "local_service_present", "l0_admitted", "service_status", "route_status",
    "source_id", "source_year", "evidence_quality", "observed_flow",
    "provider_inventory_completeness", "provider_actual_operational_status_verified",
    "provider_historical_source_only", "provider_np_identity_is_cartographic",
    "school_stage_unknown", "unknown_reason",
    "provider_identity_known", "provider_np_identity_basis", "provider_cartographic_identity_status",
)


def _true(value):
    return pd.notna(value) and bool(value)


def compare_functions(roster, edges, units, reference=None):
    """One row per (pilot, source_record_id); unknown stocks are never zero.

    ``roster`` must have source_record_id and pilot_id (or one implicit pilot).
    Edges and centres are the unchanged published national service results.
    """
    roster = roster.copy()
    if "source_record_id" not in roster:
        raise ValueError("Roster needs the accepted source_record_id")
    if "pilot_id" not in roster:
        roster["pilot_id"] = roster["pilot"] if "pilot" in roster else "pilot"
    if roster.source_record_id.isna().any() or roster.duplicated(["pilot_id", "source_record_id"]).any():
        raise ValueError("Pilot/source identities must be non-null and unique")
    if units.centre_settlement_id.duplicated().any():
        raise ValueError("Published centre identities must be unique")
    selected = edges[edges.service_family.isin(FAMILIES)]
    if selected.duplicated(["origin_id", "service_family"]).any():
        raise ValueError("One selected service outcome per origin/family is required")
    names = {} if reference is None else reference.dropna(subset=["source_record_id"]).set_index("source_record_id").name.to_dict()
    for family in FAMILIES:
        part = selected[selected.service_family.eq(family)].set_index("origin_id")
        roster[family + "__source_row_present"] = roster.source_record_id.isin(part.index)
        for column in EVIDENCE_COLUMNS:
            if column in part:
                roster[family + "__" + column] = roster.source_record_id.map(part[column])
        states = []
        for identity in roster.source_record_id:
            if identity not in part.index:
                states.append("missing_origin_row_unknown")
                continue
            row = part.loc[identity]
            target = row.get("provider_settlement_id")
            known_local = _true(row.get("known_local_supply"))
            if known_local:
                if pd.notna(target) and target != identity:
                    raise ValueError("Known local stock cannot point to another settlement")
                states.append("known_local_presence_not_verified_operation")
            elif pd.notna(target) and target != identity and _true(row.get("l0_admitted")):
                states.append("model_external_admitted_local_stock_unknown")
            elif pd.notna(target) and target != identity:
                states.append("known_external_candidate_not_admitted_local_stock_unknown")
            elif pd.notna(row.get("provider_site_id")) and pd.isna(target):
                states.append("known_provider_site_np_identity_unknown_local_stock_unknown")
            else:
                states.append("direction_and_local_stock_unknown")
        roster[family + "__comparison_status"] = states
        if names:
            roster[family + "__target_settlement_name"] = roster[family + "__provider_settlement_id"].map(names)
        # It is a known subset count, never an estimate of total capacity.
        roster[family + "__local_function_known_present"] = roster[family + "__comparison_status"].eq("known_local_presence_not_verified_operation")
    centre_index = units.set_index("centre_settlement_id")
    registered = centre_index[centre_index.is_registered_external_serving_centre.fillna(False)]
    roster["published_external_serving_centre"] = roster.source_record_id.isin(registered.index)
    for column in ["unit_id", "external_participant_count", "own_known_basic_function_count",
                   "primary_external_positive_whole_records", "unit_role"]:
        if column in centre_index:
            roster["published_" + column] = roster.source_record_id.map(centre_index[column])
    roster["known_local_basic_function_count"] = sum(roster[f + "__local_function_known_present"].astype(int) for f in FAMILIES)
    roster["published_centres_preserved_by_comparison"] = True
    roster["population_peak_is_not_a_functional_centre_test"] = True
    return roster


def compare_peaks(functions, peaks, identity_column="source_record_id", peak_column="is_local_maximum"):
    """Retain every peak scenario; a missing peak row remains unknown."""
    if identity_column not in peaks or peak_column not in peaks:
        raise ValueError("Peak input needs explicit identity and boolean peak indicator")
    left = functions.copy()
    right = peaks.rename(columns={identity_column: "source_record_id", peak_column: "population_field_local_maximum"}).copy()
    keys = ["source_record_id"]
    if "pilot_id" in right:
        keys.insert(0, "pilot_id")
    reserved = set(left.columns) & (set(right.columns) - set(keys))
    right = right.drop(columns=list(reserved))
    out = left.merge(right, on=keys, how="left", validate="one_to_many")
    out["peak_result_present"] = out.population_field_local_maximum.notna()
    out["registered_centre_without_population_peak"] = (
        out.published_external_serving_centre
        & out.population_field_local_maximum.eq(False)
    ).where(out.peak_result_present, pd.NA).astype("boolean")
    out["population_peak_without_recorded_local_basic_functions"] = (
        out.population_field_local_maximum.eq(True)
        & out.known_local_basic_function_count.eq(0)
    ).where(out.peak_result_present, pd.NA).astype("boolean")
    return out


def summarize(functions):
    rows = []
    for pilot_id, group in functions.groupby("pilot_id", sort=True):
        slices = [("all_evaluation_30km", group)]
        if "evaluation_core" in group:
            slices += [("core_20km", group[group.evaluation_core]),
                       ("outer_20_to_30km", group[~group.evaluation_core])]
        for slice_name, sample in slices:
            row = {"pilot_id": pilot_id, "evaluation_slice": slice_name, "settlement_records": len(sample),
                   "published_external_serving_centres": int(sample.published_external_serving_centre.sum()),
                   "all_three_basic_functions_known_local": int(sample.known_local_basic_function_count.eq(3).sum())}
            if "population_2021" in sample:
                row["positive_population_records"] = int(sample.population_2021.gt(0).sum())
                row["zero_population_records"] = int(sample.population_2021.eq(0).sum())
                row["unknown_population_records"] = int(sample.population_2021.isna().sum())
            for family in FAMILIES:
                prefix = family + "__"
                local = sample[prefix + "local_function_known_present"]
                row[family + "_known_local_presence"] = int(local.sum())
                row[family + "_model_external_admitted"] = int(sample[prefix + "comparison_status"].eq("model_external_admitted_local_stock_unknown").sum())
                row[family + "_no_source_row_unknown"] = int((~sample[prefix + "source_row_present"]).sum())
                row[family + "_local_stock_unknown"] = int((~local).sum())
                row[family + "_known_site_np_identity_unknown"] = int(sample[prefix + "comparison_status"].eq("known_provider_site_np_identity_unknown_local_stock_unknown").sum())
                history = prefix + "provider_historical_source_only"
                row[family + "_known_local_historical_only"] = int((local & sample[history].eq(True)).sum()) if history in sample else None
            if "peak_result_present" in sample:
                row["peak_result_present_records"] = int(sample.peak_result_present.sum())
                row["registered_centre_without_population_peak"] = int(sample.registered_centre_without_population_peak.sum())
                row["population_peak_without_recorded_local_basic_functions"] = int(sample.population_peak_without_recorded_local_basic_functions.sum())
                row["sampled_population_maxima"] = int(sample.population_field_local_maximum.eq(True).sum())
            rows.append(row)
    return pd.DataFrame(rows)


def attach_municipal_context(roster, crosswalk, municipal):
    """Municipal context is not an allocated value for the settlement."""
    if crosswalk.source_record_id.duplicated().any() or municipal.oktmo.duplicated().any():
        raise ValueError("Municipal crosswalk and territory rows must be unique")
    crosswalk = crosswalk[["source_record_id", "matched_2021_parent_code", "parent_scope_basis"]]
    fields = ["oktmo", "municipality", "year", "indicator_name", "indicator_unit",
              "partial_organisation_workers_2025_territorial",
              "territorial_boundary_2021_2025_equality_verified"]
    out = roster.merge(crosswalk, how="left", on="source_record_id", validate="many_to_one")
    out = out.merge(municipal[fields], how="left", left_on="matched_2021_parent_code", right_on="oktmo", validate="many_to_one")
    out["municipal_workers_are_not_settlement_jobs"] = True
    out["municipal_workers_are_not_resident_employment"] = True
    return out


def municipal_sector_context(crosswalk, workforce_raw):
    """Return actual annual sector rows for known parent codes, never NP shares.

    Section A combines agriculture, forestry, hunting and fishing. This module
    does not turn missing/suppressed sector values into a zero or residual.
    """
    codes = set(crosswalk.matched_2021_parent_code.dropna())
    raw = workforce_raw
    keep = (raw.oktmo.isin(codes) & raw.indicator_code.eq("Y48423005")
            & raw.indicator_period.eq("Январь-декабрь") & raw.year.isin([2021, 2025]))
    result = raw[keep].copy()
    key = ["oktmo", "year", "okved2", "indicator_code", "indicator_period"]
    if result.duplicated(key).any():
        raise ValueError("Duplicate annual municipal sector source keys")
    if not result.indicator_unit.eq("Человек").all():
        raise ValueError("Unexpected sector workforce unit")
    result["workers_allocated_to_np"] = False
    result["section_A_is_not_pure_agriculture"] = True
    result["boundary_equality_to_2021_not_proven"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--peaks", type=Path)
    parser.add_argument("--peak-column", default="is_local_maximum")
    parser.add_argument("--municipal-crosswalk", type=Path)
    parser.add_argument("--municipal-profiles", type=Path)
    parser.add_argument("--municipal-workforce-raw", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    read = lambda p: pd.read_csv(p) if p.suffix == ".csv" else pd.read_parquet(p)
    ref = read(args.reference) if args.reference else None
    result = compare_functions(read(args.roster), read(args.edges), read(args.units), ref)
    args.output.mkdir(parents=True, exist_ok=True)
    result.to_parquet(args.output / "settlement_function_comparison.parquet", index=False)
    summary = summarize(result)
    summary.to_csv(args.output / "function_summary.csv", index=False)
    if args.peaks:
        joined = compare_peaks(result, read(args.peaks), peak_column=args.peak_column)
        joined.to_parquet(args.output / "field_function_comparison.parquet", index=False)
        scenarios = [x for x in ["kernel", "half_time_minutes", "include_self", "neighbor_count"] if x in joined]
        peak_summary = []
        groups = joined.groupby(scenarios, dropna=False) if scenarios else [((), joined)]
        for key, group in groups:
            key = key if isinstance(key, tuple) else (key,)
            table = summarize(group)
            for column, value in zip(scenarios, key):
                table[column] = value
            peak_summary.append(table)
        pd.concat(peak_summary, ignore_index=True).to_csv(args.output / "field_function_summary.csv", index=False)
    if bool(args.municipal_crosswalk) != bool(args.municipal_profiles):
        raise ValueError("Both municipal source tables are required together")
    if args.municipal_crosswalk:
        context = attach_municipal_context(result[["pilot_id", "source_record_id"]], read(args.municipal_crosswalk), read(args.municipal_profiles))
        context.to_parquet(args.output / "municipal_context_not_np_jobs.parquet", index=False)
        if args.municipal_workforce_raw:
            municipal_sector_context(context, read(args.municipal_workforce_raw)).to_parquet(args.output / "municipal_sector_source_context.parquet", index=False)
    elif args.municipal_workforce_raw:
        raise ValueError("Sector context requires a verified parent crosswalk and profiles")
    inputs = {}
    for name in ["roster", "edges", "units", "reference", "peaks", "municipal_crosswalk", "municipal_profiles", "municipal_workforce_raw"]:
        path = getattr(args, name)
        if path:
            inputs[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    (args.output / "summary.json").write_text(json.dumps({"schema": "sgrt.field_function_comparison.v1", "inputs": inputs, "pilots": summary.to_dict("records"), "functions_are_known_subset_not_capacity": True, "service_choices_are_not_observed_trips": True, "base_and_existing_centres_unchanged": True}, ensure_ascii=False, indent=2) + "\n")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
