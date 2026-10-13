# Applied residual native linkage, 13 October 2026

Current working national coverage after the frozen application15 lifecycle integration and this applied batch:

| Year | Credited population | Fixed common control | Coverage | Remaining |
|---|---:|---:|---:|---:|
|2002|144618816|145166731|99.62256159091989%|547915|
|2010|142159355|142856536|99.51197122685377%|697181|
|2021|144319040|144699673|99.73694964742594%|380633|

Net gain: 22059 / 22397 / 10918 people. This is the previously requested working axis incorporating legitimate lifecycle and federal-territory routes, not a substituted strict-full3 or >500 denominator.

49 reviewed native identity edges were applied. Two proved homonym components were partitioned before linking the correct records (Tavatuy, Vorontsovka). Ordinary complete three-census components increased from142696 to142735.89 native UIDs gain credit; the incorrectly linked Vorontsovka station2002 UID(population60) loses credit and its inherited main-town point use. Every source observation/count/quality/code remains unchanged. Five ownpoint uses were added,11 existing coordinates corrected, and that one station point use withdrawn.72 of378 initial >500 uncredited source-year rows are now resolved;306 remain. This is a completed batch, not100% completion of the residual.

The source-backed rule combines actual census leaves, exact or explicitly sourced variant names, typed object/administrative context, unique qualified own-site candidates, admitted points and exclusion of competing same-year records or events. Proximity alone is not an admission rule. Prior native county/flank/code witnesses are reused. Current points are representative points, and retrospective reuse is an inference; exact census-day geometry and boundary comparability remain unknown. Sanatorny retains its existing GeoNames point; a proposed6.94km replacement was withdrawn because its superiority was not proved. Direct article evidence supplies the2004rename; protected2010count674 is not replaced by secondary673. Kalinin remains held because its same-county rival was not excluded.

The sole extreme ratio flag in the49 new edges is Ebelyakh988(2002)→0(2021). Zero is the actual existing census observation, not imputation. No new >21x growth flag was found. Torkhovo raw2010=547 and approved primary overlay=814 are retained separately. Six federal rows are counted once against unchanged national controls; their children are not added again. These checks do not establish a statistically calibrated national error rate.

For Chirshkasy, the literal captured Classinform text states that annulled97644482101 corresponds to successor97544000530. OSM carries97544000530; native2021 retains97644482101. No effective transformation date is inferred. Historical shorthand reversing these directions is not a new legal fact; the immutable older source packet is preserved. The corrected four-peer/native-branch and qualified own-article proofs independently support the place binding.

## Current files

- `applied/integrated_credited_UID_roster.csv.gz`: durable current UID membership, effective counts and full3/point flags.
- `applied/coverage.csv`: current national metric.
- `applied/applied_identity_edges.csv`, `applied/applied_point_use_delta.csv`, `applied/applied_coordinate_use_rejections.csv`: actual applied changes.
- `applied/changed_credit_native_records.csv.gz`, `applied/remaining_initial_over500_residual.csv.gz`: changed membership and remaining initial targets.
- `applied/application_receipt.json`: pinned inputs, unchanged source fields, measured77.489second batch application and full-output hashes.
- `../residual_integration_review_20261013/`: independent purposeful evidence/union review, not a random sample.

The full current native/coordinate/effective-population layer is generated outside Git at `/workspace/scratch/residual-20261013/final/integrated_spatial_temporal_records.parquet`. The adjacent core point snapshot is deliberately narrow. Rich unchanged point provenance stays in the pinned full application15 snapshot; replacements retain all qualifiers in their point-use packets. Published stage71 and its default loader are unchanged: no new metadata-complete national release is claimed.

## Reproduction

Restore necessary original source files once from the baseline raw archive using its release manifest; see `source_recovery_receipt.json`. Read-only original sources live outside Git. Current code and durable membership live in Git. Source-specific use conditions are preserved; no blanket licence is assigned.

```bash
python research_rebuild/evidence/residual_root_20261013/recover_state.py \
  --output /workspace/scratch/residual-20261013/base15
python research_rebuild/evidence/residual_root_20261013/apply_batch.py \
  --state-dir /workspace/scratch/residual-20261013/base15 \
  --output research_rebuild/evidence/residual_root_20261013/applied \
  --full-output /workspace/scratch/residual-20261013/final --include-broad
```

Recovery verifies stage71 manifest bytes, frozen application15 input hashes, all59652 threshold roots/counts/point coordinates and exact465929observations/447362activepoints. An unavailable old local graph25 ledger is recorded explicitly; its already accepted later rejection is replayed from the frozen rejection packet against the verified published point claim. Missing original cache bytes are not presented as reopened or independently verified. The old graph is not silently re-admitted.
