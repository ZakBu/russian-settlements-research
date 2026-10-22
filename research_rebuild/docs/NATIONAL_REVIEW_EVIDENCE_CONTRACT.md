# National review evidence contract

This contract keeps four different questions independent. A reviewer may accept a place identity while rejecting or leaving unresolved its population scope, mapped object, or historical coordinate use. A positive result in one field never fills another field automatically.

Each review outcome is tied to a frozen case ID, target census observation IDs, candidate source IDs, and the exact input-manifest version. Reviewers work from the blind batch and source evidence. Do not reveal or use a prediction key while deciding. The outcome stores separate evidence references and explicit limitations for each dimension.

## Decisions recorded independently

`place_identity` records whether two dated source observations refer to the same physical settlement, are distinct, have a parent/subordinate relation, or reflect an incorporation, split, or merge. “Same name,” “same region,” code continuity, and a map match alone are candidate evidence. Cite the dated source rows and record competing same-name places, type changes, and administrative relationships.

`population_scope` describes what the number counts: one physical locality, city proper, city plus subordinate settlements, a municipal or district aggregate, a federal subject, a federal district, or an unknown/conflicting scope. Preserve the published parent value and its children. A parent total can be source-internally additive without being the population of the named city. Population selection is a separate versioned source-selection assertion.

`point_object` describes the geographic object behind a coordinate or geometry: the named locality, an administrative unit, a federal city/region aggregate, a garden partnership or other named feature, a geocoder fallback, or an unresolved object. Record the original coordinate, provider response or geometry locator, provider object ID/type, address hierarchy, codes, candidate competitors, and any known query-to-response lineage. Provider quality scores and a point inside a plausible radius are screening evidence, not proof that the point belongs to the census row.

`coordinate_temporal_continuity` states when the coordinate or geometry is observed and which census years it may represent. `direct_observation_record_link` means evidence ties the specific point to the specific census observation; the point or geometry's measurement date may still be unknown. `direct_same_observation_date` is stronger and requires an observed date that matches the census observation. A contemporary OSM point/polygon can support current representative-point evidence; by itself it does not date the coordinate to 2021. Using a contemporary reference point for 2002 or 2010 is `inferred_continuity`, with the time gap and continuity evidence recorded. Do not interpolate across years or inherit coordinates solely because place identity was accepted.

## Evidence references

Every decision cites immutable evidence IDs and precise locators. For files, record the source path, SHA-256, sheet/page/row or statement locator, extraction version, and raw observation ID. For web evidence, retain the exact URL, retrieval date, archived response or content hash where available, and the relevant page/feature/statement locator. Mark evidence lineage as direct, transcribed, derived from an earlier linkage, or unknown. Wikidata population statements whose census-row link was produced by the existing matching pipeline are discovery evidence; they cannot independently validate that same match. Group sources that share an upstream publication so apparent agreement is not misreported as independent corroboration.

Contradictory evidence is retained with its source and scope. Reviewers state which evidence supports and contradicts each decision and why. Unknown, missing, or unverified lineage stays explicit; it is never silently promoted to independent evidence.

## Release rules

The review file is evidence, not a release table. A separate versioned source-selection record chooses at most one additive population observation per physical place and census year, while keeping alternative publications addressable. Same-place edges, inclusion relationships, splits, merges, and publication equivalence are different relations. Only same-place edges contribute to the place identity graph.

Coordinate admission is a separate decision. It requires a named point object tied to the specific observation or an explicitly stated temporal-continuity claim, with source lineage and competitors checked. The release build must join coordinate claims by their own admitted IDs; it must not infer admission from identity acceptance. Federal-city aggregates and other aggregate objects cannot be admitted as settlement points.

The machine-readable contract is [`national_review_outcome.schema.json`](national_review_outcome.schema.json). `unresolved` and `insufficient_evidence` are valid scientific outcomes; they must not be converted to an acceptance rate target.
