# Graph29 point-route inventory correction, v2

This corrects the component analysis in `/tmp/point_route_inventory_graph29/REPORT.md`. The v1 graph filter used `decision_status LIKE 'accepted%'`, which excluded most accepted edge statuses ending in `_accepted`. Its 1,114-edge/958-component graph and its claims of zero residual/component overlap and only 952/958 point/component intersections are withdrawn. Route counts were not affected; the v1 and v2 route CSVs have identical SHA-256 `111e2776528d5b3be8c947161d316e2dcd0c38028574b867386b7cd5e2a01dae`.

## Corrected graph intersections

V2 uses the exact edge allowlist from `measure_actual_observed_year_path_coverage_v2_20261005.py`: `checked_rule_accepted`, `checked_rule_accepted_redundant_graph_connectivity_effect`, `accepted_rule_family_after_independent_sample_review`, `case_specific_independent_review_accepted`, `case_review_accepted`, `independent_case_review_accepted`, and `accepted_case_specific`. Accepted point uses are filtered using that script's exact four statuses: `reviewed_rule_accepted`, `frozen_r5b_reviewed_baseline_preserved`, `reviewed_extension_rule_accepted`, `reviewed_case_accepted`.

The selected graph has 465,800 unique source IDs; all allowlisted edge endpoints were found. There are 348,670 accepted same_place edges, 143,263 nontrivial connected components, and 143,263 components passing the actual-year path rule (at least two distinct selected census years, no duplicate year in a component).

| Year | Physical residual rows / population | Residual rows in accepted multi-year components / population | Accepted point rows in accepted multi-year components / population |
|---|---:|---:|---:|
| 2002 | 17,411 / 4,018,209 | 714 / 199,645 | 139,454 / 126,165,015 |
| 2010 | 16,482 / 2,126,316 | 896 / 178,139 | 135,075 / 123,734,031 |

The residual/component intersection by route status is also in `receipt.json`: 2002 includes 6 shared-point-collision rows, 3 unique exact-code rows, 684 provider-unspecified route rows, and 21 no-route/unknown rows; 2010 includes 20 shared-point-collision rows, 842 provider-unspecified route rows, and 34 no-route/unknown rows. The apparent presence of a source point candidate in an accepted component remains route evidence, not coordinate acceptance or proof of a unique route association.

The exact selected/residual population and all non-graph route strata are unchanged from v1. The candidate collision holds and route-availability ceiling remain as previously reported; neither is an expected gain.

## Reproduction and hashes

Run `python /tmp/point_route_inventory_graph29_v2/point_route_inventory_graph29_v2.py`. The script writes the refreshed route CSV and receipt beside itself. The receipt pins the five unchanged data inputs, Graph29 config and application receipt, and both status allowlists. All files are under this separate `_v2` path; the original v1 artifacts were not overwritten. No project files were changed.
