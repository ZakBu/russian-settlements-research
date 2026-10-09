# A112 V25: Udmurt historical station routes and Igumnovo origin crosswalk

This successor corrects the cautious V24 scope-only note for two Udmurt targets after checking literal source hierarchy, 2009 classifier rows, 2011 GeoKLADR records, current native rows, and the exact target article revisions. V24 is preserved unchanged. No population values, coordinates, or boundaries are modified.

## Ready identity edges

- **Postol:** add old `посёлок и станция Постол` 2002 UID `2002:045_9dc3ed048e_02c__Udmurtia.xls:Sheet1:970` (1,299) → 2010 `село Постол` UID `2010:017_68e0e4537e_9._20Basq_Mari_Mord_Tatar_Udm_Chuv_2010.xls:!!!:11247`. The target's own article revision 154897490 says Postol originated around the same-named station and specifically says the station and settlement Postol were transformed into село Постол by Udmurt Republic State Council Resolution 308-III dated 26 October 2004. The 2010→2021 link is already in V23. The separate 2002 деревня Постол (572) is not joined to this event edge; its separate physical source route remains distinct. This historical identity is independent of the 2011 point mismatch.
- **Sholya:** add old `посёлок и станция Шолья` 2002 UID `2002:045_9dc3ed048e_02c__Udmurtia.xls:Sheet1:1190` (1,421) → 2010 `село Шолья` UID `2010:017_68e0e4537e_9._20Basq_Mari_Mord_Tatar_Udm_Chuv_2010.xls:!!!:11414`. The source row is in Kamбарский district; the current target is the same named village in that district, and its own article revision 148290079 says a railway station is located in the village. The 2011 typed `с Шолья` record and current raw row agree spatially within 0.123 km; the separate 2002 `деревня Шолья` (2) is an Armязьский council village and its 2021 object is 13.3 km away with a different municipality. The 2011 DBF repeats identical coordinates for its `д` and `с` records, so that duplicate point is not treated as conclusive. No exact legal reclassification date is claimed. The 2010→2021 link is already in V23.

## Igumnovo remains separately scoped

No old `посёлок Игумново` target row was found. The two same-name 2002 observations are a Kstovsky village and a Sokolsky деревня; their 2009 codes, 2011 typed points, publisher districts, and names/types bind them to separate places far from the later Dzerzhinsk posyolok. The 2002 value for the later posyolok remains UNKNOWN_NOT_ZERO. The current posyolok itself has a unique 2009 typed code and 2011 point aligned to the raw current point and its own article coordinates.

## Point limits

Postol's 2011 GeoKLADR `с Постол` point (56.773235, 52.774349) is 6.51 km from the 2021 raw DaData point (56.827614, 52.734713); the target article coordinates are close to the 2021 raw point. This is a coordinate quality conflict, not a reason to reject the explicit 2004 identity event. Sholya's 2011 `с` and `д` rows share coordinates; the current raw municipality/code and the later Armязьское counterpart disambiguate the current target, but do not supply an old station coordinate. Igumnovo's current point is 0.40 km from its 2011 typed `п Игумново` point; the two 2002 village competitors are >75 km away.

Source files and hashes are pinned in `receipt.json`; row locators and the detailed crosswalk are in the CSV ledgers.
