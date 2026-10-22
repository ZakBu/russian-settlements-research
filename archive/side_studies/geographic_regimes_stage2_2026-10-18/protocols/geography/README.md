# Stage II geography — executed 2026-10-18 UTC

Input stage71 exactly142570rows, SHA256 d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c. New files only; no stageI/raw/main changes. `protocol_geography.md` written before aggregation. Main run `python geography.py`; then `python enrich.py`, `python finalize.py`, `python figures.py`. Scripts record execution hashes; `receipts.json` is the original stage receipt, `enrichment_receipt.json` intermediate, `FINAL_CHECKSUMS.json` authoritative enriched-table hashes. Figures have own hashes.

Portable replay (Python3.12; numpy2.3.5 pandas2.2.3 pyproj3.8.0 scikit-learn1.8.0 matplotlib3.10.8):

```
python reproduce_geography.py --input /path/ordinary_full3_with_primary_population_sources.csv.gz --federal /path/accepted_common_federal_territory_axis.csv --workdir /path/new-run
```

Replay materializes scripts with input-path substitutions, preserving actual executed code and its checksum. Ordinary input must match frozen SHA. No downloaded libraries required in original environment. Every final metrics unit retains all rows and fixed2002 geographic assignment. Default NN search uses fixed2002 positions for both years; `nn2021_original_coords` is coordinate sensitivity. `nn2021_survivor_neighbors` removes new-positive2002zero neighbors for sensitivity. Raw all-year numeric2010 retained; no quality exclusion by plausibility.

Exact-distance completeness: WGS84 line metric has M,N>=a(1−e²), hence WGS84 distance >=6335.439327292819km × spherical central angle between geodetic coordinates. Candidate radius bounded by initial geodesic best/Rmin cannot omit a nearer point. All candidate distances evaluated by Geod.inv, origin UID excluded, distinct colocated UID distance0.48 separate brute-force full-neighbor checks on deterministic24 sampled positive2002 origins across2002/2021 returned0 discrepancy. These are self-checks, not independent reproduction.

Supported local detailed analysis requires>=20 positive2002rows:50km1359 of3607 occupiedcells;25km2117/9677;100km566/1344; shifted50km1377/3579;81regions. Every partition conserves142570rows, population2002=127397236 and2021=125132003. No ordinary-panel99.5%coverage claim. EPSG6933 latitude validity checked:41.28..73.51,0 outside86°.244 rows share coordinates; original2021 coordinate drift694rows>1km,23>10km. Distances remain in km, projection only assigns cells.

`top10/1`group size=ceil(fraction×ALL panel rows perunit), sorted2002population descending then UID. Zeros included in rowcount, same composition fixed acrossyears. Survival only positive2002 denominator; reentry only zero2002 denominator. Zero NN baseline ratio is NaN, no epsilon. No statistical significance, functional accessibility, land-area contraction, or legal disappearance asserted. Source/coverage uncertainty survives exact arithmetic. OrdinaryNN excludes federal aggregate masses; centre100k2002 plusfederal variant adds Moscow/SPb representativeanchors only as contextual distances, not point populations. No2021outcome enters matching-baseline fields.

Important NN distinction: paired-change median0 in1356/1359supported50kmcells. Difference of the two distance-distribution medians is a different statistic and is separately named. Upper-tailp90 is the preplanned complementary measure, not evidence that median neighborhoods all changed.
