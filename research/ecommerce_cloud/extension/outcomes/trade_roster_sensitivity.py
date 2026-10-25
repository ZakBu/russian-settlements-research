"""Trade-stock sensitivity to full official roster continuity, fixed old174.

Run after full_roster_analysis.py. This retains the exact original 174-centre
shop panel and applies separate diagnostic screens to BOTH C and parent S.
Store stocks and C/S stock shares do not measure trips, sales, outlet closures
or marketplace causal effects. Publication roster continuity is not a proof
that physical boundaries were constant.
"""
from pathlib import Path
import hashlib
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "work/sources/research/ecommerce_settlement_20261024"
SOURCE = BASE / ("settlement_role_stage_20261024/bdmo/singleton/"
                "internal_centre_district_common_panels2022_2024.csv")
ROSTERS = ROOT / ("work/ecommerce_extension_outcomes/nonshop_population_contexts/"
                  "roster_analysis/three_publication_eligibility.csv")
OUT = ROSTERS.parent / "trade_roster_sensitivity"
OUT.mkdir(parents=True, exist_ok=True)
KEY = "source_record_id_2021"

def true(v):
    return str(v).strip().casefold() in {"true", "1"}

def number(v):
    return float(v) if pd.notna(v) and math.isfinite(float(v)) else None

d = pd.read_csv(SOURCE, dtype={"centre_oktmo": str, "district_oktmo": str})
required = {
    KEY, "name_2021", "region_2021", "category", "period",
    "centre_oktmo", "district_oktmo", "medium_primary2002",
    "centre_stock_change2022_2024", "centre_share_change2022_2024_pp",
    "centre_shops_2022", "centre_shops_2023", "centre_shops_2024",
    "district_shops_2022", "district_shops_2023", "district_shops_2024",
    "centre_share_pct_2022", "centre_share_pct_2023", "centre_share_pct_2024",
}
assert required.issubset(d.columns), sorted(required-set(d.columns))
d = d.loc[d.category.eq("Магазины") & d.medium_primary2002.map(true)].copy()
assert d[KEY].is_unique and len(d) == 174
assert set(d.period) == {"IV квартал"}
for y in [2022, 2023, 2024]:
    assert d[f"centre_shops_{y}"].ge(0).all()
    assert d[f"district_shops_{y}"].gt(0).all()
    assert d[f"district_shops_{y}"].ge(d[f"centre_shops_{y}"]).all()
    assert (
        100*d[f"centre_shops_{y}"]/d[f"district_shops_{y}"]
        - d[f"centre_share_pct_{y}"]
    ).abs().lt(1e-8).all()
assert (
    d.centre_shops_2024 - d.centre_shops_2022
    - d.centre_stock_change2022_2024
).abs().lt(1e-8).all()
assert (
    d.centre_share_pct_2024 - d.centre_share_pct_2022
    - d.centre_share_change2022_2024_pp
).abs().lt(1e-8).all()

flags = pd.read_csv(ROSTERS)
flagcols = [
    KEY, "code_sets_unchanged_vs2020_2021",
    "code_name_sets_unchanged_vs2020_2021", "no_future_rows_affect_context",
    "same_singleton_all3_publications",
]
for scope, suffix in [
    ("old174_centre_units", "centre"),
    ("old174_parent_units", "parent"),
]:
    f = flags.loc[flags.scope.eq(scope) & flags.view.eq("publication"), flagcols].copy()
    assert f[KEY].is_unique and set(f[KEY]) == set(d[KEY])
    for col in flagcols[1:]:
        f[col] = f[col].map(true)
    f = f.rename(columns={col: col+"_"+suffix for col in flagcols[1:]})
    d = d.merge(f, on=KEY, validate="one_to_one")
d["both_code_sets_unchanged"] = (
    d.code_sets_unchanged_vs2020_2021_centre
    & d.code_sets_unchanged_vs2020_2021_parent
)
d["both_code_name_sets_unchanged"] = (
    d.code_name_sets_unchanged_vs2020_2021_centre
    & d.code_name_sets_unchanged_vs2020_2021_parent
)
d["both_no_future_rows"] = (
    d.no_future_rows_affect_context_centre
    & d.no_future_rows_affect_context_parent
)
assert d.both_code_sets_unchanged.sum() == 157
assert d.both_code_name_sets_unchanged.sum() == 150
assert d.same_singleton_all3_publications_centre.all()
d["centre_stock_change_pct"] = (
    100*(d.centre_shops_2024/d.centre_shops_2022-1)
).where(d.centre_shops_2022.gt(0))
d["district_stock_change"] = d.district_shops_2024-d.district_shops_2022
d["other_shops_2022"] = d.district_shops_2022-d.centre_shops_2022
d["other_shops_2024"] = d.district_shops_2024-d.centre_shops_2024
d["other_stock_change"] = d.other_shops_2024-d.other_shops_2022
d.to_csv(OUT/"fixed_old174_roster_flags_and_stock_changes.csv", index=False)

def stats(g):
    delta = g.centre_share_change2022_2024_pp
    own = g.centre_stock_change2022_2024
    return {
        "centres_n": int(len(g)),
        "regions_n": int(g.region_2021.nunique()),
        "share_increase_ge1pp_n": int(delta.ge(1).sum()),
        "share_decrease_le_minus1pp_n": int(delta.le(-1).sum()),
        "share_between_minus1_and1pp_n": int((delta.gt(-1)&delta.lt(1)).sum()),
        "share_increase_ge1pp_pct": 100*float(delta.ge(1).mean()) if len(g) else None,
        "share_decrease_le_minus1pp_pct": 100*float(delta.le(-1).mean()) if len(g) else None,
        "share_any_increase_n": int(delta.gt(0).sum()),
        "share_any_decrease_n": int(delta.lt(0).sum()),
        "centre_stock_decline_n": int(own.lt(0).sum()),
        "centre_stock_growth_n": int(own.gt(0).sum()),
        "centre_stock_unchanged_n": int(own.eq(0).sum()),
        "centre_stock_decline_share_loss_ge1pp_n": int((own.lt(0)&delta.le(-1)).sum()),
        "centre_stock_decline_share_growth_ge1pp_n": int((own.lt(0)&delta.ge(1)).sum()),
        "centre_stock_growth_share_loss_ge1pp_n": int((own.gt(0)&delta.le(-1)).sum()),
        "centre_stock_growth_share_growth_ge1pp_n": int((own.gt(0)&delta.ge(1)).sum()),
        "district_stock_decline_n": int(g.district_stock_change.lt(0).sum()),
        "other_stock_decline_n": int(g.other_stock_change.lt(0).sum()),
        "median_centre_stock_change": number(own.median()),
        "median_centre_stock_change_pct": number(g.centre_stock_change_pct.median()),
        "median_share_change_pp": number(delta.median()),
        "median_district_stock_change": number(g.district_stock_change.median()),
        "median_other_stock_change": number(g.other_stock_change.median()),
        "both_no_future_rows_n": int(g.both_no_future_rows.sum()),
    }

rows = []
for label, mask in [
    ("baseline_fixed174", pd.Series(True, index=d.index)),
    ("both_C_S_unchanged_code_sets157", d.both_code_sets_unchanged),
    ("both_C_S_unchanged_code_name_sets150", d.both_code_name_sets_unchanged),
]:
    rows.append({"restriction": label, **stats(d.loc[mask])})
pd.DataFrame(rows).to_csv(OUT/"trade_stock_sensitivity_results.csv", index=False)
summary = {
    "scope": "fixed_old174_trade_stocks_full_publication_roster_sensitivity",
    "original_panel_modified": False,
    "original_sample_definition": "category Магазины and medium_primary2002 in internal_centre_district_common_panels2022_2024.csv",
    "stock_dates": "IV quarter 2022,2023,2024, same category and period",
    "roster_publications": ["20221228","20231219","20241227"],
    "roster_reference_publications": ["20200110","20211103"],
    "screens_require_both_centre_and_parent_full_rosters": True,
    "year_specific_legal_boundaries_verified": False,
    "physical_shop_location_inside_settlement_verified": False,
    "store_disappearance_is_not_claimed_as_closure": True,
    "trips_or_sales_observed": False,
    "causal_effect_identified": False,
    "input_files": [{
        "path": str(p.relative_to(ROOT)),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    } for p in [SOURCE, ROSTERS]],
    "results": rows,
}
(OUT/"summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
    encoding="utf-8",
)
print("TRADE_ROSTER_SENSITIVITY_BEGIN")
print(json.dumps(summary, ensure_ascii=False, separators=(",",":"), allow_nan=False))
print("TRADE_ROSTER_SENSITIVITY_END")
