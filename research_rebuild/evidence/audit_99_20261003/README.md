# Audit of the 99% population target, 2026-10-03

Read-only scientific audit. No coordinates, identity links, or population
observations were admitted. The scientific checkpoint is `c9abecf`; the
500,320-row table and prior release archives remain unchanged.

The Russian report is `docs/AUDIT_AND_PLAN_99_20261003.md`. Its exact reviewed
hash and every diagnostic artifact's size/hash are in `artifact_manifest.json`.
Small reports, reproducible scripts, JSON and an executed notebook are tracked
here. Candidate Parquet and larger CSV files remain under the manifest's
`artifact_root`; a missing Git copy is not missing data. The manifest excludes
itself and Python bytecode.

The independent final scope/sampling review is
`source_scope/final_plan_review_v2.json`. Its v1 receipt remains as historical
evidence: v2 withdraws one false positive after checking the quoted source
lines. Reviews establish only their stated scope, not candidate geography.

The current Wikidata pilot frame is 351 large candidates / 2,068,453 people.
The PPS file preserves 300 draws, seed 2026100301, probabilities and repeated
IDs. Targeted diagnostic cases are separate; the union is 200 unique records.
It has not undergone independent geographical review.

History files contain 64,483 raw flat-TSV statement IDs, including 17 deprecated
claims excluded from rank-eligible candidate history. Four ambiguous dates
remain alternatives with the scalar date suppressed. All 4,984 full-entity
statements overlap that inventory; they are not an additional population
series. Full qualifiers and references remain preserved. No year prefix is
silently assigned to a census date.

Scripts currently pin this workspace's source paths and hashes; other machines
must map those paths to the same source bytes. Use the existing environment:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/settlements-venv/bin/python /workspace/settlements-work/continuation_20261003/audit_99_20261003/root/audit_baseline.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/settlements-venv/bin/python /workspace/settlements-work/continuation_20261003/audit_99_20261003/root/check_history_candidates.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/settlements-venv/bin/python /workspace/settlements-work/continuation_20261003/audit_99_20261003/root/check_wikidata_pilot.py
```

The baseline notebook has executed outputs. Candidate-production scripts live
in their corresponding folders. Re-running a producer changes diagnostic
output bytes; freeze the frame before geographical review and preserve it
through that review. Do not overwrite accepted packages or promote candidates
using these integrity checks.
