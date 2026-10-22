# Wikidata rule and source audit: 2021 unpointed physical settlements

## Finding

The cached evidence supports a **candidate pool**, not a claim that 99% of the population is correctly geocoded. In frozen F, the defined denominator is 24,948 additive 2021 physical settlement targets with no accepted point use, carrying population 7,795,201. The wide Wikidata cache contains 16,931 of those source IDs. Exact P764, name, P31/P279, point, and existing region checks reduce the potential pool substantially; none of the new rural/PGT candidates has been admitted or independently validated under the city rule.

The already-reviewed city rule is sound within its stated scope. Independent review accepted C for physical city rows with row-specific holds: 903 of 910 survived known holds. It raw-checked 1,175 P625/P764/P31 claim locators (all values matched), traversed the pinned P279 graph, and recomputed ADM1 membership for the sample. That evidence supports the city rule only. The city rule does not establish a universal rural/PGT rule or a 99% population-weighted precision estimate.

Only four of the current unpointed denominator overlap the existing C-city candidate family: Межгорье and Усть-Кут remain point-choice holds; Покачи and Феодосия remain multiple-P625 holds. Two (Межгорье, Усть-Кут; population 52,615) overlap the 12,805 pre-review core and are tagged as pre-existing hard holds. Pokачи and Феодосия are already outside that core because they have multiple distinct P625 coordinates. Quarantining the two overlaps leaves 12,803 / 3,320,225 in the same candidate-only ceiling; this is not an admission count. These holds cannot be bypassed by applying a broader rule.

## Cached profile

Counts below are by unique target row, with population summed once per target. “Inside ADM1” uses the existing 2017 simplified polygons and `region_screen_v1` region-to-geometry mapping. This is regional consistency context, not a finding that the QID is the correct locality or that the point is its exact centre.

| Screen | Rows | Population |
|---|---:|---:|
| Current unpointed physical settlement denominator | 24,948 | 7,795,201 |
| Exact truthy P764 code candidate | 16,228 | 4,247,043 |
| Exact P764 plus at least one valid P625 | 14,662 | 4,216,630 |
| Exact Russian source label plus valid P625 (also exact P764) | 12,974 | 3,807,785 |
| Same, with physical-settlement P31/P279 ancestry | 12,972 | 3,807,595 |
| Same, one distinct valid P625 and unique, noncompeting QID | 12,846 | 3,403,847 |
| Same, and that single P625 falls inside expected ADM1 | 12,805 | 3,372,840 |

The last row is a **pre-review pilot ceiling**, not an eligible/admitted count. It is about 43% of the unpointed population. The all-types profile also finds 126 targets / 403,748 population with multiple distinct P625 points, which should remain unresolved point-choice holds. It finds 1,711 exact-code/name/point targets / 745,635 population with both physical and administrative P31/P279 lineages. This is a mixed-type review stratum: an administrative parent alone is wrong grain; a mixed entity must have a clear physical-settlement path and the census source itself must be a physical settlement. The reviewed city rule did not apply a blanket administrative-class veto where a physical path was proven.

Among the 12,805 pre-review rows, the selected source coordinate is available for 11,421. Wikidata P625 is over 1 km away for 2,193 of those, over 5 km for 1,776, and over 10 km for 1,426 (99th percentile 81.35 km; maximum 611.33 km). These flags call for a **systemic provider-grain diagnostic**, not 2,193 automatic dossiers or a blanket rejection. Use the cached DaData object level, name/type payload, FIAS level, code binding and duplicate/point fields to distinguish provider results describing a street, municipality, or aggregate from a credible independent settlement-place point. Compare these strata with the Wikidata-primary candidate, sample each stratum independently, and check whether the selected provider coordinate is demonstrably the wrong object grain. If a scoped dominance rule passes that review, bulk-stage the matching stratum; individual review is then reserved for genuinely competing physical-place points, identity/code contradictions, and transformation/event conflicts. The existing city rule already treats >5 km as review context, with row-specific exceptions, rather than a universal distance veto.

## Rule audit

- **Unnecessarily strict for a Wikidata-primary coordinate:** requiring a second coordinate endpoint, DaData FIAS binding, or a universal 1 km agreement before using the P625 attached to the identified QID. Coordinate provenance, QID identity, and provider/FiAS binding are separate claims. Distance can trigger review; it is not a universal rejection. Existing city review treats >5 km provider distance as a review flag and resolved all but two scoped conflicts with separate evidence.
- **Wrong administrative test in the older high-mass probe:** matching a P131/admin label only to the ADM1 name can reject valid settlements because P131 commonly names an immediate municipality or district. The full v2 probe improved this to compare municipality/district context, but its exact linked `source_region` check is copied through the source-row join and is not independent Wikidata region evidence. The already-reviewed city rule uses expected ADM1 point containment and does not require a literal admin-label match.
- **Still necessary:** exact native code and exact Russian name are candidate gates, not identity proof alone. P764 reference/source lineage is absent from the truthy export, so its independence from the selected source code cannot be asserted. Require one unambiguous QID/source binding, an explicit physical-settlement P31/P279 path, a valid single P625, correct source grain, and no competing identity. Keep admin-only types, aggregate source rows, code/name contradictions, unknown class paths, and multiple distinct coordinates on hold. A mixed physical/admin classification requires the row-specific physical path; do not auto-accept on the presence of any one physical type.
- **Point scope:** a Wikidata P625 is a Wikidata representative point. Admission should claim a point for the linked locality only; it does not establish a footprint, census-date measurement, unchanged boundary, or FIAS identifier binding.

## Proposed scoped pilot and 99% validation

Use the existing city rule semantics for a bounded 2021 physical-settlement pilot: exact source OKTMO to one exact truthy P764 QID; exact Russian target label; no competing source/QID binding; an explicit physical-settlement P31/P279 path; exactly one valid distinct truthy P625; source record at settlement grain; and P625 inside the expected ADM1 polygon. Do not require P131's literal label to equal the region, a second endpoint, a FIAS binding, or a fixed distance threshold. Treat P131 links and all distances as review context; hard-hold contradictions, aggregates, admin-only lineage, unresolved type paths, and multiple points. For mixed physical/admin P31, inspect the actual P31-to-class path rather than treating the mix as either an automatic pass or an automatic veto.

Before any admission, extend the rule to PGT/rural types with a probability sample reviewed independently of Wikidata. First classify provider-grain/mismatch strata from raw DaData fields, then test whether exact-code/name/physical-type/ADM1 Wikidata points reliably dominate street-, municipality-, or aggregate-grain provider points as one scoped family. Define success as “correct census locality and a usable representative point in its expected ADM1,” not exact monument/centroid position. Stratify by settlement type, region, P31 family (including mixed lineage), population band, source-code width, and provider grain; draw the main precision sample proportional to population and keep a held-out seed. Resolve sampled cases from the raw census row, raw claim locators, and a non-Wikidata locality source or documented map review. Audit known hard-hold classes separately. If a family meets the precision criterion, stage that family in bulk while retaining hard holds; reserve row dossiers for genuine physical-point competition, identity/code contradictions, and transformation/event conflicts. For a 99% **population-weighted** claim, calculate a design-based one-sided 95% lower confidence bound on weighted precision; do not substitute a row-weighted rate. As a screening reference, 299 independent random checks with zero errors only support a 99% one-sided 95% lower bound for an unweighted row-precision estimand. Any errors require rule revision and a fresh holdout.

The current application pipeline correctly preserves the distinction between candidates and admissions: the coordinate packet and `admit_coordinates.py` keep new points candidate-only, require an independent review hash before finalization, and report zero new coordinate admissions. The immediate next work is the rural/PGT pilot review and validated application artifact, not loosening the current staging gate.

## Provenance and reproduction

The profile is reproducible with:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/settlements-venv/bin/python \
  /workspace/settlements-work/continuation_20261003/audit_99_20261003/wikidata/profile_cached_wikidata.py
```

Inputs and SHA-256 values are pinned in `profile.json`. Key pins are frozen F selected observations `4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657`, accepted point uses `a2087db421629ea66fe8c32de05b0aa68a3fff3c6ff3c7deb1cbcd1f286f3ae8`, WIDE v5 point bindings `f59e2a1f26b7165ffccca2d118e04f8507f1c346b27ccf2e82d4c65879c33143`, raw Wikimedia OKTMO TSV `580e20042d6dfdcc6dd29d5d7fbde59593145b97abbb37e7760e89b567b36d36`, P31/P279 ancestry snapshot `2c7971afa183285909e068c2ba9ac3ac7f95df1c71b3ada716e867c103b0ebda`, and full 2,819-row GeoNames witness evidence CSV `f071c8fe53962b3fcc00a6d30aed9f667da29088851ffe4b491f1f1b395d1180`.

WIDE v5's frozen manifest says it uses an exact digit-string join from its R2-selected OKTMO values to the flat Wikimedia TSV `?oktmo` field (R2 input hash `524e706daa32a69cac9b3e67b3bb8f9113fe2d851f10cdf42e93ba4efa5d72bf`), then retains truthy P764/P31/P131/P17/P625 statements. The TSV, statistical module, truthy cache, and class metadata are all Wikidata-derived. The truthy export preserves source file, line, item/property/value and retrieval time but omits statement references and rank/qualifiers, so the original P764/P625 provenance cannot be independently evaluated from this cache. P131 labels in the TSV are a context field; the `source_region` copied into the joined WIDE source row is not a second Wikidata region observation.

The GeoNames full witness is a separate, stricter association probe: 1,047/2,819 rows pass its extra gates, but 289 overlap existing accepted-point targets; the remaining 758 rows / 929,241 population are still candidates only. Its 1 km P625↔GeoNames condition concerns cross-provider association and is not a prerequisite for using a verified Wikidata point. Cached RU Wikipedia sitelinks were not read as article evidence. WIDE TSV, module, truthy claims, and P31/P279 metadata all belong to one Wikidata evidence family and must count once.
