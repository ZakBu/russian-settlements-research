# Limited independent mechanism check (stage63 packets)

Selection is deterministic and stratified, not a national accuracy estimate: point source-evidence file sorted by source_record_id then pandas sample(random_state=611), n=4 OSM + 3 GeoNames/RCSI + 1 article; Table5 ready packet sample(random_state=501), n=2 from each context_method (4 rows, four workbooks).

## Current named ownpoints (8/8 source checks pass)

- 4 OSM (the largest class, 532/604): raw NDJSON locator reopened for each candidate. All are named OSM `place=hamlet` nodes, with exact native own-name and matching county/region address. OSM node ID and location matched the cached match record; no native same-county same-name rival in the selected evidence rows. Sample names: Осиевская, Волегово, Пушкарские Выселки, Деньговская. District label variants (e.g. Верещагинский городской округ vs муниципальный округ; Буйский район vs муниципальный район) preserve the same district name and do not create a competing locality.
- 3 GeoNames/RCSI: reopened raw RU.txt lines are all feature class P / PPL / RU; exact own names in the specified region; the matching literal RCSI row supplies exact native OKTMO, settlement name/type and municipality, and has no same-county own-name rival in the source evidence. RCSI coordinates agree within the admitted 1km corroboration radius; GeoNames coordinates match the candidate point exactly. Sample names: Озерки, Хмелевое, Ясеновая.
- 1 article: reopened cached page 8038309 revision 152422527; own-NP infobox and lead explicitly say деревня Ушаково, Нижегородская область, Богородский район/Алешковский сельсовет; literal coordinates 56.139516, 43.349201 match point delta. Separate current coded-parish mirror explicitly lists own OKTMO 22507000241 effective 2021-02-01 and explains the specific parish, resolving same-county homonym. Point is source-bound; no general Wikidata binding claim is made.

All eight source_record_ids are current 2021 native settlement rows; point deltas target those same IDs. No new identity or population claim is introduced by point use. This sample validates the mechanisms and selected source locators only.

## Official Table5 population bindings (4/4 source checks pass)

Reopened the exact source workbook sheet/row via xlrd; caption and old population cell agree with the candidate. Extracted the pinned 2010 official PDF page with `pdftotext -layout`; exact official name, type, population and district appear on the cited page. All have `target_key_and_official_key_agree=true`, `independent_count_readback=true`, and existing source IDs; candidates replace a count on an existing observation, not create a locality identity. The two context methods are represented twice each, in four workbooks:

- Samara, `!!!` row 285: село Спиридоновка, old 1,356; Table5 p.141 line 34, Волжский район, 4,896. Three nearby exact typed locality anchors are in Волжский район; one farther neighbor is in Исаклинский район and is not treated as the target county.
- Bashkortostan, `!!!` row 3812: село Авдон, old 5,198; Table5 p.112 line 28, Уфимский район, 5,201. Context witnesses include neighboring Уфимский район settlements.
- Chechnya, `СК` row 1606: село Гелдаган, old 12,350; Table5 p.102 line 51, Курчалоевский район, 12,350. The exact-typed bracketing rows are Майртуп and Цоцин-Юрт, both Курчалоевский район.
- Moscow region, `Data Sheet` row 12320: пгт Ашукино дп, old 8,501; Table5 p.37 line 38, Пушкинский район, 9,942. Exact typed neighboring anchors are in Пушкинский район.

These are four source-row successes only; they do not validate all 501 candidates or imply the aggregate delta is accepted. No defect found in this small mechanism check.

## Pins

- Point evidence: `accepted_source_bound_ownpoint_evidence.csv.gz`, SHA256 `4378176f3a60b693b4de9ee59355d8fc31e738096cc018f7e27db20bfcaced8f`; enclosing joint admission receipt pins all source/cache inputs and output delta.
- Table5 501 packet: SHA256 `100f94a7d3bacac2a07a74b2b5295de0c0c47b9c34d5c84af2487a876389e56c`; enclosing `national_batch_receipt.json` pins workbooks, official PDF, Table5 reference and source rosters.
