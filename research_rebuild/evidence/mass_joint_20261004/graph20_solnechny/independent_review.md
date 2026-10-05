# Солнечный, Красноярский край — Graph19 targeted review

Read-only review of the exact selected 2002, 2010 and 2021 rows supplied by the coordinator. The two adjacent identity edges are accepted as physical-place identity based on the census row hierarchy plus a unique typed native-code bridge. The current DaData point is admissible for the 2021 observation only. The 2011 GeoKLADR coordinate is rejected as a point because it is about 481.5 km from both the current row and independent nearby GeoNames features.

## Decisions

- 2002 → 2010: accept same physical place. The 2002 Table 4 typed pgt row is immediately after the Sharypovo subordinate-settlement block; the 2010 Table 5 row names the settlement inside that block. The exact name/type is unique within the 2002 Krasnoyarsk rows. No inference about population-boundary comparability.
- 2010 → 2021: accept same physical place. The 2010 row, the unique 2009 classifier pgt Solnechny record (OKATO `04580000`), and 2011 GeoKLADR exact code `04580000000` agree in name/type; the 2021 proper-locality row carries the same OKATO code normalized as `4580000000.0`, plus OKTMO `4780000051.0` and the ZATO municipal context. This is identity evidence; it does not establish a legal status change date or comparable census boundaries.
- 2021 point: accept for this observation only from the raw Tochno/DaData locality record at `55.2799566, 89.825436`. The current row's FIAS level is 4 and its FIAS identifier is unique in the source snapshot. GeoNames includes both the settlement (PPLA2) and the named ZATO (ADM2) within 0.64 km.
- 2002/2010 historical point: hold. The 2011 GeoKLADR coordinate (`56.7383, 97.1236`) is 481.5 km from the 2021 source coordinate and nearby independent GeoNames objects. Do not reuse the 2021 coordinate for historical dates.

The 2010 table places this row under Sharypovo; 2009 OKATO classifies the locality under the region's federally administered urban places. These are different administrative frames and are not used to infer population-scope continuity.

## Competitors and coverage

There are many homonyms nationally. The 2010 official Table 5 also has exact-name rows in Sakha, Tver, Khanty-Mansi and Khabarovsk; none shares the Krasnoyarsk region or native code. The 2021 snapshot has distant homonyms including Khabarovsk (OKATO `08244551000`, OKTMO `8644151051`) and Tver ZATO (`28556000000` / `28756000051`). The 2021 raw snapshot has exactly one row carrying the target OKATO and exactly one carrying the target OKTMO. The 2009 Krasnoyarsk classifier line is a single typed pgt entry.

Local Wikidata/OKTMO TSV lookup yielded no matching Solnechny/Krasnoyarsk entity or target-code point. The GeoNames RU snapshot did yield a same-place locality and ZATO feature. No external network lookup was needed.

## Scope

This packet is diagnostic evidence only. It does not edit selected observations, accepted graph edges, point uses, or the canonical configuration. The chain says physical identity only; population comparability remains unassessed.
