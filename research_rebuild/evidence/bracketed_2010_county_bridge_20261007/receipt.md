# 2010 bracketed county context bridge — application receipt

This is a candidate packet only. It does not change the accepted graph or the source `district_raw` field.

## Current totals

- 106,512 selected additive 2010 rows have null district; 102,508 carry a physical source row locator.
- 79,458 received two-sided county context from accepted 2010 anchors in the same source file, sheet, and region, each no more than 20 physical rows away. The anchors have distinct settlement names, are already accepted with a 2021 row, and agree on county; where 2002 county exists it agrees too.
- 1,024 rows passed the whole-row, unique-name/type/region/county, existing 2002–2021 component, no-event, and accepted-current-point screens.
- 678 are in `usable_contextual_link_candidates.csv`: their source workbooks are staged and source row order was checked against literal workbook rows in a deterministic audit sample of 20 targets (seed 20261007) plus the five largest by population. All 60 sampled rows from staged workbooks matched; all 15 sampled rows from the unavailable Kaliningrad workbook are held.
- 346 remain in `held_unstaged_source_candidates.csv`: 345 Kaliningrad rows and one Murmansk row. Their source workbook is not staged here, so their bracket sequence is not usable for this application packet.
- The 678 usable rows represent a potential 2010 covered-population increase of 122,773 under current selected ordinary-population accounting. This is a projection, not an accepted graph result.

## Interpretation and gates

County is inferred context only. The candidate relation is `same_place` from the 2010 source row to its already accepted 2021 endpoint; that endpoint already belongs to an accepted 2002–2021 component. The CSV preserves the accepted current point provenance and marks the 2010 point as retrospective continuity from that current point, not an independent historical measurement. If an accepted 2002 point exists, the packet requires it to agree with the current point within 5 km; its absence is allowed and is not counted as independent corroboration. QID and population fingerprints are not used for identity.

Rows on county boundaries, with missing anchors, gaps over 20 rows, duplicate or non-whole physical records, unresolved within-county name competition, event flags, missing current own-points, or conflicting available old/current points are held. The source-order audit is based on raw workbook rows, not a claim that the inferred district appeared in the 2010 extracted record.

## Application fields

Use `usable_contextual_link_candidates.csv` only. The proposed edge is in `target_2010_source_record_id`, `proposed_edge_to_source_record_id`, and `proposed_relation`. The county context and bracketing provenance are in `inferred_county_key`, `lower_anchor_source_locator`, `upper_anchor_source_locator`, the anchor IDs, and row gaps. Source workbook SHA-256 and exact 2010 row locator are in `target_2010_source_sha256` and `target_2010_source_locator`. The current-point transfer proposal is described by `2010_point_action`, `proposed_2010_point_source_record_id`, and the `proposed_2010_point_*` flags. Admission remains subject to the parent apply step.

## Reproducibility

Run `PYTHONDONTWRITEBYTECODE=1 python research_rebuild/evidence/bracketed_2010_county_bridge_20261007/build_bracketed_2010_county_bridge.py` from the repository root. `summary.json` records selected-data and input-delta SHA-256 values, output CSV hashes, counts, and the exact constraints. `sampled_bracket_source_checks.csv` records literal row text and workbook hashes for the audit sample.
