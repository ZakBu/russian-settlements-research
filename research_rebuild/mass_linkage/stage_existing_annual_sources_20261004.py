#!/usr/bin/env python3
"""Stage actual-year non-Wikidata population assertions already cached in legacy DB.

This is a source-assertion inventory. A legacy settlement_id/QID lookup is only a
candidate binding, never accepted historical identity or coordinate evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import duckdb

LEGACY = Path('/workspace/settlements-assets/baseline/legacy_database_20260929.duckdb')
DELIVERY = Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
FINAL = DELIVERY / 'settlements_long.parquet'
OUTPUT = Path('/workspace/settlements-work/continuation_20261004/annual_existing')
EXPECTED_LEGACY_SHA256 = '26a2fe5b2ce05119d919a196beb57cd655a49ffffb0ff8f194762aa78e6b5b64'
SOURCES = ('wikipedia_statistical_module', 'census_table_external_year_reconciled', 'wikipedia_settlement_list')
FAMILY_LABEL = {
    'wikipedia_statistical_module': 'literal Wikipedia statistical module array; object scope not independently certified',
    'census_table_external_year_reconciled': 'source-native census-table row linked by legacy external-year reconciliation',
    'wikipedia_settlement_list': 'literal archived Wikipedia settlement-list row; page-level year rule retained',
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    legacy_sha = sha256(LEGACY)
    if legacy_sha != EXPECTED_LEGACY_SHA256:
        raise RuntimeError(f'Legacy DB checksum mismatch: {legacy_sha}')
    con = duckdb.connect(':memory:')
    con.execute("SET memory_limit='1GB'")
    con.execute('SET threads=1')
    con.execute(f"ATTACH '{LEGACY}' AS legacy (READ_ONLY)")
    con.execute(f"CREATE VIEW final_rows AS SELECT * FROM read_parquet('{FINAL.as_posix()}')")
    con.execute("""
        CREATE TEMP VIEW existing_nonwd AS
        SELECT l.*,
               x.wikidata_id_effective AS candidate_wikidata_id,
               x.article_title AS candidate_wikipedia_title,
               x.permanent_url AS candidate_current_article_revision_url,
               x.article_link_status AS candidate_article_link_status,
               CASE WHEN x.wikidata_id_effective IS NOT NULL
                    THEN 'candidate_from_legacy_current_article_crosswalk_only'
                    ELSE 'no_legacy_current_article_qid_binding'
               END AS qid_binding_status
        FROM legacy.population_observations l
        LEFT JOIN legacy.wikipedia_settlement_article_crosswalk x
          ON x.settlement_id=l.settlement_id
        WHERE l.source_family IN ('wikipedia_statistical_module',
                                  'census_table_external_year_reconciled',
                                  'wikipedia_settlement_list')
          AND l.observation_year IS NOT NULL
          AND l.population IS NOT NULL
          AND l.temporal_quality_flag='observed_year'
    """)
    # F has exactly 34,004 literal module assertions. Match by the literal module
    # article identifier and exact observation year/value, and use source row IDs
    # for the two non-module families. These are assertion-duplication checks only.
    con.execute("""
      CREATE TEMP VIEW classified AS
      SELECT l.*,
        CASE
          WHEN l.source_family='wikipedia_statistical_module' AND EXISTS (
            SELECT 1 FROM final_rows f WHERE f.record_type='wiki_literal_series'
              AND f.source_record_id LIKE 'WIKI-LUA:' || l.source_record_id || ':line:%'
              AND f.observation_year=l.observation_year AND f.population_value=l.population
          ) THEN 'already_in_F_exact_module_article_year_value'
          WHEN l.source_family='wikipedia_statistical_module' THEN 'additive_to_F_module_assertion'
          WHEN l.source_family='census_table_external_year_reconciled' AND EXISTS (
            SELECT 1 FROM final_rows f WHERE f.source_record_id=l.source_record_id
              AND f.observation_year=l.observation_year AND f.population_value=l.population
          ) THEN 'already_in_F_exact_source_row_year_value'
          WHEN l.source_family='census_table_external_year_reconciled' THEN 'additive_to_F_external_reconciled_assertion'
          WHEN l.source_family='wikipedia_settlement_list' AND EXISTS (
            SELECT 1 FROM final_rows f WHERE f.source_record_id=l.source_record_id
              AND f.observation_year=l.observation_year AND f.population_value=l.population
          ) THEN 'already_in_F_exact_list_row_year_value'
          ELSE 'additive_to_F_archived_list_assertion'
        END AS duplicate_status
      FROM existing_nonwd l
    """)
    # Module-level source hash and file location; external census workbooks are
    # hashed directly. List pages have permanent revision URLs and row locators.
    con.execute("""
      CREATE TEMP VIEW staged AS
      SELECT c.*,
        CASE WHEN c.source_family='wikipedia_statistical_module'
             THEN 'data/raw/wikipedia_statistical/' || split_part(c.source_record_id, ':', 1) || '.lua.gz'
             WHEN c.source_family='census_table_external_year_reconciled' THEN c.source_detail
             ELSE NULL END AS raw_source_path_relative,
        CASE WHEN c.source_family='wikipedia_statistical_module' THEN c.source_record_id || ':year=' || c.observation_year
             WHEN c.source_family='census_table_external_year_reconciled' THEN c.source_record_id
             ELSE c.source_record_id END AS raw_source_locator_preserved,
        CASE WHEN c.source_family='wikipedia_statistical_module' THEN 'module/article record id + parsed observation year; legacy DB has no line locator'
             WHEN c.source_family='census_table_external_year_reconciled' THEN 'workbook row locator embedded in source_record_id'
             ELSE 'archived page revision + source_record_id section/table/row locator'
        END AS locator_precision,
        'secondary dated source assertion candidate; current QID/place link requires independent review' AS candidate_status,
        'no historical physical identity or coordinate claim; no year-label substitution; no interpolation' AS interpretation_conditions
      FROM classified c
    """)
    rows = con.execute('SELECT * FROM staged ORDER BY source_family, observation_year, source_record_id').fetchdf()
    # Render columns to a portable Parquet file, excluding legacy-derived wide
    # diagnostic fields that do not contribute to the source assertion.
    keep = [
        'settlement_id','observation_year','observation_date','population','source_family','source_detail',
        'source_record_id','wikidata_id','wikidata_statement_id','candidate_wikidata_id',
        'candidate_wikipedia_title','candidate_current_article_revision_url','candidate_article_link_status',
        'qid_binding_status','link_method','link_quality_flag','population_scope','source_priority',
        'article_title','article_revision_id','article_permanent_url','source_url','year_evidence_text',
        'temporal_quality_flag','duplicate_status','raw_source_path_relative','raw_source_locator_preserved',
        'locator_precision','candidate_status','interpretation_conditions'
    ]
    export = rows[keep].copy()
    # Add per-file hashes after extracting only path names. Input source bytes are
    # not changed; unavailable legacy paths are marked explicitly in the receipt.
    import pandas as pd
    def raw_hash(path: object) -> str | None:
        if not isinstance(path, str) or not path:
            return None
        p = Path('/workspace/settlements-raw') / path
        if not p.exists():
            return None
        return sha256(p)
    export['raw_source_sha256'] = export['raw_source_path_relative'].map(raw_hash)
    # Hash of the legacy table itself is retained for claims whose upstream asset
    # is not separately cached (Wikipedia list page assertions).
    export['legacy_database_sha256'] = legacy_sha
    export.to_parquet(OUTPUT / 'non_wikidata_existing_year_assertion_candidates.parquet', index=False)

    # Isolate current-place code/name/region candidates only where a module's
    # article family is already among F's reviewed literal-Wikipedia series.
    # Exact matching here creates review candidates, not accepted bindings.
    current = con.execute("""
      SELECT DISTINCT
        l.source_family, l.settlement_id, l.source_record_id AS legacy_module_article_id,
        l.candidate_wikidata_id, l.candidate_wikipedia_title,
        a.settlement_name AS legacy_current_anchor_name, a.region_raw AS legacy_current_anchor_region,
        f.wiki_current_source_oktmo_literal AS F_current_source_oktmo_literal,
        f.settlement_name AS F_associated_current_name, f.region_raw AS F_associated_current_region,
        min(f.source_record_id) AS representative_F_reviewed_literal_row_id,
        'same F literal-Wikipedia article family + exact current OKTMO/name/region fields; manual review required' AS candidate_binding_status
      FROM existing_nonwd l
      JOIN legacy.settlements_2021 a ON a.settlement_id=l.settlement_id
      JOIN final_rows f ON f.record_type='wiki_literal_series'
        AND f.source_record_id LIKE 'WIKI-LUA:' || l.source_record_id || ':line:%'
      WHERE l.source_family='wikipedia_statistical_module'
        AND f.wiki_current_source_oktmo_literal=replace(l.settlement_id, 'RU-OKTMO-', '')
        AND f.settlement_name=a.settlement_name
        AND f.region_raw=a.region_raw
      GROUP BY l.source_family, l.settlement_id, l.source_record_id, l.candidate_wikidata_id,
        l.candidate_wikipedia_title, a.settlement_name, a.region_raw,
        f.wiki_current_source_oktmo_literal, f.settlement_name, f.region_raw
    """).fetchdf()
    current_path = OUTPUT / 'current_place_exact_code_name_region_candidates.parquet'
    current.to_parquet(current_path, index=False)

    # Family and year matrices make additivity inspectable without asserting any
    # annual national denominator or accepting identity candidates.
    summary_rows = con.execute("""
      SELECT source_family, observation_year, duplicate_status, count(*) AS assertions,
             count(DISTINCT settlement_id) AS legacy_settlement_ids,
             count(DISTINCT candidate_wikidata_id) AS candidate_qids,
             count(*) FILTER (WHERE candidate_wikidata_id IS NOT NULL) AS rows_with_candidate_qid,
             count(*) FILTER (WHERE raw_source_path_relative IS NOT NULL) AS rows_with_raw_path
      FROM staged GROUP BY ALL ORDER BY source_family, observation_year, duplicate_status
    """).fetchdf()
    summary_rows.to_csv(OUTPUT / 'annual_assertion_status_by_family_year.csv', index=False)

    # Cached source file inventory and hashes used by the exported candidate set.
    raw_assets = []
    for path in sorted({x for x in export['raw_source_path_relative'].tolist() if isinstance(x, str)}):
        p = Path('/workspace/settlements-raw') / path
        raw_assets.append({'raw_source_path_relative': path, 'exists': p.exists(), 'sha256': sha256(p) if p.exists() else None})
    final_sha = sha256(FINAL)
    parquet_path = OUTPUT / 'non_wikidata_existing_year_assertion_candidates.parquet'
    report = {
        'status': 'staged_actual_year_non_wikidata_legacy_assertions_candidates_only',
        'source_scope': list(SOURCES),
        'legacy_database': {'path': str(LEGACY), 'sha256': legacy_sha, 'read_only': True},
        'existing_F': {'path': str(FINAL), 'sha256': final_sha, 'rows': 500320,
                       'record_types': {'census': 465800, 'annual_official_2022_24': 516, 'wiki_literal_series': 34004}},
        'candidate_export': {'path': str(parquet_path), 'sha256': sha256(parquet_path), 'rows': len(export)},
        'current_place_exact_candidates': {'path': str(current_path), 'sha256': sha256(current_path), 'rows': len(current),
                                           'status': 'candidate_only; filtered to same F literal-Wikipedia article family and exact current code/name/region'},
        'families': con.execute("""
          SELECT source_family, count(*) n, min(observation_year) first_year, max(observation_year) last_year,
                 count(DISTINCT observation_year) year_count,
                 count(*) FILTER (WHERE duplicate_status LIKE 'additive%') additive_assertions,
                 count(*) FILTER (WHERE duplicate_status LIKE 'already%') exact_F_duplicates,
                 count(*) FILTER (WHERE candidate_wikidata_id IS NOT NULL) qid_candidate_rows,
                 count(*) FILTER (WHERE source_family='wikipedia_statistical_module' AND candidate_wikidata_id IS NOT NULL) module_qid_rows
          FROM staged GROUP BY source_family ORDER BY source_family
        """).fetchdf().to_dict(orient='records'),
        'raw_assets': raw_assets,
        'interpretation': {
            'observation_year_is_source_asserted_year': True,
            'publication_year_labels_never_replace_observation_year': True,
            'exact_F_duplicates_are_source_assertion_overlap_only': True,
            'legacy_settlement_id_and_crosswalk_QID_are_candidate_bindings_only': True,
            'no_historical_physical_identity_or_coordinate_claim': True,
            'no_interpolation_or_fabricated_years': True,
            'no_national_annual_denominator_or_coverage_claim': True,
            'family_conditions': FAMILY_LABEL,
        },
        'artifacts': {
            'by_family_year_csv': str(OUTPUT / 'annual_assertion_status_by_family_year.csv'),
            'by_family_year_sha256': sha256(OUTPUT / 'annual_assertion_status_by_family_year.csv'),
        },
    }
    (OUTPUT / 'receipt.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'rows': len(export), 'families': report['families'],
                      'export_sha256': report['candidate_export']['sha256'], 'output': str(OUTPUT)},
                     ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
