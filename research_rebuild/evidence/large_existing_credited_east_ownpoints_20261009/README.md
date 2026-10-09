# East assigned own-locality point packet

This packet resolves the point-use criterion for all 53 UIDs in the frozen `east_exact_roster.csv`: 52 native locality records receive a representative point for their physical locality, and one Khakassia record is documented as a non-locality aggregate and receives no point.

`accepted_point_use_delta.csv` is the integration delta. Every row targets the original census UID, carries a pinned coordinate origin and source locator, and explicitly leaves the historical-coordinate, population-boundary-comparability, and external-provider-ID claims false. Counts, source quality, and accepted lifecycle/identity decisions are unchanged.

The point sources are:

- 20 exact-name, exact-type rows from the raw 2011 GeoKLADR/OKATO DBF. The selected row numbers, byte offsets, source names, types, codes, and coordinates are in `geokladr_2011_exact_name_candidate_witnesses.csv`; the raw file hash is in `source_file_manifest.csv`.
- 30 named OSM locality or neighborhood objects. Their full Nominatim responses, including all returned rivals, query URLs, retrieval timestamps, object IDs, names, and coordinates are preserved in `osm_nominatim_raw_witnesses.json`.
- Two own-article coordinates: the former pgt Abagur (also called Abagur-Lesnoy) and the former village Sosnovka near Chelyabinsk. `wikipedia_article_point_witnesses.json` pins article revisions, coordinate literals, and article locators. Both articles identify the matching 2002 population, while their histories place the settlements in the current city after dated inclusion events.

The source-row witnesses in `native_source_row_witnesses.csv` pin each original workbook row, raw row cells, file hash, and preceding hierarchy context. Those hierarchies resolve same-name localities: examples include the Tolyatti and Samara urban districts, Kopeysk neighborhoods, Ulan-Ude settlements, Barnaul and Novoaltaysk subordinate settlements, and the Kemerovo and Novokuznetsk entries.

Literal census parts use the named whole locality’s point only as **coarse joint location support**. The point is not represented as a measured or estimated centre for an individual part. These records are marked `accepted_coarse_joint_point_use` in `point_dispositions.csv`.

The Khakassia source UID `2002:065_392a5859cb_Xakasia.xls:Sheet1:383` is excluded from locality point use. The accepted scope correction at `over1000_south_other_completion_20261009/batch3_two_wrong_object_scopes/accepted_typed_native_scope_corrections.csv` identifies the raw “Селосонский сельсовет” row as a council aggregate totaling three distinct settlements, not a settlement. The accepted correction preserves the source value and does not assign the aggregate a point.

All coordinates are retrospective locality/neighborhood representatives. They are not claimed as census-day measurements, do not assert population-boundary comparability, and are not municipal-parent coordinates. The complete artifact and input hashes are in `manifest.json`; `run_receipt.json` records the exact-roster validation.
