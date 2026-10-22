# Independently admitted477 NP coordinate overlay

`nodes_coordinate_overlay.parquet` is the actual versioned173,864-row,535-column SOURCE/MASS feature frame with477 previously missing coordinates filled from independently admitted historical2021 OSM settlement nodes. It is not a completed model or hierarchy. Source identity admission:3,517/3,517 checks; full overlay cell/dtype admission:430/430.

The477 admitted NP contain351 positive-population and126 zero-population settlements,9,671 people in census2021. Both Chusovoy Centralny cases remain held because published geocoder/GKGN/sourcepoint assertions conflict. The remaining1,137 missing-coordinate NP/19,337 people and153 existing over10km road rejections remain explicit unknowns or unchanged rejections.

Every529 noncoordinate column is exactly preserved from the individually pinned original source/mass checkpoint. Only lat/lon and the declared current coordinate-source/geography/provenance flags change on the477 approved rows; all unaffected coordinate cells/dtypes are exact. The old source frame and original provenance remain byte-identical and pinned in the receipt. `approved_coordinate_patch.parquet` records old/new coordinates and exact source object/version/date/admission hashes.

Source snapshot2021-01-01T21:42:03Z is not a coordinate measurement date, and calibrated coordinate precision is unknown. User-supplied OSM codes are corroborated by independent dated official native identity, not treated as official positioning. No nearest-road selection was used to choose a settlement point.

This is a coordinate overlay, so cached geometry-derived flags from the old feature frame remain unchanged by design. The NEW prepared execution frame must recompute coordinate/route availability from the admitted lat/lon and actual new partial-edge attachments. It must not discard these477 using old `routable_coordinate=False`. Institution counts/ownMi/provider eligibility need their separate actual source-relink step; old zero counts are not evidence of service absence. Climate/FAOsoil pixels are separately resampled in `context/cycle07_coordinate_recovery/`.

All frozen cycle06 axes, source inventories, graphs, snaps, matrices, configurations and model outputs remain unchanged. New routing belongs to the versioned cycle07 extension with explicit nearest-original-segment/directed-partial-edge policy.
