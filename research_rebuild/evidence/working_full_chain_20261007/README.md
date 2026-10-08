# Working coverage receipt, 2026-10-07

Reproduce from repository root:

```bash
python research_rebuild/evidence/working_full_chain_20261007/build_report.py --stage 30
```

Frozen State() baseline and working_state_20261007.load(stage=selected_stage) reproduce their pinned population totals. Population is credited by exclusive source-ID union, never by summing successive receipts.

The leading table requires admitted point uses and finite source populations on all three census rows in every ordinary identity component. The one unknown-2010 component is excluded for every year; the separate all-three-point axis retains it with its unknown flag. Whole partitions and federal territories use their separately admitted representative-point scopes.

| Year | Ordinary full3, all three points and finite numbers | + whole partitions + Moscow/SPB territories | Common control % | + qualified physical scopes | Common control % | Qualified gap to 99% |
|---|---:|---:|---:|---:|---:|---:|
| 2002 | 126,512,604 | 141,663,859 | 97.58700 | 141,943,926 | 97.77993 | 1,771,138 |
| 2010 | 123,680,510 | 140,164,782 | 98.11576 | 140,465,591 | 98.32633 | 962,380 |
| 2021 | 124,284,015 | 142,996,509 | 98.82297 | 143,529,232 | 99.19112 | 0 |

Companion axis: an ordinary row has its own point use and a three-year identity component, while another census row in that component may lack a point use. These totals are not labelled as all-three-point coverage.

| Year | Ordinary own-point + full3 identity | + partitions + FED | Common control % | + qualified physical scopes | Common control % |
|---|---:|---:|---:|---:|---:|
| 2002 | 126,512,836 | 141,664,091 | 97.58716 | 141,944,158 | 97.78009 |
| 2010 | 123,680,787 | 140,165,059 | 98.11596 | 140,465,868 | 98.32653 |
| 2021 | 124,284,063 | 142,996,557 | 98.82300 | 143,529,280 | 99.19116 |

The ordinary point_and_full_three_census_identity axis requires a point on the row being counted and a three-year identity component. The stricter full_three_census_with_all_component_points axis requires an admitted own-point use on each of its three census source rows. The small difference is listed explicitly in own_point_full3_components_missing_other_year_points.csv.

Coordinate origin and claimed quality counts are recorded separately. Seven proximity candidates remain held for physical source county contradictions. For example, Курилово (2,371 in the historical Подольский source) was near a 33-person Солнечногорск namesake because the earlier accepted coordinate itself was wrongly bound; that candidate edge remains excluded. See the pinned root_review_physical_county_context.csv evidence.

The mixed-grain exclusive source-ID union reaches 99% of common control for 2021; 2002, 2010 remains below 99%. Ordinary settlement full3 coverage and the all-three-census-year goal remain unmet. Official national and common controls are explicit in the JSON; 2021 common excludes Crimea and Sevastopol. The 2010 selected-source population shortfall remains 493,512. Regional rankings include both selected-population gaps and a separate 2010 official-control reconciliation with 83 explicit region mappings folded to 80 disjoint controls. Nenets folds into Arkhangelsk; Khanty-Mansi and Yamalo-Nenets fold into Tyumen. This is a region-level check, not a full municipal audit.

Qualified physical scopes contain 1919 three-observed-year series, including two secondary-supported 2021 children and one dated secondary 2002 observation. Nine unpointed candidate series are held and excluded. Later Norilsk districts and auxiliary 2010 observations contribute zero additive population. Existing primary source IDs are credited once in the sidecar union.

Accepted points are reviewed representative point uses, including retrospective continuity inferences. Coordinate calibration, census-date measurements, boundary equivalence and ordinary NP grain equivalence for physical sidecars are not asserted. Source population values and quality flags are unchanged. Candidate-only paths, 2014-only paths and absorption-only receiving-parent context never count as full3.

The existing strict top100 and regional ranking files retain ordinary full3 + point semantics. regional_final_mixed_residual_rank.csv and top100_final_mixed_residual_YEAR.csv rank actual remaining native source IDs after all finite ordinary, partition, qualified, named and territorial credits. Regional denominators use selected known native population; national control shortfalls are not assigned to individual settlements. Growth flags describe accepted adjacent ordinary census pairs; zero and unknown populations are not imputed.

Wall time: 162.37 seconds. Exact graph, point, delta, sidecar and code hashes are in input_hash_manifest.json.

Separate named merger/event lineage extension: 10 complete named rosters, 30 census-year group observations and 10 receiving-parent representative scope points. This different grain retains boundary comparability UNKNOWN and secondary documented event sources; historical constituents are not asserted as ordinary settlements individually observed in all three censuses.

| Year | Finite ordinary + partitions + qualified + FED | Named lineage net exclusive source-ID gain | Extended lineage population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 141,943,926 | 607,784 | 142,551,710 | 98.19861 |
| 2010 | 140,465,591 | 317,161 | 140,782,752 | 98.54835 |
| 2021 | 143,529,232 | 0 | 143,529,232 | 99.19112 |

The individual lineage observations, complete constituent source IDs, scope points and event relations are exported separately in named_merger_lineage_*.csv. Ordinary NP3 and the qualified physical register remain separate. No group sum is added on top of constituent credits.

Separate complete territorial scopes: 19 scopes with 57 observed census-year values. Published city territories and transferred municipality grains remain explicit; boundary comparability, legal annexation and historical individual NP point coverage are not asserted. Native constituent IDs are credited once; secondary municipal aggregates are descriptive.

| Year | + complete territorial scopes | Common control % | Gap to 99% |
|---|---:|---:|---:|
| 2002 | 142,995,393 | 98.50425 | 719,671 |
| 2010 | 140,851,653 | 98.59658 | 576,318 |
| 2021 | 143,539,653 | 99.19833 | 0 |

Imported empty population quality values remain unknown, unchanged: 2002: 0 export rows, 2010: 3 export rows, 2021: 0 export rows.
