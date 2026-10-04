#!/usr/bin/env python3
"""Correct a legacy 2021 OKTMO leading-zero claim against its raw source rows.

This job is diagnostic. It preserves legacy claims and produces explicitly
derived format candidates; it never admits an identifier binding or rewrites a
frozen observation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

ROOT = Path('/workspace/russian-settlements-research')
WORK = Path('/workspace/settlements-work/continuation_20261004')
OUT = WORK / 'identifier_history_inventory/leading_zero_recovery'
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
RAW = Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
CLAIMS = Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/identifier_claim_candidates.parquet')
CLAIM_REVIEW = WORK / 'identifier_history_inventory/receipt.json'
PRIOR_CLAIMS_OUTPUT = WORK / 'identifier_history_inventory/current_oktmo_observations.parquet'
PRIOR_BUILDER = WORK / 'identifier_history_inventory/build_identifier_history_inventory_20261004.py'
GRAPH = WORK / 'accepted_mass_extensions/accepted_identity_edges.parquet'
POINTS = WORK / 'accepted_mass_extensions/accepted_point_uses.parquet'
WIDE = Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet')
QIDS = WORK / 'independent_history_review/review_eligible_current_QID_binding_candidates.csv'
LEGACY_BUILD = Path('/workspace/settlements-data/research_audit/build.py')
RAW_SHA = '86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'
ACCEPTED_EDGE_STATUSES = (
    'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
    'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def qpath(path: Path) -> str:
    return str(path).replace("'", "''")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = [SELECTED, RAW, CLAIMS, CLAIM_REVIEW, PRIOR_CLAIMS_OUTPUT, PRIOR_BUILDER, GRAPH, POINTS, WIDE, QIDS, LEGACY_BUILD]
    missing = [str(x) for x in files if not x.is_file()]
    if missing:
        raise FileNotFoundError('\n'.join(missing))
    if sha(RAW) != RAW_SHA:
        raise RuntimeError('2021 Tochno raw source hash does not match pinned source')
    con = duckdb.connect(':memory:')
    con.execute('SET threads=1')
    con.execute("SET memory_limit='1GB'")
    con.execute(f"CREATE VIEW selected AS SELECT * FROM read_parquet('{qpath(SELECTED)}')")
    con.execute(f"CREATE VIEW claims AS SELECT * FROM read_parquet('{qpath(CLAIMS)}')")
    con.execute(f"CREATE VIEW raw AS SELECT *, file_row_number AS raw_file_row_zero_based FROM read_parquet('{qpath(RAW)}', file_row_number=true)")
    con.execute(f"CREATE VIEW wide AS SELECT * FROM read_parquet('{qpath(WIDE)}')")
    con.execute(f"CREATE VIEW graph AS SELECT * FROM read_parquet('{qpath(GRAPH)}')")
    con.execute(f"CREATE VIEW points AS SELECT * FROM read_parquet('{qpath(POINTS)}')")
    con.execute(f"CREATE VIEW qids AS SELECT * FROM read_csv_auto('{qpath(QIDS)}', all_varchar=true)")

    # Exact row ID -> raw Parquet ordinal binding. Verify the full selected 2021
    # cohort before deriving any discrepancy subset.
    con.execute("""
      CREATE TEMP TABLE selected_raw AS
      SELECT s.source_record_id, s.census_year, s.source_file, s.source_sha256,
             s.source_locator, s.source_row, s.source_native_id,
             s.oktmo AS selected_oktmo, s.okato AS selected_okato,
             s.source_name_raw AS selected_name, s.region_raw AS selected_region,
             s.population AS selected_population,
             r.object_level AS raw_object_level, r.object_name AS raw_object_name,
             r.oktmo AS raw_oktmo, r.region AS raw_region,
             r.population AS raw_population, r.oktmo_dadata AS raw_oktmo_dadata,
             r.raw_file_row_zero_based,
             c.raw_code AS legacy_claim_code, c.source_file AS claim_source_file,
             c.source_sha256 AS claim_source_sha256, c.source_locator AS claim_source_locator,
             c.source_snapshot_version AS claim_snapshot_version, c.source_url AS claim_source_url
      FROM selected s
      LEFT JOIN raw r ON r.raw_file_row_zero_based =
        try_cast(regexp_extract(s.source_record_id, 'parquet:([0-9]+)$', 1) AS BIGINT)-1
      LEFT JOIN claims c ON c.source_record_id=s.source_record_id
        AND c.source_table='administrative_identifiers_2021'
        AND c.source_field='oktmo' AND c.identifier_system='OKTMO'
      WHERE s.census_year=2021 AND s.source_file LIKE '%data_allsettlements_anon_156%'
    """)
    total, raw_missing, oktmo_mismatch, population_mismatch, region_mismatch, claim_missing = con.execute("""
      SELECT count(*), count(*) FILTER(WHERE raw_file_row_zero_based IS NULL),
        count(*) FILTER(WHERE selected_oktmo IS DISTINCT FROM raw_oktmo),
        count(*) FILTER(WHERE selected_population IS DISTINCT FROM raw_population),
        count(*) FILTER(WHERE selected_region IS DISTINCT FROM raw_region),
        count(*) FILTER(WHERE legacy_claim_code IS NULL)
      FROM selected_raw
    """).fetchone()
    if total != 155414 or any((raw_missing, oktmo_mismatch, population_mismatch, region_mismatch, claim_missing)):
        raise RuntimeError(f'raw row replay failed: rows={total}, raw_missing={raw_missing}, oktmo_mismatch={oktmo_mismatch}, population_mismatch={population_mismatch}, region_mismatch={region_mismatch}, claim_missing={claim_missing}')

    con.execute("""
      CREATE TEMP TABLE discordant AS
      SELECT *, length(raw_oktmo) AS raw_code_width,
        lpad(raw_oktmo, 11, '0') AS derived_11digit_format_candidate,
        CASE WHEN raw_oktmo=legacy_claim_code THEN 'legacy_claim_equals_raw_literal'
             WHEN legacy_claim_code=lpad(raw_oktmo,11,'0') AND length(raw_oktmo)=10
               THEN 'legacy_claim_is_zero_padded_10digit_derivative'
             WHEN legacy_claim_code=lpad(raw_oktmo,11,'0') AND length(raw_oktmo)<10
               THEN 'legacy_claim_is_zero_padded_non10digit_derivative_hold_grain'
             ELSE 'legacy_claim_conflicts_with_raw_source_unclassified' END AS source_claim_diagnosis,
        CASE WHEN length(raw_oktmo)=10 AND raw_object_level='Населенный пункт'
               THEN 'format_derivative_candidate_only_no_exact_cached_P764_support'
             WHEN length(raw_oktmo)<10
               THEN 'hold_federal_or_aggregate_grain_do_not_pad'
             ELSE 'manual_source_claim_diagnosis_required' END AS binding_candidate_status
      FROM selected_raw WHERE legacy_claim_code IS DISTINCT FROM raw_oktmo
    """)
    discord_count = con.execute('SELECT count(*) FROM discordant').fetchone()[0]
    if discord_count != 6948:
        raise RuntimeError(f'expected 6948 legacy/raw discrepancies, found {discord_count}')

    # Direct same-record WIDE provenance, with the native code and WIDE P764
    # carried side by side. No padded-code search is treated as a match.
    con.execute("""
      CREATE TEMP TABLE wide_by_source AS
      SELECT d.source_record_id, w.wikidata_qid, w.source_oktmo_raw,
        w.source_oktmo_exact_digits, w.wikidata_tsv_exact_p764_value_raw,
        w.wikidata_truthy_exact_p764_claims_json, w.wikidata_truthy_exact_p764_match,
        w.wikidata_truthy_p31_claims_json, w.wikidata_truthy_p131_claims_json,
        w.wikidata_tsv_ru_labels_json, w.source_type, w.source_region,
        w.tsv_entity_competition_for_exact_oktmo,
        w.truthy_entity_competition_for_exact_oktmo,
        w.source_observation_competition_for_exact_oktmo
      FROM discordant d LEFT JOIN wide w USING(source_record_id)
    """)
    con.execute("""
      CREATE TEMP TABLE qid_by_source AS
      SELECT d.source_record_id, q.wikidata_qid AS reviewed_candidate_qid,
        q.exact_source_oktmo_p764, q.physical_p31_lineage,
        q.current_source_name_exact, q.current_source_type_exact,
        q.current_source_region_exact, q.source_code_unique_qid,
        q.qid_unique_current_source_code, q.native_competition_clear
      FROM discordant d LEFT JOIN qids q USING(source_record_id)
    """)
    con.execute("""
      CREATE TEMP TABLE point_by_source AS
      SELECT d.source_record_id, count(p.target_source_record_id) AS accepted_point_use_count,
        string_agg(DISTINCT p.coordinate_provider_family, ';' ORDER BY p.coordinate_provider_family)
          AS accepted_point_provider_families
      FROM discordant d LEFT JOIN points p
        ON p.target_source_record_id=d.source_record_id
      GROUP BY d.source_record_id
    """)
    con.execute("""
      CREATE TEMP TABLE result AS
      SELECT d.*, w.wikidata_qid AS wide_qid,
        w.source_oktmo_raw AS wide_source_code_raw,
        w.wikidata_tsv_exact_p764_value_raw AS wide_exact_p764_raw,
        w.wikidata_truthy_exact_p764_match AS wide_exact_p764_match,
        w.wikidata_truthy_exact_p764_claims_json AS wide_p764_claims_json,
        w.wikidata_truthy_p31_claims_json AS wide_p31_claims_json,
        w.wikidata_truthy_p131_claims_json AS wide_p131_claims_json,
        w.wikidata_tsv_ru_labels_json AS wide_ru_labels_json,
        w.tsv_entity_competition_for_exact_oktmo AS wide_tsv_code_competition,
        w.truthy_entity_competition_for_exact_oktmo AS wide_truthy_code_competition,
        w.source_observation_competition_for_exact_oktmo AS wide_source_code_competition,
        q.reviewed_candidate_qid, q.exact_source_oktmo_p764, q.physical_p31_lineage,
        q.current_source_name_exact, q.current_source_type_exact, q.current_source_region_exact,
        q.source_code_unique_qid, q.qid_unique_current_source_code, q.native_competition_clear,
        p.accepted_point_use_count, p.accepted_point_provider_families,
        CASE WHEN d.raw_code_width=10 AND d.raw_object_level='Населенный пункт'
              AND w.wikidata_truthy_exact_p764_match
              AND w.source_oktmo_exact_digits=d.raw_oktmo
             THEN 'raw_source_literal_code_corroborated_by_cached_exact_P764'
             WHEN d.raw_code_width=8 AND w.wikidata_truthy_exact_p764_match
              AND w.source_oktmo_exact_digits=d.raw_oktmo
             THEN 'raw_source_literal_code_corroborated_but_federal_city_grain_hold'
             WHEN d.raw_code_width=10 AND d.raw_object_level='Населенный пункт'
             THEN 'derived_11digit_format_candidate_only_no_cached_literal_QID_binding'
             ELSE 'hold_unresolved_source_code_or_grain' END AS final_binding_scope
      FROM discordant d
      LEFT JOIN wide_by_source w USING(source_record_id)
      LEFT JOIN qid_by_source q USING(source_record_id)
      LEFT JOIN point_by_source p USING(source_record_id)
    """)
    # Graph exposure is diagnostic only. Count accepted edges incident to these
    # source records by the other endpoint year.
    status_sql = ','.join("'" + s + "'" for s in ACCEPTED_EDGE_STATUSES)
    graph_counts = con.execute(f"""
      WITH incident AS (
        SELECT d.source_record_id, g.decision_id, g.relation, g.decision_status,
          CASE WHEN g.from_source_record_id=d.source_record_id THEN g.to_year ELSE g.from_year END AS other_year,
          CASE WHEN g.from_source_record_id=d.source_record_id THEN g.to_source_record_id ELSE g.from_source_record_id END AS other_source_record_id
        FROM discordant d JOIN graph g ON d.source_record_id IN (g.from_source_record_id,g.to_source_record_id)
        WHERE g.decision_status IN ({status_sql})
      ) SELECT coalesce(other_year,'(null)'), count(*), count(DISTINCT source_record_id),
        count(DISTINCT other_source_record_id) FROM incident GROUP BY 1 ORDER BY 1
    """).fetchall()

    out_parquet = OUT / 'raw_source_correction_candidates.parquet'
    con.execute(f"COPY result TO '{qpath(out_parquet)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    status_counts = con.execute("SELECT source_claim_diagnosis,binding_candidate_status,final_binding_scope,count(*) FROM result GROUP BY 1,2,3 ORDER BY 1,2,3").fetchall()
    qid_metrics = con.execute("""
      SELECT count(*) FILTER(WHERE wide_qid IS NOT NULL),
        count(*) FILTER(WHERE wide_exact_p764_match),
        count(*) FILTER(WHERE reviewed_candidate_qid IS NOT NULL),
        count(*) FILTER(WHERE accepted_point_use_count>0),
        sum(coalesce(accepted_point_use_count,0)),
        count(*) FILTER(WHERE raw_code_width=10 AND raw_object_level='Населенный пункт'),
        count(*) FILTER(WHERE raw_code_width=8 AND raw_object_level='Город федерального значения')
      FROM result
    """).fetchone()
    cohort_size = con.execute("SELECT count(DISTINCT raw_oktmo) FROM result WHERE raw_code_width=10").fetchone()[0]
    legacy_logic = {
      'file': str(LEGACY_BUILD), 'sha256': sha(LEGACY_BUILD),
      'code_excerpt': "identifier_normalized=identifier_digits.where(~identifier_length.eq(10),identifier_digits.str.zfill(11)); normalization_note='leading_zero_recovery_candidate'",
      'interpretation': 'Legacy audit code explicitly derives 11-digit strings from every 10-digit OKTMO/OKATO and labels these leading_zero_recovery_candidate. Its identifier_raw remains source literal, while identifier_normalized is a format candidate. The corresponding claim artifact labels padded values raw_code; this receipt corrects that distinction without replacing the old artifact.'
    }
    summary = {
      'task': 'raw source correction and candidate-only leading-zero review',
      'created_utc_date': '2026-10-04',
      'inputs': {str(p): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in files},
      'raw_source': {'path': str(RAW), 'sha256': sha(RAW), 'locator': 'source_record_id suffix parquet:N maps exactly to zero-based Parquet file_row_number N-1', 'selected_2021_rows': total, 'raw_row_locator_misses': raw_missing, 'selected_raw_oktmo_mismatches': oktmo_mismatch, 'population_mismatches': population_mismatch, 'region_mismatches': region_mismatch, 'missing_legacy_oktmo_claims': claim_missing},
      'cohort': {'legacy_claim_vs_raw_literal_discrepancies': discord_count, 'actual_10digit_NP_rows': qid_metrics[5], 'actual_8digit_federal_city_rows': qid_metrics[6], 'distinct_10digit_codes': cohort_size, 'same_source_wide_qid_rows': qid_metrics[0], 'same_source_exact_raw_p764_matches': qid_metrics[1], 'reviewed_current_qid_candidate_rows': qid_metrics[2], 'point_target_rows_with_any_accepted_point': qid_metrics[3], 'accepted_point_use_rows': qid_metrics[4]},
      'legacy_derivation': legacy_logic,
      'prior_inventory_preserved': {'prior_parquet_path': str(PRIOR_CLAIMS_OUTPUT), 'prior_parquet_sha256': sha(PRIOR_CLAIMS_OUTPUT), 'prior_builder_path': str(PRIOR_BUILDER), 'prior_builder_sha256': sha(PRIOR_BUILDER), 'status': 'input frozen in place; this receipt and candidate table are separate correction artifacts'},
      'status_counts': [{'source_claim_diagnosis':a,'binding_candidate_status':b,'final_binding_scope':c,'rows':n} for a,b,c,n in status_counts],
      'accepted_graph_incident_edge_diagnostics_by_other_year': [{'other_year':y,'edges':n,'discrepant_current_records':ids,'other_endpoint_records':others} for y,n,ids,others in graph_counts],
      'decision': 'No native-code correction/admission is made here. Keep raw current OKTMO exactly as published; keep historical legacy padded claim as a derived-format artifact, not source literal. Ten-digit locality rows remain candidate-only because cached exact WIDE P764 does not independently corroborate the derived eleven-digit value. Three eight-digit federal-city rows remain at their raw grain and must not be padded.',
      'output': {'path': str(out_parquet), 'sha256': sha(out_parquet), 'rows': discord_count},
    }
    out_json = OUT / 'correction_receipt.json'
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output':str(out_parquet),'sha256':sha(out_parquet),'rows':discord_count,'summary':str(out_json),'cohort':summary['cohort'],'status_counts':summary['status_counts']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
