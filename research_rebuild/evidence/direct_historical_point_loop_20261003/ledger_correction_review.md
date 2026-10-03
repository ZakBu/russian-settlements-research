# Corrected point-ledger check

**Result: `PASS_CORRECTED_ADMISSION_FLAGS_ONLY`**

The corrected v2 ledger contains the same 4,575 reviewed targets and preserves all 327,430 pre-existing point uses. Compared with v1, only `coordinate_admitted` and `point_admitted` changed, each on exactly the 4,575 new targets; both are now true. All 133 pre-existing base columns match the frozen base rows, and the 12 additional application fields are null on those base rows.

The 4,575 v2 rows preserve the frozen stage coordinates, source origin, temporal and uncertainty semantics, and scientific gate fields. Identity-edge, historical-propagation, native-ID/FIAS, boundary/population comparability, and measurement assertions remain false. The v2 acceptance receipt pins the same base, stage, and application review as v1 and records `base_values_unchanged=true`.

This check does not verify a combined delivery export; that remains pending the corrected final build. Exact target IDs and all pins are in `review.json`.
