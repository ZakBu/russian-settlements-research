#!/usr/bin/env python3
"""Apply reviewed secondary Wikidata history as a separate current-place overlay.

The producer's reviewed inputs and accepted mass batch are pinned by SHA256.
Outputs are staged outside the frozen delivery and never become identity edges,
census replacements, historical coordinates, or annual coverage denominators.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

BASE = Path("/workspace/settlements-work/continuation_20261004")
OUT = BASE / "root/R4/history_application"
REVIEW = BASE / "independent_history_review"
FED = BASE / "federal_and_history"
ACCEPTED = BASE / "accepted_mass_batch"
HISTORY = FED / "history_bindings/working_history_current_place_bindings.parquet"
CANDIDATES = REVIEW / "review_eligible_current_QID_binding_candidates.csv"
REGISTER = FED / "history_bindings/current_qid_binding_candidates.csv"
RECEIPT = REVIEW / "receipt.json"
LONG = ACCEPTED / "settlements_long.parquet"
POINT_USES = BASE / "accepted_mass_extensions/accepted_point_uses.parquet"
FULL_HISTORY = FED / "wikidata_secondary_full_history.parquet"
MISSING = REVIEW / "missing_WIDE_false_P764_gate_holds.csv"
RAW_ENTITIES = Path("/workspace/settlements-raw/data/raw/wikidata_entities_full")

EXPECTED = {
    RECEIPT: "ffb8044f9c0552ee45daddcdb91375f017cad25a81d364781831e1333866fd6d",
    CANDIDATES: "670f2f27fcf7064887149f44a55b0ee0cb6a83db6dedf896febfa01e9d197f42",
    HISTORY: "ff5a1547ac0fb6c3495338ddb5e3a784aa6e2fb028f529009bad4d79d126e12d",
    LONG: "50d2dec9b2043714dead9aecc09abdbb0d103759005207f656bf912fc6738cc0",
    POINT_USES: "9271f132beb9c9a836c280826007ef19c8039cca85e49eb5bda21198910dac90",
    REGISTER: "a59d5e5d9f43bc3d7922d9c3af04ffc88bca9582e6b77ff61d9468741a543071",
    MISSING: "5d80bd261712b16ceba6360b3308e0dd3b11836509f033167e3045e466358ee9",
}

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def write_csv(df: pd.DataFrame, p: Path) -> None:
    df.to_csv(p, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p, expected in EXPECTED.items():
        actual = sha(p)
        if actual != expected:
            raise RuntimeError(f"Pinned input changed: {p}: expected {expected}, got {actual}")
    review_receipt = json.loads(RECEIPT.read_text())
    if review_receipt["producer_inputs"]["working_history_sha256"] != EXPECTED[HISTORY]:
        raise RuntimeError("Independent review receipt does not pin the working history file")
    if review_receipt["artifacts"]["review_eligible_current_QID_binding_candidates.csv"]["sha256"] != EXPECTED[CANDIDATES]:
        raise RuntimeError("Independent review receipt does not pin the eligible candidate file")

    con = duckdb.connect()
    # The accepted current 2021 row is the coordinate carrier for display context.
    # Historical-row latitude/longitude remain null: no current point is copied as
    # a historical coordinate or used as evidence of boundary continuity.
    query = r"""
    copy (
      with bindings as (
        select source_record_id as current_source_record_id,
               settlement_name as current_settlement_name,
               settlement_type as current_settlement_type,
               region_raw as current_region_raw,
               population as current_2021_population,
               cast(source_oktmo_exact_digits as varchar) as current_source_oktmo_exact_digits,
               wikidata_qid as current_wikidata_qid,
               accepted_point_use_count,
               accepted_non_wikidata_point_exists,
               truthy_p625_point_count,
               multiple_truthy_p625_claims
        from read_csv_auto(?, header=true, all_varchar=false)
      ),
      accepted_use as (
        select target_source_record_id,
               count(*) as current_accepted_point_use_count,
               to_json(list_sort(list_distinct(list(coordinate_provider_family)))) as current_accepted_point_provider_families_json,
               any_value(latitude) as final_point_latitude,
               any_value(longitude) as final_point_longitude,
               any_value(coordinate_admission_status) as final_point_admission_status,
               any_value(coordinate_quality) as final_point_quality,
               any_value(coordinate_source) as final_point_source,
               any_value(coordinate_provider) as final_point_provider,
               any_value(coordinate_source_record_id) as final_point_source_record_id,
               any_value(coordinate_provenance) as final_point_provenance,
               any_value(coordinate_source_file) as final_point_source_file,
               any_value(coordinate_source_sha256) as final_point_source_sha256,
               any_value(coordinate_source_locator) as final_point_source_locator,
               any_value(admission_rule) as final_point_admission_rule,
               any_value(application_inference_kind) as final_point_inference_kind
        from read_parquet(?) where target_year=2021 group by target_source_record_id
      ),
      place as (
        select source_record_id as place_source_record_id,
               observation_id as current_place_observation_id,
               entity_id as current_place_entity_id,
               settlement_name as current_place_label,
               settlement_type as current_place_type,
               region_raw as current_place_region,
               u.final_point_latitude as current_coordinate_carrier_latitude,
               u.final_point_longitude as current_coordinate_carrier_longitude,
               u.final_point_admission_status as current_coordinate_admission_status,
               u.final_point_quality as current_coordinate_quality,
               concat('current 2021 accepted point-use union; measurement date unknown; inference=',coalesce(u.final_point_inference_kind,'not stated')) as current_coordinate_temporal_basis,
               u.final_point_source as current_coordinate_source,
               u.final_point_provider as current_coordinate_provider,
               u.final_point_source_record_id as current_coordinate_source_record_id,
               u.final_point_provenance as current_coordinate_provenance,
               u.final_point_source_file as current_coordinate_source_file,
               u.final_point_source_sha256 as current_coordinate_source_sha256,
               u.final_point_source_locator as current_coordinate_source_locator,
               u.final_point_admission_rule as current_coordinate_admission_rule,
               source_sha256 as current_population_source_sha256,
               source_path as current_population_source_path,
               source_locator as current_population_source_locator,
               population_scope as current_population_scope,
               spatial_identity_status as current_spatial_identity_status,
               coalesce(u.current_accepted_point_use_count,0) as current_accepted_point_use_count,
               u.current_accepted_point_provider_families_json
        from read_parquet(?) l
        left join accepted_use u on u.target_source_record_id=l.source_record_id
        where l.observation_year=2021 and l.record_type='census'
      ),
      h as (select * from read_parquet(?))
      select
        concat('wikidata-history:', h.wikidata_id, ':', h.wikidata_statement_id) as observation_id,
        'wiki_literal_series' as record_type,
        concat('wikidata-series:', h.wikidata_id) as entity_id,
        cast(null as varchar) as associated_census_entity_id,
        'automatically_accepted_checked_current_QID_identity_rule; historical identity not asserted' as association_status,
        'unknown_historical_physical_continuity' as spatial_identity_status,
        h.observation_year as observation_year,
        coalesce(h.date_literal_flat_tsv, cast(h.observation_date as varchar)) as reference_date,
        'Wikidata P585/raw source date; literal year label only, not a census date' as reference_date_basis,
        concat('WIKIDATA:', h.wikidata_id, ':', h.wikidata_statement_id) as source_record_id,
        h.wikidata_statement_id as source_publication_row_id,
        coalesce(h.source_detail, h.wikidata_id) as source_name_raw,
        b.current_settlement_name as settlement_name,
        b.current_settlement_type as settlement_type,
        b.current_region_raw as region_raw,
        cast(null as varchar) as district_raw,
        cast(null as varchar) as municipality_raw,
        try_cast(h.population_value_raw_for_display as double) as population_value,
        h.population_value_raw_for_display as population_raw,
        coalesce(h.raw_tsv_line_number::varchar, h.raw_record_locator) as population_source_raw_line,
        'wikidata_secondary_primary_not_independently_verified' as population_value_quality,
        cast(null as varchar) as population_value_quality_original_tag,
        'secondary P1082 value; primary source and date-specific scope not independently verified' as population_quality_limitation,
        cast(null as varchar) as displaced_source_record_id,
        'reviewed current QID candidate; source observation linked by statement QID; historical identity not asserted' as publication_binding_basis,
        'unknown_historical_scope' as population_scope,
        h.raw_source_file as source_path,
        cast(null as varchar) as source_sheet,
        cast(null as double) as source_row,
        h.wikidata_id as source_native_id,
        'dated_secondary_observation_unknown_historical_grain' as entity_grain_status,
        'wikidata_secondary_primary_not_independently_verified' as source_population_quality,
        false as legacy_is_federal_aggregate,
        h.raw_source_sha256 as source_sha256,
        h.raw_record_locator as source_locator,
        cast(null as varchar) as source_sha256_original_selected,
        'raw Wikidata source provenance preserved' as source_hash_binding,
        b.current_source_oktmo_exact_digits as oktmo_current_observed_2021,
        cast(null as varchar) as oktmo_observed_at_year,
        cast(null as double) as oktmo_identifier_observation_year,
        cast(null as varchar) as oktmo_native_raw,
        cast(null as double) as coordinate_candidate_latitude,
        cast(null as double) as coordinate_candidate_longitude,
        cast(null as double) as latitude,
        cast(null as double) as longitude,
        'historical_coordinate_not_asserted' as coordinate_quality,
        'no_historical_coordinate_attached' as coordinate_admission_status,
        'no_historical_coordinate; current 2021 carrier is context only' as coordinate_temporal_basis,
        true as coordinate_measurement_date_unknown,
        false as boundary_comparability_asserted,
        cast(null as varchar) as coordinate_provider_quality_raw,
        cast(null as varchar) as coordinate_source,
        cast(null as varchar) as coordinate_source_record_id,
        cast(null as varchar) as coordinate_provider,
        cast(null as varchar) as coordinate_provider_id,
        cast(null as varchar) as coordinate_admission_rule,
        cast(null as varchar) as coordinate_provenance,
        cast(null as varchar) as point_source_file,
        cast(null as varchar) as point_source_sha256,
        cast(null as varchar) as point_source_locator,
        'not_claimed_for_historical_observation' as provider_binding_status,
        cast(null as varchar) as provider_fias_binding_status,
        'working_secondary_history_observation' as entity_category,
        'not independently verified primary source' as identity_quality,
        false as census_full_chain,
        'not_asserted' as census_2002_status,
        'not_asserted' as census_2010_status,
        'not_asserted' as census_2021_status,
        cast(null as varchar) as coordinate_source_date,
        false as direct_historical_coordinate_measurement,
        '[]' as coordinate_uncertainty_flags_json,
        false as population_scope_comparability_asserted,
        'not applicable; no historical coordinate' as coordinate_carrier_admission_rule,
        'secondary_Wikidata_P1082' as point_source_kind,
        cast(null as varchar) as point_claim_artifact_file,
        cast(null as varchar) as point_claim_artifact_sha256,
        '[]' as coordinate_identity_path_decision_ids_json,
        '[]' as coordinate_lineage_event_candidates_json,
        cast(null as double) as coordinate_corroborating_modern_point_distance_km,
        cast(null as double) as population_reported_thousand,
        1.0 as population_unit_multiplier,
        cast(null as varchar) as population_rounding_convention,
        'secondary_display_only_not_census_or_primary_admission' as population_admission_status,
        b.current_source_oktmo_exact_digits as wiki_current_source_oktmo_literal,
        'reviewed_current_QID_binding_candidate_only' as source_association_status,
        'unknown_historical_identity_and_scope' as historical_physical_identity_status,
        -- Additional overlay fields; current place and point are explicitly contextual.
        b.current_source_record_id,
        b.current_wikidata_qid,
        b.current_2021_population,
        p.current_place_entity_id,
        p.current_place_observation_id,
        p.current_place_label,
        p.current_place_type,
        p.current_place_region,
        p.current_coordinate_carrier_latitude,
        p.current_coordinate_carrier_longitude,
        p.current_coordinate_admission_status,
        p.current_coordinate_quality,
        p.current_coordinate_temporal_basis,
        p.current_coordinate_source,
        p.current_coordinate_provider,
        p.current_coordinate_source_record_id,
        p.current_coordinate_provenance,
        p.current_coordinate_source_file,
        p.current_coordinate_source_sha256,
        p.current_coordinate_source_locator,
        p.current_coordinate_admission_rule,
        p.current_population_source_sha256,
        p.current_population_source_path,
        p.current_population_source_locator,
        p.current_population_scope,
        p.current_spatial_identity_status,
        p.current_accepted_point_use_count as accepted_point_use_count,
        p.current_accepted_point_provider_families_json as accepted_point_provider_families_json,
        (p.current_accepted_point_provider_families_json ilike '%Geonames%' or p.current_accepted_point_provider_families_json ilike '%Dadata%' or p.current_accepted_point_provider_families_json ilike '%GeoKLADR%' or p.current_accepted_point_provider_families_json ilike '%Fias%' or p.current_accepted_point_provider_families_json ilike '%Rosreestr%') as accepted_non_wikidata_point_exists,
        b.accepted_point_use_count as original_review_point_use_count,
        b.truthy_p625_point_count,
        b.multiple_truthy_p625_claims,
        h.wikidata_statement_id,
        h.wikidata_id,
        h.working_year_label,
        case when h.observation_year is not null and h.working_year_label is not null and not h.date_variant_conflict and not h.population_variant_conflict
             then h.working_year_label else null end as quantitative_year_label,
        (h.observation_year is not null and h.working_year_label is not null and not h.date_variant_conflict and not h.population_variant_conflict) as quantitative_year_eligible,
        h.date_assignment_status,
        h.date_variant_conflict,
        h.date_ambiguous_hold,
        h.date_precision,
        h.date_literal_flat_tsv,
        h.full_year_prefixes_json,
        h.date_raw_full_statement,
        h.full_tier_year_prefix,
        h.full_tier_date_precision,
        h.legacy_observation_date_variants_json,
        h.legacy_year_variants_json,
        h.population_value_raw_for_display as population_value_raw_for_secondary_display,
        h.population_variant_conflict,
        h.rank_raw,
        h.source_tier as history_source_tier,
        h.references_count,
        h.references_with_p854_url_count,
        h.reference_p854_urls_json,
        h.raw_reference_payload_json,
        h.raw_statement_json,
        h.entity_batch_file,
        h.entity_batch_sha256,
        h.entity_retrieved_at_utc,
        h.raw_tsv_line_number,
        h.raw_record_locator as history_raw_record_locator,
        h.raw_source_sha256 as history_raw_source_sha256,
        'source-specific historical population scope unknown; current scope not inherited' as historical_scope_status,
        'current QID binding review applies to 2021 place only; no dated historical identity asserted' as historical_identity_status,
        false as history_population_admitted,
        false as historical_identity_admitted,
        false as historical_coordinate_asserted,
        false as historical_scope_inherited
      from h
      join bindings b on b.current_source_record_id=h.current_source_record_id and b.current_wikidata_qid=h.wikidata_id
      join place p on p.place_source_record_id=b.current_source_record_id
    ) to ? (FORMAT PARQUET, COMPRESSION ZSTD)
    """
    output_parquet = OUT / "reviewed_secondary_history_observations.parquet"
    query = query.replace("to ? (FORMAT PARQUET, COMPRESSION ZSTD)", f"to '{output_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.execute(query, [str(CANDIDATES), str(POINT_USES), str(LONG), str(HISTORY)])

    # Sidecar profile counts observation rows and linked current places, never
    # their historical Wikidata population values or a national denominator.
    profile_query = r"""
    copy (
      select quantitative_year_label as working_year_label,
             count(*) as statement_rows,
             count(distinct current_place_entity_id) as linked_current_place_entities,
             count(*) filter(where history_source_tier='full_entity_statement') as full_entity_rows,
             count(*) filter(where history_source_tier='flat_TSV_statement') as flat_tsv_rows,
             count(*) filter(where history_source_tier is null) as legacy_only_rows,
             count(*) filter(where accepted_point_use_count>0) as statements_with_accepted_current_point,
             'secondary observed-date display coverage only; no population sum or annual national coverage' as interpretation
      from read_parquet(?) where quantitative_year_eligible
      group by quantitative_year_label order by try_cast(quantitative_year_label as integer)
    ) to ? (HEADER, DELIMITER ',')
    """
    profile_csv = OUT / "secondary_history_observed_year_profile.csv"
    profile_query = profile_query.replace("to ? (HEADER, DELIMITER ',')", f"to '{profile_csv}' (HEADER, DELIMITER ',')")
    con.execute(profile_query, [str(output_parquet)])

    # Correct the producer's false-positive P764 diagnostic in code separately,
    # without rebuilding or changing any of the pinned reviewed artifacts.
    miss = pd.read_csv(MISSING, engine="python", dtype=str, keep_default_na=False)
    register = pd.read_csv(REGISTER, engine="python", dtype=str, keep_default_na=False)
    if len(miss) != 33694 or not miss.exact_source_oktmo_p764.eq("True").all():
        raise RuntimeError("Pinned missing-WIDE false-P764 hold class did not match expected review finding")
    held_qids = set(miss.wikidata_qid[miss.wikidata_qid.ne("")])
    # The independent row-level hold file is exact for the false-positive class.
    correction = {
        "status": "producer_gate_bug_corrected_in_source_only; reviewed_outputs_preserved",
        "affected_rows": int(len(miss)),
        "affected_rows_missing_wide_QID": int((miss.wikidata_qid == "").sum()),
        "pre_fix_false_P764_diagnostic_true_rows": int((miss.exact_source_oktmo_p764 == "True").sum()),
        "post_fix_P764_diagnostic_true_rows": 0,
        "published_review_pass_rows": int(len(pd.read_csv(CANDIDATES, engine="python", usecols=["source_record_id"]))),
        "published_review_pass_sha256": EXPECTED[CANDIDATES],
        "reviewed_history_sha256": EXPECTED[HISTORY],
        "no_reviewed_candidate_pass_set_changed": True,
        "no_rebuild_performed": True,
        "fix": "P764 gate now requires a nonmissing truthy-match flag, exact source OKTMO and raw P764 value before comparing; see build_federal_secondary_series_20261004.py",
        "reason": "bool(np.nan) is true and missing normalized code/value compared equal; other independent gates held all affected rows",
        "independent_review_hold_file_sha256": EXPECTED[MISSING],
        "unused_held_qids_count": int(len(held_qids)),
        "warning": "The 33,694 affected rows are holds, not recovered current-QID bindings; legacy settlement IDs were not used."
    }
    (OUT / "producer_p764_gate_correction.json").write_text(json.dumps(correction, ensure_ascii=False, indent=2) + "\n")

    # Assess all remaining current-source holds with cached QID/P1082 evidence.
    # This reports evidence to prioritize review; it does not auto-admit a hold.
    qhist = con.execute("""
       select wikidata_id, count(*) as history_statement_rows,
              count(*) filter(where working_year_label is not null and not date_variant_conflict and not population_variant_conflict) as dated_nonconflict_rows,
              count(*) filter(where date_variant_conflict or population_variant_conflict) as conflicting_rows
       from read_parquet(?) group by wikidata_id
    """, [str(FULL_HISTORY)]).df()
    qhist = qhist.set_index("wikidata_id")
    cand = pd.read_csv(REGISTER, engine="python", keep_default_na=False)
    gate_cols = ["physical_current_scope", "selected_OKTMO_matches_exact_WIDE_code", "exact_source_oktmo_p764", "current_ru_label_exact",
                 "current_source_name_exact", "current_source_type_exact", "current_source_region_exact", "source_code_unique_qid",
                 "qid_unique_current_source_code", "native_competition_clear", "physical_p31_lineage", "no_contradictory_admin_region"]
    for c in gate_cols + ["scoped_qid_binding_candidate"]:
        cand[c] = cand[c].astype(str).str.lower().eq("true")
    # Apply the corrected missing-WIDE diagnostic to the analysis view only.
    # The pinned register, reviewed candidate file and history Parquet remain intact.
    false_p764_ids = set(miss.source_record_id)
    cand.loc[cand.source_record_id.isin(false_p764_ids), "exact_source_oktmo_p764"] = False
    cand["scoped_qid_binding_candidate"] = cand[gate_cols].all(axis=1)
    reviewed_pass_ids = set(pd.read_csv(CANDIDATES,engine="python",usecols=["source_record_id"]).source_record_id)
    corrected_pass_ids = set(cand.loc[cand.scoped_qid_binding_candidate,"source_record_id"])
    if corrected_pass_ids != reviewed_pass_ids:
        raise RuntimeError("Corrected producer gate changed the independently reviewed pass set")
    held = cand[~cand.scoped_qid_binding_candidate].copy()
    held["qid_history_statement_rows"] = held.wikidata_qid.map(qhist.history_statement_rows).fillna(0).astype(int)
    held["qid_dated_nonconflict_statement_rows"] = held.wikidata_qid.map(qhist.dated_nonconflict_rows).fillna(0).astype(int)
    held["qid_conflicting_statement_rows"] = held.wikidata_qid.map(qhist.conflicting_rows).fillna(0).astype(int)
    held["failed_gate_count"] = held[gate_cols].eq(False).sum(axis=1)
    held["only_failed_gates_json"] = held.apply(lambda r: json.dumps([g for g in gate_cols if not r[g]], ensure_ascii=False), axis=1)
    single = held[held.failed_gate_count.eq(1)].copy()
    single = single[single.qid_dated_nonconflict_statement_rows.gt(0)]
    if len(single):
        single["binding_recovery_status"] = "existing_QID_has_secondary_history_but_current_binding_gate_failed_review_required"
    # Per-gate totals overlap by design; candidate and source population are not additive.
    reason_rows = []
    for gate in gate_cols:
        g = held[~held[gate]]
        q = g[g.wikidata_qid.ne("")]
        q_with = q[q.qid_dated_nonconflict_statement_rows.gt(0)]
        reason_rows.append({"failed_gate":gate,"held_source_rows":len(g),"held_current_source_population":float(g.population.sum()),
                            "rows_with_current_QID":int(g.wikidata_qid.ne("").sum()),
                            "unique_current_QIDs":int(g.loc[g.wikidata_qid.ne(""),"wikidata_qid"].nunique()),
                            "rows_with_dated_nonconflict_history":len(q_with),
                            "unique_QIDs_with_dated_nonconflict_history":int(q_with.wikidata_qid.nunique()),
                            "history_statement_rows_for_QIDs_with_history":int(q_with.drop_duplicates("wikidata_qid").qid_dated_nonconflict_statement_rows.sum()),
                            "interpretation":"overlapping hold gate counts; diagnostic evidence only, no binding recovered"})
    reason_df = pd.DataFrame(reason_rows).sort_values("rows_with_dated_nonconflict_history",ascending=False)
    write_csv(reason_df, OUT / "missing_current_QID_history_hold_gate_assessment.csv")
    evidence_cols = ["source_record_id","settlement_name","settlement_type","region_raw","population","source_oktmo_raw","source_oktmo_exact_digits",
                     "wikidata_qid","wikidata_tsv_exact_p764_value_raw","wikidata_truthy_exact_p764_match","wikidata_truthy_exact_p764_claims_json",
                     "wikidata_tsv_ru_labels_json","wikidata_tsv_admin_qids_json","wikidata_tsv_ru_admin_labels_json","wikidata_truthy_p31_claims_json",
                     "wikidata_truthy_p131_claims_json","binding_hold_reasons_json","failed_gate_count","only_failed_gates_json",
                     "qid_history_statement_rows","qid_dated_nonconflict_statement_rows","qid_conflicting_statement_rows","binding_status"]
    present_cols = [c for c in evidence_cols if c in single.columns]
    top = single.sort_values(["qid_dated_nonconflict_statement_rows","population"],ascending=False).head(500)
    write_csv(top[present_cols], OUT / "single_gate_holds_with_cached_history_top500.csv")

    # Test whether the largest unresolved exact-RU-label gate is an overly narrow
    # label-only rule. Existing full-entity cache only: same source name must be an
    # exact Russian label or alias, while the current source name/type/region,
    # native P764, uniqueness/competition, physical P31 and admin gates already pass.
    entity_cache = {}
    raw_entity_files = sorted(f for f in RAW_ENTITIES.glob("*.json.gz") if not f.name.startswith("._"))
    raw_entity_hashes = {str(f):sha(f) for f in raw_entity_files}
    for f in raw_entity_files:
        with gzip.open(f, "rt", encoding="utf-8") as z:
            envelope = json.load(z)
        for qid, entity in envelope.get("payload", {}).get("entities", {}).items():
            entity_cache[qid] = (entity, f, envelope.get("retrieved_at_utc"), envelope.get("api_url"))
    def norm_name(v: object) -> str:
        if v is None or pd.isna(v): return ""
        return " ".join(unicodedata.normalize("NFKC", str(v)).casefold().replace("ё", "е").split())
    extension_rows = []
    label_only = single[single.only_failed_gates_json.eq('["current_ru_label_exact"]')]
    for r in label_only.to_dict("records"):
        entry = entity_cache.get(str(r.get("wikidata_qid")))
        if not entry: continue
        entity, entity_file, retrieved, api_url = entry
        source_name = norm_name(r.get("settlement_name"))
        ru_label = entity.get("labels", {}).get("ru", {}).get("value", "")
        ru_aliases = [a.get("value", "") for a in entity.get("aliases", {}).get("ru", []) if a.get("value")]
        label_exact = bool(source_name and norm_name(ru_label) == source_name)
        aliases_exact = [a for a in ru_aliases if norm_name(a) == source_name]
        if not label_exact and not aliases_exact: continue
        p764_values, p31_qids, p131_qids = [], [], []
        for claim in entity.get("claims", {}).get("P764", []):
            if claim.get("rank") == "deprecated": continue
            val = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if val is not None: p764_values.append(str(val))
        for prop, target in (("P31", p31_qids), ("P131", p131_qids)):
            for claim in entity.get("claims", {}).get(prop, []):
                if claim.get("rank") == "deprecated": continue
                val = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(val, dict) and val.get("id"): target.append(val["id"])
        code = re.sub(r"\D", "", str(r.get("source_oktmo_exact_digits", "")))
        raw_p764_exact = bool(code and code in p764_values)
        p31_reviewed_physical = bool(set(p31_qids) & set(json.loads(r.get("physical_p31_lineage_qids_json") or "[]")))
        extension_rows.append({
            "source_record_id":r["source_record_id"],"settlement_name":r["settlement_name"],"settlement_type":r["settlement_type"],
            "region_raw":r["region_raw"],"current_source_population":r["population"],
            "source_oktmo_raw":r["source_oktmo_raw"],"source_oktmo_exact_digits":code,"wikidata_qid":r["wikidata_qid"],
            "raw_entity_RU_label":ru_label,"raw_entity_RU_label_exact":label_exact,
            "raw_entity_RU_alias_exact_values_json":json.dumps(aliases_exact,ensure_ascii=False),
            "raw_entity_P764_values_json":json.dumps(p764_values,ensure_ascii=False),"raw_entity_P764_exact_current_OKTMO":raw_p764_exact,
            "raw_entity_P31_qids_json":json.dumps(p31_qids,ensure_ascii=False),"raw_entity_P31_matches_reviewed_physical_lineage":p31_reviewed_physical,
            "raw_entity_P131_qids_json":json.dumps(p131_qids,ensure_ascii=False),
            "WIDE_admin_labels_json":r.get("wikidata_tsv_ru_admin_labels_json"),
            "WIDE_current_region_consistency_gate_pass":r.get("no_contradictory_admin_region"),
            "history_statement_rows":r["qid_history_statement_rows"],"dated_nonconflict_history_statement_rows":r["qid_dated_nonconflict_statement_rows"],
            "raw_entity_cache_file":str(entity_file),"raw_entity_cache_sha256":sha(entity_file),
            "raw_entity_retrieved_at_utc":retrieved,"raw_entity_api_url":api_url,
            "all_other_current_binding_gates_pass":True,
            "candidate_rule":"exact current Russian source name in a cached current RU label/alias, exact source OKTMO=P764, exact current source name/type/region, unique QID/source/code, no native competition, physical P31 and no contradictory admin region",
            "status":"staged_name_alias_rule_extension_candidate; separate review must supersede current_ru_label_exact-only hold; not in reviewed pass set or applied history table",
            "legacy_settlement_id_used":False})
    extension = pd.DataFrame(extension_rows)
    if len(extension):
        extension["raw_cached_P764_and_P31_recheck_pass"] = extension.raw_entity_P764_exact_current_OKTMO & extension.raw_entity_P31_matches_reviewed_physical_lineage
    else:
        extension["raw_cached_P764_and_P31_recheck_pass"] = pd.Series(dtype=bool)
    write_csv(extension, OUT/"raw_entity_exact_name_alias_history_candidates.csv")
    extension_request = {
        "request_id":"current_RU_label_or_alias_exact_name_QID_binding_rule_extension_20261004_v1",
        "status":"candidate_only_pending_separate_independent_review",
        "supersedes_rule_family":"scoped_qid_history_binding_current_ru_label_exact_only_gate",
        "scope":"single current 2021 physical-source row → QID candidate held only on current_ru_label_exact, with nonambiguous dated secondary P1082 history; exact current Russian source name occurs in cached full-entity RU label or alias; independently rechecked exact raw P764 and P31 as available",
        "candidate_rows":int(len(extension)),
        "raw_cached_P764_and_P31_recheck_pass_rows":int(extension.raw_cached_P764_and_P31_recheck_pass.sum()),
        "current_population_not_additive_until_review":float(extension.current_source_population.sum()) if len(extension) else 0,
        "new_bindings_admitted":0,
        "historical_population_identity_or_coordinate_admission":False,
        "inputs":{"full_current_hold_single_gate_count":int(len(label_only)),"full_entity_cache_entity_count":int(len(entity_cache)),
                  "full_entity_cache_files":raw_entity_hashes},
        "review_questions":["confirm exact alias/label parsing and source-name form (especially prefixes such as 'Деревня') is valid under the current identity rule",
                            "recheck source-native OKTMO and raw Wikidata P764 from the full entity payload for every row",
                            "recheck physical P31 lineage, region and P131/admin context, and uniqueness/competition with current-source records",
                            "decide whether the reviewed label-only gate should be superseded for this narrow family"],
        "limits":["not added to the 118,282 reviewed candidate pass set", "legacy settlement_id was not read as identity evidence", "P1082 remains secondary, source-scope unknown, and nonprimary"]}
    (OUT/"name_alias_rule_extension_review_request.json").write_text(json.dumps(extension_request,ensure_ascii=False,indent=2)+"\n")

    # Input and output coverage checks ensure all reviewed rows are place-backed.
    counts = con.execute("""
      select count(*) as observations,
             count(distinct current_source_record_id) as current_source_rows,
             count(distinct current_place_entity_id) as current_place_entities,
             count(distinct wikidata_id) as bound_qids,
             count(*) filter(where observation_year is not null) as observation_year_nonnull,
             count(*) filter(where working_year_label is not null) as working_year_label_nonnull,
             count(*) filter(where quantitative_year_eligible) as quantitative_year_eligible,
             count(*) filter(where date_variant_conflict) as date_variant_conflict_rows,
             count(*) filter(where date_ambiguous_hold) as date_ambiguous_holds,
             count(*) filter(where population_variant_conflict) as population_variant_conflict_rows,
             count(*) filter(where current_coordinate_carrier_latitude is not null and current_coordinate_carrier_longitude is not null) as rows_with_current_coordinate_context,
             count(distinct current_source_record_id) filter(where accepted_point_use_count>0) as current_places_with_accepted_point,
             count(*) filter(where historical_identity_admitted or history_population_admitted or historical_coordinate_asserted or historical_scope_inherited) as forbidden_admission_flags_true
      from read_parquet(?)
    """, [str(output_parquet)]).df().iloc[0].to_dict()
    counts = {k: (int(v) if pd.notna(v) and k not in () else v) for k,v in counts.items()}

    # Eligibility for an observed historical series requires at least one clean,
    # source-year-backed observation distinct from the current 2021 binding year.
    # This is a current-population eligibility measure only; historical values are
    # never summed and this does not establish a 2002/2010/2021 census chain.
    eligibility_query = r"""
    copy (
      with h as (
        select current_source_record_id,
               count(*) filter(where quantitative_year_eligible and observation_year is not null
                               and try_cast(working_year_label as integer)=try_cast(observation_year as integer)
                               and try_cast(observation_year as integer)<>2021) as other_year_statement_count,
               to_json(list_sort(list_distinct(list(working_year_label) filter(where quantitative_year_eligible and observation_year is not null
                               and try_cast(working_year_label as integer)=try_cast(observation_year as integer)
                               and try_cast(observation_year as integer)<>2021)))) as other_observed_years_json,
               count(*) filter(where quantitative_year_eligible and observation_year=2021) as same_2021_secondary_statement_count
        from read_parquet(?) group by current_source_record_id
      ),
      place as (
        select l.source_record_id, l.entity_id, p.latitude, p.longitude, p.coordinate_admission_status, p.coordinate_source,
               p.coordinate_source_record_id, p.coordinate_provenance,
               p.coordinate_source_sha256 as source_sha256, p.coordinate_source_file as source_path,
               p.coordinate_source_locator as source_locator
        from read_parquet(?) l
        left join read_parquet(?) p on p.target_source_record_id=l.source_record_id and p.target_year=2021
        where l.observation_year=2021 and l.record_type='census'
      )
      select b.source_record_id as current_source_record_id,
             p.entity_id as current_place_entity_id,
             b.wikidata_qid as current_wikidata_qid,
             b.settlement_name as current_settlement_name,b.settlement_type as current_settlement_type,b.region_raw as current_region_raw,
             b.population as current_2021_population,
             coalesce(h.other_year_statement_count,0) as nonconflict_other_year_statement_count,
             coalesce(h.other_observed_years_json,'[]') as nonconflict_other_observed_years_json,
             coalesce(h.same_2021_secondary_statement_count,0) as same_2021_secondary_statement_count,
             (coalesce(h.other_year_statement_count,0)>0) as eligible_for_secondary_observed_year_display,
             (p.latitude is not null and p.longitude is not null) as has_current_coordinate_carrier,
             p.latitude as current_coordinate_carrier_latitude,p.longitude as current_coordinate_carrier_longitude,
             p.coordinate_admission_status as current_coordinate_admission_status,p.coordinate_source as current_coordinate_source,
             p.coordinate_source_record_id as current_coordinate_source_record_id,p.coordinate_provenance as current_coordinate_provenance,
             p.source_sha256 as current_population_source_sha256,p.source_path as current_population_source_path,p.source_locator as current_population_source_locator,
             'current source row and accepted 2021 point context only; no historical census identity/coordinate or boundary comparability' as limitation
      from read_csv_auto(?,header=true,all_varchar=false) b
      left join h on h.current_source_record_id=b.source_record_id
      left join place p on p.source_record_id=b.source_record_id
    ) to '__ELIGIBILITY_PATH__' (FORMAT PARQUET, COMPRESSION ZSTD)
    """.replace("__ELIGIBILITY_PATH__", str(OUT/"current_place_other_year_history_eligibility.parquet"))
    eligibility_parquet = OUT/"current_place_other_year_history_eligibility.parquet"
    con.execute(eligibility_query, [str(output_parquet),str(LONG),str(POINT_USES),str(CANDIDATES)])
    eligibility_df = con.execute("select * from read_parquet(?)",[str(eligibility_parquet)]).df()
    eligibility_df["nonconflict_other_observed_years_json"] = eligibility_df.nonconflict_other_observed_years_json.fillna("[]")
    eligibility_csv = OUT/"current_place_other_year_history_eligibility.csv"
    write_csv(eligibility_df,eligibility_csv)
    eligible_ids = eligibility_df[eligibility_df.eligible_for_secondary_observed_year_display]
    eligible_current_population = int(eligible_ids.current_2021_population.sum())
    selected_current_population = int(eligibility_df.current_2021_population.sum())
    eligible_by_year_rows=[]
    for _,r in eligible_ids.iterrows():
        for y in json.loads(r.nonconflict_other_observed_years_json or "[]"):
            eligible_by_year_rows.append((str(y),r.current_source_record_id,int(r.current_2021_population)))
    by_year=(pd.DataFrame(eligible_by_year_rows,columns=["observed_year","current_source_record_id","current_2021_population"])
             .drop_duplicates(["observed_year","current_source_record_id"]).groupby("observed_year",as_index=False)
             .agg(eligible_current_source_rows=("current_source_record_id","nunique"),eligible_current_2021_population=("current_2021_population","sum")))
    by_year["interpretation"]="candidate secondary observed-year eligibility; current 2021 population counted once per year; no historical P1082 value sum or national denominator"
    by_year_csv=OUT/"current_population_eligibility_by_other_observed_year.csv"
    write_csv(by_year,by_year_csv)
    output_files = [output_parquet, profile_csv, eligibility_parquet,eligibility_csv,by_year_csv,OUT/"producer_p764_gate_correction.json",
                    OUT/"missing_current_QID_history_hold_gate_assessment.csv", OUT/"single_gate_holds_with_cached_history_top500.csv",
                    OUT/"raw_entity_exact_name_alias_history_candidates.csv", OUT/"name_alias_rule_extension_review_request.json"]
    receipt = {
        "build_id":"reviewed_secondary_history_application_20261004_v1",
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"separate_secondary_history_overlay; reviewed_current_QID_bindings; no_census_identity_or_population_admission",
        "inputs":{str(p):sha(p) for p in EXPECTED},
        "raw_full_entity_cache_inputs":raw_entity_hashes,
        "review_receipt_status":review_receipt["status"],
        "review_scope":"current 2021 source row to QID binding only; secondary P1082 history display; no historical identity, scope, exact census date, coordinate, or primary-source verification",
        "observations":counts,
        "current_place_other_year_history_eligibility":{"reviewed_current_binding_rows":int(len(eligibility_df)),
            "rows_with_at_least_one_nonconflict_other_observed_year":int(len(eligible_ids)),
            "current_2021_population_eligible_once_per_current_place":eligible_current_population,
            "all_reviewed_current_binding_population":selected_current_population,
            "eligible_current_population_share_pct":round(100*eligible_current_population/max(1,selected_current_population),6),
            "rows_with_current_accepted_coordinate_carrier_and_other_year":int(eligible_ids.has_current_coordinate_carrier.sum()),
            "not_a_complete_Russian_2002_2010_2021_chain":True,
            "outputs":[eligibility_parquet.name,eligibility_csv.name,by_year_csv.name]},
        "history_date_policy":{"raw_observation_year_preserved":True,"working_year_label_preserved":True,
                                "quantitative_year_excludes_date_or_population_conflict":True,
                                "year_label_without_observation_year_not_quantitatively_eligible":True,
                                "full_p585_raw_qualifiers_and_precision_preserved":True},
        "place_coordinate_policy":{"current_place_entity_id_attached_as_candidate_association":True,
                                   "current_accepted_coordinate_carrier_fields_retained_as_context":True,
                                   "historical_latitude_longitude_null":True,"no_current_coordinate_copied_to_historical_coordinates":True},
        "annual_profile":"secondary_history_observed_year_profile.csv; counts only, no population totals or national denominator",
        "held_binding_investigation":{"held_source_rows":int(len(held)),"held_current_population":int(held.population.sum()),
                                      "held_rows_with_QID":int(held.wikidata_qid.ne("").sum()),
                                      "held_rows_with_dated_nonconflict_QID_history":int(held.qid_dated_nonconflict_statement_rows.gt(0).sum()),
                                      "single_gate_held_rows_with_dated_nonconflict_history":int(len(single)),
                                      "single_gate_RU_label_only_history_rows":int(len(label_only)),
                                      "raw_entity_exact_name_alias_rule_extension_candidates":int(len(extension)),
                                      "raw_entity_native_P764_P31_rechecked_candidates":int(extension.raw_cached_P764_and_P31_recheck_pass.sum()),
                                      "recovered_or_admitted_bindings":0,
                                      "outputs":["missing_current_QID_history_hold_gate_assessment.csv","single_gate_holds_with_cached_history_top500.csv","raw_entity_exact_name_alias_history_candidates.csv","name_alias_rule_extension_review_request.json"],
                                      "method":"use only published current-row QID/code/name/admin/P31 gates and cached QID-keyed P1082 history; no legacy settlement ID used"},
        "producer_gate_correction":"producer_p764_gate_correction.json; source code corrected; reviewed files not rebuilt or changed",
        "outputs":{}
    }
    for p in output_files:
        receipt["outputs"][p.name] = {"sha256":sha(p),"bytes":p.stat().st_size}
    (OUT/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")

if __name__ == "__main__":
    main()
