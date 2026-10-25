"""Audit upper-MO population exclusions without changing analytical membership.

Run nonshop_population_contexts.py first in the restored CI environment.
Every match below is diagnostic; no value is imputed, joined or substituted.
"""
from pathlib import Path
import json
import math
import hashlib
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "work/ecommerce_extension_outcomes"
SOURCE = BASE / "raw/data_Y48112027_112_v20260928.parquet"
PANEL = BASE / "nonshop_population_contexts"
OUT = PANEL / "source_coverage_diagnostics"
OUT.mkdir(parents=True, exist_ok=True)
KEY = "source_record_id_2021"
YEARS = [2023, 2024, 2025]
UPPER = "Муниципальное образование верхнего уровня"
ALLOWED = {
    "Муниципальный район", "Муниципальный округ", "Городской округ",
    "Городской округ, городской округ с внутригородским делением",
    "Городской округ с внутригородским делением",
    "Внутригородская территория города федерального значения",
}

def true(v):
    return str(v).strip().casefold() in {"true", "1"}

def safe(v):
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v if isinstance(v, (str, int, float, bool)) else str(v)

def records(frame):
    return [{k: safe(v) for k, v in r.items()} for r in frame.to_dict("records")]

pop = pd.read_parquet(SOURCE)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == (
    "0229e7d0186f2f6ad750b0dcbce501056af0770112d52cda020ba9820492402b"
)
ex = pd.read_csv(PANEL / "excluded_centres.csv", dtype=str, keep_default_na=False)
rel = pd.read_csv(PANEL / "registry_relations_before_selection.csv",
                  dtype=str, keep_default_na=False)
p = pop.loc[pop.year.isin(YEARS)].copy()
p["source_row_index"] = p.index
# Exact string conversion deliberately does NOT zfill, strip or parse codes.
p["exact_oktmo_string"] = p.oktmo.map(str)
p["exact_stable_string"] = p.oktmo_stable.map(str)
p["matches_population_cell"] = (
    p.mest.eq("Все население")
    & p.indicator_period.eq("На 1 января")
    & p.indicator_unit.eq("Человек")
)
p["matches_upper_level"] = p.mun_level.eq(UPPER)
p["matches_allowed_type"] = p.mun_type.isin(ALLOWED)
p["matches_complete_filter"] = (
    p.matches_population_cell & p.matches_upper_level & p.matches_allowed_type
)
counts = p.groupby(["year", "mun_level", "mun_type"], dropna=False).size().reset_index(name="rows_n")
counts.to_csv(OUT / "raw_counts_year_level_type.csv", index=False)
cell_counts = p.loc[p.matches_population_cell].groupby(
    ["year", "mun_level", "mun_type"], dropna=False
).size().reset_index(name="rows_n")
cell_counts.to_csv(OUT / "population_cell_counts_year_level_type.csv", index=False)

shared = ex.loc[
    ex.medium_primary2002.map(true)
    & ex.shared_centre2020.map(true)
    & ex.reason.eq("incomplete_upper_municipality_panel")
].copy()
missing = []
for r in shared.to_dict("records"):
    for code, year in json.loads(r["missing_keys"]):
        m = p.exact_oktmo_string.eq(str(code)) & p.year.eq(int(year))
        s = p.exact_stable_string.eq(str(code)) & p.year.eq(int(year))
        g = p.loc[m]
        f = g.loc[g.matches_complete_filter]
        missing.append({
            KEY: r[KEY], "name_2021": r["name_2021"],
            "region_2021": r["region_2021"],
            "requested_oktmo_exact": str(code), "year": int(year),
            "exact_oktmo_raw_rows_n": int(m.sum()),
            "exact_stable_raw_rows_n": int(s.sum()),
            "exact_oktmo_population_cells_n": int(g.matches_population_cell.sum()),
            "exact_oktmo_upper_population_cells_n": int(
                (g.matches_population_cell & g.matches_upper_level).sum()
            ),
            "exact_oktmo_complete_filter_rows_n": int(len(f)),
            "complete_filter_distinct_values": json.dumps(
                [safe(v) for v in f.indicator_value.unique()], ensure_ascii=False
            ),
            "raw_types": json.dumps(sorted(set(g.mun_type.map(str))), ensure_ascii=False),
            "raw_levels": json.dumps(sorted(set(g.mun_level.map(str))), ensure_ascii=False),
        })
missing = pd.DataFrame(missing)
missing.to_csv(OUT / "all_shared_context_missing_exact_codes.csv", index=False)

requested = set(missing.requested_oktmo_exact) if not missing.empty else set()
targets = {"05706000", "61705000", "36708000"}
cols = ["source_row_index", "oktmo", "oktmo_stable", "exact_oktmo_string",
        "exact_stable_string", "year", "mun_level", "mun_type", "municipality",
        "mest", "indicator_period", "indicator_unit", "indicator_value",
        "oktmo_history", "oktmo_year_from", "oktmo_year_to",
        "matches_population_cell", "matches_upper_level", "matches_allowed_type",
        "matches_complete_filter"]
cols = [c for c in cols if c in p]
match = p.exact_oktmo_string.isin(requested) | p.exact_stable_string.isin(requested)
p.loc[match, cols].to_csv(OUT / "raw_candidates_for_all_missing_codes.csv", index=False)
exact = p.exact_oktmo_string.isin(targets) | p.exact_stable_string.isin(targets)
target_rows = p.loc[exact, cols].copy()
target_rows["diagnostic_match"] = "exact_oktmo_or_exact_stable"
# Leading-zero loss check is reported as CANDIDATE ONLY, never used in analysis.
target_numeric = {str(int(c)) for c in targets}
numeric_match = (
    p.exact_oktmo_string.isin(target_numeric)
    | p.exact_stable_string.isin(target_numeric)
) & ~exact
numeric_rows = p.loc[numeric_match, cols].copy()
numeric_rows["diagnostic_match"] = "numeric_string_candidate_only_NOT_A_JOIN"
target_rows = pd.concat([target_rows, numeric_rows], ignore_index=True)
target_rows.to_csv(OUT / "three_requested_codes_raw_candidates.csv", index=False)
missing_unique = (
    missing.drop_duplicates(["requested_oktmo_exact", "year"])
    if not missing.empty else missing
)
summary = {
    "source_path": str(SOURCE.relative_to(ROOT)),
    "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    "source_code_dtypes": {c: str(pop[c].dtype) for c in ["oktmo", "oktmo_stable", "year"]},
    "source_columns": list(pop.columns),
    "raw_counts_year_level_type": records(counts),
    "population_cell_counts_year_level_type": records(cell_counts),
    "accepted_medium_shared_registry_n": int((
        rel.medium_primary2002.map(true) & rel.shared_centre2020.map(true)
    ).sum()),
    "excluded_shared_incomplete_municipal_n": int(len(shared)),
    "all_shared_missing_exact_codes": {
        "columns": list(missing_unique.columns),
        "rows": [[safe(v) for v in row] for row in missing_unique.itertuples(index=False, name=None)],
    },
    "requested_three_code_candidates": records(target_rows),
    "missing_code_years_with_exact_raw_rows_n": int(
        missing_unique.exact_oktmo_raw_rows_n.gt(0).sum()
    ) if not missing_unique.empty else 0,
    "missing_code_years_with_complete_filter_rows_n": int(
        missing_unique.exact_oktmo_complete_filter_rows_n.gt(0).sum()
    ) if not missing_unique.empty else 0,
    "raw_candidate_rows_for_all_missing_codes_n": int(match.sum()),
    "analysis_membership_modified": False,
    "values_imputed_or_substituted": False,
    "same_code_is_proof_of_constant_boundaries": False,
}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
)
print("NONSHOP_SOURCE_COVERAGE_DIAGNOSTICS_BEGIN")
print(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
print("NONSHOP_SOURCE_COVERAGE_DIAGNOSTICS_END")
