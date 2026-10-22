# Working settlements stage70 — 2026-10-09

Actual working coverage: **99.554610% /99.450848% /99.696357%** for2002/2010/2021 against fixed common-territory controls145166731/142856536/144699673. Eligible ordinary native census records with raw OR approved-primary population >1000 outside the admitted working spatial/available-year route: **0**. This includes explicitly typed lifecycle/publication-scope routes; it does not assert three independently published own counts for every locality.

- `ordinary_full3_with_primary_population_sources.csv.gz`:142570 ordinary place rows,135 columns, own source IDs/counts/points/native codes for all three censuses.
- `primary_credited_source_year_full.parquet`:431463 admitted source-year observations, raw and effective populations, imported native codes, separate point provenance, ordinary/available-year/event/joint scope flags. This companion is necessary for inclusions and unavailable historical individual counts.
- Full native observations465928, active own-point claims446739, final graph components, source-ID roster, separately typed federal-territory observations and scope overlays.
- Receipts and SHA256 manifest allow exact byte verification. Federal territorial masses are15043973/16383067/18612023 and are not credited again as ordinary children.

Remaining to national controls:646558/784500/439370 people. Source-count gaps are not allocated. Historical individual counts for Igumnovo2002 and Shatalovo-12002/2010 stay unknown. Priuralsky2002 uses its own former-locality representative point and a secondary/cited2004 Magnitogorsk inclusion route; the primary act portal returned503. Modern representative points are not asserted to be census-day measurements; boundary comparability is separate. Complete reporting-unit partitions have coarse joint associations, not invented exact old-part centres or one-to-one identity.

Census `oktmo` and provider `oktmo_dadata` are separate code axes. Empty historical codes remain unknown. Codes alone are not a reconstructed complete legal transformation history. Original populations/names/quality are preserved; approved2010 exact-source replacements remain separate overlays. No smoothing, residual allocation or artificial zero histories.

Recipe: `research_rebuild/evidence/over1000_root_20261009/apply_batch16.py` with optional final export hook `export_final_state_v2.py`; schema error fix changes only mixed boolean/string flag serialization. Source evidence, rejected claims and decision diary are committed on `research/mass-linkage-2026-10-02`. The preceding stage68 release stays immutable.
