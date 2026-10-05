# Point-route mass-linkage audit (read-only)

## Snapshot and limits

The available quantified route inventory is the frozen older-year audit from 2026-10-03, not a Graph28-era re-extract. It is therefore a historical baseline, and I cannot honestly label its counts as current Graph28-selected/residual/point-ledger totals. The frozen inputs and hashes are recorded in `research_rebuild/evidence/audit_99_20261003/older_years/summary.json`; Graph28's current artifact says the working ledgers are on the data volume, while its qualifying residual export is scoped to path coverage and is not a point/provider ledger. Graph28 currently adds three 2002↔2010 edges and six GeoKLADR point uses only for those bridge endpoints.

## Measured route inventory (historical baseline)

| Year | Residual rows / people without accepted point | R5 legacy route available | Unavailable | Unknown (no R5 projection) | Existing unique accepted 2021 carrier | Exact historical point candidates |
|---|---:|---:|---:|---:|---:|---:|
| 2002 | 36,165 / 19,887,379 | 30,874 / 16,839,264 | 5,287 | 4 | 8 / 536,953 | 1,689 / 8,344,574 |
| 2010 | 72,676 / 23,683,753 | 68,443 / 22,383,645 | 1,253 | 2,980 | 5 / 471,642 | 1,444 / 2,866,202 |

R5 availability is an inventory route, not acceptance. The historic candidate gate was exact regional typed name joined to raw 2009 classifier/2011 GeoKLADR, additive source row, and no known unlocated competitor. Candidates are not accepted points. Source-native ID was present on every residual but repeated heavily (17,826 distinct among 36,165 in 2002; 21,707 among 72,676 in 2010); selected OKATO/OKTMO were null throughout. Thus native-ID uniqueness cannot be assumed as a broad discriminator. Candidate point collision holds dominate: among candidates, 1,945 2002/2010 rows (1,868 shared point + 77 also code-bridge hold) had 1,340 same-year distinct raw-object collision groups; 1,258 rows also had the unapproved 8-digit urban OKATO→11-digit GeoKLADR width bridge. Possible unlocated competitors: 2,871 / 10,891; these are uncertainty flags, not proved competing settlements. Two rows per year had accepted-final legacy-coordinate conflict holds. No broad automatic acceptance rule is supported by route existence alone.

Provider-specific route totals, the current Graph28 point-ledger accepted/held partition, and current exact identifier/typed-name uniqueness and coordinate-validity counts are not present in this frozen summary. A correct current breakdown requires replay against the current selected observation, accepted point-use and candidate/hold ledgers; old totals must not be relabeled as current. The key provider in this historical candidate cohort is GeoKLADR (2011-06-20); the R5 rollup does not identify provider per row in its summary.

## Defensible rule / pilot

Use routes only to nominate candidates. For a promotion pilot, take the exact historical named-point candidate cohort and partition before review by year, type (urban / PGT / rural), route/provider, uniqueness (typed key and raw identifier), coordinate validity/range, shared-coordinate collision, unlocated competitor, existing accepted/held point, and current Graph28 membership. Admit only strata where an independent replay proves exact source row + exact source locator/hash + exact typed name and region, unique raw point object, valid WGS84 coordinate, and no unresolved collision/competitor; retain city code-width bridging as its own separately reviewed stratum. Existing sources/scripts are `research_rebuild/evidence/audit_99_20261003/older_years/historical_candidate_gate.py` and the narrower `research_rebuild/mass_linkage/stage_historical_city_points.py`; neither is a ready broad apply rule. The closest bulk point staging workflow is `apply_coordinate_extensions.py`, but it consumes reviewed extensions, not naked route availability.

Smallest useful reproducible pilot: rerun the historic gate on Graph28's exact selected/residual/accepted-point snapshot; freeze disjoint candidate strata; independently double-review a stratified random sample from each provider × year × settlement-type × collision/uniqueness band, including holds and route-unavailable controls. A simple exact-name-only sample is inadequate. Apply only a separately frozen zero-collision, exact-typed-key, valid-coordinate stratum after review, then report admitted row/population counts plus false-match rate and held remainder by stratum. Keep all route-backed-but-unreviewed points held.

## References

- `research_rebuild/evidence/audit_99_20261003/older_years/summary.json` and `report.md` (historic baseline and explicit gates)
- `research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/graph28_three_bounded_code_bridges_20261005/README.md` (Graph28 scope)
