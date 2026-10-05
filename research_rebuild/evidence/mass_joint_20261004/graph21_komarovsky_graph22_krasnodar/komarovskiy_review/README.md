# Комаровский, Оренбургская область — Graph20 targeted review

Read-only review of the supplied exact selected observations for 2002, 2010 and 2021.

## Decisions

- 2002 → 2010: accept physical identity. The official 2002 Table 4 row is `пгт Комаровский` (8,344), immediately after the regional city entries. The official 2010 Table 5 row is the exact same typed name (8,064), likewise in the urban list before districts. The 2009 OKATO classifier has one typed Orenburg pgt Комаровский record (`53555000`) under federally administered urban-type settlements. The separate `53259825` record is an administrative/rural branch named Комаровский with `п Комарово` and other village children, not a second typed pgt settlement.
- 2010 → 2021: accept physical identity. The current proper-locality row is exact-name Комаровский in Orenburg, now under the explicitly named ZATO municipality. Current independent point references identify that same locality: Wikidata Q4229407 has OKATO `53000000001`, OKTMO `53755000101`, and a nearby P625 point; GeoNames 545905 is `Komarovskiy` (PPLA2) with aliases `Dombarovskiy-3`, `Jasnyy-2`, and `Yasniy-2`. The 2009 code `53555000` does not directly equal the 2021 native code `53000000001`; identity acceptance is based on the unique typed name/region, official ZATO context, and spatially coherent independent current-place records, not an asserted exact code crosswalk.
- 2021 point: accept the raw Tochno/DaData locality point `51.0302453, 59.8691632` for the 2021 observation only. It is within about 0.3 km of GeoNames and about 0.8 km of Wikidata Q4229407. The source provides a FIAS level-6 ID unique in the raw snapshot.
- 2002/2010 historical points: hold. No census-year point was found. The 2011 GeoKLADR DBF has a row `53259825000` labelled Комаровский, but it is a `RAZDEL=1` area/administrative row in the `Комаровский` branch, not a direct point binding for the exact selected locality. Its `51.0245,59.8037` coordinate is 4.623 km from the current-source point; do not attach it to the population rows.

No population-boundary comparability, legal status-change date, or exact native-code continuity across 2009–2021 is inferred.

## Native-code field distinction

The selected 2021 observation carries native `okato=53000000001`, `oktmo=53755000001`. In the same raw row, the embedded DaData fields are `okato_dadata=53000000001.0`, `oktmo_dadata=53755000101.0`; FIAS level is 6, FIAS ID `a4f7fd84-1e17-4c10-bbcd-9f3c78f00c05`. The local Wikidata/OKTMO entity cache has two duplicate lines for Q4229407 with OKATO `53000000001`, OKTMO `53755000101`, and point `59.873889 51.036945`. The OKTMO mismatch is preserved rather than normalized away; both values tie to the locality at different source fields.

## Nearby names and source conflicts

The 2021 raw snapshot also contains `п Комарово` in Orenburg, with different native IDs, OKATO `53259825001.0`, OKTMO `53507000151.0`, and point `51.1881668,60.0941023`. It is not the target `Комаровский`; it is a separate named locality, far from the target point. The 2011 DBF's `53259825000` row is the parent/admin row for that named branch and is not treated as a same-grain selected settlement competitor.

The 2009 typed classifier row `53555000` and the 2021 selected native OKATO value do not form a direct equality join. The 2011 DBF lacks an exact 2011 native row under `535550...`; it has only the separate `53259825000` administrative row and child `п Комарово`. This gap limits code-chain evidence but does not conflict with the name, region, ZATO and independent point evidence.

No external network lookup was needed. The local Wikidata OKTMO entity TSV contained Q4229407, and the GeoNames RU snapshot contained matching nearby feature 545905.

## Scope

This packet is diagnostic evidence only. It does not edit selected observations, accepted graph edges, point uses, or the canonical configuration.
