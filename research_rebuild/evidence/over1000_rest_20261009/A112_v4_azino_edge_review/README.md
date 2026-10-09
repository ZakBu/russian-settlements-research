# A112 v4: Azino 2002→2010 source review

This is a single source-bound same-place edge candidate for parent review. It does not modify the graph or add population.

The 2002 Udmurtia raw census workbook has exactly one Azino row: `посёлок и станция Азино`, 1,767 people, under Zav'yalovsky rayon and Kiyaiksky rural council (physical row 915). The 2010 raw census workbook has exactly one region-wide Azino row: `село Азино`, 687 people (physical row 11,213). The 2021 Tochno row is `село Азино`, 1,130 people, under Zav'yalovsky municipal rayon and Kiyaiksky settlement, with OKATO 94216828002 and an accepted own-locality point.

The 2009 classifier has one `с Азино` typed row for the code. The 2011 GeoKLADR record for that code is `с Азино` at 56.973515, 52.709604; the current accepted point is 0.093 km away. The existing Graph68 component snapshot assigns the 2021 row to the 2010 row’s component and records an accepted own point. The old workbook label includes the settlement and station, while the current article describes the village in Kiyaiksky settlement and separately mentions the railway station located in the village. This supports the ordinary type wording change without equating every station with a settlement.

The raw 2010 workbook was reopened for its value: 687. The existing `exact_interyear_counterpart_candidates.csv` has the 2010 and 2021 population columns reversed for this pair, so this candidate relies on the raw source row replay and not those two fields. The candidate edge would add the 2002 source row to the existing 2010/2021 component; the root must replay current graph collision checks before applying it.

`azino_2002_2010_source_bound_edge_candidate.csv`, `azino_existing_accepted_point_context.csv`, and `receipt.json` contain the row locators, point carrier, and SHA-256 pins. The accepted point row is contextual only; no new point use is proposed.
