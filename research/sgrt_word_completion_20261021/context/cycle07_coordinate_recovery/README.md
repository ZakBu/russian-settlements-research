# Context at independently admitted recovered2021 settlement coordinates

This version samples the exact477 source-admitted OSM2021 NP coordinates in `source_geography_recovery_cycle07/approved_coordinate_patch.parquet`. The source/mass coordinate overlay is individually pinned by SHA; it is not a completed model or hierarchy. Both Centralny cases remain held and unchanged.

All35 previously accepted rasters and formulas are reused:24 WorldClim monthly temperature/precipitation layers, annual GlobalAI/ET0, GAEZ1981–2010 active-temperature sum and April–September P/PET, and7 FAO/GAEZ low-input maize soil-constraint rating layers. All16,695 containing-grid-cell observations were actually read and checked again by individual1×1 windows. Every477 sourcepoint has valid pixels in all35 sources. There is no interpolation.

The two annualAI/ET0 TIFF copies had been evicted. Their complete members in the retained ZIP were streamed through SHA256 verification against the accepted source receipt and accessed through GDAL `/vsizip`; no archive extraction or new download was needed. The exact source raster/grid/pixel ID, raw value, scale, coordinate and validity are retained in `source_pixel_observations.parquet`.

The full climate/soil sidecars retain173,862 ordinary-axis IDs in their original order and schema. Only477 coordinate-recovery rows are updated; every other173,385 row and dtype is exact. The2 external federal-city context anchors have no invented own-soil rows. `context_field_change_inventory.parquet` lists old/new missingness and exact changed-value counts for every field.

Climate normals are1970–2000 or1981–2010 as declared, not2021 weather observations. FAO crop-constraint classes and rating intervals are regional-grid context, not cadastral soil samples, independent Russian agronomic bonitet or observed yield. The477 Russian bonitet entries remain NA. The inherited `scientific_word_acceptance=False` concerns strict own-bonitet/agronomic interpretation; it does not negate verified source-pixel extraction.
