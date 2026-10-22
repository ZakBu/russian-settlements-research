# Applied national working-axis integration, 2026-10-09

This is the current applied working coverage layer after the fifteenth >500 State application. Published stage71 and its default loader remain unchanged; this is not a new full national release.

| Census | Credited population | Fixed common control | Coverage | Remaining |
|---|---:|---:|---:|---:|
|2002|144596757|145166731|99.6073659604555%|569974|
|2010|142136958|142856536|99.49629326025376%|719578|
|2021|144308122|144699673|99.72940436430703%|391551|

31 actual census UID routes were integrated: 24 new credits and 7 already credited. Increment over the conservative application15 union: 12898 / 2317 / 0 people. The resulting union contains 431781 native UIDs; six federal territory rows are added once, separately. Population overlay and national controls are unchanged.

21 inclusion/merger edges and 25 typed events preserve historical transformations separately from ordinary same-place components. Source packet flags describing their former separate axis are preserved; this application explicitly integrates approved routes into the requested working union. No graph union, invented census record, assigned child population, or replacement of an unknown with zero occurs. Year-only Gornaya Polyana event timing leaves its 2010 own count unknown. The ordinary complete-three-census component count remains 142696; working coverage is not strict full3 coverage.

`applied/integrated_credited_UID_roster.csv.gz` is the durable membership and effective population table. `applied/coverage.csv` is the resulting metric. Typed events, routes, year statuses and input hashes are alongside it. Independent bounded checks are in `../over500_lifecycle_integration_review_20261009/final_check_receipt.json`.

Reproduce after reconstructing the pinned fifteenth State using `../over500_root_20261009/fifteenth_recipe.json`:

```bash
python research_rebuild/evidence/over500_lifecycle_integration_20261009/integrate.py \
  --state-dir /dev/shm/over500-20261009/fifteenth-application \
  --output research_rebuild/evidence/over500_lifecycle_integration_20261009/applied \
  --full-output /dev/shm/over500-20261009/integrated-working-target
```

The full generated observation/point/credit parquet is outside Git at the full-output path and reproducible from pinned inputs. Its digest is recorded in the application and review receipts. Git stores the durable credit roster and replay code rather than claiming this temporary file is a published release attachment.
