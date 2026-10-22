# Actual climate and soil context for 335 added settlements

The two full sidecars contain all 173,862 axis IDs in their source order. Every
column, dtype and value of the existing 173,527 climate/soil records is preserved
exactly, including missing values. Only the 335 genuinely new IDs are sampled.
Use these full files in place of the older context paths:

- `climate_settlement_features.parquet`
- `soil_settlement_features.parquet`

All 35 accepted rasters were already available locally; no download was needed.
Their SHA256 hashes match the existing accepted climate/soil source receipts.
Sampling uses the containing source grid cell, without interpolation or nearest
valid-pixel replacement. The observation table records source hash, row, column,
pixel center, raw value, scale factor, validity and a stable hash:row:column ID
for all 11,725 observations. A source nodata value remains missing.

All 335 new points have valid FAO GAEZv4 SAT and summer P/PET pixels, and valid
rating intervals in all seven soil layers. SAT is the published sum for days
above 10°C; summer P/PET covers April–September. Both describe the 1981–2010
normal. Legacy WorldClim and GlobalAI context retains its 1970–2000 normal and
its explicitly named monthly approximations. None is 2021 observed weather.

The soil layers retain the accepted HWSD-based low-input maize parameterization.
Palette colors are matched to the primary FAO legend before decoding rating
intervals. These ratings do not become Russian soil bonitet. Russian bonitet is
missing for every new point; no historical or regional score is extrapolated.
Source coordinates and their provenance are retained from the input axis;
sampling does not establish their survey dates.

Run from the repository root:

```sh
python research/sgrt_word_completion_20261021/context/cycle05_federal335/extend_context.py
python research/sgrt_word_completion_20261021/context/cycle05_federal335/verify_context_extension.py
```

The builder performs all 11,725 one-pixel physical readbacks. The separate
verifier uses Rasterio's point-sampling API on every observation, independently
checks grid indices, matches direct output features, checks original source
hashes and compares every old output value exactly. Actual results are in
`context_extension_receipt.json` and `verification.json`. Scientific acceptance
of the overall Word requirements remains the guardian's responsibility.
