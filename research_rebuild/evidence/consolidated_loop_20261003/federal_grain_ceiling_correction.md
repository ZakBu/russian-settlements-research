# Federal-city ceiling correction: source grain flags

This immutable addendum corrects the 2010 theoretical point-ceiling calculation only. The prior feasibility inventory is unchanged. Inputs are the exact pre- and post-Dagestan selected/evidence parquet hashes pinned in `correction.json`; the current calculation uses the 465,800-row post-Dagestan snapshots.

The legacy scope-field-only ceiling counts rows whose `population_scope` value is treated as point-eligible. The 2010 field says `settlement` for both Moscow (11,503,501) and Saint Petersburg (4,879,566), so it counts both populations as point-eligible: 99.653456% before the 56 replacements and 99.654540% after. But each exact ID has `is_federal_aggregate=true` and `grain_review_flag=federal_aggregate_hard_block` in source evidence. Their union is 16,383,067, so the grain-evidence guarded ceiling is 88.185260% before and 88.186345% after, using the unchanged 2010 official control of 142,856,536. The 56-row Dagestan source-value update adds 1,549 people and raises this guarded ceiling by 0.001084 percentage points; it changes neither flagged ID nor coordinate/identity state.

The 2002 federal aggregate is Saint Petersburg alone (4,661,219); the Moscow source row `ROSSTAT2002:T1:T4:sheet01-04:excel_row02155` (10,126,424) is explicitly `physical_settlement_city_only`, `is_federal_aggregate=false`, and `grain_review_flag=grain_explicit`. It remains outside the hard-block union. The 2021 hard-block union is the three federal-city totals, 19,159,843. Exact IDs and values are in `aggregate_flagged_records.csv`.

| Year | Scope-only ceiling | Grain-guard ceiling | Aggregate evidence excluded |
|---|---:|---:|---:|
| 2002 | 96.780981% | 96.780981% | 4,661,219 (1 row) |
| 2010, before 56 replacements | 99.653456% | 88.185260% | 16,383,067 (2 rows) |
| 2010, after 56 replacements | 99.654540% | 88.186345% | 16,383,067 (same 2 rows) |
| 2021 | 86.982221% | 86.982221% | 19,159,843 (3 rows) |

These are ceilings against official population controls, not claims that all remaining populations have valid coordinates or harmonized physical boundaries. The 2010 source-quality mismatch remains unresolved until direct core counts or authoritative census-scope evidence are found. No points, graph links, selections, or source records are changed here.
