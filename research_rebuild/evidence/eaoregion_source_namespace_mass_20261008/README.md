# EAO source-header interpretation and native 2002 continuity

The actual original XLS `086_3c3b73a0d2_EvrejskajaAO.xls` has the exact
`Sheet1!A1` header **Еврейская АО**. Its published rural control is 62556.
All 98 selected native rows reopen to their original labels and literal counts.
The other selected 2002 EAO population is 128359; together they equal 190915.
The original imported region namespace is a filename, not another region.
The frozen known-source manifest verifies the XLS SHA-256 and bytes.

`source_namespace_interpretation_delta.csv` changes only the effective matching
region for these exact 98 source IDs to `еврейская`. It preserves imported
`region_raw` and `region_norm` separately. No selected Parquet, released archive,
raw source, source population, quality, name, type or locator is overwritten.
Root integration must set `region_norm_original_import` before updating the
effective `region_norm` consistently in both State.obs and State.by_id.

Actual State50 local application yields 15 native histories, 15 accepted edges,
and 15 own current-point retrospective uses for their 2002 rows. Names match
literally after the declared normalization; historical and current counties
match explicitly. Compatible rural printed classes include `посёлок` versus
`село`; other classes require equality. Their 2010–2021 components and accepted
current own points already exist. All region/name/type/county competitors are
enumerated before component filtering, and existing point conflicts or a
historical/current point difference over 5 km block acceptance.

Finite native histories increase from 138896 to 138911, with population gains
5153 / 3414 / 3419 in 2002 / 2010 / 2021. Final finite totals are
126801407 / 123957564 / 124562245. Exclusive native-source-ID gains on the
original mixed, direct and formation axes are **5153 / 1220 / 972**: earlier
qualified 2010/2021 credits are retained once. This is distinct from the full
native-history population gain. Federal or auxiliary counts are never added.

71 rows already have complete native identity and are retained. Twelve remain
held: unresolved station descriptors, railway class changes and the Лондоко
urban/rural competitor. Rural compatibility does not collapse urban records,
and railway facilities do not become settlements. Existing admitted point uses
are retained; no point rejection or override is proposed. Real extreme counts
are preserved without smoothing or confidence/calibration claims.

Historical point reuse is an inferred physical continuity claim, not a
census-day measurement. No municipal point projection, new network request or
source-value reconstruction occurs. The independent verifier checks all source
and output pins, reopens all 98 source rows and the 15 native 2010 rows, verifies
all-class rival completeness, and replays the accepted CSVs through State API.

Reproduce with `python build.py`, `python verify.py`, and
`python verify_county_headers.py` in this directory. The separate county verifier
reopens the literal district header above every one of the 98 source rows.
The source-manifest context is frozen locally so a later report refresh does
not rewrite this application's input provenance. Root owns State51 integration,
national report recalculation and Git.
