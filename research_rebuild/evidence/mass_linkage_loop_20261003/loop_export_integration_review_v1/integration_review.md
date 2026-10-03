# Final loop export integration review

**Verdict: PASS_DATA_ONLY_EXPORT_INTEGRATION**

The pinned export reconciles to the frozen R4 selected observations, identity graph, accepted point uses, restrictive source-evidence addendum, legacy-availability projection and cumulative publication bindings. It contains 500,320 unique observation IDs; the CSV-gzip and Parquet outputs have matching ordered IDs, record types and source IDs.

The census layer has 465,800 exact selected records and 327,430 accepted points. The table carries 495 annual-record point associations and no coordinates on its 34,004 Wikipedia literal-series records. Census native OKTMO strings match the selected source values exactly; the export adds no validity-interval fields. The canonical point-origin fields and uncertainty JSON match all frozen point uses, including GeoNames 2021 points and historical continuity uses.

Only the 780 primary-bound context records have the three restrictive metadata keys. Their original JSON values and all other evidence rows are unchanged; the district flag remains unverified and the identity assertion is false. Recomputed coverage axes match the export coverage using the full controls 145,166,731 (2002), 142,856,536 (2010) and 147,182,123 (2021). The coordinates/identity/publication conclusions are reused from their existing pinned reviews, not reevaluated here.

Checksums, counts and coverage numerators are in `integration_review.json`. No export, source, code or admission artifact was modified.
