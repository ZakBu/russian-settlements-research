# Whole-application review v1

**Verdict: approve 45,465 staged pairs as eligible for root-owned promotion** under the reviewed ordinary rural NP same-place rule. Keep 1,950 records held and 64 exact pairs already in the accepted graph as corroboration only. This review does not edit or promote the staged application.

## Full-frame audit

The pinned application contains 47,479 candidate rows. Application rows align one-to-one and in order with the frozen candidate frame; all candidates satisfy the v1 rule predicate. The staged set consists of 45,465 new pending edges, 64 existing exact-pair corroborations, and 1,950 holds. Every new staged pair maps back to an exact candidate endpoint pair; all endpoint projections are active selected records.

I replayed the 45,529 eligible-or-corroborating pairs against the unchanged 128,569-edge baseline with the year-constrained graph. It reproduced 45,465 component merges and 64 already-connected exact pairs, with zero same-year collisions. All 243 legacy identity-conflict flags are held; there are no legacy same-year-collision flags in this candidate frame. The application has zero code-keyed event matches. Baseline edge values are identical in the staged prefix; five staging-only audit columns are null on baseline rows. New edges do not change population quality, coordinate admission or boundary comparability.

## Exact source-row checks and retained holds

The whole application reports 45,756 exact raw label/population/region row checks. Its handled source coverage includes the source-specific XLS profiles, explicit handling for 010/011/013, constant-region source profiles, Arkhangelsk archived HTML rows and Karelia DOCX rows. No district carry is used. The source population rule requires exact numeric same-publication-row agreement; there is no ±10 allowance. Source dashes remain raw, and the builder provides no global dash waiver.

The 1,950 held cases break down as follows, with 16 source and identity holds overlapping: 1,458 literal label mismatches; 171 region-context mismatches; 73 Karelia physical XML-cell mismatches; 20 Kaliningrad/Murmansk source families not yet applied; one row outside its source profile; and 243 legacy identity-conflict flags. The held families and mismatches remain held. The Karelia parser uses physical XML table/row/cell values; its 73 layout mismatches are not resolved by this review. The earlier Karelia `source_name_raw` metadata discrepancy remains separate from literal raw-row evidence.

## Bounded independent raw reread

I reopened 20 deterministic hash-ranked proposed-positive source rows, using seed `application-review-2026-10-03`; this sample is distinct from the 120-row rule-review sample. All 20 had exact typed labels, exact same-row populations and matching source-region context. I also reopened one representative per source-file × raw-check hold class. The 21 representatives from applied families matched the builder’s recorded literal row extraction. Two representatives belong to the not-yet-applied Kaliningrad XLSX and Murmansk DOC families; the application keeps those source groups held. This bounded reread corroborates the application without replacing its full-frame source-row checks. Details and locators are in `raw_row_reread_sample.csv`; the rerunnable bounded checker is `bounded_application_reread.py`.

## Pinned inputs and promotion

The artifact hashes and frozen candidate, selected-source, prior accepted-graph, and rule-review pins are in `review.json`; the application receipt pins its input/output hashes and builder. Promotion should use only the 45,465 pending rows from this exact staged output, leave the 64 corroborations and 1,950 holds out of new additions, and preserve the accepted baseline. Keep identity edges separate from population, coordinate and boundary admissions. Root owns the promotion and its receipt.
