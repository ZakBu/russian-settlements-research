# Large-settlement Wikidata P1082 history inventory

**Status:** candidate-only source inventory. No population value, historical identity edge, or coordinate was admitted. Current scope is 2021 physical settlement observations with population >= 2,000.

## Coverage

- Current large physical universe: 5,287 rows, population 106,373,959.
- Exact WIDE-v5 truthy P764-linked QID: 3,989 rows, population 87,533,558 (82.3% of this large universe), 3,989 QIDs. These remain exact-code candidates.
- Cached full entity records: 187 of 3,989 exact QIDs are present in 29 cached batches (1,450 unique entity QIDs across the cache). These matching full entities contain nondeprecated P1082 for 187 current rows (population 5,455,409), with 4,984 distinct statements. Cache absence for another exact QID means only that its full entity is not in this cache.
- The flat TSV raw inventory contains 64,483 distinct QID-statement observations for 3,965 of the large exact QIDs (128,309 raw matching rows before deduplication); 64,466 are nondeprecated and eligible for candidate history, while 17 deprecated-rank statements remain preserved in the raw inventory but are explicitly excluded from candidate history. Rank counts are {"<http://wikiba.se/ontology#DeprecatedRank>": 17, "<http://wikiba.se/ontology#NormalRank>": 62447, "<http://wikiba.se/ontology#PreferredRank>": 2019}. 4,984 statement IDs overlap the full-entity inventory after GUID normalization. See `candidate_tsv_long.parquet` for literal amount/date/rank/OKTMO and source-line provenance.
- Existing accepted identity graph components connect 2,752 exact-QID current targets (population 79,073,600) to historical endpoint rows; endpoint years are {"2002": 2497, "2010": 1915}. This is existing identity context only.

## What is preserved

`candidate_long.parquet` has one row per 2021 source-QID-P1082 statement found in cached full entities. It preserves literal amount and unit, rank, statement ID, raw P585 time/precision/calendar/before/after, every qualifier (including P518 and P459 where present), all references, full raw statement JSON, QID/entity revision and modified time, full-entity retrieval time, raw batch SHA-256, and locator. Deprecated P1082 claims are excluded; they are counted in `summary.json`. P585 year prefixes are indexed for coverage summaries but remain literal qualifiers; a year-only `2002` does not establish a 2002 census observation.

`candidate_tsv_long.parquet` retains the full raw TSV inventory deduplicated by QID + statement ID, including literal amount/rank/OKTMO, every distinct raw date literal, all duplicate source line numbers and the source hash. It marks normal/preferred ranks as admissible for candidate history and deprecated ranks as ineligible; all 17 deprecated statements remain preserved but must not enter the usable history series. Four statement IDs have conflicting date literals across repeated raw rows; for those rows the scalar date field is suppressed and all alternatives remain in `date_literal_variants_json`. The flat TSV omits date precision, full qualifiers and references, so its dates do not settle population scope/grain or census-year interpretation alone. Shared statement GUIDs are deduplicated across tiers for overlap counts and are never independent corroboration.

## Evidence limits and next step

The full-entity JSON preserves the richest cached statement form. TSV, module rows (12 matching QIDs), and existing literal associations (234) belong to one Wikimedia/Wikipedia lineage and are not independent corroboration. The TSV/module flattening does not retain the full qualifiers and references present in the raw entity.

Treat this as a bounded large-population historical-series pilot. Review dated statements' scope, P518 qualifiers, references and object grain against source records before creating any census-year population assertion. Do not infer a census match from P585 year alone, use city/municipality population as settlement population, or create new graph links. Existing accepted graph components remain unchanged. The historical component uses the canonical `decision_status` allowlist from `research_rebuild/mass_linkage/coverage.py`; optional flags do not define acceptance. Existing small-settlement exceptions remain untouched.

Reproduce with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/settlements-venv/bin/python /workspace/settlements-work/continuation_20261003/audit_99_20261003/wikidata_history_large/build_large_p1082_diagnostic.py`. Full source, batch, and output hashes are in `summary.json`.
