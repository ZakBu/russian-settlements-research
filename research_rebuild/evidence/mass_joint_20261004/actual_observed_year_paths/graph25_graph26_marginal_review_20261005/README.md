# Graph25/Graph26 marginal review — 2026-10-05

## What was admitted

Graph25 adds six case-reviewed `same_place` edges for Хорлово, Мамоны, and Струги Красные. The three triplets have one selected additive census row per year; the full-long collision check reports zero same-year collisions. Population values are unchanged. Boundary/population comparability remains unasserted. Strugi received one direct 2021 publisher-row point and one explicitly retrospective 2010 use of its already accepted 2002 GeoKLADR representative point.

Graph26 adds retrospective representative-point uses for Гай-Кодзор in 2002 and 2010, carried from the independently crosswalked 2021 RCSI locality row along the already accepted identity chain. Neither is a historical coordinate measurement; the displaced 2002 GeoKLADR point is not used. Population values and boundary comparability are unchanged.

The Graph25 result is retained outside Git under `/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/`. Its receipt pins the full output ledgers. The Graph26 point ledger and receipt are under `/tmp/graph26_gaikodzor_continuity_20261005/`; the receipt is copied here. Large ledgers remain outside Git. The Graph24 identity/point Parquet paths referenced by the existing manifest are currently absent: the `accepted_graph24_anapa_20261005` symlink resolves to a directory with coverage receipts and residual diagnostics only. Therefore the Graph24 comparison below is explicitly a semantic reconstruction from Graph25's pinned append receipt, not byte-level rereading of the original Graph24 files.

## Separate the two joint measures

The existing scope-aware measure combines reviewed territorial/event-aware layers with selected ordinary rows that have an accepted point and a path across at least two actually observed census years. It is **not** the strict full 2002→2010→2021 ordinary-settlement chain.

| Year | Point + path across ≥2 observed census years | Control share | Remaining to 99% | Strict full 2002→2010→2021 chain + accepted point | Strict control share |
|---|---:|---:|---:|---:|---:|
| 2002 | 141,798,936 | 97.680050% | 1,916,128 | 125,083,555 | 86.165442% |
| 2010 | 140,192,926 | 98.135465% | 1,235,045 | 122,370,619 | 85.659797% |
| 2021 | 145,939,198 | 99.155519% | 0 | 122,902,334 | 83.503575% |

The first column is Graph25; Graph26 does not change that measure. Against the prior Graph24 report, Graph25 adds 14,288 / 11,004 / 10,986 people to that measure. The strict calculation is separately recomputed from selected additive rows and current accepted ledgers. Compared with the semantically reconstructed Graph24 baseline, Graph25+26 add 17,205 / 22,422 / 15,857 people to the strict measure. Its remaining amounts to 99% are 18,631,509 / 19,057,352 / 22,807,968. These strict figures exclude separately handled territorial layers; see the scope-aware report for those decisions.

The identity-only full-chain axis (does not require a coordinate) is 125,246,716 / 122,486,638 / 123,008,987, or 86.277837% / 85.741011% / 83.576038% of national controls. It exceeds the point-plus-full-chain axis, as expected, because a few otherwise connected components still lack an accepted point on one of their selected year records.

The large gap between the two axes is real: two-date links, accepted territorial representations, and event-aware paths can contribute to the broad measure without constituting an ordinary three-census settlement chain. Do not report the broad percentages as full-chain coverage.

## Residual candidate with high population

The top reviewed residual shortcut, Светлый (Саратовская область), is held. The 2002 and 2010 observations (12,313 and 12,493) are already linked and have a point near 51.7426, 48.9580. The 2021 urban candidate (12,702; native OKTMO 63775000101) is about 225 km away. The same-name 2021 record near the historical point is a zero-population rural locality in another district. A name or type-transition rule cannot safely bridge these records. No population is added to coverage.

Detailed row dispositions: `/workspace/settlements-work/continuation_20261004/regions/top15_2010_residual_graph24_cached_evidence_audit_v1/top15_dispositions.csv`.

An independent read-only check of existing annual-source artifacts found no exact-name match for the top-20 2010 residual cohort in either the staged annual module series or the accepted official yearbook table. That yearbook has 516 city assertions for 2022–2024, rounded to thousands, but does not cover this high-residual cohort. The surfaced Wikidata residual-history packet has 12 claims for six localities, only for census years 2002/2010; claims remain secondary display only. Thus current annual artifacts do not close this residual without new source work.

## Reproducibility and critique

- `measure_graph26_strict_three_year_coverage_20261005.py` validates active edge/point statuses, endpoints, WGS84 ranges, and same-year collisions; it measures the exact strict axis and reconstructs Graph24 by removing the six pinned Graph25 edge IDs and two Strugi point-use IDs from Graph25.
- `apply_graph26_gaikodzor_continuity_20261005.py` validates source row, RCSI hash/locator, current identity path, and accepted 2021 carrier point before adding only two point uses.
- `strict_three_year_coverage.json` contains input SHA-256 pins and year-by-year results. `graph26_application_receipt.json` pins the application outputs.
- The audit found and corrected a brittle source-label assertion in the Graph26 application script. It compared the expected string literally even though the accepted point ledger had an equivalent, pinned label without the word “row.” Coordinates, origin hash, locator, and code were verified before applying the fix.
- The new cases improve coverage but do not close the 2002/2010 residual. No remaining high-mass candidate reviewed in this batch supports an automatic identity edge. Next work should continue from residual rows ranked by population × plausible rule applicability, not broaden the acceptance threshold.
