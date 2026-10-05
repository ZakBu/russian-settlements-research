# Independent raw-source replay sample: 1,167 clear bridge candidates

## Sample and evidence

The sample contains 20 highest-population rows plus 40 deterministic, stratified rows (seed 20261005) from the 1,167 noncollision rows with locally available source files. Stratification uses year, city/PGT class, and exact selected source-file path. It covers both census years and urban classes, and every source-file family represented in the clear cohort.

For each row, the replay reopened its raw XLS, PDF, or HTML source row and checked the publisher name, type, population, and regional context. It recomputed SHA-256 and compared it with the selected source manifest when a manifest pin existed. It also checked the raw 2009 classifier code/line and directly decoded the exact 2011 GeoKLADR DBF record by one-based record number and byte offset, including raw code pieces, KOD3, name, and coordinates. For 2021, it required a unique exact normalized name/type/region counterpart and measured distance to the accepted point-use coordinates from Graph24.

## Summary

- Sample: 60 rows (20 highest-population and 40 stratified).
- Raw source rows opened: 60/60; name/type/population checks pass for 60/60. Regional row or hierarchy context is evidenced for 60/60.
- Source hashes: exact prior manifest hash matches for 58/58 sampled rows with manifest pins. Two Arkhangelsk archive HTML rows have no old manifest pin; their current file hashes are included in the receipt.
- Raw classifier: code appears exactly once and the raw classifier name matches after punctuation normalization for 60/60.
- GeoKLADR: raw 11-character OKATO, literal KOD3=000, and DBF coordinates match candidate evidence for 60/60.
- 2021 exact name/type/region tuple: unique for 50/60. Ten have no unique exact tuple. Accepted point distances are available for 50: median 0.134 km, maximum 2.165 km; 0 exceed 25 km.

Graph24 accepted-point statuses for exact counterparts: reviewed_extension_rule_accepted: 44, reviewed_rule_accepted: 6.

### 2021 exact-tuple misses

- Железнодорожный (московская, 2002): 0 exact tuple matches; same name and region rows 1; current type values: посёлок.
- Климовск (московская, 2002): 0 exact tuple matches; same name and region rows 0; current type values: .
- Маго (хабаровский, 2002): 0 exact tuple matches; same name and region rows 1; current type values: посёлок.
- Навля (брянская, 2002): 0 exact tuple matches; same name and region rows 1; current type values: посёлок.
- Пески (московская, 2002): 0 exact tuple matches; same name and region rows 5; current type values: деревня; посёлок; село.
- Железнодорожный (московская, 2010): 0 exact tuple matches; same name and region rows 1; current type values: посёлок.
- Им. Свердлова (ленинградская, 2010): 0 exact tuple matches; same name and region rows 0; current type values: .
- Климовск (московская, 2010): 0 exact tuple matches; same name and region rows 0; current type values: .
- Ожерелье (московская, 2010): 0 exact tuple matches; same name and region rows 0; current type values: .
- им. Степана Разина (нижегородская, 2010): 0 exact tuple matches; same name and region rows 0; current type values: .

## Artifacts

- `sample_findings.csv`: compact row checks, source pins, 2021 match status, and distance.
- `sample_replay.csv`: row-level raw snippets, context and full evidence.
- `replay_sample.py`: deterministic sample and verification replay.
- `receipt.json`: input/output hashes, sample method, and summary.

Distances are a location diagnostic; they do not decide historical identity. No canonical population, identity, or coordinate records were changed.
