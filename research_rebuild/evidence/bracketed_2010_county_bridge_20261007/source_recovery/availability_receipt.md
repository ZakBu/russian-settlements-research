# Source availability recovery for the 346 held 2010 rows

The binaries are absent from `/workspace/settlements-raw` at the selected legacy paths, but they are present under `/workspace/settlements-work/sources/r2-missing/`. `existing_binary_inventory.json` hashes the three exact files there: the Kaliningrad workbook, Murmansk population DOC, and its grouping companion. Each physical byte count and SHA-256 exactly matches its source manifest. The full source-cell ledgers independently restore the exact row cells and complete physical sequence used below. No network download was needed; no accepted edge or point ledger was changed.

## Results

- **Kaliningrad: 345/345 mapped.** The full sheet 4 cell ledger has all 1,257 rows in 1-based order. All 345 target IDs map to the same source row and exact raw label as selected; each lower and upper anchor also maps to its selected source row and exact raw label. The manifest pins the official workbook to SHA-256 `7e17a4bdb54e3ee8ff014c4311396f84c01b7f3ed38d12f4f9c1f9e6b100705f` (306,344 bytes). Its official URL is recorded in `source_recovery.json`; an archived asset URL is also recorded. The existing independent review verdict is `accepted_for_primary_observation_migration_with_source_lineage_note`.
- **Murmansk: 1/1 mapped.** The complete table ledger has 226 rows in 1-based order. The held row `MURMANSK2010:POPSEX:T1:R119` maps to table row 119 and exact raw label `н.п. Вайда-Губа`; its lower and upper anchors map to rows 113 and 120. The source manifest pins the DOC to SHA-256 `d4bdb36d541ed3f90594ba95ee209fabafc5f02088758e46a143e1155f5fbc57` (384,000 bytes). The existing extraction comparison reports 223 complete matching rows, zero mismatches, with the regional-control row checked separately. The independent review passes the source-observation slice and zero-bin closure while holding cross-census identity.

For every one of the 346 entries, the build checked the selected source file hash against its manifest, target and anchor IDs against the full ledger, selected row numbers and source labels against ledger row numbers and raw labels, and strict lower < target < upper order. The mapping carries literal raw/cached cells (all six XLSX cells for Kaliningrad; all table fields for Murmansk), row locators, ledger/manifest paths and hashes.

## Files

- `held_source_recovery_mapping.csv`: row-level target plus its two bracket anchors and exact source cell payloads.
- `source_recovery.json`: workbook URLs/hashes, full ledger paths/hashes, manifest hashes, row counts, and mapping hash.
- `existing_binary_inventory.json`: exact physical workspace paths, byte counts, computed SHA-256 values, and matches to published-source manifest hashes.
- `build_source_recovery.py`: reproducible local join and checks.

Source binaries are available at `/workspace/settlements-work/sources/r2-missing/`; source-cell ledgers are under `/workspace/settlements-work/continuation_20261004/R4/exact_population_source_inventory/parser_runtime/{kaliningrad,murmansk}/`. No copies of these source assets or larger ledgers were made. This recovers source-cell and order availability only; it does not make a new identity decision or modify the previously applied 678-row packet.
