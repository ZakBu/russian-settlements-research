"""Conditional postcensus population contexts, independent of shop selection.

Own named urban population C is from the accepted Rosstat bulletin linkage.
S is a sum of distinct upper municipalities sharing one documented centre2020.
Inside2020: denominator S, remainder S-C. Outside2020: denominator C+S, remainder S.
2020 membership is not proof of2023/2024/2025 territorial comparability or flows.
Writes new outputs only under work/; does not modify the previous170-centre panel.
"""
from pathlib import Path
import hashlib
import json
import math
import pandas as pd

# File location: research/ecommerce_cloud/extension/outcomes/this_script.py.
# parents[0]=outcomes, [1]=extension, [2]=ecommerce_cloud, [3]=research, [4]=repo.
ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "work/sources/research/ecommerce_settlement_20261024"
OUT = ROOT / "work/ecommerce_extension_outcomes/nonshop_population_contexts"
OUT.mkdir(parents=True, exist_ok=True)
KEY = "source_record_id_2021"
YEARS = [2023, 2024, 2025]
UPPER = "Муниципальное образование верхнего уровня"
CENTRES = BASE / "history_stage_20261024/centres/centres_20200110.csv"
URBAN = BASE / "national/urban_population_panel_main_wide.parquet"
SYSTEM = BASE / "settlement_role_stage_20261024/system/centre_system_demography.csv"
POP = ROOT / "work/ecommerce_extension_outcomes/raw/data_Y48112027_112_v20260928.parquet"
OLD = ROOT / "research/ecommerce_cloud/extension/outcomes/recent_population_panels.csv"

def true(v):
    return str(v).strip().casefold() in {"true", "1"}

def number(v):
    return float(v) if pd.notna(v) and math.isfinite(float(v)) else None

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, obj):
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

for path in [CENTRES, URBAN, SYSTEM, POP, OLD]:
    if not path.is_file():
        raise FileNotFoundError("Required input missing: " + str(path.relative_to(ROOT)))

centres = pd.read_csv(CENTRES, dtype=str, keep_default_na=False)
urban = pd.read_parquet(URBAN)
system = pd.read_csv(SYSTEM)
population = pd.read_parquet(POP)
old = pd.read_csv(OLD)
assert urban[KEY].is_unique and system[KEY].is_unique and old[KEY].is_unique
assert set(population.indicator_code) == {"Y48112027"}
assert set(centres.register_vintage) == {"20200110"}
assert sha(POP) == "0229e7d0186f2f6ad750b0dcbce501056af0770112d52cda020ba9820492402b"

initial_centre_rows = len(centres)
centres = centres.loc[
    centres.link_status.eq("accepted_exact_code_name_type_census2021")
    & centres.centre_in_main_target.map(true)
    & centres[KEY].ne("")
    & centres.municipality_oktmo8.str.fullmatch(r"\d{8}")
    & centres.official_centre_oktmo11.str.fullmatch(r"\d{11}")
    & centres.administrative_centre_raw.ne("")
    & centres.municipality_oktmo8.str.endswith("000")
    & ~centres.municipality_oktmo8.str.slice(2, 5).str.endswith("00")
].copy()
assert centres.official_centre_resolution.isin({
    "unique_exact_name_type_inside_parent",
    "unique_exact_name_type_in_region_external_centre",
}).all()
owners = centres.groupby("municipality_oktmo8")[KEY].nunique()
assert owners.le(1).all(), "Upper municipality assigned to multiple centres."
centres = centres.drop_duplicates([KEY, "municipality_oktmo8"])

urban = urban.merge(
    system[[KEY, "medium_primary2002"]],
    on=KEY, how="inner", validate="one_to_one",
)
urban["medium_primary2002"] = urban.medium_primary2002.map(true)
urban = urban.set_index(KEY)

raw = population.loc[
    population.year.isin(YEARS)
    & population.mest.eq("Все население")
    & population.indicator_period.eq("На 1 января")
    & population.indicator_unit.eq("Человек")
    & population.mun_level.eq(UPPER)
].copy()
raw["original_parquet_index"] = raw.index
allowed_types = {
    "Муниципальный район", "Муниципальный округ", "Городской округ",
    "Городской округ с внутригородским делением",
    "Внутригородская территория города федерального значения",
}
raw = raw.loc[raw.mun_type.isin(allowed_types)].copy()

lookup, conflicts = {}, []
for key, g in raw.groupby(["oktmo", "year"], dropna=False):
    # Equal values with conflicting territorial metadata remain unresolved.
    check = ["indicator_value", "mun_type", "municipality", "oktmo_stable",
             "oktmo_history", "oktmo_year_from", "oktmo_year_to"]
    if any(g[c].nunique(dropna=False) != 1 for c in check):
        conflicts.append({
            "oktmo": str(key[0]), "year": int(key[1]),
            "reason": "conflicting_population_or_territorial_metadata",
            "source_indices": json.dumps(
                [int(i) for i in g.original_parquet_index]
            ),
        })
        continue
    r = g.iloc[0]
    if pd.isna(r.indicator_value) or r.indicator_value < 0:
        continue
    lookup[(str(key[0]), int(key[1]))] = r

# Registry geometry BEFORE selection on observed urban/municipal population.
system_lookup = system.set_index(KEY)
relations = []
for centre_id, group in centres.groupby(KEY):
    npcodes = sorted(set(group.official_centre_oktmo11))
    codes = sorted(set(group.municipality_oktmo8))
    top = npcodes[0][:5] + "000" if len(npcodes) == 1 else ""
    mode = ("inside2020_C_over_S" if top in codes else
            "outside2020_C_over_CplusS") if top else "ambiguous_centre_code2020"
    sr = system_lookup.loc[centre_id] if centre_id in system_lookup.index else None
    ur = urban.loc[centre_id] if centre_id in urban.index else None
    relations.append({
        KEY: centre_id,
        "name_2021": str(sr.name_2021) if sr is not None else "",
        "region_2021": str(sr.region_2021) if sr is not None else "",
        "medium_primary2002": true(sr.medium_primary2002) if sr is not None else False,
        "mode": mode, "shared_centre2020": len(codes) > 1,
        "upper_municipalities_n2020": len(codes),
        "upper_municipality_codes2020": ",".join(codes),
        "centre_top_code2020": top,
        "official_centre_np_codes2020": ",".join(npcodes),
        "registered_external_relation_rows_n": int(
            group.official_centre_resolution.eq(
                "unique_exact_name_type_in_region_external_centre"
            ).sum()
        ),
        "complete_named_urban_panel":
            ur is not None and true(ur.complete_2023_2025),
    })
relations = pd.DataFrame(relations)
assert relations[KEY].is_unique
relations.to_csv(OUT / "registry_relations_before_selection.csv", index=False)
relations_by_id = relations.set_index(KEY).to_dict("index")

excluded, observations, panels, membership, source_values = [], [], [], [], []

def reject(centre_id, reason, **extra):
    excluded.append({KEY: centre_id, **relations_by_id.get(centre_id, {}),
                     "reason": reason, **extra})

for centre_id, group in centres.groupby(KEY):
    if centre_id not in urban.index:
        reject(centre_id, "no_named_urban_population_panel")
        continue
    u = urban.loc[centre_id]
    if not true(u.complete_2023_2025):
        reject(centre_id, "incomplete_named_urban_population_2023_2025")
        continue
    cvalues = {y: u[f"population_{y}"] for y in YEARS}
    if any(pd.isna(v) or v <= 0 for v in cvalues.values()):
        reject(centre_id, "invalid_named_urban_population")
        continue
    npcodes = sorted(set(group.official_centre_oktmo11))
    if len(npcodes) != 1:
        reject(centre_id, "ambiguous_official_centre_code2020")
        continue
    codes = sorted(set(group.municipality_oktmo8))
    centre_top_code2020 = npcodes[0][:5] + "000"
    inside2020 = centre_top_code2020 in codes
    mode = "inside2020_C_over_S" if inside2020 else "outside2020_C_over_CplusS"
    missing = [(code, year) for code in codes for year in YEARS
               if (code, year) not in lookup]
    if missing:
        reject(centre_id, "incomplete_upper_municipality_panel",
               missing_keys=json.dumps(missing, ensure_ascii=False))
        continue
    unchanged_observed_metadata = all(
        len({str(lookup[(code, y)][col]) for y in YEARS}) == 1
        for code in codes for col in ["mun_type", "municipality", "oktmo_stable"]
    )
    publisher_no_transformation_flags = all(
        str(lookup[(code, y)].oktmo_history) == "Без изменений"
        for code in codes for y in YEARS
    )
    local, invalid = [], False
    for year in YEARS:
        C = float(cvalues[year])
        S = sum(float(lookup[(code, year)].indicator_value) for code in codes)
        R = S - C if inside2020 else S
        denominator = S if inside2020 else C + S
        if R < 0 or denominator <= 0:
            reject(centre_id, "centre_exceeds_inside_total_or_invalid_total",
                   year=year, C=C, S=S)
            invalid = True
            break
        local.append({
            KEY: centre_id, "name_2021": str(u.name_2021),
            "region_2021": str(u.region_2021),
            "medium_primary2002": bool(u.medium_primary2002),
            "year": year, "mode": mode,
            "centre_population": C, "upper_municipality_population_sum": S,
            "other_population": R, "context_population": denominator,
            "centre_share_pct": 100 * C / denominator,
            "upper_municipality_codes2020": ",".join(codes),
            "upper_municipalities_n2020": len(codes),
            "centre_top_code2020": centre_top_code2020,
            "unchanged_observed_metadata": unchanged_observed_metadata,
            "publisher_no_transformation_flags": publisher_no_transformation_flags,
            "membership_verified_2023_2024_2025": False,
            "boundaries_verified": False, "observed_travel_catchment": False,
            "causal_effect_identified": False,
        })
    if invalid:
        continue
    observations.extend(local)
    byyear = {r["year"]: r for r in local}
    a, z = byyear[2023], byyear[2025]
    panels.append({
        KEY: centre_id, "name_2021": str(u.name_2021),
        "region_2021": str(u.region_2021),
        "medium_primary2002": bool(u.medium_primary2002),
        "mode": mode, "upper_municipality_codes2020": ",".join(codes),
        "upper_municipalities_n2020": len(codes),
        "positive_other_population_all_years":
            all(r["other_population"] > 0 for r in local),
        "own_change2023_2025_pct":
            100 * (z["centre_population"] / a["centre_population"] - 1),
        "other_change2023_2025_pct":
            100 * (z["other_population"] / a["other_population"] - 1)
            if a["other_population"] > 0 else None,
        "centre_share_change2023_2025_pp":
            z["centre_share_pct"] - a["centre_share_pct"],
        "unchanged_observed_metadata": unchanged_observed_metadata,
        "publisher_no_transformation_flags": publisher_no_transformation_flags,
        "membership_verified_2023_2024_2025": False,
        "boundaries_verified": False, "causal_effect_identified": False,
    })
    for code in codes:
        membership.append({
            KEY: centre_id, "municipality_oktmo8": code,
            "centre_top_code2020": centre_top_code2020,
            "centre_inside_this_municipality2020": code == centre_top_code2020,
            "mode_of_combined_context": mode,
        })
        for year in YEARS:
            r = lookup[(code, year)]
            source_values.append({
                KEY: centre_id, "oktmo": code, "year": year,
                "indicator_value": float(r.indicator_value),
                "mun_type": str(r.mun_type),
                "municipality": str(r.municipality),
                "oktmo_stable": str(r.oktmo_stable),
                "oktmo_history": str(r.oktmo_history),
                "original_parquet_index": int(r.original_parquet_index),
            })

obs, panel, member = map(pd.DataFrame, [observations, panels, membership])
panel = panel.merge(system[[KEY, "population_2002"]], on=KEY,
                    how="left", validate="one_to_one")
if panel.empty:
    raise RuntimeError("No complete context panel; inspect source schemas and exclusions.")
assert not obs.duplicated([KEY, "year"]).any()
assert panel[KEY].is_unique
assert not member.duplicated([KEY, "municipality_oktmo8"]).any()
assert member.groupby("municipality_oktmo8")[KEY].nunique().le(1).all()
# Unique upper-MO ownership does not prove that an added external city C
# lies outside every OTHER context. Keep this overlap check separate.
registry_owner = centres.set_index("municipality_oktmo8")[KEY].to_dict()
complete_owner = member.set_index("municipality_oktmo8")[KEY].to_dict()
complete_ids = set(panel[KEY])
analysis_medium_ids = set(panel.loc[
    panel.medium_primary2002 & panel.positive_other_population_all_years, KEY
])
cross_context = []
for r in relations.loc[
    relations["mode"].eq("outside2020_C_over_CplusS")
].to_dict("records"):
    other = registry_owner.get(r["centre_top_code2020"])
    if other is not None and other != r[KEY]:
        cross_context.append({
            "external_centre_source_record_id_2021": r[KEY],
            "external_centre_name_2021": r["name_2021"],
            "containing_upper_municipality_oktmo2020": r["centre_top_code2020"],
            "other_context_centre_source_record_id_2021": other,
            "external_context_in_complete_panel": r[KEY] in complete_ids,
            "other_context_in_complete_panel":
                complete_owner.get(r["centre_top_code2020"]) == other,
            "both_contexts_in_medium_analysis_panel":
                r[KEY] in analysis_medium_ids and other in analysis_medium_ids,
            "territorial_relation_is2020_not_current_verified": True,
        })
cross_context = pd.DataFrame(cross_context)
cross_context.to_csv(OUT / "external_centre_cross_context_overlap2020.csv", index=False)
exclusions = pd.DataFrame(excluded)
assert len(relations) == len(panel) + len(exclusions)
assert set(relations[KEY]) == set(panel[KEY]) | set(exclusions[KEY])

def relation_counts(frame):
    if frame.empty:
        return []
    return [
        {"mode": mode, "shared_centre2020": bool(shared), "centres_n": int(n)}
        for (mode, shared), n in frame.groupby(["mode", "shared_centre2020"]).size().items()
    ]

medium_relations = relations.loc[relations.medium_primary2002]
medium_excluded = exclusions.loc[exclusions.medium_primary2002]
reason_counts = [
    {"mode": mode, "shared_centre2020": bool(shared),
     "reason": reason, "centres_n": int(n)}
    for (mode, shared, reason), n in medium_excluded.groupby(
        ["mode", "shared_centre2020", "reason"]
    ).size().items()
]
example_columns = [KEY, "name_2021", "region_2021", "mode", "shared_centre2020",
                   "upper_municipality_codes2020", "centre_top_code2020", "reason"]
example_columns = [c for c in example_columns if c in medium_excluded]
example_frame = medium_excluded.sort_values(KEY).groupby("reason", sort=True).head(3)
exclusion_examples = example_frame[example_columns].to_dict("records")
relations_diagnostics = {
    "accepted_registry_all_centres": relation_counts(relations),
    "accepted_registry_medium_centres": relation_counts(medium_relations),
    "medium_with_complete_named_urban_panel": relation_counts(
        medium_relations.loc[medium_relations.complete_named_urban_panel]
    ),
    "medium_complete_municipal_contexts": relation_counts(
        medium_relations.loc[medium_relations[KEY].isin(complete_ids)]
    ),
    "exclusion_reason_counts_medium": reason_counts,
    "exclusion_examples_medium_up_to3_per_reason": exclusion_examples,
    "initial_external_or_shared_medium_examples_up_to8": medium_relations.loc[
        medium_relations["mode"].eq("outside2020_C_over_CplusS")
        | medium_relations.shared_centre2020
    ].sort_values(KEY).head(8).to_dict("records"),
    "external_centre_top_in_other_registry_context_n": len(cross_context),
    "external_centre_top_in_other_complete_context_n": int(
        (cross_context.external_context_in_complete_panel
         & cross_context.other_context_in_complete_panel).sum()
    ) if not cross_context.empty else 0,
    "external_overlap_pairs_both_in_medium_analysis_n": int(
        cross_context.both_contexts_in_medium_analysis_panel.sum()
    ) if not cross_context.empty else 0,
    "independent_empirical_markets_established": False,
    "context_totals_are_nationally_additive": False,
}
write_json(OUT / "relations_selection_diagnostics.json", relations_diagnostics)

obs.to_csv(OUT / "observations.csv", index=False)
panel.to_csv(OUT / "panels.csv", index=False)
member.to_csv(OUT / "municipal_membership2020.csv", index=False)
pd.DataFrame(source_values).to_csv(OUT / "municipal_source_values.csv", index=False)
pd.DataFrame(excluded).to_csv(OUT / "excluded_centres.csv", index=False)
pd.DataFrame(conflicts).to_csv(OUT / "conflicting_municipal_keys.csv", index=False)

old_ids = set(old.loc[old.medium_primary2002.map(true), KEY])
population_base = system.loc[system.medium_primary2002.map(true)].copy()
assert len(population_base) == 1273, "Primary medium-centre definition changed."
new_primary = panel.loc[
    panel.medium_primary2002 & panel.positive_other_population_all_years
].copy()
new_ids = set(new_primary[KEY])
population_base["in_new_conditional_panel"] = population_base[KEY].isin(new_ids)
population_base["in_old170_panel"] = population_base[KEY].isin(old_ids)
region_coverage = population_base.groupby("region_2021").agg(
    medium_centres_n=(KEY, "size"),
    new_conditional_n=("in_new_conditional_panel", "sum"),
    old170_n=("in_old170_panel", "sum"),
).reset_index()
region_coverage["new_conditional_coverage_pct"] = (
    100 * region_coverage.new_conditional_n / region_coverage.medium_centres_n
)
region_coverage.to_csv(OUT / "coverage_by_region.csv", index=False)

selection_rows = []
for selected, g in population_base.groupby("in_new_conditional_panel"):
    for col in ["population_2002", "population_2021", "context_members_n",
                "centre_change2002_2021_pct", "centre_population_share_change_pp"]:
        selection_rows.append({
            "in_new_conditional_panel": bool(selected), "centres_n": len(g),
            "measure": col, "observed_n": int(g[col].notna().sum()),
            "median": number(g[col].median()),
            "q25": number(g[col].quantile(.25)),
            "q75": number(g[col].quantile(.75)),
        })
pd.DataFrame(selection_rows).to_csv(OUT / "selection_characteristics.csv", index=False)


def sign_label(value):
    return "decline" if value < 0 else ("growth" if value > 0 else "stable")

def size_bin(value):
    value = number(value)
    if value is None:
        return "missing"
    if value < 10000:
        return "below10000"
    if value < 20000:
        return "10000to19999"
    if value < 50000:
        return "20000to49999"
    return "50000plus"

new_primary["population2002_bin"] = new_primary.population_2002.map(size_bin)
for col, source in [
    ("own_direction", "own_change2023_2025_pct"),
    ("other_direction", "other_change2023_2025_pct"),
    ("share_direction", "centre_share_change2023_2025_pp"),
]:
    new_primary[col] = new_primary[source].map(sign_label)

def outcome_stats(g):
    return {
        "centres_n": int(len(g)),
        "own_decline_n": int(g.own_change2023_2025_pct.lt(0).sum()),
        "other_decline_n": int(g.other_change2023_2025_pct.lt(0).sum()),
        "share_increase_n": int(g.centre_share_change2023_2025_pp.gt(0).sum()),
        "share_decrease_n": int(g.centre_share_change2023_2025_pp.lt(0).sum()),
        "shrink_concentration_n": int((
            g.own_change2023_2025_pct.lt(0)
            & g.other_change2023_2025_pct.lt(0)
            & g.centre_share_change2023_2025_pp.gt(0)
        ).sum()),
        "median_own_change_pct": number(g.own_change2023_2025_pct.median()),
        "median_other_change_pct": number(g.other_change2023_2025_pct.median()),
        "median_share_change_pp": number(g.centre_share_change2023_2025_pp.median()),
    }

region_results, size_results, trajectory_results = [], [], []
for strict in [False, True]:
    g = new_primary
    if strict:
        g = g.loc[g.unchanged_observed_metadata & g.publisher_no_transformation_flags]
    selection = "publisher_metadata_screen" if strict else "all_conditional"
    for region, sub in g.groupby("region_2021"):
        region_results.append({"selection": selection, "region_2021": region,
                               **outcome_stats(sub)})
    for size, sub in g.groupby("population2002_bin"):
        size_results.append({"selection": selection, "population2002_bin": size,
                             **outcome_stats(sub)})
    for (own, other, share), sub in g.groupby(
        ["own_direction", "other_direction", "share_direction"]
    ):
        trajectory_results.append({
            "selection": selection, "own_direction": own,
            "other_direction": other, "share_direction": share,
            "centres_n": int(len(sub)),
        })
pd.DataFrame(region_results).to_csv(OUT / "region_results.csv", index=False)
pd.DataFrame(size_results).to_csv(OUT / "population2002_bin_results.csv", index=False)
pd.DataFrame(trajectory_results).to_csv(OUT / "trajectory_counts.csv", index=False)
# Compact regional table in job logs; full named columns remain in CSV.
region_columns = ["selection", "region_2021", "centres_n", "own_decline_n",
                  "other_decline_n", "share_increase_n", "share_decrease_n",
                  "shrink_concentration_n", "median_own_change_pct",
                  "median_other_change_pct", "median_share_change_pp"]

summaries = []
for strict in [False, True]:
    usable = new_primary
    if strict:
        usable = usable.loc[
            usable.unchanged_observed_metadata
            & usable.publisher_no_transformation_flags
        ]
    for mode, g in usable.groupby("mode"):
        summaries.append({
            "selection": "publisher_metadata_screen" if strict else "all_conditional",
            "mode": mode, "centres_n": int(len(g)),
            "regions_n": int(g.region_2021.nunique()),
            "shared_centres_n": int(g.upper_municipalities_n2020.gt(1).sum()),
            "own_decline_n": int(g.own_change2023_2025_pct.lt(0).sum()),
            "other_decline_n": int(g.other_change2023_2025_pct.lt(0).sum()),
            "share_increase_n": int(g.centre_share_change2023_2025_pp.gt(0).sum()),
            "share_decrease_n": int(g.centre_share_change2023_2025_pp.lt(0).sum()),
            "median_own_change_pct": number(g.own_change2023_2025_pct.median()),
            "median_other_change_pct": number(g.other_change2023_2025_pct.median()),
            "median_share_change_pp": number(g.centre_share_change2023_2025_pp.median()),
        })

summary = {
    "scope": "new_nonshop_selected_conditional_administrative_context_panel",
    "centre_identity_vintage": "2020-01-10",
    "population_dates": ["2023-01-01", "2024-01-01", "2025-01-01"],
    "initial_registry_rows": initial_centre_rows,
    "accepted_upper_municipality_rows": len(centres),
    "accepted_distinct_centres": int(centres[KEY].nunique()),
    "all_complete_contexts": len(panel),
    "old_170_panel_modified": False,
    "territorial_comparability_verified": False,
    "overlap_old170": {
        "old_medium_n": len(old_ids), "new_medium_positive_remainder_n": len(new_ids),
        "intersection_n": len(old_ids & new_ids),
        "new_only_n": len(new_ids - old_ids),
        "old_only_n": len(old_ids - new_ids),
    },
    "relations_selection_diagnostics": relations_diagnostics,
    "representativeness": {
        "target_medium_centres_n": len(population_base),
        "new_medium_coverage_pct": 100 * len(new_ids) / len(population_base),
        "target_regions_n": int(population_base.region_2021.nunique()),
        "new_regions_n": int(new_primary.region_2021.nunique()),
        "regions_without_new_panel": region_coverage.loc[
            region_coverage.new_conditional_n.eq(0), "region_2021"
        ].tolist(),
        "selection_characteristics": selection_rows,
        "representative_probability_sample": False,
        "rural_centres_without_named_urban_panel_not_imputed": True,
    },
    "rules": {
        "inside2020": "C/S; R=S-C", "outside2020": "C/(C+S); R=S",
        "S": "distinct upper municipalities sharing one documented centre",
        "reform_stitching": False, "lower_municipal_sums": False,
        "missing_as_zero": False,
        "no_change_metadata_is_boundary_proof": False,
    },
    "inputs": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)}
               for p in [CENTRES, URBAN, SYSTEM, POP, OLD]],
    "results": summaries,
    "trajectories": trajectory_results,
    "population2002_bins": size_results,
    "region_results": {"columns": region_columns,
        "rows": [[r[k] for k in region_columns] for r in region_results]},
}
write_json(OUT / "summary.json", summary)
print("NONSHOP_POPULATION_CONTEXTS_SUMMARY_BEGIN")
print(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
print("NONSHOP_POPULATION_CONTEXTS_SUMMARY_END")
