#!/usr/bin/env python3
"""Build dated federal-territory reference points and secondary Wikidata history.

This is a reproducible staging build. It does not edit the frozen delivery or
admit ordinary populated-place coordinates, census populations, or identity edges.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from datetime import datetime, timezone

import duckdb
import pandas as pd

OUT = Path("/workspace/settlements-work/continuation_20261004/federal_and_history")
ROOT = Path("/workspace/settlements-work/continuation_20261003")
DELIVERY = Path("/workspace/settlements-delivery/continuation-consolidated-20261003")
RAW = Path("/workspace/settlements-raw/data/raw")
HIST = ROOT / "audit_99_20261003/wikidata_history_large"
WIDE = Path("/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet")
BASELINE = ROOT / "audit_99_20261003/root/baseline.json"
AGGREGATES = ROOT / "federal_atomic_scope_ceiling_addendum_v1/aggregate_flagged_records.csv"
HISTORY_TSV = HIST / "candidate_tsv_long.parquet"
HISTORY_FULL = HIST / "candidate_long.parquet"
OBS = DELIVERY / "selected_observations.parquet"
EDGES = DELIVERY / "accepted_identity_edges.parquet"
LEGACY_DB = Path("/workspace/settlements-assets/baseline/legacy_database_20260929.duckdb")

CITIES = {
    "Москва": {"qid": "Q649", "lat": 55.750556, "lon": 37.6175,
              "wd_file": "batch_0139.jsonl.gz", "wd_line": 13780,
              "raw_point": "POINT(37.617500 55.750556)"},
    "Санкт-Петербург": {"qid": "Q656", "lat": 59.95, "lon": 30.316667,
              "wd_file": "batch_0139.jsonl.gz", "wd_line": 14073,
              "raw_point": "POINT(30.316667 59.950000)"},
    "Севастополь": {"qid": "Q7525", "lat": 44.605, "lon": 33.5225,
              "wd_file": "batch_0140.jsonl.gz", "wd_line": 9803,
              "raw_point": "POINT(33.522500 44.605000)"},
}
EXPECTED = [
    (2002, "Санкт-Петербург", "2002:1_TOM_01_04.xls:0:3218", 4661219,
     "Rosstat 2002 Tom 1 Table 4, sheet 01-04, Excel row 3218"),
    (2010, "Москва", "2010:pub-11-1-4.pdf:pdf_page_11:41", 11503501,
     "Rosstat 2010 Tom 11 Table 1.4, PDF page 11, printed page 39, row 41"),
    (2010, "Санкт-Петербург", "2010:pub-11-1-4.pdf:pdf_page_15:39", 4879566,
     "Rosstat 2010 Tom 11 Table 1.4, PDF page 15, printed page 43, row 39"),
    (2021, "Севастополь", "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:121540", 547820,
     "Rosstat 2021 Table 5, root row 10612 / cached selected record parquet row 121540"),
    (2021, "Санкт-Петербург", "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:126656", 5601911,
     "Rosstat 2021 Table 5, root row 7555 / cached selected record parquet row 126656"),
    (2021, "Москва", "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:64748", 13010112,
     "Rosstat 2021 Table 5, root row 5393 / cached selected record parquet row 64748"),
]
POP_SOURCES = {
    2002: {"path": RAW / "2002_official_tom1/1_TOM_01_04.xls", "sha256": "745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3"},
    2010: {"path": RAW / "2010_official_tom11/pub-11-1-4.pdf", "sha256": "db2528e6db3c6089351bd09d253c9dfa607e2f2dff6cc45d1174fb21fa96d500"},
    2021: {"path": RAW / "rosstat_2021/Tom1_tab-5_VPN-2020.xlsx", "sha256": "0b232b3d2ab5daa231568acc719ac6fda4fb0979a01a0da6bacc69be6f252474"},
}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL,
              lineterminator="\n")

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for info in POP_SOURCES.values():
        assert sha(info["path"]) == info["sha256"]
    con = duckdb.connect()
    # Bind the six exact source rows to current federal-city QIDs and their cached
    # truthy P625 values. Old-year use is expressly a current territory reference.
    agg = pd.read_csv(AGGREGATES, engine="python", encoding="utf-8")
    obs = con.execute("select * from read_parquet(?)", [str(OBS)]).df()
    wide = con.execute("select source_record_id, wikidata_qid, wikidata_truthy_p625_claims_json, points_json, candidate_status, identity_admission, coordinate_admission from read_parquet(?)", [str(WIDE)]).df()
    wide_by_id = wide.set_index("source_record_id", drop=False)
    bindings = []
    for year, city, rid, pop, locator in EXPECTED:
        a = agg[agg.source_record_id == rid]
        assert len(a) == 1 and int(a.iloc[0].population) == pop
        c = CITIES[city]
        matching = wide[wide.wikidata_qid == c["qid"]]
        p625 = None
        for raw in matching.wikidata_truthy_p625_claims_json.dropna().tolist():
            vals = json.loads(raw)
            p625 = next((v for v in vals if v.get("value_raw") == c["raw_point"]), p625)
        assert p625 and p625.get("wgs84_valid")
        # Candidate binding in the current exact census row (2021) is corroborative
        # cache context only; no inherited point admission is asserted here.
        target = wide_by_id.loc[rid] if rid in wide_by_id.index else None
        status = "exact city QID/P625 cached; territory-reference role authorized"
        if target is not None:
            status += "; exact census-row QID present in wide binding cache"
        else:
            status += "; earlier-year QID carried by continuing-city relation inference"
        # Include the source artifact locator and hash from the immutable audit.
        bindings.append({
            "census_year": year, "city_name": city, "source_record_id": rid,
            "population_source_file": str(POP_SOURCES[year]["path"]),
            "population_source_sha256": POP_SOURCES[year]["sha256"],
            "population_source_locator": locator,
            "source_population": pop, "source_scope_class": "federal_city_territory",
            "object_scope": "federal_city_territory", "point_role": "territory_reference",
            "wikidata_qid": c["qid"], "longitude": c["lon"], "latitude": c["lat"],
            "coordinate_crs": "WGS84", "coordinate_property": "Wikidata P625",
            "coordinate_raw_value": c["raw_point"], "coordinate_claim_source_file": c["wd_file"],
            "coordinate_claim_source_line": c["wd_line"],
            "coordinate_claim_source_sha256": sha(RAW / "wikidata_truthy_claims" / c["wd_file"]),
            "coordinate_retrieved_at_utc": p625.get("retrieved_at_utc"),
            "coordinate_point_semantics": "current city entity point reused as representative territory reference; not a population centroid or physical-NP point",
            "source_locator": locator, "selected_source_record_id": rid,
            "aggregate_ceiling_addendum": "federal_atomic_scope_ceiling_addendum_v1",
            "aggregate_source_label": str(a.iloc[0].source_label),
            "source_scope_evidence_status": "federal aggregate retained at territory grain; exact source ID and population unchanged",
            "qid_binding_status": status,
            "identity_relation_status": "same continuing city entity relation allowed; no atomic same_place edge created",
            "observation_grain_note": ("2002 Moscow physical-city observation is a distinct grain from 2010/2021 Moscow federal-territory observations; city continuity does not assert equal boundaries or count scope" if city == "Москва" else "federal-territory observation; not a physical populated-place count"),
            "additivity_rule": "select this parent territory total in place of every included child in the same year; never sum parent and child observations",
            "admission_status": "authorized secondary spatial representation staging; requires integration into separate territory metric",
        })
    federal = pd.DataFrame(bindings)
    write_csv(federal, OUT / "federal_territory_reference_bindings.csv")

    baseline = json.loads(BASELINE.read_text())
    metrics = {int(x["year"]): x for x in baseline["metrics"]}
    gains = []
    for y in sorted(set(int(x["census_year"]) for x in bindings)):
        ids = [x for x in bindings if x["census_year"] == y]
        m = metrics[y]
        pop = sum(int(x["source_population"]) for x in ids)
        current = int(m["canonical_national_point_coverage"] * int(m["control"]))
        # Baseline canonical population has no federal aggregate rows in its accepted
        # point numerator. Conditional value assumes parent selection displaces all
        # child contributions in those federal territories, retaining one total.
        numerator = current + pop
        control = int(m["control"])
        gains.append({"census_year": y, "baseline_joint_coordinate_population": m["axes"]["joint_admitted_coordinate_and_full_chain"]["known_population"],
                      "baseline_joint_coordinate_full_chain_share": m["axes"]["joint_admitted_coordinate_and_full_chain"]["official_control_population_fraction"],
                      "federal_territory_population": pop, "federal_source_record_ids_json": json.dumps([x["source_record_id"] for x in ids], ensure_ascii=False),
                      "conditional_spatial_numerator_after_exclusive_parent_selection": numerator,
                      "official_control": control, "conditional_spatial_coverage_pct": round(100*numerator/control, 6),
                      "incremental_spatial_population_gain": pop,
                      "exclusive_parent_children_rule": "one parent total per city replaces all contained child populations; source-child identities have not been changed or merged",
                      "status": "conditional ceiling scenario; point bindings staged, not admitted coverage"})
    # Full-chain scenario for the 2021 federal cities: only Moscow and Petersburg have
    # census observations in both 2002 and 2010; Sevastopol is explicitly outside those
    # Russian census territories. This adds territory observations, not same_place edges.
    y21 = metrics[2021]
    current_joint = int(y21["axes"]["joint_admitted_coordinate_and_full_chain"]["known_population"])
    msp = sum(x["source_population"] for x in bindings if x["census_year"] == 2021 and x["city_name"] in ("Москва", "Санкт-Петербург"))
    strict = current_joint + msp
    gains.append({"census_year": 2021, "baseline_joint_coordinate_population": current_joint,
                  "baseline_joint_coordinate_full_chain_share": y21["axes"]["joint_admitted_coordinate_and_full_chain"]["official_control_population_fraction"],
                  "federal_territory_population": msp, "federal_source_record_ids_json": json.dumps([x["source_record_id"] for x in bindings if x["census_year"] == 2021 and x["city_name"] in ("Москва", "Санкт-Петербург")], ensure_ascii=False),
                  "conditional_spatial_numerator_after_exclusive_parent_selection": strict,
                  "official_control": int(y21["control"]), "conditional_spatial_coverage_pct": round(100*strict/int(y21["control"]), 6),
                  "incremental_spatial_population_gain": msp,
                  "exclusive_parent_children_rule": "Moscow and Saint Petersburg territory roots replace included children; same city identity across 2002/2010/2021 may support chain relation while observation scopes remain distinct",
                  "status": "conditional joint-coordinate/full-chain scenario; Sevastopol excluded from strict 2002-2010-2021 chain as outside prior Russian census coverage"})
    # Exact selected 2021 Crimea population and Sevastopol amounts are preserved as
    # separate scope facts; Crimea is not a zero for prior Russian census years.
    crimea = con.execute("select sum(population) from read_parquet(?) where census_year=2021 and (lower(region_raw) like '%крым%' or lower(region_norm) like '%крым%')", [str(OBS)]).fetchone()[0]
    crimea = int(crimea or 0)
    outside_scope = crimea + 547820
    strict_maximum = int(y21["control"]) - outside_scope
    gains[-1]["selected_2021_crimea_population"] = crimea
    gains[-1]["selected_2021_sevastopol_population"] = 547820
    gains[-1]["selected_2021_crimea_plus_sevastopol_outside_old_census_population"] = outside_scope
    gains[-1]["strict_chain_maximum_2021_population_after_geographic_exclusions"] = strict_maximum
    gains[-1]["strict_chain_geographic_exclusion_share_pct"] = round(100*outside_scope/int(y21["control"]), 6)
    gains[-1]["strict_chain_maximum_coverage_pct_before_other_holds"] = round(100*strict_maximum/int(y21["control"]), 6)
    gains[-1]["strict_chain_below_99pct_by_people_from_geographic_exclusions_alone"] = max(0, int(y21["targets"]["99_percent"]["minimum_population"]) - strict_maximum)
    gains[-1]["strict_full_chain_out_of_scope_reason"] = "Crimea and Sevastopol lack Russian 2002/2010 census endpoints; absence is outside-scope, never zero"
    gains[-1]["full_chain_99pct_feasible_with_federal_rows_alone"] = strict >= int(y21["targets"]["99_percent"]["minimum_population"])
    write_csv(pd.DataFrame(gains), OUT / "federal_joint_potential_gains.csv")

    # Build one row per nondeprecated QID+statement ID from cached TSV, enriching the
    # 4,984 overlapping full-entity statements. Full qualifiers/references take priority.
    tsv = con.execute("select * from read_parquet(?)", [str(HISTORY_TSV)]).df()
    full = con.execute("select * from read_parquet(?)", [str(HISTORY_FULL)]).df()
    assert tsv.statement_id.notna().all() and not tsv.duplicated(["qid", "statement_id"]).any()
    assert not full.duplicated(["wikidata_qid", "statement_id"]).any()
    full = full.rename(columns={"wikidata_qid": "qid"})
    fullcols = ["qid", "statement_id", "population_amount_literal", "rank", "p585_literals_json",
                "p585_literal_year_prefixes_json", "references_count", "references_with_p854_url_count",
                "reference_p854_urls_json", "all_references_raw_json", "raw_statement_json",
                "raw_record_locator", "raw_claim_index_in_entity", "entity_batch_file", "entity_batch_sha256",
                "entity_retrieved_at_utc", "entity_modified_utc", "entity_lastrevid"]
    full = full[fullcols].copy()
    d = tsv[~tsv.rank_is_deprecated.fillna(False)].copy()
    d = d.merge(full, on=["qid", "statement_id"], how="left", validate="one_to_one", suffixes=("_tsv", "_full"))
    d["source_tier"] = d.raw_statement_json.notna().map({True: "full_entity_statement", False: "flat_TSV_statement"})
    d["population_value_raw"] = d.population_amount_literal.combine_first(d.population_literal_flat_tsv)
    d["rank_raw"] = d["rank"].combine_first(d.rank_uri_flat_tsv)
    d["population_quality"] = "wikidata_secondary_primary_not_independently_verified"
    d["observation_class"] = "dated_secondary_population_observation"
    d["historical_identity_status"] = "not_asserted_by_dated_population_statement"
    d["population_admission_status"] = "working_series_only; not exact census replacement"
    d["date_ambiguous_hold"] = d.date_literal_ambiguous.fillna(False) | (d.date_literal_variant_count.fillna(1) > 1)
    d["year_prefix"] = d.date_literal_flat_tsv.astype("string").str.extract(r"([+-]?\d{4})", expand=False)
    full_dates = d.p585_literal_year_prefixes_json.fillna("[]").map(json.loads)
    d["full_year_prefixes_json"] = full_dates.map(lambda x: json.dumps(x, ensure_ascii=False))
    d["date_precision"] = "not recoverable from flat TSV date literal"
    d["date_raw_full_statement"] = d.p585_literals_json
    for i in d.index[d.source_tier == "full_entity_statement"]:
        try:
            p585 = json.loads(d.at[i, "p585_literals_json"] or "[]")
            precisions = [x.get("precision") for x in p585 if x.get("precision") is not None]
            d.at[i, "date_precision"] = json.dumps(precisions)
        except Exception:
            pass
    d.loc[d.date_ambiguous_hold, "year_prefix"] = pd.NA
    d["date_assignment_status"] = d.date_ambiguous_hold.map({True: "date_ambiguity_hold_no_chosen_year", False: "year_prefix_working_label_not_census_assignment"})
    d["raw_source_file"] = d.raw_source_file.fillna(str(RAW / "wikimedia/wikidata_oktmo_population.tsv"))
    d["raw_source_sha256"] = d.raw_source_sha256.fillna(sha(RAW / "wikimedia/wikidata_oktmo_population.tsv"))
    d["raw_reference_payload_json"] = d.all_references_raw_json
    d["raw_source_locator"] = d.raw_record_locator.combine_first(d.raw_source_line_number.astype("Int64").astype("string").radd("TSV line "))
    d["current_qid_binding_status"] = d.target_source_record_ids_2021_json.map(lambda x: "2021 exact-code candidate target recorded; identity/coordinate review status is separate" if x and x != "[]" else "no 2021 target record listed in cached working inventory")
    output_cols = ["qid", "statement_id", "population_value_raw", "year_prefix", "date_assignment_status", "date_ambiguous_hold",
                   "date_precision", "full_year_prefixes_json", "date_literal_flat_tsv", "date_literal_variants_json", "date_raw_full_statement",
                   "rank_raw", "rank_is_deprecated", "population_quality", "observation_class", "population_admission_status",
                   "historical_identity_status", "current_qid_binding_status", "target_source_record_ids_2021_json", "source_tier",
                   "raw_source_file", "raw_source_sha256", "raw_tsv_line_number", "raw_matching_line_numbers_json",
                   "raw_source_locator", "raw_record_locator", "raw_claim_index_in_entity", "entity_batch_file", "entity_batch_sha256",
                   "entity_retrieved_at_utc", "entity_modified_utc", "entity_lastrevid", "references_count",
                   "references_with_p854_url_count", "reference_p854_urls_json", "raw_reference_payload_json", "raw_statement_json"]
    series = d[output_cols].copy()
    series = series.sort_values(["qid", "year_prefix", "statement_id"], na_position="last")
    series.to_parquet(OUT / "wikidata_secondary_working_series.parquet", index=False)
    # Accessible smaller flat CSV accompanies the typed full parquet.
    write_csv(series, OUT / "wikidata_secondary_working_series.csv")

    # The focused 64,483-row cache is not the full historical Wikidata inventory.
    # Export every legacy-DB P1082 observation, retaining source lineage and joining
    # only explicit QID-to-2021 exact-code candidates as candidate evidence.
    legacy = duckdb.connect(str(LEGACY_DB), read_only=True)
    wd = legacy.execute("""
        with base as (
          select *, row_number() over () as _row_id,
                 coalesce(wikidata_statement_id, 'NO_STATEMENT|' || cast(row_number() over () as varchar)) as _statement_key
          from population_observations
        where source_family='wikidata'
          and (observation_year is null or observation_year <= 2026)
          and (observation_date is null or observation_date <= TIMESTAMPTZ '2026-10-03 23:59:59+00')
          and coalesce(link_quality_flag,'') not ilike '%deprecated%'
        )
        select any_value(settlement_id) as settlement_id,
               any_value(observation_year) as observation_year,
               any_value(observation_date) as observation_date,
               any_value(population) as population,
               any_value(source_family) as source_family,
               any_value(source_detail) as source_detail,
               any_value(source_record_id) as source_record_id,
               wikidata_id, wikidata_statement_id,
               any_value(link_method) as link_method,
               any_value(link_quality_flag) as link_quality_flag,
               any_value(population_scope) as population_scope,
               any_value(source_priority) as source_priority,
               any_value(source_url) as source_url,
               any_value(year_evidence_text) as year_evidence_text,
               any_value(temporal_quality_flag) as temporal_quality_flag,
               any_value(note) as note,
               count(*) as duplicate_legacy_row_count,
               to_json(list_sort(list_distinct(list(cast(population as varchar))))) as legacy_population_variants_json,
               to_json(list_sort(list_distinct(list(cast(observation_date as varchar))))) as legacy_observation_date_variants_json,
               to_json(list_sort(list_distinct(list(cast(observation_year as varchar))))) as legacy_year_variants_json,
               to_json(list_sort(list_distinct(list(settlement_id)))) as legacy_settlement_id_variants_json
        from base
        group by wikidata_id, wikidata_statement_id, _statement_key
    """).df()
    wide_candidate = con.execute("""
        select wikidata_qid,
               list(distinct source_record_id) as candidate_2021_source_record_ids,
               list(distinct candidate_status) as candidate_statuses,
               bool_or(identity_admission) as any_identity_admitted,
               bool_or(coordinate_admission) as any_coordinate_admitted
        from read_parquet(?) where wikidata_qid is not null group by wikidata_qid
    """, [str(WIDE)]).df()
    candidate_by_qid = wide_candidate.set_index("wikidata_qid", drop=False)
    legacy_full_cols = ["qid", "statement_id", "population_value_raw", "year_prefix", "date_ambiguous_hold",
                        "date_literal_flat_tsv", "date_precision", "full_year_prefixes_json", "date_raw_full_statement", "rank_raw", "source_tier",
                        "references_count", "references_with_p854_url_count", "reference_p854_urls_json",
                        "raw_reference_payload_json", "raw_statement_json", "raw_record_locator",
                        "raw_source_file", "raw_source_sha256", "raw_tsv_line_number", "entity_batch_file",
                        "entity_batch_sha256", "entity_retrieved_at_utc"]
    tiered = series[legacy_full_cols].drop_duplicates(["qid", "statement_id"]).copy()
    tiered["statement_id"] = tiered.statement_id.astype("string").str.replace("$", "-", regex=False)
    tiered = tiered.rename(columns={"qid": "wikidata_id", "statement_id": "wikidata_statement_id",
                                    "population_value_raw": "full_tier_population_value_raw",
                                    "year_prefix": "full_tier_year_prefix",
                                    "date_precision": "full_tier_date_precision"})
    # Summarize duplicate copies by stable Wikidata statement ID. Conflicting values
    # or dates stay visible as holds; a repeated legacy settlement_id is not identity.
    allwd = wd.copy()
    allwd["population_variant_conflict"] = allwd.legacy_population_variants_json.map(lambda x: len(json.loads(x or "[]")) > 1)
    allwd["date_variant_conflict"] = allwd.legacy_observation_date_variants_json.map(lambda x: len(json.loads(x or "[]")) > 1) | allwd.legacy_year_variants_json.map(lambda x: len(json.loads(x or "[]")) > 1)
    allwd["legacy_duplicate_rows_removed"] = allwd.duplicate_legacy_row_count - 1
    # Full-entity statements override flat/legacy details where statement IDs overlap.
    allwd = allwd.merge(tiered, on=["wikidata_id", "wikidata_statement_id"], how="left", validate="one_to_one")
    allwd["secondary_source_quality"] = "wikidata_secondary_primary_not_independently_verified"
    allwd["working_observation_class"] = "dated_secondary_population_observation"
    allwd["source_level_population_scope"] = allwd.population_scope
    allwd["population_value_raw_for_display"] = allwd.population.astype("string")
    allwd.loc[allwd.population_variant_conflict, "population_value_raw_for_display"] = pd.NA
    full_mask = allwd.source_tier.eq("full_entity_statement")
    allwd.loc[full_mask, "population_value_raw_for_display"] = allwd.loc[full_mask, "full_tier_population_value_raw"]
    allwd["working_year_label"] = allwd.observation_year.astype("Int64").astype("string")
    allwd.loc[allwd.date_variant_conflict, "working_year_label"] = pd.NA
    # Full entity P585 qualifiers override flat/legacy date variants when exactly
    # one dated year remains; absent or multiple qualifier dates remain held.
    for i in allwd.index[full_mask]:
        try:
            prefixes = json.loads(allwd.at[i, "full_year_prefixes_json"] or "[]")
        except Exception:
            prefixes = []
        if len(prefixes) == 1:
            allwd.at[i, "working_year_label"] = str(prefixes[0])
            allwd.at[i, "date_variant_conflict"] = False
        else:
            allwd.at[i, "working_year_label"] = pd.NA
            allwd.at[i, "date_variant_conflict"] = True
    allwd["date_assignment_status"] = "legacy_db_observed_year_not_census_assignment"
    allwd.loc[allwd.date_variant_conflict, "date_assignment_status"] = "date_ambiguity_hold_no_chosen_year"
    allwd.loc[allwd.population_variant_conflict, "date_assignment_status"] = "population_variant_hold"
    allwd["date_precision"] = allwd.temporal_quality_flag.fillna("precision_not_recorded")
    allwd.loc[full_mask, "date_precision"] = allwd.loc[full_mask, "full_tier_date_precision"]
    allwd["historical_identity_asserted"] = False
    allwd["historical_coordinate_asserted"] = False
    allwd["legacy_settlement_id_identity_status"] = "candidate_only; legacy ID alone does not admit identity"
    binding_lookup = {}
    for r in wide_candidate.itertuples(index=False):
        ids, statuses = r.candidate_2021_source_record_ids, r.candidate_statuses
        if hasattr(ids, "tolist"): ids = ids.tolist()
        if hasattr(statuses, "tolist"): statuses = statuses.tolist()
        ids, statuses = ids or [], statuses or []
        binding_lookup[r.wikidata_qid] = (json.dumps(ids, ensure_ascii=False), json.dumps(statuses, ensure_ascii=False),
                                           bool(r.any_identity_admitted) if pd.notna(r.any_identity_admitted) else False,
                                           bool(r.any_coordinate_admitted) if pd.notna(r.any_coordinate_admitted) else False)
    allwd["f2021_candidate_source_record_ids_json"] = allwd.wikidata_id.map(lambda q: binding_lookup.get(q, ("[]", "[]", False, False))[0])
    allwd["f2021_candidate_statuses_json"] = allwd.wikidata_id.map(lambda q: binding_lookup.get(q, ("[]", "[]", False, False))[1])
    allwd["f2021_any_identity_admitted_in_screen"] = allwd.wikidata_id.map(lambda q: binding_lookup.get(q, ("[]", "[]", False, False))[2])
    allwd["f2021_any_coordinate_admitted_in_screen"] = allwd.wikidata_id.map(lambda q: binding_lookup.get(q, ("[]", "[]", False, False))[3])
    allwd["f2021_binding_status"] = allwd.f2021_candidate_source_record_ids_json.map(lambda x: "no exact-code candidate" if x == "[]" else "candidate only; screen identity status in separate boolean")
    allwd["full_entity_tier_priority_applied"] = allwd.source_tier.eq("full_entity_statement")
    allwd = allwd.sort_values(["wikidata_id", "observation_year", "wikidata_statement_id"], na_position="last")
    allwd.to_parquet(OUT / "wikidata_secondary_full_history.parquet", index=False)
    write_csv(allwd, OUT / "wikidata_secondary_full_history.csv")
    legacy.close()

    # Historical values for three federal city entities at actual cached dates. A
    # year prefix is retained literally; no year is coerced to a census date.
    # Federal territory roots are intentionally absent from the 64,483-record
    # locality-targeted cache inventory. Extract their actual raw TSV statements
    # separately so real years (notably 1989/2001) can be shown with honest lineage.
    qid_city = {v["qid"]: name for name, v in CITIES.items()}
    qid_lookup = set(qid_city)
    raw_pop = pd.read_csv(RAW / "wikimedia/wikidata_oktmo_population.tsv", sep="\t",
                          engine="python", dtype=str, keep_default_na=False)
    raw_pop["qid"] = raw_pop["?item"].str.extract(r"(Q\d+)", expand=False)
    raw_city = raw_pop[raw_pop.qid.isin(qid_lookup)].copy()
    raw_city["raw_tsv_line_number"] = raw_city.index + 2
    raw_city["statement_id"] = raw_city["?statement"].str.extract(r"(Q\d+-[A-F0-9-]+)", expand=False)
    city_records = []
    for sid, rows in raw_city.groupby("statement_id", dropna=False, sort=False):
        qids = sorted(set(rows.qid))
        vals = sorted(set(rows["?population"]))
        dates = sorted(set(rows["?date"]))
        ranks = sorted(set(rows["?rank"]))
        qid = qids[0] if len(qids) == 1 else None
        ambiguous = len(qids) != 1 or len(vals) != 1 or len(dates) != 1 or len(ranks) != 1
        date = dates[0] if len(dates) == 1 else None
        city_records.append({
            "qid": qid, "current_city_name": qid_city.get(qid), "statement_id": sid,
            "population_value_raw": vals[0] if len(vals) == 1 else json.dumps(vals, ensure_ascii=False),
            "year_prefix": (re.search(r"[+-]?\d{4}", date).group(0) if date and re.search(r"[+-]?\d{4}", date) else None) if not ambiguous else None,
            "date_literal_raw": date if date else json.dumps(dates, ensure_ascii=False),
            "date_precision": "not present in flat TSV; normalized date literal only",
            "date_ambiguous_hold": ambiguous,
            "date_assignment_status": "date_ambiguity_hold_no_chosen_year" if ambiguous else "year_prefix_working_label_not_census_assignment",
            "rank_raw": ranks[0] if len(ranks) == 1 else json.dumps(ranks, ensure_ascii=False),
            "rank_is_deprecated": any("DeprecatedRank" in r for r in ranks),
            "population_scope": "Wikidata P1082 scope unknown; requires date-specific source review",
            "population_quality": "wikidata_secondary_primary_not_independently_verified",
            "observation_class": "dated_secondary_population_observation_federal_city_entity",
            "population_admission_status": "working_series_only; not exact census replacement",
            "historical_identity_status": "current QID binding; no dated historical boundary or population-scope identity asserted",
            "city_continuity_binding_basis": "current city QID; source observation's census-year place membership requires independent date-specific source",
            "raw_source_file": str(RAW / "wikimedia/wikidata_oktmo_population.tsv"),
            "raw_source_sha256": sha(RAW / "wikimedia/wikidata_oktmo_population.tsv"),
            "raw_tsv_line_numbers_json": json.dumps([int(x) for x in rows.raw_tsv_line_number], ensure_ascii=False),
            "raw_matching_line_count": int(len(rows)),
            "reference_payload_status": "no full entity references present in this TSV inventory",
        })
    city_history = pd.DataFrame(city_records)
    city_history = city_history[~city_history.rank_is_deprecated].sort_values(["qid", "year_prefix", "statement_id"], na_position="last")
    write_csv(city_history, OUT / "federal_city_dated_history.csv")
    city_profile = (allwd[allwd.wikidata_id.isin(qid_lookup) & allwd.working_year_label.notna()]
                    .groupby(["wikidata_id", "working_year_label"], as_index=False)
                    .agg(statement_count=("wikidata_statement_id", "nunique"),
                         date_ambiguity_holds=("date_variant_conflict", "sum"),
                         population_value_holds=("population_variant_conflict", "sum")))
    city_profile["city_name"] = city_profile.wikidata_id.map(qid_city)
    city_profile["current_qid_binding_note"] = "current city QID only; dated population scope and historical location require independent evidence"
    city_profile["annual_denominator_status"] = "no national year denominator in this output"
    write_csv(city_profile, OUT / "federal_city_year_coverage.csv")

    # Crimea-specific alternative coverage: show which selected 2021 source IDs have
    # at least one real, nonambiguous Wikidata P1082 year on their current QID. This
    # supports a secondary observed-year display only; it creates no 2002/2010 RU link.
    crimea2021 = con.execute("""
        select o.source_record_id as current_2021_source_record_id, o.settlement_name,
               o.settlement_type, o.region_raw, o.population as current_2021_population,
               o.population_value_quality, w.wikidata_qid,
               w.candidate_status as f2021_qid_candidate_status,
               w.identity_admission as f2021_identity_admission,
               w.coordinate_admission as f2021_coordinate_admission
        from read_parquet(?) o
        join read_parquet(?) w using(source_record_id)
        where o.census_year=2021
          and (lower(o.region_raw) like '%крым%' or lower(o.region_norm) like '%крым%')
          and w.wikidata_qid is not null
    """, [str(OBS), str(WIDE)]).df()
    hist_for_crimea = allwd[allwd.wikidata_id.isin(set(crimea2021.wikidata_qid))].copy()
    witnesses = hist_for_crimea[
        hist_for_crimea.working_year_label.notna()
        & hist_for_crimea.working_year_label.astype(str).ne("2021")
        & ~hist_for_crimea.date_variant_conflict.fillna(False)
        & ~hist_for_crimea.population_variant_conflict.fillna(False)
    ].copy()
    witness_fields = ["wikidata_id", "wikidata_statement_id", "working_year_label",
                      "population_value_raw_for_display", "observation_date", "date_precision",
                      "temporal_quality_flag", "link_quality_flag", "source_detail", "source_url",
                      "source_tier", "full_tier_date_precision", "raw_reference_payload_json",
                      "date_variant_conflict", "population_variant_conflict"]
    witnesses = witnesses[witness_fields].copy()
    witnesses["history_source_file"] = str(LEGACY_DB)
    witnesses["history_source_sha256"] = "26a2fe5b2ce05119d919a196beb57cd655a49ffffb0ff8f194762aa78e6b5b64"
    witnesses["historical_witness_source_status"] = "Wikidata P1082 working observation; primary source not independently verified"
    witnesses["historical_relation_status"] = "current QID candidate relation only; no historical identity or Russian census endpoint admitted"
    witness_groups = {}
    for qid, g in witnesses.groupby("wikidata_id", sort=False):
        cols = ["wikidata_statement_id", "working_year_label", "population_value_raw_for_display",
                "observation_date", "date_precision", "temporal_quality_flag", "link_quality_flag",
                "source_detail", "source_url", "source_tier", "full_tier_date_precision",
                "raw_reference_payload_json", "history_source_file", "history_source_sha256",
                "historical_witness_source_status", "historical_relation_status"]
        witness_groups[qid] = g[cols].where(pd.notna(g[cols]), None).to_dict(orient="records")
    conflict_holds = hist_for_crimea[hist_for_crimea.date_variant_conflict.fillna(False) | hist_for_crimea.population_variant_conflict.fillna(False)].copy()
    conflict_groups = {}
    for qid, g in conflict_holds.groupby("wikidata_id", sort=False):
        cols = ["wikidata_statement_id", "legacy_observation_date_variants_json", "legacy_year_variants_json",
                "legacy_population_variants_json", "date_variant_conflict", "population_variant_conflict",
                "raw_reference_payload_json", "raw_statement_json"]
        conflict_groups[qid] = g[cols].where(pd.notna(g[cols]), None).to_dict(orient="records")
    eligible = crimea2021[crimea2021.wikidata_qid.isin(witness_groups)].copy()
    eligible["secondary_other_year_witness_count"] = eligible.wikidata_qid.map(lambda q: len(witness_groups[q]))
    eligible["secondary_other_year_years_json"] = eligible.wikidata_qid.map(lambda q: json.dumps(sorted({x["working_year_label"] for x in witness_groups[q]}), ensure_ascii=False))
    eligible["secondary_other_year_witnesses_json"] = eligible.wikidata_qid.map(lambda q: json.dumps(witness_groups[q], ensure_ascii=False, default=str))
    eligible["has_1989_dated_literal_witness"] = eligible.wikidata_qid.map(lambda q: "1989" in {x["working_year_label"] for x in witness_groups[q]})
    eligible["has_2001_dated_literal_witness"] = eligible.wikidata_qid.map(lambda q: "2001" in {x["working_year_label"] for x in witness_groups[q]})
    eligible["secondary_date_conflict_hold_count"] = eligible.wikidata_qid.map(lambda q: len(conflict_groups.get(q, [])))
    eligible["secondary_date_conflict_holds_json"] = eligible.wikidata_qid.map(lambda q: json.dumps(conflict_groups.get(q, []), ensure_ascii=False, default=str))
    eligible["history_source_file"] = str(LEGACY_DB)
    eligible["history_source_sha256"] = "26a2fe5b2ce05119d919a196beb57cd655a49ffffb0ff8f194762aa78e6b5b64"
    eligible["f2021_qid_binding_status"] = "exact-code Wikidata QID candidate; not accepted identity or coordinate binding"
    eligible["strict_Russian_2002_2010_2021_chain_eligible"] = False
    eligible["strict_chain_hold_reason"] = "Crimea is outside Russian census territorial coverage in 2002 and 2010; no zero or substitute endpoint"
    eligible["applicable_observed_series_status"] = "eligible for secondary dated-value display only, subject to source-scope review; not exact census replacement"
    eligible["historical_coordinate_status"] = "no historical coordinate asserted or copied from current P625"
    write_csv(eligible, OUT / "crimea_eligible_outsidecoverage_ids.csv")
    dated_89_01 = witnesses[witnesses.working_year_label.isin(["1989", "2001"])].merge(
        crimea2021[["current_2021_source_record_id", "current_2021_population", "settlement_name", "wikidata_qid"]],
        left_on="wikidata_id", right_on="wikidata_qid", how="inner", validate="many_to_many")
    dated_89_01["date_literal_source_status"] = "legacy read-only database derived from Wikidata P1082; year preserved as source observation, not census-date validation"
    dated_89_01["source_country_or_census_assignment"] = "not asserted; 1989 is not a Russian 2002/2010 endpoint and 2001 values are not independently verified Ukraine census values"
    dated_89_01["identity_status"] = "candidate QID binding only; no historical identity admission"
    dated_89_01["history_source_file"] = str(LEGACY_DB)
    dated_89_01["history_source_sha256"] = "26a2fe5b2ce05119d919a196beb57cd655a49ffffb0ff8f194762aa78e6b5b64"
    write_csv(dated_89_01, OUT / "crimea_1989_2001_dated_literal_witnesses.csv")
    def coverage_year(year: str) -> dict:
        ids = eligible[eligible.wikidata_qid.isin(set(witnesses.loc[witnesses.working_year_label.astype(str) == year, "wikidata_id"]))]
        return {"witness_year_literal": int(year), "eligible_2021_source_id_count": int(ids.current_2021_source_record_id.nunique()),
                "eligible_current_2021_population": int(ids.current_2021_population.sum()),
                "current_population_share_of_selected_Crimea": round(100*int(ids.current_2021_population.sum())/max(1,int(crimea2021.current_2021_population.sum())),6),
                "interpretation": "candidate observed-year display coverage only; not census-date or national denominator coverage"}
    crimea_conditional = {
        "status": "candidate_coverage_only_no_population_or_identity_admission",
        "selected_2021_crimea": {"rows": int(crimea2021.current_2021_source_record_id.nunique()),
                                 "population": int(crimea2021.current_2021_population.sum()),
                                 "exact_qid_candidate_rows": int(crimea2021.current_2021_source_record_id.nunique())},
        "secondary_series_eligibility": {"eligible_current_2021_source_ids": int(eligible.current_2021_source_record_id.nunique()),
                                         "eligible_current_2021_population": int(eligible.current_2021_population.sum()),
                                         "selected_Crimea_population_share_pct": round(100*int(eligible.current_2021_population.sum())/max(1,int(crimea2021.current_2021_population.sum())),6),
                                         "current_ids_with_additional_ambiguous_history_holds": int(eligible.loc[eligible.secondary_date_conflict_hold_count > 0, "current_2021_source_record_id"].nunique()),
                                         "ambiguous_history_hold_statement_rows": int(eligible.secondary_date_conflict_hold_count.sum()),
                                         "conditional_1989": coverage_year("1989"), "conditional_2001": coverage_year("2001"),
                                         "identity_from_legacy_identifier_alone": False},
        "strict_Russian_2002_2010_2021_chain": {"eligible_current_Crimea_ids": 0, "eligible_current_Crimea_population": 0,
                                                 "reason": "outside Russian census territorial scope in 2002/2010; missing endpoints are not zero"},
        "limits": ["Wikidata is secondary and not primary-source verified", "a current QID candidate does not prove date-specific identity or scope", "1989 and 2001 labels do not establish Russian census endpoints", "no historical coordinates are asserted", "the file contains candidate population eligibility, not additive year totals"],
        "outputs": ["crimea_eligible_outsidecoverage_ids.csv", "crimea_1989_2001_dated_literal_witnesses.csv"]
    }
    (OUT / "crimea_conditional_series_coverage.json").write_text(json.dumps(crimea_conditional, ensure_ascii=False, indent=2) + "\n")

    # Scoped current-place QID binding for the full dated series. This is an
    # independent name/code/object-grain gate; point acceptance is joined only as
    # separate context and P625 multiplicity never acts as an identity veto.
    HB = OUT / "history_bindings"
    HB.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from research_rebuild.mass_linkage.coordinate_validation_packet import wikidata_type_lineage
    hierarchy_path = Path("/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json")
    p31_profiles = wikidata_type_lineage(json.loads(hierarchy_path.read_text()))
    def norm(v):
        if v is None or pd.isna(v): return ""
        return " ".join(unicodedata.normalize("NFKC", str(v)).casefold().replace("ё", "е").split())
    def regnorm(v):
        return re.sub(r"\s+(?:область|край|республика|автономная область|автономный округ)$", "", norm(v))
    def jslist(v):
        if v is None or pd.isna(v) or not str(v): return []
        try: return json.loads(str(v))
        except Exception: return []
    def code_digits(v):
        if v is None or pd.isna(v): return ""
        return re.sub(r"\D", "", str(v))
    selected21 = obs[(obs.census_year == 2021) & obs.is_additive_settlement_record.fillna(False)].copy()
    selected21 = selected21[~selected21.population_scope.fillna("").astype(str).str.contains("federal|territory|aggregate", case=False, regex=True)].copy()
    wide_all = con.execute("""
        select source_record_id, source_row, source_oktmo_raw, source_oktmo_exact_digits,
               source_name, source_type, source_region, wikidata_qid,
               wikidata_tsv_exact_p764_value_raw, wikidata_truthy_exact_p764_match,
               wikidata_truthy_exact_p764_claims_json, wikidata_name_exact_label,
               wikidata_tsv_ru_labels_json, wikidata_truthy_p31_claims_json,
               wikidata_truthy_p131_claims_json, wikidata_tsv_admin_qids_json,
               wikidata_tsv_ru_admin_labels_json, entity_competition_across_tsv_or_truthy,
               tsv_entity_competition_for_exact_oktmo, truthy_entity_competition_for_exact_oktmo,
               source_observation_competition_for_exact_oktmo, truthy_p625_point_count,
               wikidata_truthy_p625_claims_json, points_json, candidate_status,
               identity_admission, coordinate_admission
        from read_parquet(?)
    """, [str(WIDE)]).df()
    # WIDE intentionally retains multiple Wikidata entities for some exact source
    # codes. Preserve that competition as an explicit hold while making the source
    # row join one-to-one with the selected census observations.
    wide_all["wide_qid_values_json"] = wide_all.wikidata_qid.map(lambda x: json.dumps([x] if pd.notna(x) else [], ensure_ascii=False))
    wide_row_counts = wide_all.groupby("source_record_id").size().rename("source_record_wide_row_count")
    wide_cols = [c for c in wide_all.columns if c not in ("source_record_id", "wide_qid_values_json")]
    agg_spec = {c: "first" for c in wide_cols}
    agg_spec["wide_qid_values_json"] = lambda s: json.dumps(sorted({str(q) for raw in s for q in json.loads(raw)}), ensure_ascii=False)
    wide_all = wide_all.groupby("source_record_id", as_index=False).agg(agg_spec)
    wide_all = wide_all.merge(wide_row_counts, left_on="source_record_id", right_index=True, validate="one_to_one")
    wide_all["source_row_qid_unique"] = wide_all.wide_qid_values_json.map(lambda x: len(json.loads(x)) == 1)
    bindings = selected21.merge(wide_all, on="source_record_id", how="left", validate="one_to_one", suffixes=("_target", "_wide"))
    bindings["current_source_name_exact"] = bindings.apply(lambda r: norm(r.get("settlement_name")) == norm(r.get("source_name")), axis=1)
    bindings["current_source_type_exact"] = bindings.apply(lambda r: norm(r.get("settlement_type")) == norm(r.get("source_type")), axis=1)
    bindings["current_source_region_exact"] = bindings.apply(lambda r: regnorm(r.get("region_raw")) == regnorm(r.get("source_region")), axis=1)
    bindings["current_ru_label_exact"] = bindings.apply(lambda r: bool(r.get("wikidata_name_exact_label")) and any(norm(x) == norm(r.get("settlement_name")) for x in jslist(r.get("wikidata_tsv_ru_labels_json"))), axis=1)
    def p764_match(r):
        match = r.get("wikidata_truthy_exact_p764_match")
        code = r.get("source_oktmo_exact_digits")
        value = r.get("wikidata_tsv_exact_p764_value_raw")
        # Missing WIDE rows must be false: bool(np.nan) is true, and treating two
        # missing values as normalized empty strings created a false-positive hold
        # diagnostic (the reviewed pass set was unaffected by other gates).
        if match is None or pd.isna(match) or not bool(match): return False
        if code is None or pd.isna(code) or not str(code).strip(): return False
        if value is None or pd.isna(value) or not str(value).strip(): return False
        return norm(code) == norm(value)
    bindings["exact_source_oktmo_p764"] = bindings.apply(p764_match, axis=1)
    bindings["selected_OKTMO_matches_exact_WIDE_code"] = bindings.apply(lambda r: code_digits(r.get("oktmo")) == code_digits(r.get("source_oktmo_exact_digits")), axis=1)
    # Uniqueness is checked on source code and QID across the complete WIDE screen,
    # in addition to its native-code competition flags.
    code_counts = wide_all.dropna(subset=["source_oktmo_exact_digits"]).groupby("source_oktmo_exact_digits").agg(qids=("wikidata_qid", "nunique"), source_rows=("source_record_id", "nunique"))
    qid_counts = wide_all.dropna(subset=["wikidata_qid"]).groupby("wikidata_qid").agg(codes=("source_oktmo_exact_digits", "nunique"), source_rows=("source_record_id", "nunique"))
    bindings["source_code_unique_qid"] = bindings.source_oktmo_exact_digits.map(code_counts.qids).fillna(0).eq(1) & bindings.source_row_qid_unique.fillna(False)
    bindings["qid_unique_current_source_code"] = bindings.wikidata_qid.map(qid_counts.codes).fillna(0).eq(1) & bindings.wikidata_qid.map(qid_counts.source_rows).fillna(0).eq(1)
    bindings["native_competition_clear"] = ~(bindings.entity_competition_across_tsv_or_truthy.fillna(True) | bindings.source_observation_competition_for_exact_oktmo.fillna(True) | bindings.tsv_entity_competition_for_exact_oktmo.fillna(True) | bindings.truthy_entity_competition_for_exact_oktmo.fillna(True))
    def p31_evidence(raw):
        qids = sorted({str(x.get("value_qid")) for x in jslist(raw) if x.get("value_qid")})
        physical = [q for q in qids if p31_profiles.get(q, {}).get("physical_settlement_lineage")]
        admin = [q for q in qids if p31_profiles.get(q, {}).get("admin_only_lineage_without_physical_settlement")]
        return qids, physical, admin
    p31 = bindings.wikidata_truthy_p31_claims_json.map(p31_evidence)
    bindings["p31_qids_json"] = p31.map(lambda x: json.dumps(x[0]))
    bindings["physical_p31_lineage_qids_json"] = p31.map(lambda x: json.dumps(x[1]))
    bindings["admin_only_p31_lineage_qids_json"] = p31.map(lambda x: json.dumps(x[2]))
    bindings["physical_p31_lineage"] = p31.map(lambda x: bool(x[1]))
    region_keys = {regnorm(x) for x in selected21.region_raw.dropna()}
    def admin_conflict(raw, source_region):
        target_region = regnorm(source_region)
        return any(regnorm(x) in region_keys and regnorm(x) != target_region for x in jslist(raw))
    bindings["no_contradictory_admin_region"] = bindings.apply(lambda r: not admin_conflict(r.get("wikidata_tsv_ru_admin_labels_json"), r.get("region_raw")), axis=1)
    bindings["physical_current_scope"] = bindings.population_scope.fillna("").astype(str).str.lower().ne("federal_city_region") & bindings.settlement_type.notna()
    gate_cols = ["physical_current_scope", "selected_OKTMO_matches_exact_WIDE_code", "exact_source_oktmo_p764", "current_ru_label_exact", "current_source_name_exact",
                 "current_source_type_exact", "current_source_region_exact", "source_code_unique_qid",
                 "qid_unique_current_source_code", "native_competition_clear", "physical_p31_lineage", "no_contradictory_admin_region"]
    bindings["scoped_qid_binding_candidate"] = bindings[gate_cols].fillna(False).all(axis=1)
    def hold_reasons(row): return json.dumps([k for k in gate_cols if not bool(row.get(k))], ensure_ascii=False)
    bindings["binding_hold_reasons_json"] = bindings.apply(hold_reasons, axis=1)
    bindings["binding_status"] = bindings.scoped_qid_binding_candidate.map({True:"scoped_secondary_history_binding_candidate_pending_independent_review",False:"held_current_QID_binding_candidate"})
    bindings["historical_scope_status"] = "source-specific historical scope unknown; no same-scope inference from current place"
    bindings["historical_identity_status"] = "current QID binding candidate only; no historical same_place edge admitted"
    bindings["historical_coordinate_status"] = "no historical coordinates attached or inferred"
    # Coordinate admission is a separate context axis. Multiple Wikidata P625 claims
    # do not invalidate the name/identifier binding when a point was accepted elsewhere.
    uses = con.execute("""
        select target_source_record_id, count(*) as accepted_point_use_count,
               to_json(list_sort(list_distinct(list(coordinate_provider_family)))) as accepted_point_provider_families_json,
               to_json(list_sort(list_distinct(list(coordinate_source_record_id)))) as accepted_point_source_record_ids_json
        from read_parquet(?) where target_year=2021 group by target_source_record_id
    """, [str(DELIVERY / "accepted_point_uses.parquet")]).df()
    bindings = bindings.merge(uses, left_on="source_record_id", right_on="target_source_record_id", how="left", validate="one_to_one")
    bindings["accepted_point_use_count"] = bindings.accepted_point_use_count.fillna(0).astype(int)
    bindings["accepted_non_wikidata_point_exists"] = bindings.accepted_point_provider_families_json.fillna("").str.contains("Geonames|Dadata|GeoKLADR|Fias|Rosreestr", case=False, regex=True)
    bindings["multiple_truthy_p625_claims"] = bindings.truthy_p625_point_count.fillna(0).gt(1)
    bindings["coordinate_gate_used_for_QID_binding"] = False
    bindings["point_interpretation"] = "accepted coordinate graph remains separate; Wikidata point count does not gate this name/code/QID binding"
    # The exact candidate register records all 2021 input rows in scope, including holds.
    register_cols = ["source_record_id", "settlement_name", "settlement_type", "region_raw", "district_raw", "municipality_raw",
                     "population", "population_scope", "settlement_id", "source_file", "source_sha256", "source_locator",
                     "source_oktmo_raw", "source_oktmo_exact_digits", "wikidata_qid", "wikidata_tsv_exact_p764_value_raw",
                     "wikidata_truthy_exact_p764_match", "wikidata_truthy_exact_p764_claims_json", "wikidata_name_exact_label",
                     "wikidata_tsv_ru_labels_json", "wide_qid_values_json", "source_record_wide_row_count", "source_row_qid_unique", "wikidata_truthy_p31_claims_json", "p31_qids_json", "physical_p31_lineage_qids_json",
                     "admin_only_p31_lineage_qids_json", "wikidata_truthy_p131_claims_json", "wikidata_tsv_admin_qids_json",
                     "wikidata_tsv_ru_admin_labels_json", *gate_cols, "scoped_qid_binding_candidate", "binding_status",
                     "binding_hold_reasons_json", "candidate_status", "truthy_p625_point_count", "multiple_truthy_p625_claims",
                     "accepted_point_use_count", "accepted_point_provider_families_json", "accepted_non_wikidata_point_exists",
                     "coordinate_gate_used_for_QID_binding", "point_interpretation", "historical_scope_status", "historical_identity_status",
                     "historical_coordinate_status"]
    bindings[register_cols].to_csv(HB / "current_qid_binding_candidates.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)
    passing = bindings[bindings.scoped_qid_binding_candidate].copy()
    history_wide = allwd.merge(passing[["source_record_id", "settlement_name", "settlement_type", "region_raw", "population",
                                        "source_oktmo_exact_digits", "wikidata_qid", "accepted_point_use_count",
                                        "accepted_point_provider_families_json", "accepted_non_wikidata_point_exists",
                                        "truthy_p625_point_count", "multiple_truthy_p625_claims"]].rename(columns={"source_record_id":"current_source_record_id"}),
                               left_on="wikidata_id", right_on="wikidata_qid", how="inner", validate="many_to_many")
    history_wide["history_binding_status"] = "secondary working display via exact current QID candidate; pending independent rule review"
    history_wide["history_binding_population_admission"] = False
    history_wide["history_binding_historical_identity_admission"] = False
    history_wide["historical_population_scope_from_current_place"] = False
    history_wide["historical_coordinate_from_current_P625"] = False
    history_wide.to_parquet(HB / "working_history_current_place_bindings.parquet", index=False)
    # Coverage profile counts distinct current source IDs/population with at least one
    # dated statement per source year; it never sums the historical Wikidata values.
    hist_profile_rows = history_wide[history_wide.working_year_label.notna()]
    hp_statements = hist_profile_rows.groupby("working_year_label").agg(statement_rows=("wikidata_statement_id", "nunique"), date_holds=("date_variant_conflict", "sum"))
    hp_ids = hist_profile_rows.drop_duplicates(["working_year_label", "current_source_record_id"]).groupby("working_year_label").agg(
        current_place_ids=("current_source_record_id", "nunique"), current_2021_population=("population_y", "sum"))
    hp = hp_statements.join(hp_ids).reset_index()
    hp.to_csv(HB / "working_history_year_binding_profile.csv", index=False, encoding="utf-8")
    sample_ids = bindings[bindings.scoped_qid_binding_candidate].nlargest(25, "population").source_record_id.tolist()
    seed_sample = bindings[bindings.scoped_qid_binding_candidate & ~bindings.source_record_id.isin(sample_ids)].sample(n=min(15, int(bindings.scoped_qid_binding_candidate.sum())-len(sample_ids)), random_state=20261004).source_record_id.tolist()
    review_ids = list(dict.fromkeys(sample_ids + seed_sample))
    bindings[bindings.source_record_id.isin(review_ids)][register_cols].to_csv(HB / "independent_review_sample.csv", index=False, encoding="utf-8")
    review_request = {"request_id":"federal_and_history_scoped_wikidata_binding_review_20261004_v1",
                      "review_family":"current_place_exact_code_name_physical_P31_to_secondary_history_QID_binding",
                      "status":"prepared_for_independent_review_not_admitted",
                      "scope":{"current_year":2021,"candidate_population_scope":"physical/additive 2021 selected place rows; federal territory aggregates removed",
                               "history":"nondeprecated Wikidata P1082 rows with source year/date/provenance preserved; no population primary verification",
                               "binding_gates":gate_cols,
                               "coordinate_rule":"coordinate admission remains separate; P625 multiplicity does not block an otherwise passing QID name/code binding if an accepted coordinate exists from another provider; no historical coordinates attached",
                               "historical_scope":"always unknown absent statement-specific evidence; current place scope never copied into historical observation",
                               "identity":"current scoped QID candidate only; no historical same_place edge, no identity from legacy settlement_id alone"},
                      "population_and_history_are_not_admitted":True,
                      "inputs":{"selected_observations":str(OBS),"selected_sha256":sha(OBS),"wide_bindings":str(WIDE),"wide_sha256":sha(WIDE),
                                "secondary_history":str(OUT/"wikidata_secondary_full_history.parquet"),"secondary_history_sha256":sha(OUT/"wikidata_secondary_full_history.parquet"),
                                "accepted_point_uses":str(DELIVERY/"accepted_point_uses.parquet"),"accepted_point_uses_sha256":sha(DELIVERY/"accepted_point_uses.parquet"),
                                "physical_P31_hierarchy":str(hierarchy_path),"physical_P31_hierarchy_sha256":sha(hierarchy_path),"P31_class_nodes_reused":458},
                      "reviewer_actions":["recheck gate semantics and independent applicability across settlement types/regions",
                                          "inspect exact selected-source row, WIDE native OKTMO P764/label/P31 and competition evidence for supplied sample",
                                          "check administrative-context conflict handling and identify false passes/holds",
                                          "confirm that history display retains source date, rank, raw statement/reference and no inferred historical scope/coordinates"],
                      "sample_ids":review_ids,"output":"working_history_current_place_bindings.parquet",
                      "reviewer_must_not_treat_as":"primary population verification, census-date scope, accepted historical identity, or historical coordinate validation"}
    review_request["review_artifacts"] = {
        "candidate_register_sha256": sha(HB / "current_qid_binding_candidates.csv"),
        "history_binding_sha256": sha(HB / "working_history_current_place_bindings.parquet"),
        "sample_sha256": sha(HB / "independent_review_sample.csv"),
        "profile_sha256": sha(HB / "working_history_year_binding_profile.csv"),
    }
    (HB / "independent_review_family_request.json").write_text(json.dumps(review_request, ensure_ascii=False, indent=2) + "\n")
    bind_summary = {"status":"candidate_scoped_QID_history_bindings_pending_independent_review",
                    "current_2021_rows_in_scope":int(len(bindings)),"passing_binding_candidate_rows":int(bindings.scoped_qid_binding_candidate.sum()),
                    "passing_candidate_current_population":int(bindings.loc[bindings.scoped_qid_binding_candidate,"population"].sum()),
                    "passing_candidate_unique_QIDs":int(bindings.loc[bindings.scoped_qid_binding_candidate,"wikidata_qid"].nunique()),
                    "joined_secondary_history_statement_rows":int(len(history_wide)),
                    "history_year_prefixes":int(history_wide.working_year_label.nunique()),
                    "current_candidate_rows_with_accepted_point":int(bindings.loc[bindings.scoped_qid_binding_candidate,"accepted_point_use_count"].gt(0).sum()),
                    "current_candidate_rows_with_accepted_non_Wikidata_point":int(bindings.loc[bindings.scoped_qid_binding_candidate,"accepted_non_wikidata_point_exists"].sum()),
                    "multiple_truthy_P625_rows_passing_name_ID_binding":int(bindings.loc[bindings.scoped_qid_binding_candidate,"multiple_truthy_p625_claims"].sum()),
                    "coordinate_gate_used_for_binding":False,"full_entity_P1082_tier_overrides":int(history_wide.full_entity_tier_priority_applied.sum()),
                    "historical_identity_admitted":False,"population_admitted":False,"historical_coordinates_asserted":False,
                    "candidate_register":"current_qid_binding_candidates.csv","history_output":"working_history_current_place_bindings.parquet",
                    "year_profile":"working_history_year_binding_profile.csv","independent_review_request":"independent_review_family_request.json",
                    "candidate_population_and_gate_counts":bindings[gate_cols + ["scoped_qid_binding_candidate"]].astype(bool).sum().to_dict(),
                    "candidate_ids_with_multiple_P625_not_blocked":int(bindings.loc[bindings.scoped_qid_binding_candidate,"multiple_truthy_p625_claims"].sum())}
    (HB / "coverage.json").write_text(json.dumps(bind_summary, ensure_ascii=False, indent=2) + "\n")

    # Census chain coverage identifiers for proposed territory entity relation.
    chain = pd.DataFrame([
        {"chain_id": "federal_territory_moscow_2002_2010_2021", "city": "Москва", "years": "2002|2010|2021",
         "source_record_ids_json": json.dumps(["ROSSTAT2002:T1:T4:sheet01-04:excel_row02155", "2010:pub-11-1-4.pdf:pdf_page_11:41", "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:64748"]),
         "relation_type": "continuing_city_identity_with_observation_grain_change", "atomic_same_place_edge": False,
         "territory_point_reuse": "current Q649 P625 as territory reference; earlier use is explicit inference", "population_scope_comparability": "not asserted"},
        {"chain_id": "federal_territory_petersburg_2002_2010_2021", "city": "Санкт-Петербург", "years": "2002|2010|2021",
         "source_record_ids_json": json.dumps(["2002:1_TOM_01_04.xls:0:3218", "2010:pub-11-1-4.pdf:pdf_page_15:39", "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:126656"]),
         "relation_type": "continuing_federal_city_territory_identity", "atomic_same_place_edge": False,
         "territory_point_reuse": "current Q656 P625 as territory reference; earlier use is explicit inference", "population_scope_comparability": "not asserted"},
        {"chain_id": "federal_territory_sevastopol_2021_only", "city": "Севастополь", "years": "2021",
         "source_record_ids_json": json.dumps(["2021:data_allsettlements_anon_156_v20251217.parquet:parquet:121540"]),
         "relation_type": "federal_city_territory_observation", "atomic_same_place_edge": False,
         "territory_point_reuse": "current Q7525 P625 as territory reference", "population_scope_comparability": "outside Russian 2002/2010 census geography; not zero"},
    ])
    write_csv(chain, OUT / "federal_territorial_chain_coverage_ids.csv")

    # Verify source input invariants and publish receipt/provenance.
    rank_counts = d.rank_is_deprecated.value_counts(dropna=False).to_dict()
    ambiguous = int(d.date_ambiguous_hold.sum())
    assert len(federal) == 6 and federal.source_record_id.nunique() == 6
    assert len(series) == 64466 and series.statement_id.nunique() == 64466
    assert int(series.date_ambiguous_hold.sum()) == 4
    assert int(len(allwd)) < 488628 and not allwd.duplicated(["wikidata_id", "wikidata_statement_id"]).any()
    inputs = [OBS, EDGES, WIDE, AGGREGATES, BASELINE, HISTORY_TSV, HISTORY_FULL, LEGACY_DB,
              *[v["path"] for v in POP_SOURCES.values()],
              DELIVERY / "accepted_point_uses.parquet",
              Path("/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json"),
              RAW / "wikimedia/wikidata_oktmo_population.tsv"] + [RAW / "wikidata_truthy_claims" / c["wd_file"] for c in CITIES.values()]
    receipt = {
        "build_id": "federal_and_history_20261004_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "/workspace/russian-settlements-research/research_rebuild/mass_linkage/build_federal_secondary_series_20261004.py",
        "status": "staged_federal_territory_references_and_secondary_working_history_no_frozen_delivery_mutation",
        "federal_bindings": {"rows": len(federal), "unique_source_records": int(federal.source_record_id.nunique()),
                             "population_total": int(federal.source_population.sum()), "point_role": "territory_reference",
                             "current_city_qids": {k:v["qid"] for k,v in CITIES.items()},
                             "unique_coordinate_count": len(set((v["lat"],v["lon"]) for v in CITIES.values())),
                             "q625_claim_source_coordinates": {k:{"latitude":v["lat"],"longitude":v["lon"],"raw":v["raw_point"],"file":v["wd_file"],"line":v["wd_line"]} for k,v in CITIES.items()},
                             "caveat": "staged source/QID/P625 binding for a territorial metric; does not assert inhabited-place coordinate or accepted graph edge"},
        "joint_potential": {"results_file": "federal_joint_potential_gains.csv", "method": "baseline canonical spatial point numerator plus selected federal parent totals under exclusive parent-over-children rule; full-chain scenario adds only Moscow and Petersburg territory populations to current joint coordinate/full-chain population",
                            "selected_2021_crimea_population": crimea,
                            "selected_2021_crimea_plus_sevastopol_outside_old_census_population": outside_scope,
                            "strict_chain_maximum_2021_population_after_geographic_exclusions": strict_maximum,
                            "strict_chain_geographic_exclusion_share_pct": round(100*outside_scope/int(y21["control"]), 6),
                            "strict_chain_maximum_coverage_pct_before_other_holds": round(100*strict_maximum/int(y21["control"]), 6),
                            "strict_chain_below_99pct_people_due_to_geographic_exclusions_alone": max(0, int(y21["targets"]["99_percent"]["minimum_population"]) - strict_maximum),
                            "sevastopol_2002_2010": "outside Russian census territorial coverage; not zero",
                            "2021_full_chain_99_percent_reached_with_federal_rows_alone": bool(strict >= int(y21["targets"]["99_percent"]["minimum_population"]))},
        "working_history": {"rows": int(len(series)), "unique_qid_statement_ids": int(series.statement_id.nunique()),
                            "deprecated_excluded": 17, "date_ambiguity_holds": ambiguous,
                            "full_entity_priority_rows": int((series.source_tier == "full_entity_statement").sum()),
                            "flat_tsv_only_rows": int((series.source_tier == "flat_TSV_statement").sum()),
                            "population_quality": "wikidata_secondary_primary_not_independently_verified",
                            "year_rule": "literal P585 year prefix retained as an observed-date label; not assigned to any census date",
                            "historical_coordinates_or_same_place_asserted": False},
        "federal_city_secondary_history": {"rows": int(len(city_history)), "unique_statement_ids": int(city_history.statement_id.nunique()),
                                            "qid_counts": city_history.groupby("qid").size().to_dict(),
                                            "observed_year_prefixes": sorted(city_history.year_prefix.dropna().unique().tolist()),
                                            "real_1989_or_2001_values_available": bool(city_history.year_prefix.isin(["1989", "2001"]).any()),
                                            "status": "extra raw TSV statements for Q649/Q656/Q7525; deduplicated by statement ID; flat TSV provides no full reference payload or precision"},
        "legacy_database_wikidata_history": {"raw_rows_pre_filter": 488628, "rows_output_nondeprecated_not_future": int(len(allwd)),
                                              "distinct_wikidata_statement_ids": int(allwd.wikidata_statement_id.nunique()),
                                              "source_qid_count": int(allwd.wikidata_id.nunique()),
                                              "legacy_duplicate_rows_removed": int(allwd.legacy_duplicate_rows_removed.sum()),
                                              "population_variant_conflict_statements": int(allwd.population_variant_conflict.sum()),
                                              "date_variant_conflict_statements": int(allwd.date_variant_conflict.sum()),
                                              "future_rows_year_gt_2026_excluded": 2,
                                              "deprecated_rows_excluded": 17,
                                              "full_entity_tier_overrides": int(allwd.full_entity_tier_priority_applied.sum()),
                                              "f2021_candidate_rows": int((allwd.f2021_binding_status != "no exact-code candidate").sum()),
                                              "f2021_qids_with_candidates": int(allwd.loc[allwd.f2021_binding_status != "no exact-code candidate", "wikidata_id"].nunique()),
                                              "trusted_identity_claims_from_legacy_settlement_id": 0,
                                              "future_year_rule": "exclude observation_year > 2026 or observation_date after 2026-10-03 UTC; retain raw observation date and hold ambiguous variant groups"},
        "territorial_chain_ids": "federal_territorial_chain_coverage_ids.csv",
        "crimea_alternative_series": {"coverage_file": "crimea_conditional_series_coverage.json",
                                      "selected_2021_crimea_ids": int(crimea2021.current_2021_source_record_id.nunique()),
                                      "eligible_outsidecoverage_ids_with_secondary_year_witness": int(eligible.current_2021_source_record_id.nunique()),
                                      "eligible_current_population": int(eligible.current_2021_population.sum()),
                                      "1989_witness_rows": int((dated_89_01.working_year_label.astype(str) == "1989").sum()),
                                      "2001_witness_rows": int((dated_89_01.working_year_label.astype(str) == "2001").sum()),
                                      "date_or_population_conflict_hold_statements": int(eligible.secondary_date_conflict_hold_count.sum()),
                                      "strict_Russian_2002_2010_2021_Crimea_eligible_ids": 0,
                                      "strict_chain_identity_admission": False},
        "scoped_history_bindings": bind_summary,
        "outputs": {},
        "inputs": {str(p): sha(p) for p in inputs},
    }
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name != "receipt.json":
            receipt["outputs"][str(p.relative_to(OUT))] = {"sha256": sha(p), "bytes": p.stat().st_size}
    (OUT / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")

if __name__ == "__main__":
    main()
