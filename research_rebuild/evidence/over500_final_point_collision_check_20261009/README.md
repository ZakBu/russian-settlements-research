Read-only exact same-year accepted-ownpoint collision screen.

59,652 threshold records; all 59,643 records with has_ownpoint=True examined. One group of two records remains: Kaluga 2010, село совхоза Чкаловский (801) and село Совхоз им. Ленина (545), shared point 54.5599717, 35.8822581. Duplication is reported without inferring an error or exemption. Nine records without accepted ownpoints are outside this requested point-equality comparison.

Reproduce:

```sh
python research_rebuild/evidence/over500_final_point_collision_check_20261009/check.py --input /dev/shm/over500-20261009/eleventh-application/all_whole_NP_over500_record_status.csv.gz --output /dev/shm/over500-final-point-collision-recheck
```

Input and output hashes, exact comparison conditions, and row totals are in receipt.json. No source or accepted data was changed.
