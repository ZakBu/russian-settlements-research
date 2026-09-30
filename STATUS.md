# Research status at 2026-09-30

## Preserved baseline

The private baseline snapshot contains 7,054 raw and interim files, legacy and forensic DuckDB databases, and original audit outputs. These are retained as comparison inputs. The historic crosswalk and coordinates remain hypotheses, not a validated national identity or spatial database. Files in each asset are verified against SHA-256 manifests.

## R6 source-corrected Karelia pilot

R6 uses the actual Rosstat Volume 1 Table 5 PDF for the 2010 urban rows. Older R4b/R5 linkage releases that mislabeled this PDF as the separate Volume 11 Table 1.4 source are superseded and should not be cited as source-correct releases. Volume 11 Table 1.4 is retained as separate comparison evidence. A row-level reconciliation checks prior case citations against the correct publication.

The 2010 Karelia selected slice contains 800 source rows and 643,548 people: 24 urban Table 5 rows and 776 official rural-volume rows, including 109 zeros. It reconciles to the official regional control. The corrected DOCX parser preserves the full row evidence for two names previously damaged by smart-tag extraction. The original download had a local TLS certificate-chain failure; its bytes, SHA-256, and independent content controls are preserved, but transport verification remains open.

The pilot has 24 case-reviewed urban and urban-type identity chains and 72 observation-level point admissions. Earlier-year coordinate uses are explicitly `inferred_continuity`, not direct historical measurements. Population coverage for these reviewed chains is 75.0254% (537,395/716,284) in 2002, 78.0388% (502,217/643,548) in 2010, and 79.4716% (423,680/533,121) in 2021. These percentages apply only to the selected Karelia snapshots; they do not imply matching precision or national accuracy. The 2002 selected slice remains 3 people above its regional control, unassigned.

The distribution includes a self-contained DuckDB copy of all 26 Parquet tables and one analyst-facing view. Its sidecar records table schemas, row counts, and typed-content hashes; a copied database was reopened from a separate directory and queried without access to the original Parquet paths. The Parquet outputs remain authoritative. The builder-created `linkage_review.duckdb` uses local Parquet-backed views and should not be moved independently.

## National audit findings and remaining work

The national database has not been fully rebuilt or independently validated. The 99.9% population-linked goal remains unproven. Candidate names, codes, population similarity, and the presence of coordinates do not independently prove place identity or coordinate applicability.

### Reviewed national identity bridge R4 (2026-09-30)

R4 is a metadata-only correction to the deterministic R3 bridge release. Its selected endpoint provenance now records missing Volume 11 `source_locator` values as typed JSON nulls with an explicit reason and keeps the actual page/line native ID and PDF hash resolvable. All scientific outputs, populations, coordinate claims, and coverage values are unchanged from R3. An independent review verified the pinned source/output hashes, all 965 candidate-to-endpoint bindings, all 965 exact Table 5 settlement-grain bindings, no same-year collisions in connected components, and deduplicated coverage.

The combined identity graph has 1,003 unique temporal edges. R4 added 952 new 2002–2010 pairs and recorded 13 eligible pairs already represented in the parent graph without double-counting them. Identity-linked selected population is 76,546,921/145,155,005 (52.7346%) in 2002; 76,695,785/142,172,038 (53.9458%) in 2010; and 4,146,187/147,182,123 (2.8170%) in 2021. These are identity-linked population shares, not spatial coverage. Coordinate claims are unchanged from R2; this release adds none.

The 965-rule subset is not a probability sample, and the 24-case review validates source-binding implementation rather than estimating national precision. Footnote, competitor, federal-city and other exceptional rows remain held. Table 5 records each matched line as a settlement row with atomic-settlement scope; its broader hierarchy label remains `subject_settlement_or_subject_aggregate`, and 21 rows have layout-only parent context. Those limitations are retained in the review record. See the R4 asset manifest and independent review linked from README.

### Reviewed national checkpoint (2026-09-30)

Source-selection R1 is a versioned population-grain repair. For 2002, it replaces the Moscow-plus-subordinate-settlements aggregate (10,382,754) with five disjoint component rows whose population and sex totals reconcile exactly to that parent; the city-only row is 10,126,424. The selected snapshot adds four rows and preserves the national dataset sum of 145,155,005. For 2010, it replaces the Karelia legacy slice with 800 official-source observations totaling 643,548, a +4,784 change and one additional row. For 2021, selected IDs and values remain unchanged. Independent review and clean reproduction are included in the checkpoint assets.

Reviewed-admissions R2 contains 51 accepted temporal same-place edges and 81 point claims. Among selected snapshot denominators, admitted coordinate population is 537,395/145,155,005 (0.3702%) for 2002, 502,217/142,172,038 (0.3532%) for 2010, and 9,354,610/147,182,123 (6.3558%) for 2021. Identity-linked population shares are 2.6615%, 0.3532%, and 2.8170%; link share and coordinate share are separate measures. All historical point applications are marked `inferred_continuity`; provider-coordinate measurement date is unknown. Four direct Karelia points have captured OSM geometry responses queried as of 2021-10-01, with raw response hashes and point-in-polygon checks. OSM is not a census boundary, and these admissions do not validate a national matching rule.

The 2002 Moscow row-grain problem is handled in the selected R1 snapshot, but the census-specific scope remains distinct from modern administrative boundaries and no temporal identity follows automatically from that migration.

The 2010 NW workbook labels its population column `Всего`, but explicitly warns that values are confidentiality-protected. Direct candidate-key comparisons to final Rosstat Table 5 show many differences; the column remains secondary evidence only. Table 5 is non-exhaustive and has aggregate rows, and St Petersburg data have mixed municipal/locality grain; full-sheet residuals are not allocated to places.

Remaining gates include resolving high-population source-scope conflicts, independently reviewing national identity and coordinate rules, checking historical admin changes and same-name competitors, and reporting population-weighted and row-weighted coverage separately. No map or dashboard should present candidate or unresolved links as certified points.

## Use conditions

The repository stays private. Source rights vary; no blanket license or public redistribution permission is asserted. The national baseline is preserved for comparison, not endorsed as an analytical release.
