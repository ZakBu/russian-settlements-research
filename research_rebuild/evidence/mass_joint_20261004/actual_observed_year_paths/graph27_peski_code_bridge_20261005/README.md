# Graph27: Moscow-oblast Peski code bridge and corrected coverage measure

## Applied decision

One bounded `same_place` edge links the selected 2002 and 2010 rows for Пески, Московская область (3,736 and 3,847). Both rows resolve to the same unique 2009 OKATO / 2011 GeoKLADR locality code and raw named point (55.211577, 38.773192). The exact 2010 population retains its secondary confidentiality-protected, exact-scope-unverified status. Population and boundary comparability are not asserted. No 2021 edge is admitted: the nearby 2021 record has a type transition and needs an event/source witness.

Independent bounded review screened the five remaining exact typed-name/type/region candidates in this bridge cohort. Пески alone was eligible. Лондоко, Пироговский, Львовский, and Юбилейный remain held for the collision, missing-successor, or competing-identity reasons described in the decision diary.

## Coverage measurement correction

The previous actual-year-path calculator restricted its additions to residual rows classified `identity_path`. This excluded eligible rows classified `identity_and_point` or `point` when an admitted decision supplied both a path and a coordinate. Graph27 Пески rows were a concrete reproducer: both exact selected rows were in the frozen residual as `identity_and_point`, and after Graph27 both had accepted points and a 2002–2010 path. The old calculator consequently omitted both rows.

`measure_actual_observed_year_path_coverage_v2_20261005.py` now evaluates every exact additive selected row in the frozen residual against the actual accepted-point and >=2-observed-year-path predicates, regardless of its old missing-axis label. It does not impute missing census years and excludes a component with duplicate selected records in a year. Corrected residual additions by prior axis are recorded in each coverage JSON and row-level CSV.

| Graph | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| Graph25 corrected coordinate + path (>=2 actual census years) | 97.680050% | 98.141378% | 99.158829% |
| Graph26 corrected coordinate + path (>=2 actual census years) | 97.682060% | 98.143458% | 99.158829% |
| Graph27 corrected coordinate + path (>=2 actual census years) | 97.684633% | 98.146151% | 99.158829% |

Graph27 population numerators are 141,805,589 / 140,208,191 / 145,944,069 against official controls 145,166,731 / 142,856,536 / 147,182,123. Remaining to 99% is 1,909,475 / 1,219,780 / 0 people. These are mixed available-year path and reviewed-scope results; they do not mean every included place has a full 2002–2010–2021 chain.

The strict ordinary-NP full three-census-chain result is unchanged at 125,083,555 / 122,370,619 / 122,902,334 (86.165442% / 85.659797% / 83.503575%). No full chain is manufactured for Пески.

## Reproduction and limits

- Application script: `research_rebuild/mass_linkage/apply_graph27_peski_historical_code_bridge_20261005.py`.
- Corrected measurement script: `research_rebuild/mass_linkage/measure_actual_observed_year_path_coverage_v2_20261005.py`.
- Application receipt pins the selected layer, Graph26 edge and point inputs, raw source hashes and exact DBF locator.
- Coverage JSONs pin the inputs and publish Graph25/26/27 corrected outputs; the Graph27 CSV gives qualifying residual rows.
- The combined accepted national Parquet ledgers remain in the working data volume, outside this Git checkout. This commit records the reproducible delta and receipt, not a full duplicate of those large ledgers.
- The 2010 population-source limitation and unknown census-boundary comparability remain visible. The point is a 2011 GeoKLADR representative point with unknown measurement date, not a survey-date coordinate.
