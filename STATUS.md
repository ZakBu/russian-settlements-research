# Research status at 2026-09-30

## Preserved baseline

The private baseline snapshot contains 7,054 raw and interim files, legacy and forensic DuckDB databases, and original audit outputs. These are retained as comparison inputs. The historic crosswalk and coordinates remain hypotheses, not a validated national identity or spatial database. Files in each asset are verified against SHA-256 manifests.

## R6 source-corrected Karelia pilot

R6 uses the actual Rosstat Volume 1 Table 5 PDF for the 2010 urban rows. Older R4b/R5 linkage releases that mislabeled this PDF as the separate Volume 11 Table 1.4 source are superseded and should not be cited as source-correct releases. Volume 11 Table 1.4 is retained as separate comparison evidence. A row-level reconciliation checks prior case citations against the correct publication.

The 2010 Karelia selected slice contains 800 source rows and 643,548 people: 24 urban Table 5 rows and 776 official rural-volume rows, including 109 zeros. It reconciles to the official regional control. The corrected DOCX parser preserves the full row evidence for two names previously damaged by smart-tag extraction. The original download had a local TLS certificate-chain failure; its bytes, SHA-256, and independent content controls are preserved, but transport verification remains open.

The pilot has 24 case-reviewed urban and urban-type identity chains and 72 observation-level point admissions. Earlier-year coordinate uses are explicitly `inferred_continuity`, not direct historical measurements. Population coverage for these reviewed chains is 75.0254% (537,395/716,284) in 2002, 78.0388% (502,217/643,548) in 2010, and 79.4716% (423,680/533,121) in 2021. These percentages apply only to the selected Karelia snapshots; they do not imply matching precision or national accuracy. The 2002 selected slice remains 3 people above its regional control, unassigned.

The distribution includes a self-contained DuckDB copy of all 26 Parquet tables and one analyst-facing view. Its sidecar records table schemas, row counts, and typed-content hashes; a copied database was reopened from a separate directory and queried without access to the original Parquet paths. The Parquet outputs remain authoritative. The builder-created `linkage_review.duckdb` uses local Parquet-backed views and should not be moved independently.

## National audit findings and remaining work

The national database has not been rebuilt or independently validated. The 99.9% population-linked goal remains unproven. Candidate names, codes, population similarity, and the presence of coordinates do not independently prove place identity or coordinate applicability.

A national source-scope problem is already confirmed: official 2002 Table 4 row 2154 is an aggregate for Moscow and settlements subordinate to its administration (10,382,754); its nested row 2155 is the physical city of Moscow (10,126,424). The existing selected row used the aggregate value. This needs a new versioned selection and separate aggregate claim before the national layer can be treated as a settlement-level observation.

The 2010 NW workbook labels its population column `Всего`, but explicitly warns that values are confidentiality-protected. Direct candidate-key comparisons to final Rosstat Table 5 show many differences; the column remains secondary evidence only. Table 5 is non-exhaustive and has aggregate rows, and St Petersburg data have mixed municipal/locality grain; full-sheet residuals are not allocated to places.

Remaining gates include resolving high-population source-scope conflicts, independently reviewing national identity and coordinate rules, checking historical admin changes and same-name competitors, and reporting population-weighted and row-weighted coverage separately. No map or dashboard should present candidate or unresolved links as certified points.

## Use conditions

The repository stays private. Source rights vary; no blanket license or public redistribution permission is asserted. The national baseline is preserved for comparison, not endorsed as an analytical release.
