# Working settlements stage71 — 2026-10-09

Actual working coverage: **99.554610% /99.450848% /99.696357%** for2002/2010/2021 against fixed common-territory controls145166731/142856536/144699673. Eligible ordinary native census records with raw OR approved-primary population >1000 outside the admitted working spatial/available-year route: **0**. This includes explicitly typed lifecycle/publication-scope routes; it does not assert three independently published own counts for every locality.

- `ordinary_full3_with_primary_population_sources.csv.gz`:142570 ordinary place rows,135 columns, own source IDs/counts/points/native codes for all three censuses.
- `primary_credited_source_year_full.parquet`:431463 admitted source-year observations, raw and effective populations, imported native codes, separate point provenance, ordinary/available-year/event/joint scope flags. This companion is necessary for inclusions and unavailable historical individual counts.
- Full native observations465928, active own-point claims446739, final graph components, source-ID roster, separately typed federal-territory observations and scope overlays.
- Receipts and SHA256 manifest allow exact byte verification. Federal territorial masses are15043973/16383067/18612023 and are not credited again as ordinary children.

Remaining to national controls:646558/784500/439370 people. Source-count gaps are not allocated. Historical individual counts for Igumnovo2002 and Shatalovo-12002/2010 stay unknown. Priuralsky2002 uses its own former-locality representative point and a secondary/cited2004 Magnitogorsk inclusion route; the primary act portal returned503. Modern representative points are not asserted to be census-day measurements; boundary comparability is separate. Complete reporting-unit partitions have coarse joint associations, not invented exact old-part centres or one-to-one identity.

Census `oktmo` and provider `oktmo_dadata` are separate code axes. Empty historical codes remain unknown. Codes alone are not a reconstructed complete legal transformation history. Original populations/names/quality are preserved; approved2010 exact-source replacements remain separate overlays. No smoothing, residual allocation or artificial zero histories.

Recipe: `research_rebuild/evidence/over1000_root_20261009/apply_batch16.py` with optional final export hook `export_final_state_v2.py`; schema error fix changes only mixed boolean/string flag serialization. Source evidence, rejected claims and decision diary are committed on `research/mass-linkage-2026-10-02`. The preceding stage68 release stays immutable.

## Own-point completion

185 own representative point uses are now added for already-admitted historical native observations. Every genuinely whole-NP additive record with raw OR approved-primary population greater than1000 has an accepted active own point.38 explicitly classified part/admin/federal-territory source rows are preserved separately, not counted as whole-NP targets. This threshold check includes Crimea2021; absent2002/2010 Russian census coverage there is not a missing match. Ordinary point use does not create an unavailable historical population or a three-year identity chain.

The spatial-coordinate addition does not increase the mixed working population percentage because these records previously had accepted territorial/event representation. It removes the distinction between a parent/joint scope anchor and a whole-NP own representative point for the185 targets. Updated active points:446924. The ordinary142570-row three-census table remains unchanged.

newly_admitted_own_point_uses.csv preserves all source-point qualifiers.32 historic part rows do not receive artificial own-part centres;14 new East part proposals are copied only to a typed coarse-association layer. Vatutinki’s point refers to the large residential compound explicitly counted within the2002 published village record;2010 exact composition remains unknown. The sovkhoz im.1May point is a1985 map housing representative with approximate300m uncertainty. Five north candidate coordinates were replaced before admission by their qualified own-article references; this does not reject the identity or provider entity. Two Wikipedia URL origins are mapped to their own local captures with original URLs preserved.

Independent fixed12 targeted source checks, the additional LowerKamennomost map check, and cross-year duplicate-coordinate review are recorded in crosscheck_large_old_ownpoints_20261009. This is a bounded risk review, not a random national error-rate estimate. Source-count confidentiality limitations and boundary comparability remain separate.

Reproduce stage71 with apply_ownpoint_completion71.py and the six committed point packets; the full receipt pins the exact inputs. Stage70 remains immutable.
