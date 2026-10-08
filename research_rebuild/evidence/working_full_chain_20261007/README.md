# Working coverage receipt, 2026-10-07

Reproduce from repository root:

```bash
python research_rebuild/evidence/working_full_chain_20261007/build_report.py --stage 26
```

Frozen State() baseline and working_state_20261007.load(stage=selected_stage) reproduce their pinned population totals. Population is credited by exclusive source-ID union, never by summing successive receipts.

The leading table requires admitted point uses and finite source populations on all three census rows in every ordinary identity component. The one unknown-2010 component is excluded for every year; the separate all-three-point axis retains it with its unknown flag. Whole partitions and federal territories use their separately admitted representative-point scopes.

| Year | Ordinary full3, all three points and finite numbers | + whole partitions + Moscow/SPB territories | Common control % | + qualified physical scopes | Common control % | Qualified gap to 99% |
|---|---:|---:|---:|---:|---:|---:|
| 2002 | 126,338,387 | 141,489,642 | 97.46699 | 141,829,408 | 97.70104 | 1,885,656 |
| 2010 | 123,516,746 | 140,001,018 | 98.00113 | 140,301,827 | 98.21170 | 1,126,144 |
| 2021 | 124,112,953 | 142,825,447 | 98.70475 | 143,450,116 | 99.13645 | 0 |

Companion axis: an ordinary row has its own point use and a three-year identity component, while another census row in that component may lack a point use. These totals are not labelled as all-three-point coverage.

| Year | Ordinary own-point + full3 identity | + partitions + FED | Common control % | + qualified physical scopes | Common control % |
|---|---:|---:|---:|---:|---:|
| 2002 | 126,338,619 | 141,489,874 | 97.46715 | 141,829,640 | 97.70120 |
| 2010 | 123,519,385 | 140,003,657 | 98.00298 | 140,304,466 | 98.21354 |
| 2021 | 124,114,889 | 142,827,383 | 98.70609 | 143,452,052 | 99.13779 |

The ordinary point_and_full_three_census_identity axis requires a point on the row being counted and a three-year identity component. The stricter full_three_census_with_all_component_points axis requires an admitted own-point use on each of its three census source rows. The small difference is listed explicitly in own_point_full3_components_missing_other_year_points.csv.

Coordinate origin and claimed quality counts are recorded separately. Seven proximity candidates remain held for physical source county contradictions. For example, Курилово (2,371 in the historical Подольский source) was near a 33-person Солнечногорск namesake because the earlier accepted coordinate itself was wrongly bound; that candidate edge remains excluded. See the pinned root_review_physical_county_context.csv evidence.

The mixed-grain exclusive source-ID union reaches 99% of common control for 2021; 2002, 2010 remains below 99%. Ordinary settlement full3 coverage and the all-three-census-year goal remain unmet. Official national and common controls are explicit in the JSON; 2021 common excludes Crimea and Sevastopol. The 2010 selected-source population shortfall remains 493,512. Regional rankings include both selected-population gaps and a separate 2010 official-control reconciliation with 83 explicit region mappings folded to 80 disjoint controls. Nenets folds into Arkhangelsk; Khanty-Mansi and Yamalo-Nenets fold into Tyumen. This is a region-level check, not a full municipal audit.

Qualified physical scopes contain 1919 three-observed-year series, including two secondary-supported 2021 children and one dated secondary 2002 observation. Nine unpointed candidate series are held and excluded. Later Norilsk districts and auxiliary 2010 observations contribute zero additive population. Existing primary source IDs are credited once in the sidecar union.

Accepted points are reviewed representative point uses, including retrospective continuity inferences. Coordinate calibration, census-date measurements, boundary equivalence and ordinary NP grain equivalence for physical sidecars are not asserted. Source population values and quality flags are unchanged. Candidate-only paths, 2014-only paths and absorption-only receiving-parent context never count as full3.

The existing strict top100 and regional ranking files retain ordinary full3 + point semantics. regional_final_mixed_residual_rank.csv and top100_final_mixed_residual_YEAR.csv rank actual remaining native source IDs after all finite ordinary, partition, qualified, named and territorial credits. Regional denominators use selected known native population; national control shortfalls are not assigned to individual settlements. Growth flags describe accepted adjacent ordinary census pairs; zero and unknown populations are not imputed.

Wall time: 147.69 seconds. Exact graph, point, delta, sidecar and code hashes are in input_hash_manifest.json.

Separate named merger/event lineage extension: 10 complete named rosters, 30 census-year group observations and 10 receiving-parent representative scope points. This different grain retains boundary comparability UNKNOWN and secondary documented event sources; historical constituents are not asserted as ordinary settlements individually observed in all three censuses.

| Year | Finite ordinary + partitions + qualified + FED | Named lineage net exclusive source-ID gain | Extended lineage population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 141,829,408 | 607,784 | 142,437,192 | 98.11972 |
| 2010 | 140,301,827 | 317,161 | 140,618,988 | 98.43371 |
| 2021 | 143,450,116 | 0 | 143,450,116 | 99.13645 |

The individual lineage observations, complete constituent source IDs, scope points and event relations are exported separately in named_merger_lineage_*.csv. Ordinary NP3 and the qualified physical register remain separate. No group sum is added on top of constituent credits.

Separate complete territorial scopes: 9 scopes with 27 observed census-year values. Published city territories and transferred municipality grains remain explicit; boundary comparability, legal annexation and historical individual NP point coverage are not asserted. Native constituent IDs are credited once; secondary municipal aggregates are descriptive.

| Year | + complete territorial scopes | Common control % | Gap to 99% |
|---|---:|---:|---:|
| 2002 | 142,704,062 | 98.30356 | 1,011,002 |
| 2010 | 140,637,514 | 98.44668 | 790,457 |
| 2021 | 143,451,943 | 99.13771 | 0 |

Imported empty population quality values remain unknown, unchanged: 2002: 0 export rows, 2010: 3 export rows, 2021: 0 export rows.
