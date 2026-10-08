# Follow-up check after root applied the cache patch

## Actual method regression

Imported `current_chain_state_20261007.State` and invoked its checked-in `reject_point_uses` method on `State.__new__` fixtures; patched only module-level `sha` to count calls. Live source pin at check time: commit `af70fdf96d45c84c67df5afcdd6a216a10946140`; `current_chain_state_20261007.py` SHA256 `8c3aaa317bd2aff53a4ee40c30c69bbd88de40c22ad8cffbd7524dba941bd1ce`.

`actual_method_regression.py` PASS:

- two valid records with one active ledger call sha once;
- a bad expected digest on row two still raises after row one used cached digest;
- a separate invocation rehashes changed bytes at same path and raises;
- first-row status, old-coordinate, active-ledger and wrong-digest guards remain enforced before row mutation.

The original isolated mirror test remains in `regression.py`; the follow-up exercises the live method itself.

## Source100 parent-grain / denominator audit

Bounded readback only; no source100 or State edits. In the 100-row packet the two new Astrakhan observations are Sheet1 rows 6 and 16, with 8 and 38 residents. The 544-person parent is the existing row456 record and the ordinary child is existing row457; parent row456 is not duplicated as one of the 100 additions. The one parent-grain sidecar retains raw 544, marks row456 nonadditive, and does not change source counts, identity graph, points, or primary credit. Its helper asserts unchanged parent population and explicit negative additive delta.

However all 100 appended observations carry additive=True in the 20-column State schema, while separate metadata tags all 100 as `secondary_compilation_of_2002_census` and primary-credit flags false. Since `State.metrics` sums all additive rows without consulting that metadata, the effective selected-ordinary denominator increases by 9,856 minus 544 = 9,312 with zero new primary numerator credit. This is permissible only when reported as mixed-source selected ordinary denominator; don't label it the primary denominator. Keep `plan.json` baseline `raw_primary_population` (144,017,893) separate from conditional all-selected population (145,164,317).

Readback sources: `original_2002_population_control_residual_20261008/finalized_stage64_source100/{accepted_source_observations_100_20col.csv,accepted_source_observation_metadata_100.csv,accepted_Astrakhan_parent_nonadditive_interpretation.csv,future64_schema_admission_receipt.json}` and `main_axis_residual_application64_20261008/{plan.json,add_source_observations.py,frozen_State_API64.py}`. No repeated source-record audit performed.
