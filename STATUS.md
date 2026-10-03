# Research status

## User decisions after the audit — 2026-10-03, 23:49 MSK

[Scope and working-series decisions](docs/FEDERAL_CITIES_AND_WORKING_SERIES_DECISIONS_20261003.md)
allow federal-territory reference points in the primary spatial measure, with
exclusive parent-or-child counting and separate atomic-NP coverage. Dated
Wikidata secondary observations may be displayed before independent primary
verification, with quality flags and no replacement of exact census values.
These decisions alone add no accepted points/edges or validated coverage.
The frozen scientific checkpoint and prior audit below remain unchanged.

## Rule audit and revised priority, 2026-10-03 evening MSK

[The audited 99% plan](docs/AUDIT_AND_PLAN_99_20261003.md) keeps the scientific
checkpoint below unchanged. The user prioritizes reliable interyear series and
places >=2000 people, then the remaining population needed for99%. That threshold
covers81.984502%/83.173177%/85.291474% of the full census controls, not95%.
A Wikidata rule-extension candidate pool has12803rows/3320225people after
preserving known city holds. Historical8/11digit urban-code bridges and1138
candidate2021continuations of accepted older pairs require scoped review.
No new coordinate/identity admissions are claimed by this audit. Federal-territory
representation remains a separately labeled spatial metric. Cached dated Wikidata
population claims are being extracted with full statement and source provenance.

## Local working checkpoint, 2026-10-03

The current local checkpoint contains465800 selected census records,177707 accepted
identity edges,44758 full census chains and332005 accepted census point uses.
1400 independently reviewed2010 publication replacements are applied; the
known2010 sum is142363024,493512 below the primary national control. The original
published R2/R5b snapshots below remain preserved and have not been republished.

Accepted point coverage weighted by recorded population and divided by verified
national controls is83.081300%/71.607647%/81.685925% for2002/2010/2021. The99.9%
target remains unmet. Coordinate availability, identity, full chains, source-count
quality and comparability are separate. The final working long table has500320
observations, including516 official2022–2024 observations and34004 literal
Wikipedia assertions that have no accepted historical coordinates.

See [consolidated result](docs/CONSOLIDATED_LOOP_RESULT_20261003.md),
[active run](docs/ACTIVE_RESEARCH_RUN.md) and [decision diary](docs/DECISION_DIARY.md).
Large outputs are under `/workspace/settlements-delivery/continuation-consolidated-20261003`.
The actual execution manifest and an independently checked metadata-correction
manifest are distinct; the latter claims no re-execution. The federal aggregate
grain guard caps current-source point coverage below99.9% in every year.
Legacy optional status/nested-ID limitations are disclosed in the final review.
GitHub is public and readable; branch pushes last returned403, so new work is
recorded locally and supplied as a Git bundle. The following2026-09-30 sections
describe preserved published states and their then-current limitations.

## Latest national state: reviewed R5b over the current R2 source snapshot

R5b is an independently reviewed Yearbook 4.9 identity bridge over the selected R1 endpoints. It contains 1,162 graph edges: 159 new 2010–2021 edges and four supporting decisions for pairs already connected in R4. Its coordinates and publication bindings are byte-identical to R4; it adds no point claims. Nine Yearbook exceptions remain held. The 24-case check validates the rule family and does not estimate national matching precision.

Regional source-selection R2 is the current 2010 population snapshot and supersedes R1 for current endpoint selection. It selects 152,314 rows and 142,202,712 people for 2010, compared with 152,313 rows and 142,172,038 people in R1. Its endpoint projection leaves 1,108 identity edges active and holds 54 pre-existing edges attached to displaced 2010 endpoints. An independent review accepts 50 replacement publication bindings for those 54 edges, making them eligible for migration; that migration has not been integrated into a published graph. Do not count those edges as restored or active.

The archived R5b graph remains a verified R1-based checkpoint. Its 2010/2021 bridge is not represented as the current R2 graph until the endpoint migration is integrated and independently checked. Experimental point candidates, including the 8-point component, remain quarantined and are not coordinate admissions. The 99.9% population-linked goal remains unproven.

The private release `national-reviewed-checkpoint-r5b-r2-selection-2026-09-30` carries R5b evidence, the full R2 selection/projection output, and an experimental current research code/docs snapshot. See the [release asset manifest](research_rebuild/evidence/releases/national_reviewed_checkpoint_r5b_r2_20260930/asset_manifest.json) and [snapshot inventory](research_rebuild/evidence/releases/research_code_docs_snapshot_20260930/source_snapshot_manifest.json). The snapshot excludes raw data, evidence, generated outputs, and caches while listing each omitted file with its size and hash; prior baseline bundles are referenced instead of duplicated.

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
