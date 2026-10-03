# Dagestan 2010 publication application review

**Verdict: PASS_DAGESTAN_PUBLICATION_APPLICATION_INDEPENDENTLY_VERIFIED_WITH_EVIDENCE_ID_CORRECTION**

The application matches the exact 56 pairs approved in the scientific review. Selected population moved from 142,361,475 to 142,363,024 (+1,549); the selected file remains 465,800 rows. All 56 displaced population assertions match their pre-application records exactly, retaining the old population, protected quality tag and limitation.

Every non-target selected record is unchanged across all fields (465,744 rows), including all 1,344 prior accepted publication-binding rows. The graph preserves all non-endpoint decision/evidence fields and changes only the reviewed 45 endpoint occurrences, preserving connectivity under the exact one-to-one ID map. The 49 affected point targets and one structural identity-path-from reference migrate; all other point fields, including canonical origins, remain exact. No `source_point_use_target_source_record_id` reference touches this cohort.

The initial application contained a null nested `source_record_id` on the 56 new evidence JSON records. The separately pinned correction layer fixes only that nested field for the 56 approved IDs. Independent comparison confirms all other JSON values and top-level columns for those targets are unchanged, and all 465,744 non-target evidence rows remain exact. The earlier 780 restrictive district-context annotations also remain unchanged.

The previous 1,344 binding evidence records already have null nested `source_record_id` metadata; that optional legacy field remains unchanged, with top-level IDs authoritative. No new scientific admission was made. The cumulative publication ledger has 1,400 exact bindings (1,344 prior + 56 Dagestan). Detailed checks and pins are in `application_review.json`; the correction comparison is in `evidence_correction_review.json`.
