# Methodology: settlement identity and coordinate admission

Status: preliminary research implementation. It is designed to preserve every
source observation and to make every proposed and accepted relation replayable.
An output marked pending review is not released as a scientific spatial point.

## Unit and scope

The immutable input grain is one published census observation, identified by
`source_record_id` and its source file, sheet/partition, row, and source checksum.
Population remains attached to that observation. A place is a physical
settlement; an observation is not automatically proof of a place's identity in
another census. Every observation receives an internal provisional ID derived
from its source record key, never from the 2021 OKTMO or a current master row.

The three census years remain separate population slices. Each year is measured
against its published national control, while source coverage, candidate points,
reviewed point admissions, and cross-year identity are reported as different
quantities. Administrative totals and regional residuals are not apportioned to
settlements.

## Candidate identity links

The candidate builder normalizes case, whitespace, and `ё/е`, then requires an
exact normalized settlement name, settlement type, and region. A one-to-one key
becomes `unreviewed`; any multiple-record side becomes a conflict group. The
candidate builder never accepts a link and does not use fuzzy scores, row order,
population similarity, or present-day codes as historical identifiers. A
reviewed identity event must cite dated evidence for both records and address
administrative changes, split/merger branches, and any population-territory
change. Applying or revoking a relation is an appended ledger event; previous
events remain available.

Historical event rows from the existing audit output are retained intact and
marked as legacy claims until independently reviewed. They are not collapsed to
one successor and do not trigger coordinate inheritance.

## Coordinate claims and pilot rule

All coordinates found on an observation are retained as claims with their
original value, source, precision metadata, observation ID, and source locator.
The current pilot proposes only for 2021. Its rule requires all of the following:

1. The published observation is scoped to a settlement and has a valid WGS84
   point in a broad Russian geographic envelope.
2. The 2021 record has an accepted exact OKTMO-and-OKATO agreement to one
   Wikidata item, with exact name agreement, a Russian Wikipedia article, and
   Wikidata coordinates.
3. The source point and Wikidata point are within 500 metres, the Wikidata item
   is not reused by another 2021 row, and the source point is not shared with
   another 2021 row.
4. Each proposed decision keeps locators and URLs for the Tochno row, Wikidata
   item, and Russian Wikipedia article, plus the checksum when available.

DaData `qc_geo` is retained as a precision claim (the source documentation says
3 means settlement and 4 means city), not as proof that the point belongs to
the cited census observation. The 500 metre agreement test is a candidate
conflict screen, not a probability of correctness or a universal distance
limit. DaData and Wikidata may have shared upstream coordinate sources; their
agreement is not described as independent. Source IDs anchor the 2021
enumeration; current identifiers and coordinates are not projected backward to
2002 or 2010.

The rule writes `propose / pending_blind_validation` events. A separate review
batch omits predicted status and rule rationale. The prediction-key file is
stored separately and must not be shown to the blind reviewer. At least 100
random examples from each automated rule family, or all examples if fewer than
100 exist, must be independently reviewed before the rule is enabled. A
successful 100-row review is not a statistical demonstration of 99.9% accuracy;
confidence limits and affected population must be reported. Failed examples
pause that rule version and require a narrower replacement plus re-review.

Statuses are deliberately distinct:

- `direct`: a dated primary source directly identifies the observation or
  coordinate and its scope. A current map or present-day polygon does not date
  an undated point to the census year.
- `rule`: a reviewed, versioned combination of dated evidence and explicit
  constraints has been approved; validation scope is recorded.
- `inferred_continuity`: a point is associated with an earlier observation from
  a separately documented continuous place; it is not applied to the current
  pilot without a dated continuity source.
- `unresolved`: only a candidate, incomplete evidence, or no admissible point.
- `conflict`: incompatible identities, admin context, duplicate point, or
  competing source evidence.

## Provenance and audit limits

If `research_rebuild/ingestion/observations.parquet` and
`source_dispositions.parquet` are available, only observations referenced as
included by the disposition ledger enter the new run. Otherwise the build uses
`research_audit/output/audited_census_snapshots.parquet` with explicit status
`legacy_audit_comparison_fallback`; the result must not be represented as a
parser-certified production release. In either case, parser outputs alone do not
prove extraction completeness. Independent sheet/page-level reconciliation to
source publications is a separate acceptance requirement.

The current preliminary Karelia release is scoped to 2,443 rows selected by
the row-level disposition ledger, with a separate 2,481-row observation
registry retaining previous IDs and a `selected_observations_for_release`
mapping. The mapping is versioned; choosing a different publication adds a
new assertion and does not rewrite an existing observation. Source dispositions
remain available for rows that have not yet been admitted to the observation
registry.

Proposals do not contribute to admitted coverage. A case-specific decision
from a completed independent review is scoped only to that case and does not
validate an automated rule family. A review `apply` event may later be
superseded by a `revoke`; consumers query the latest event for the same target.
Identity components are derived per release from accepted `same_place` edges;
stable observation/place-node IDs do not change when membership changes.
Component lineage records overlap and requires an explicit alias/supersession
decision. Inclusion, incorporation, and succession are historical events, not
equivalence edges. Coordinate admissions are bound to their own observations
and claims. Historical inferred-continuity claims have separate temporal
applicability and depend on reviewed identity; revoking that identity removes
dependent claims from effective views on rebuild.

Population source selection is versioned independently from place identity and
coordinate admission. When official and secondary extracts disagree, retain
both source values and record the selected publication, locator and review
reason. Do not overwrite the source observation or average the values.
Aggregate scopes (such as a city plus subordinate settlements) are not the
population of the physical city.

In `karelia_pilot_release_r2`, ten case-specific city chains are accepted: six
blind-sample cases plus Kostomuksha and three out-of-sample major-city followups.
The six blind-sample verdicts do not validate the automated family because only
6 of 100 sampled cases have been reviewed. All ten present-day representative
points have class `rule`; the twenty 2002/2010 point uses have class
`inferred_continuity`. The source coordinate measurement date is unknown, and
the contemporary OSM geometry checks do not date a point to a census year.
Admitted population is 442,187 of 716,284 in 2002, 421,489 of 638,764 in 2010,
and 362,225 of 533,121 in 2021. These percentages describe this selected Karelia
snapshot only. The 2010 selected-source slice still has a -4,784 regional
residual; a separately extracted official Table 5 census view reconciles 800
named localities and is being prepared as a new population-selection release.

## Reproduction

From the project root:

```sh
python3 research_rebuild/linkage/build.py --build
python3 -m unittest discover -s research_rebuild/tests -p 'test_linkage*.py' -v
```

The resulting Parquet tables, review batch, decision key, metrics, and DuckDB
database are written only under `research_rebuild/output/`.

## R4 Karelia primary-source selection

`karelia_pilot_release_r4_primary2010_v2` replaces the R3 2010 value slice with
800 freshly extracted 2010 observations: 24 urban rows from Rosstat Volume 1,
Table 5 (502,217 people) and 776 rural rows from the official Karelia rural
settlements volume (141,331), totaling 643,548. The old release remains
unchanged. The new values are selected source records; that selection does not
assert 776 rural inter-publication identity matches. Ten reviewed urban chains
have explicit, case-specific bindings from the old Table 1.4 observation to its
matching direct Table 5 row. There is one selected observation per place-year.
The 2010 point on that newly selected row remains `inferred_continuity`, because
the contemporary point is not a dated 2010 coordinate.

The corrected rural extractor reads visible WordprocessingML cell text. An
earlier `python-docx` pass dropped smart-tagged `6 км` and `14 км` name prefixes
although its population controls still matched; these are distinct localities
with populations 4 and 584. R4 stores the earlier 776-row extraction under
versioned superseded IDs and uses the corrected extraction version for selected
values. This is why matching a total or row count alone is not a sufficient
parser check: source row locators, full row text, extraction version, and
name-level controls must also agree.

R4's selected set is checked by exact source-record ID equality against the
versioned selection assertions, in addition to 799/800/845 counts and the three
yearly population controls. The immutable registry contains all 2,481 Karelia
raw replay observations and both 2010 rural extraction versions; raw 2002/2010
alternatives stay in that registry and do not enter the selected additive
snapshot. The build checks exact source-ID set equality for the union of
baseline, v1, and v2 records and rejects duplicate IDs; registry row count is
not its completeness proof. The effective admitted-coordinate view is also required to join only
to selected observation IDs. Older decisions on unselected source observations
remain in the event ledger for provenance, but are excluded from this release's
coverage and database view.

The independent reviewer has applied ten urban cases only. R4 coverage is
10/799 places in 2002, 10/800 in 2010, and 10/845 in 2021; accepted population
is respectively 442,187/716,284, 421,489/643,548, and 362,225/533,121. Thus
coverage by population is 61.73%, 65.49%, and 67.94% of the selected snapshots.
There are ten 2021 `rule` representative points and twenty 2002/2010
`inferred_continuity` claims. The 2002 selected count exceeds the published
regional control by 3 people; this remains unassigned. The 2010 primary slice
reconciles exactly. Neither result validates the pending nationwide point rule.

Portable builds require `--data-root`, `--inputs-root`, and `--output-root`.
The runner verifies baseline and supplemental inputs against their manifests,
extracts the 2010 primary source into the output root, and fails if required
inputs or hashes are absent. For extracted Parquet it records both the binary
artifact hash and a stable typed-content hash: machine-specific DOCX paths are
normalized to the declared bundle path, and rows are sorted by source record ID.
Reproduction under a pinned runtime is checked separately by a clean staging
build and byte comparison of generated outputs.

## R6 source-citation correction

R4/R5 parser outputs and linkage releases are superseded as source-citation
releases. The Table 5 values were extracted from the full Rosstat Volume 1 PDF
(`data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf`,
SHA-256 `42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3`),
but R4b incorrectly labeled these rows as the separate Volume 11 Table 1.4
PDF. R5 corrects each extracted row's logical source locator and pins the actual
PDF by hash. Volume 11 Table 1.4 remains separate comparison evidence; its
same-census record bindings require explicit row-level reconciliation.

The 2010 selected slice contains 800 observations: 24 Table 5 urban rows with
502,217 people and 776 rural rows with 141,331, total 643,548. The R5 source
manifest is `research_rebuild/evidence/ingestion/source_manifest_karelia_r5_fresh.json`
(SHA-256 `0988f9092c385b7aaa506bd2da6724bb6fb65593c1843a98ee0479158f06104e`).
It records the actual Tom 1 input, the excluded-as-parser-input Volume 11
companion, DOCX extraction version and source/code lineage. The fresh receipt's
canonical typed content hash is
`551e4cef5653997045ef3710bc16f8fef1d8239f81f55a5819a521f91a5b250b`; the
reproduced Parquet artifact SHA-256 is
`adc48e2ef4db760bebb51b65cbccdd7e5f946ffd69dd8e474fb35be1fd4af6d3`.

R6 binds the 14 latest independent urban reviews to the corrected source-binding
revision (`32660feea35651dee2d553272c769c3d8fcf03f64c9d549e5a3d0ff239ab1910`)
and its exact Table 5 comparison CSV. Spatial response snapshots are inherited
from the prior immutable review manifest (`b57d83ea1aeb07217c8b1b4865e52324b9d8163a3dd146f74b6004c9ccab6e55`);
that prior manifest is used only for the geometry snapshot hashes, not for the
superseded Table 5 citation. The previous ten urban chains have a separate
publication-equivalence sidecar (`prior_10_city_table1_4_to_table5_reconciliation.csv`,
SHA-256 `b56f060ef3545fd5a676eba133c460f99599dc6e3e4417bd0bcfa02b95a44df8`).
It checks ten Volume 11 Table 1.4 rows against ten exact Volume 1 Table 5
rows. The selected entity-year uses one Table 5 observation; the other
publication is preserved as comparison evidence, with no population double
counting.

The source-corrected R6b build selects 799/800/845 observations for 2002/2010/2021.
All 24 individually reviewed city/urban-type-settlement chains cover 537,395,
502,217, and 423,680 people respectively. Those are 75.0254%, 78.0388%, and
79.4716% of the selected snapshot populations; using official regional totals,
the shares are 75.0257%, 78.0388%, and 79.4716%. The 2002 selected slice still
exceeds its cited regional total by 3 people, unassigned to any locality.
Historical coordinate uses are explicit continuity inferences; the current
representative points do not become coordinates dated to a census year.
