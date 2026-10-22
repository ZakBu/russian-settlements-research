# Stage-aware primary population application

This recipe preserves the frozen stage63 application and reuses its reviewed 1,775 same-census primary population claims plus 8 and 127 disjoint claims grounded by the actual printed county and all same-region namesake rivals (1,910 total). It reads the observations emitted by the same actual stage64 application, using only additive rows for population sums and lookups. The original selected parquet remains hash-pinned, and every 2010 identity, raw count, quality and source field is compared to it before application.

The supplementary 2002 rows remain explicitly secondary census compilations. A parent subtotal keeps its printed 544 count but is excluded from additive totals; it is not credited as an ordinary settlement. Signed regional and national discrepancies are retained. No unknown population is imputed and no coordinate or temporal identity is created by this display layer.

The effective wide CSV retains all original fields next to the replacement 2010 source fields. This directory is prepared but application is not complete until `application_receipt.json` exists and all output pins verify.
