"""Small-remainder sensitivity of the conditional demographic contexts.

Run after nonshop_population_contexts.py. These are parallel diagnostic
restrictions, not a replacement selection or evidence of platform causality.
"""
from pathlib import Path
import hashlib
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "work/ecommerce_extension_outcomes/nonshop_population_contexts"
OUT = BASE / "remainder_sensitivity"
OUT.mkdir(parents=True, exist_ok=True)
KEY = "source_record_id_2021"

def true(v):
    return str(v).strip().casefold() in {"true", "1"}

def number(v):
    return float(v) if pd.notna(v) and math.isfinite(float(v)) else None

panels = pd.read_csv(BASE / "panels.csv")
obs = pd.read_csv(BASE / "observations.csv")
assert panels[KEY].is_unique
assert not obs.duplicated([KEY, "year"]).any()
p = panels.loc[
    panels.medium_primary2002.map(true)
    & panels.positive_other_population_all_years.map(true)
].copy()
ids = set(p[KEY])
o = obs.loc[obs[KEY].isin(ids) & obs.year.isin([2023, 2024, 2025])].copy()
assert set(o[KEY]) == ids
assert o.groupby(KEY).year.nunique().eq(3).all()
assert o.other_population.gt(0).all()
for col in ["centre_population", "other_population", "context_population"]:
    w = o.pivot(index=KEY, columns="year", values=col)
    for y in [2023, 2024, 2025]:
        p = p.merge(w[y].rename(f"{col}_{y}"), on=KEY, validate="one_to_one")
p["min_R2023_2025"] = p[
    ["other_population_2023", "other_population_2024", "other_population_2025"]
].min(axis=1)
p["baseline_Rshare_pct"] = 100 * p.other_population_2023 / p.context_population_2023
p["shared_centre2020"] = p.upper_municipalities_n2020.gt(1)
p["own_change_absolute"] = p.centre_population_2025 - p.centre_population_2023
p["other_change_absolute"] = p.other_population_2025 - p.other_population_2023
assert (
    100 * (p.other_population_2025 / p.other_population_2023 - 1)
    - p.other_change2023_2025_pct
).abs().lt(1e-8).all()

scenarios = [
    ("baseline_positive_R_all_years", p.min_R2023_2025.gt(0)),
    ("min_R_all_years_ge100", p.min_R2023_2025.ge(100)),
    ("min_R_all_years_ge500", p.min_R2023_2025.ge(500)),
    ("min_R_all_years_ge1000", p.min_R2023_2025.ge(1000)),
    ("baseline_Rshare_ge1pct", p.baseline_Rshare_pct.ge(1)),
    ("baseline_Rshare_ge5pct", p.baseline_Rshare_pct.ge(5)),
]

def stats(g):
    return {
        "centres_n": int(len(g)), "regions_n": int(g.region_2021.nunique()),
        "share_increase_n": int(g.centre_share_change2023_2025_pp.gt(0).sum()),
        "own_decline_n": int(g.own_change2023_2025_pct.lt(0).sum()),
        "other_decline_n": int(g.other_change2023_2025_pct.lt(0).sum()),
        "share_increase_pct": 100 * float(g.centre_share_change2023_2025_pp.gt(0).mean())
            if len(g) else None,
        "own_decline_pct": 100 * float(g.own_change2023_2025_pct.lt(0).mean())
            if len(g) else None,
        "other_decline_pct": 100 * float(g.other_change2023_2025_pct.lt(0).mean())
            if len(g) else None,
        "shrink_concentration_n": int((
            g.own_change2023_2025_pct.lt(0)
            & g.other_change2023_2025_pct.lt(0)
            & g.centre_share_change2023_2025_pp.gt(0)
        ).sum()),
        "median_own_change_pct": number(g.own_change2023_2025_pct.median()),
        "median_other_change_pct": number(g.other_change2023_2025_pct.median()),
        "median_share_change_pp": number(g.centre_share_change2023_2025_pp.median()),
        "median_min_R_all_years": number(g.min_R2023_2025.median()),
        "median_baseline_Rshare_pct": number(g.baseline_Rshare_pct.median()),
    }

rows, membership = [], []
for label, mask in scenarios:
    for centre_id in p.loc[mask, KEY]:
        membership.append({KEY: centre_id, "scenario": label})
    for strict in [False, True]:
        selected = p.loc[mask]
        if strict:
            selected = selected.loc[
                selected.unchanged_observed_metadata.map(true)
                & selected.publisher_no_transformation_flags.map(true)
            ]
        for group, g in [
            ("all", selected),
            ("shared2020", selected.loc[selected.shared_centre2020]),
            ("not_shared2020", selected.loc[~selected.shared_centre2020]),
        ]:
            rows.append({
                "scenario": label,
                "metadata_screen": "publisher_metadata_screen" if strict else "all_conditional",
                "centre_relation_group": group, **stats(g),
            })
results = pd.DataFrame(rows)
results.to_csv(OUT / "sensitivity_results.csv", index=False)
p.to_csv(OUT / "centre_absolute_endpoints_and_remainders.csv", index=False)
pd.DataFrame(membership).to_csv(OUT / "scenario_membership.csv", index=False)
extreme_columns = [
    KEY, "name_2021", "region_2021", "shared_centre2020",
    "upper_municipality_codes2020",
    "centre_population_2023", "centre_population_2025",
    "other_population_2023", "other_population_2025",
    "context_population_2023", "context_population_2025",
    "min_R2023_2025", "baseline_Rshare_pct",
    "own_change_absolute", "other_change_absolute",
    "own_change2023_2025_pct", "other_change2023_2025_pct",
    "centre_share_change2023_2025_pp",
    "unchanged_observed_metadata", "publisher_no_transformation_flags",
]
extreme = p.sort_values(
    ["other_change2023_2025_pct", KEY], ascending=[False, True]
).head(10)[extreme_columns]
extreme.to_csv(OUT / "ten_largest_R_growth_absolute_endpoints.csv", index=False)

def safe(v):
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v

columns = list(results.columns)
summary = {
    "scope": "small_remainder_parallel_sensitivity_conditional_contexts",
    "main_selection_unchanged": True,
    "causal_effect_identified": False,
    "boundaries_verified": False,
    "thresholds_are_parallel_diagnostics_not_preferred_estimator": True,
    "baseline_Rshare_denominator": "C2023+R2023 equals context_population2023",
    "min_R_window": [2023, 2024, 2025],
    "input_files": [{
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    } for path in [BASE / "panels.csv", BASE / "observations.csv"]],
    "results": {"columns": columns, "rows": [
        [safe(v) for v in r] for r in results.itertuples(index=False, name=None)
    ]},
    "ten_largest_R_growth": {"columns": extreme_columns, "rows": [
        [safe(v) for v in r] for r in extreme.itertuples(index=False, name=None)
    ]},
}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    encoding="utf-8",
)
print("NONSHOP_REMAINDER_SENSITIVITY_BEGIN")
print(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
print("NONSHOP_REMAINDER_SENSITIVITY_END")
