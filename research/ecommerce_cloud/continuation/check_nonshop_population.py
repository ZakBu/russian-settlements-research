"""Independent derived-table arithmetic audit of conditional population contexts.

Run: python research/ecommerce_cloud/continuation/check_nonshop_population.py
     work/ecommerce_extension_outcomes/nonshop_population_contexts

Success does NOT validate territorial boundaries, named-urban source accuracy,
physical retail locations, actual travel catchments or causal effects.
"""
from pathlib import Path
from collections import defaultdict
from statistics import median
import csv
import json
import math
import sys

D = Path(sys.argv[1])

def read(name):
    with (D / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def yes(v):
    return str(v).strip().lower() in {"true", "1"}

def eq(a, b):
    assert math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-8), (a, b)

K = "source_record_id_2021"
members = read("municipal_membership2020.csv")
sources = read("municipal_source_values.csv")
observations = read("observations.csv")
panels = read("panels.csv")
summary = json.loads((D / "summary.json").read_text(encoding="utf-8"))

membership = defaultdict(set)
top_codes = defaultdict(set)
owners = defaultdict(set)
for r in members:
    membership[r[K]].add(r["municipality_oktmo8"])
    top_codes[r[K]].add(r["centre_top_code2020"])
    owners[r["municipality_oktmo8"]].add(r[K])
assert len(members) == sum(map(len, membership.values()))
assert all(len(v) == 1 for v in owners.values())

source = {}
by_year = defaultdict(list)
for r in sources:
    key = r[K], r["oktmo"], int(r["year"])
    assert key not in source
    source[key] = r
    by_year[(r[K], int(r["year"]))].append(r)

obs = {}
for r in observations:
    cid, year = r[K], int(r["year"])
    assert (cid, year) not in obs
    assert year in {2023, 2024, 2025}
    assert len(top_codes[cid]) == 1
    rows = by_year[cid, year]
    assert {x["oktmo"] for x in rows} == membership[cid]
    C = float(r["centre_population"])
    S = sum(float(x["indicator_value"]) for x in rows)
    inside = next(iter(top_codes[cid])) in membership[cid]
    assert r["mode"] == (
        "inside2020_C_over_S" if inside else "outside2020_C_over_CplusS"
    )
    R, T = (S - C, S) if inside else (S, C + S)
    assert C > 0 and R >= 0 and T > 0
    eq(S, r["upper_municipality_population_sum"])
    eq(R, r["other_population"])
    eq(T, r["context_population"])
    eq(100 * C / T, r["centre_share_pct"])
    obs[cid, year] = r

assert len(panels) == len({r[K] for r in panels})
assert len(observations) == 3 * len(panels)
eligible = []

for p in panels:
    cid = p[K]
    rows = [obs[cid, y] for y in (2023, 2024, 2025)]
    a, z = rows[0], rows[-1]
    for r in rows:
        assert r["mode"] == p["mode"]
        assert yes(r["medium_primary2002"]) == yes(p["medium_primary2002"])

    eq(100 * (float(z["centre_population"]) /
              float(a["centre_population"]) - 1),
       p["own_change2023_2025_pct"])
    if float(a["other_population"]) > 0:
        eq(100 * (float(z["other_population"]) /
                  float(a["other_population"]) - 1),
           p["other_change2023_2025_pct"])
    else:
        assert p["other_change2023_2025_pct"] == ""
    eq(float(z["centre_share_pct"]) - float(a["centre_share_pct"]),
       p["centre_share_change2023_2025_pp"])

    no_flags = all(
        source[cid, code, y]["oktmo_history"] == "Без изменений"
        for code in membership[cid] for y in (2023, 2024, 2025)
    )
    same_metadata = all(
        len({source[cid, code, y][field] for y in (2023, 2024, 2025)}) == 1
        for code in membership[cid]
        for field in ("mun_type", "municipality", "oktmo_stable")
    )
    assert yes(p["publisher_no_transformation_flags"]) == no_flags
    assert yes(p["unchanged_observed_metadata"]) == same_metadata

    positive_R = all(float(r["other_population"]) > 0 for r in rows)
    assert yes(p["positive_other_population_all_years"]) == positive_R
    if yes(p["medium_primary2002"]) and positive_R:
        eligible.append(p)

expected_modes = {p["mode"] for p in eligible}
for selection in ("all_conditional", "publisher_metadata_screen"):
    selected = eligible
    if selection == "publisher_metadata_screen":
        selected = [
            p for p in eligible if yes(p["unchanged_observed_metadata"])
            and yes(p["publisher_no_transformation_flags"])
        ]
    actual_modes = {
        s["mode"] for s in summary["results"] if s["selection"] == selection
    }
    assert actual_modes == {p["mode"] for p in selected}

for s in summary["results"]:
    assert s["selection"] in {"all_conditional", "publisher_metadata_screen"}
    g = [p for p in eligible if p["mode"] == s["mode"]]
    if s["selection"] == "publisher_metadata_screen":
        g = [p for p in g if yes(p["unchanged_observed_metadata"])
             and yes(p["publisher_no_transformation_flags"])]
    assert len(g) == s["centres_n"]
    assert len({p["region_2021"] for p in g}) == s["regions_n"]
    checks = {
        "own_decline_n": sum(float(p["own_change2023_2025_pct"]) < 0 for p in g),
        "other_decline_n": sum(float(p["other_change2023_2025_pct"]) < 0 for p in g),
        "share_increase_n": sum(float(p["centre_share_change2023_2025_pp"]) > 0 for p in g),
        "share_decrease_n": sum(float(p["centre_share_change2023_2025_pp"]) < 0 for p in g),
        "shared_centres_n": sum(int(p["upper_municipalities_n2020"]) > 1 for p in g),
    }
    for field, value in checks.items():
        assert value == s[field], (field, value, s[field])
    for result, field in [
        ("median_own_change_pct", "own_change2023_2025_pct"),
        ("median_other_change_pct", "other_change2023_2025_pct"),
        ("median_share_change_pp", "centre_share_change2023_2025_pp"),
    ]:
        eq(median(float(p[field]) for p in g), s[result])

assert len(panels) == summary["all_complete_contexts"]
assert len(eligible) == summary["overlap_old170"]["new_medium_positive_remainder_n"]
assert not summary["territorial_comparability_verified"]
assert not summary["old_170_panel_modified"]
result = {
    "status": "PASS",
    "source_values_checked": len(sources),
    "observations_checked": len(observations),
    "panels_checked": len(panels),
    "medium_positive_remainder_n": len(eligible),
    "scope": "Derived-source arithmetic only; no boundary or causal validation",
    "named_urban_population_independently_verified": False,
    "territorial_boundaries_verified": False,
    "actual_travel_catchments_verified": False,
    "causal_effect_validated": False,
}
(D / "independent_arithmetic_check.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print("INDEPENDENT_NONSHOP_ARITHMETIC_CHECK_BEGIN")
print(json.dumps(result, ensure_ascii=False, indent=2))
print("INDEPENDENT_NONSHOP_ARITHMETIC_CHECK_END")
