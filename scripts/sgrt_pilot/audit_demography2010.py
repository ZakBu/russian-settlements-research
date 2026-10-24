#!/usr/bin/env python3
"""Compare dated 2010 source variants without changing the accepted population base.

Inputs are obtained by scripts/research_data.py. Detailed outputs belong outside
Git, in a versioned data release. The classification is a diagnostic of settlement
trajectories, not the nine functional SGRT types and not an error-rate estimate.
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

PILOTS = {"удмуртская": "Удмуртия", "вологодская": "Вологодская область", "челябинская": "Челябинская область"}
PROTECTED = "secondary_confidentiality_protected_value_exact_scope_unverified"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def valid_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def state(initial, final, years: int, threshold: float = 0.0025) -> str:
    """A nonnegative census pair; both-zero is distinct from stability."""
    if years <= 0 or not 0 <= threshold < 1:
        raise ValueError("positive year span and threshold in [0,1) required")
    if not valid_number(initial) or not valid_number(final):
        return "unknown"
    if initial == final == 0:
        return "zero_both"
    if initial == 0:
        return "zero_to_positive"
    if final == 0:
        return "positive_to_zero"
    annual_log = (math.log(final) - math.log(initial)) / years
    if annual_log > math.log1p(threshold) + 1e-14:
        return "growth"
    if annual_log < math.log1p(-threshold) - 1e-14:
        return "decline"
    return "stable"


def trajectory(row: dict, p2010: float, threshold: float) -> tuple[str, str]:
    return (state(row["population_2002"], p2010, 8, threshold),
            state(p2010, row["population_2021"], 11, threshold))


def complete(row: dict) -> bool:
    return all(valid_number(row[k]) for k in ["population_2002", "population_2010", "effective_population_2010", "population_2021"])


def csv_write(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def region_of(row: dict) -> str:
    return row.get("region_norm_2021") or row.get("region_norm_2010") or row.get("region_norm_2002") or "unknown"


def summarize(rows, label, region, threshold):
    eligible = [r for r in rows if complete(r)]
    pairs = [(trajectory(r, r["population_2010"], threshold), trajectory(r, r["effective_population_2010"], threshold)) for r in eligible]
    changed = sum(a != b for a, b in pairs)
    return {
        "scope": label, "region": region, "annual_threshold": threshold,
        "rows_total": len(rows), "complete_triples_denominator": len(eligible),
        "overlay_rows_total": sum(bool(r["population_overlay_applied_2010"]) for r in rows),
        "numeric2010_changed_rows_total": sum(r["population_2010"] != r["effective_population_2010"] for r in rows),
        "trajectory_changed_numerator": changed,
        "trajectory_changed_percent": 100 * changed / len(eligible) if eligible else None,
        "period2002_2010_state_changed": sum(a[0] != b[0] for a, b in pairs),
        "period2010_2021_state_changed": sum(a[1] != b[1] for a, b in pairs),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population-dir", type=Path, required=True)
    parser.add_argument("--accepted-overlay", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, help="Optional hydrated research/sgrt_word_completion_20261021 directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    wide_path = args.population_dir / "settlements_census_wide.parquet"
    long_path = args.population_dir / "settlements_census_long.parquet"
    inputs = [wide_path, long_path, args.accepted_overlay]
    hashes_before = {str(p): sha256(p) for p in inputs}
    rows = pq.read_table(wide_path).to_pylist()
    raw2010 = pq.read_table(long_path, filters=[("census_year", "=", 2010)]).to_pylist()
    if len({r["root"] for r in rows}) != len(rows):
        raise ValueError("duplicate accepted root")
    if len({r["source_record_id"] for r in raw2010}) != len(raw2010):
        raise ValueError("duplicate source_record_id in 2010")
    by_source = {r["source_record_id"]: r for r in raw2010}
    with gzip.open(args.accepted_overlay, "rt", encoding="utf-8") as handle:
        overlay = list(csv.DictReader(handle))
    overlay_ids = [r["original_source_record_id"] for r in overlay]
    if len(set(overlay_ids)) != len(overlay_ids):
        raise ValueError("duplicate accepted-overlay source ID")
    flagged = {r["source_record_id"] for r in raw2010 if r["population_overlay_applied"]}
    if set(overlay_ids) != flagged:
        raise ValueError("accepted overlay IDs do not match base flags")
    overlay_map = {r["original_source_record_id"]: r for r in overlay}
    for uid, record in overlay_map.items():
        if float(record["population"]) != by_source[uid]["effective_population"]:
            raise ValueError(f"accepted-overlay value mismatch: {uid}")
        if not all(record[k] for k in ["population_source_record_id", "population_source_path", "population_source_sha256", "population_source_locator"]):
            raise ValueError(f"incomplete accepted-overlay provenance: {uid}")

    # Quality belongs to a numeric source variant, not to the shared settlement ID.
    qualities = collections.Counter()
    source_populations = collections.Counter()
    for row in raw2010:
        effective_quality = overlay_map.get(row["source_record_id"], {}).get("population_value_quality", row["population_value_quality"])
        for variant, quality in [("raw", row["population_value_quality"]), ("effective", effective_quality)]:
            for region in ["Россия: все исходные строки 2010", row["region_norm"] or "unknown"]:
                qualities[(region, variant, quality or "unknown")] += 1
        if row["source_record_id"] in overlay_map:
            source_populations[Path(overlay_map[row["source_record_id"]]["population_source_path"]).name] += 1
    csv_write(args.output / "source_quality_counts.csv", [
        {"region": region, "variant": variant, "quality": quality, "rows": count}
        for (region, variant, quality), count in sorted(qualities.items())
    ])
    summaries = []
    for threshold in [0.0, 0.001, 0.0025, 0.005]:
        for label, subset in [
            ("all_accepted_components", rows),
            ("ordinary_full3", [r for r in rows if r["ordinary_full3"]]),
            ("accepted_overlay_components", [r for r in rows if r["population_overlay_applied_2010"]]),
        ]:
            summaries.append(summarize(subset, label, "Россия", threshold))
        for region, title in PILOTS.items():
            subset = [r for r in rows if region_of(r) == region]
            summaries.append(summarize(subset, "pilot_all_components", title, threshold))
            summaries.append(summarize([r for r in subset if r["ordinary_full3"]], "pilot_ordinary_full3", title, threshold))
    csv_write(args.output / "raw_effective_sensitivity.csv", summaries)
    details = []
    for row in rows:
        if not row["population_overlay_applied_2010"]:
            continue
        old, new = trajectory(row, row["population_2010"], .0025), trajectory(row, row["effective_population_2010"], .0025)
        source = overlay_map[row["source_record_id_2010"]]
        details.append({
            "root": row["root"], "source_record_id_2010": row["source_record_id_2010"],
            "region": region_of(row), "name": row["settlement_name_2021"] or row["settlement_name_2010"],
            "population_2002": row["population_2002"], "population_2010_raw": row["population_2010"],
            "population_2010_effective": row["effective_population_2010"], "population_2021": row["population_2021"],
            "ordinary_full3": row["ordinary_full3"], "raw_quality_2010": row["population_value_quality_2010"],
            "effective_quality_2010": source["population_value_quality"],
            "raw_state2002_2010": old[0], "raw_state2010_2021": old[1],
            "effective_state2002_2010": new[0], "effective_state2010_2021": new[1],
            "complete_pair_comparison": complete(row), "trajectory_changed": old != new,
            "primary_source_record_id": source["population_source_record_id"],
            "primary_source_path": source["population_source_path"],
            "primary_source_sha256": source["population_source_sha256"],
            "primary_source_locator": source["population_source_locator"],
        })
    pq.write_table(pa.Table.from_pylist(details), args.output / "accepted_overlay_trajectory_comparison.parquet", compression="zstd")

    historical_summary = None
    if args.historical_root:
        old_axis_path = args.historical_root / "axis/full_settlement_axis.parquet"
        old_audit_path = args.historical_root / "analysis/node_source2010_recovery_audit.parquet"
        for path in [old_axis_path, old_audit_path]:
            hashes_before[str(path)] = sha256(path)
        axis = {r["id"]: r for r in pq.read_table(old_axis_path).to_pylist()}
        cohort = [r for r in pq.read_table(old_audit_path).to_pylist() if r["recovered2010_reviewed_primary2010_override_allowed"]]
        if len({r["id"] for r in cohort}) != len(cohort):
            raise ValueError("duplicate historical primary comparison ID")
        historical = []
        for threshold in [0.0, 0.001, 0.0025, 0.005]:
            for region in ["all_four_regions"] + sorted({axis[r["id"]]["region"] for r in cohort}):
                sub = [r for r in cohort if region == "all_four_regions" or axis[r["id"]]["region"] == region]
                eligible = [r for r in sub if valid_number(r["original_population_2010"]) and valid_number(r["population_2010"]) and valid_number(axis[r["id"]]["population_2021"])]
                changed = sum(state(r["original_population_2010"], axis[r["id"]]["population_2021"], 11, threshold) != state(r["population_2010"], axis[r["id"]]["population_2021"], 11, threshold) for r in eligible)
                historical.append({"region": region, "annual_threshold": threshold, "cohort_rows": len(sub), "complete2010_2021_denominator": len(eligible), "state2010_2021_changed_numerator": changed, "state_changed_percent": 100 * changed / len(eligible) if eligible else None})
        csv_write(args.output / "historical_four_region_sensitivity.csv", historical)
        # Reattach only by literal accepted 2010 source ID. Never overwrite base.
        accepted_by2010 = {r["source_record_id_2010"]: r for r in rows if r["source_record_id_2010"]}
        candidate = []
        candidate_current_rows = []
        unmatched = 0
        for record in cohort:
            old = axis[record["id"]]
            uid = old["source_record_id_2010"]
            current = accepted_by2010.get(uid)
            if current is None:
                unmatched += 1
                continue
            raw = record["original_population_2010"]
            reviewed = record["recovered2010_reviewed_primary2010_population"]
            comparison = dict(current)
            comparison["population_2010"] = current["effective_population_2010"]
            comparison["effective_population_2010"] = reviewed
            comparison["population_overlay_applied_2010"] = True
            candidate_current_rows.append(comparison)
            candidate.append({
                "source_record_id_2010": uid, "root": current["root"],
                "historical_axis_id": record["id"], "region": region_of(current),
                "name": current["settlement_name_2021"] or current["settlement_name_2010"],
                "accepted_raw2010": current["population_2010"], "accepted_effective2010": current["effective_population_2010"],
                "historical_axis_original2010": raw, "reviewed_primary2010_candidate": reviewed,
                "historical_original_matches_current_effective": raw == current["effective_population_2010"],
                "candidate_changes_effective2010": reviewed != current["effective_population_2010"],
                "accepted_ordinary_full3": current["ordinary_full3"],
                "reviewed_quality": record["recovered2010_reviewed_primary2010_quality"],
                "primary_source_sha256": record["recovered2010_source_sha256"],
                "primary_source_path": record["recovered2010_source_path"],
                "primary_source_locator": record["recovered2010_source_record_id"],
                "original_official_url": record["recovered2010_source_original_official_URL"],
                "archived_retrieval_url": record["recovered2010_source_archived_retrieval_URL"],
                "historical_boundary_equivalence_assumed": record["recovered2010_source_2010_boundary_equals2021_boundary_assumed"],
                "historical_boundary_equivalence_proven": None,
            })
        pq.write_table(pa.Table.from_pylist(candidate), args.output / "historical_primary_candidates_on_accepted_ids.parquet", compression="zstd")
        candidate_summaries = []
        for threshold in [0.0, 0.001, 0.0025, 0.005]:
            for region in ["all_four_regions"] + sorted({region_of(r) for r in candidate_current_rows}):
                subset = [r for r in candidate_current_rows if region == "all_four_regions" or region_of(r) == region]
                candidate_summaries.append(summarize(subset, "historical_regional_candidate_on_current_base", region, threshold))
                candidate_summaries.append(summarize([r for r in subset if r["ordinary_full3"]], "historical_regional_candidate_on_current_full3", region, threshold))
        csv_write(args.output / "historical_candidate_current_base_sensitivity.csv", candidate_summaries)
        historical_summary = {"cohort_rows": len(cohort), "matched_current_2010_id": len(candidate), "unmatched": unmatched, "matched_original_equals_accepted_effective": sum(r["historical_original_matches_current_effective"] for r in candidate), "candidate_changes_current_effective": sum(r["candidate_changes_effective2010"] for r in candidate), "admitted_to_base": False, "original_primary_documents_reread": False}

    if any(sha256(Path(p)) != expected for p, expected in hashes_before.items()):
        raise ValueError("input changed during audit")
    result = {
        "question": "Sensitivity of settlement demographic states to explicit 2010 source variants, not functional SGRT types or national error rate",
        "input_sha256": hashes_before,
        "source2010_rows": len(raw2010),
        "raw_protected_secondary_rows": sum(r["population_value_quality"] == PROTECTED for r in raw2010),
        "effective_protected_secondary_rows": sum(overlay_map.get(r["source_record_id"], {}).get("population_value_quality", r["population_value_quality"]) == PROTECTED for r in raw2010),
        "accepted_overlay_rows": len(overlay),
        "accepted_overlay_numeric_changed": sum(float(r["population"]) != float(r["original_population"]) for r in overlay),
        "accepted_overlay_sources": dict(source_populations),
        "accepted_overlay_complete_provenance_rows": len(overlay),
        "source13percent_claim": "Exact original calculation/denominator not identified; tested definitions and denominators are in sensitivity CSVs; no national 13% estimate endorsed",
        "default_annual_stability_threshold": .0025,
        "threshold_meaning": "Analytical convention reused for comparability; not a statistical confidence band; sensitivity includes 0, 0.001, 0.005",
        "zero_states": ["zero_both", "zero_to_positive", "positive_to_zero"],
        "historical_four_region_comparison": historical_summary,
        "limitations": ["A protected secondary number is not necessarily an imputation; exact scope remains unverified", "Only explicit source variants are compared; unobserved source errors are not measured", "Cross-year population boundaries remain unproven", "Settlement trajectory changes do not equal SGRT type changes", "Historical regional supplements remain candidates separate from immutable accepted base"],
    }
    (args.output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
