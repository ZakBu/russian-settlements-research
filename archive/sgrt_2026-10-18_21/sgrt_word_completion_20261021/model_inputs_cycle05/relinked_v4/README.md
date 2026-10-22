# Frozen 2021 source re-linkage onto 173862 settlement IDs

This layer reads dated repaired education (74998 rows), commerce (458727 rows), and medical (64976 rows) objects. It reads no model assignments, agreement scores, or validation outcomes. Source inventory remains intact, including unlocated, inactive, nonclinical, ambiguous, and external objects. Raw tags, dated eligibility, source canonical IDs, and previous-axis linkage fields are retained.

Run from any directory:

```
python research/sgrt_word_completion_20261021/model_inputs_cycle05/relinked_v4/relink_sources_2021.py --family all
python research/sgrt_word_completion_20261021/model_inputs_cycle05/relinked_v4/verify_linkage_source_semantics.py
```

Do not rerun into this frozen folder after model comparisons. Create a versioned successor instead.

The reference has 154132 finite-coordinate, own-population-2021-observed, additive, nonterritory units. The 335 supplemental settlements belong to the new axis; old nonadditive federal territory totals are not physical-provider settlement identities. No historical alias is guessed. The medical amendment to a dated current-population reference was explicitly approved by root before comparisons. Original reference links are retained as `previous_axis_*` diagnostics; a removed link does not imply that a physical facility closed or is absent.

Education and commerce preserve the original literal normalization, unique-address ≤5 km baseline and separated ≤2.5 km candidate policy. Medical preserves unique-address ≤10 km lookup, ≤5 km baseline, and 5–10 km conditional assignment. Same-name KD-tree searches optimize computation without changing the admissible set. No fuzzy or new prefix match is introduced.

Each canonical campus can contribute to only one NP across counted channels. Baseline precedes additional candidate evidence; conflicting baseline identities exclude that canonical campus. Medical additionally gives conditional links priority over coordinate evidence. Source raw nearest medical `coordinate_candidate_uid` remains a diagnostic; counted coordinate features are **additional only**, unlike the original duplicated-nearest diagnostic features. Use `count_<channel>_uid` for counting, rather than raw link columns. Global one-canonical/one-counted-UID assertions hold for all three families. One explicitly proven medical multipolygon/outer-way geometric identity is unioned in `count_canonical_site_id`; original source canonical IDs remain intact.

Medical general, dental, pharmacy, alternative, unknown, mortuary, veterinary and residential-care classes remain distinct. `healthcare_sites_count` is general clinical-tag evidence (including generic healthcare=yes without a known clinical level); `general_and_dental_clinical_sites_count` additionally includes dental. `explicit_clinical_function_sites_count`, `generic_healthcare_yes_unspecified_level_sites_count`, and `explicit_hospital_sites_count` permit stricter definitions without re-extraction. Hospital counts require explicit hospital tags. None of these fields establishes operation, real patient trips, attendance, capacity, or a complete facility census. Pharmacy, alternative, morgue, veterinary, unknown and residential-only care never create clinical positivity. Dental is actual clinical evidence but does not imply a general practice or hospital.

`settlement_features_full_axis.parquet` in each family contains all 173862 unique IDs and the source family's previous count schemas. `source_objects_relinked.parquet` preserves raw source rows and new link diagnostics. `baseline_count_changes.parquet` compares canonical eligible source counts under the previous and current references; `changed_baseline_links.parquet` contains every changed raw strict identity; `new335_features.parquet` contains all supplemental IDs, including zero observed records. Zero counts mean unknown absence of accepted observations.

Author self-check directly recomputes the original full-reference ball search on every changed baseline row plus the first 256 and a fixed-seed random 256 per family, and checks counted canonical uniqueness and reference admissibility exhaustively. This is not an independent scientific acceptance. A separate guardian must review this source freeze before model use.

V4 excludes counted medical coordinate candidates when the nearest two distances tie within1e-7km. Raw nearest diagnostics and source-address strict/conditional identities remain intact; ties cannot choose an NP by KD-tree implementation order.
