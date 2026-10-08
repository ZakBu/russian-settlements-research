# Working coverage receipt, 2026-10-07

Reproduce from repository root:

```bash
python research_rebuild/evidence/working_full_chain_20261007/build_report.py --stage 46
```

Frozen State() baseline and working_state_20261007.load(stage=selected_stage) reproduce their pinned population totals. Population is credited by exclusive source-ID union, never by summing successive receipts.

The leading table requires admitted point uses and finite source populations on all three census rows in every ordinary identity component. The one unknown-2010 component is excluded for every year; the separate all-three-point axis retains it with its unknown flag. Whole partitions and federal territories use their separately admitted representative-point scopes.

| Year | Ordinary full3, all three points and finite numbers | + whole partitions + Moscow/SPB territories | Common control % | + qualified physical scopes | Common control % | Qualified gap to 99% |
|---|---:|---:|---:|---:|---:|---:|
| 2002 | 126,709,814 | 141,861,069 | 97.72285 | 142,141,187 | 97.91581 | 1,573,877 |
| 2010 | 123,868,391 | 140,352,663 | 98.24728 | 140,679,069 | 98.47577 | 748,902 |
| 2021 | 124,470,404 | 143,182,898 | 98.95178 | 143,671,650 | 99.28955 | 0 |

Companion axis: an ordinary row has its own point use and a three-year identity component, while another census row in that component may lack a point use. These totals are not labelled as all-three-point coverage.

| Year | Ordinary own-point + full3 identity | + partitions + FED | Common control % | + qualified physical scopes | Common control % |
|---|---:|---:|---:|---:|---:|
| 2002 | 126,710,046 | 141,861,301 | 97.72301 | 142,141,419 | 97.91597 |
| 2010 | 123,868,668 | 140,352,940 | 98.24748 | 140,679,346 | 98.47596 |
| 2021 | 124,470,452 | 143,182,946 | 98.95181 | 143,671,698 | 99.28958 |

The ordinary point_and_full_three_census_identity axis requires a point on the row being counted and a three-year identity component. The stricter full_three_census_with_all_component_points axis requires an admitted own-point use on each of its three census source rows. The small difference is listed explicitly in own_point_full3_components_missing_other_year_points.csv.

Coordinate origin and claimed quality counts are recorded separately. Seven proximity candidates remain held for physical source county contradictions. For example, Курилово (2,371 in the historical Подольский source) was near a 33-person Солнечногорск namesake because the earlier accepted coordinate itself was wrongly bound; that candidate edge remains excluded. See the pinned root_review_physical_county_context.csv evidence.

The mixed-grain exclusive source-ID union reaches 99% of common control for 2021; 2002, 2010 remains below 99%. Ordinary settlement full3 coverage and the all-three-census-year goal remain unmet. Official national and common controls are explicit in the JSON; 2021 common excludes Crimea and Sevastopol. The 2010 selected-source population shortfall remains 493,512. Regional rankings include both selected-population gaps and a separate 2010 official-control reconciliation with 83 explicit region mappings folded to 80 disjoint controls. Nenets folds into Arkhangelsk; Khanty-Mansi and Yamalo-Nenets fold into Tyumen. This is a region-level check, not a full municipal audit.

Qualified physical scopes contain 2187 three-observed-year series, including two secondary-supported 2021 children and one dated secondary 2002 observation. Nine unpointed candidate series are held and excluded. Later Norilsk districts and auxiliary 2010 observations contribute zero additive population. Existing primary source IDs are credited once in the sidecar union.

Accepted points are reviewed representative point uses, including retrospective continuity inferences. Coordinate calibration, census-date measurements, boundary equivalence and ordinary NP grain equivalence for physical sidecars are not asserted. Source population values and quality flags are unchanged. Candidate-only paths, 2014-only paths and absorption-only receiving-parent context never count as full3.

The existing strict top100 and regional ranking files retain ordinary full3 + point semantics. regional_final_mixed_residual_rank.csv and top100_final_mixed_residual_YEAR.csv rank actual remaining native source IDs after all finite ordinary, partition, qualified, named and territorial credits. Regional denominators use selected known native population; national control shortfalls are not assigned to individual settlements. Growth flags describe accepted adjacent ordinary census pairs; zero and unknown populations are not imputed.

Wall time: 160.446 seconds. Exact graph, point, delta, sidecar and code hashes are in input_hash_manifest.json.

Separate named merger/event lineage extension: 10 complete named rosters, 30 census-year group observations and 10 receiving-parent representative scope points. This different grain retains boundary comparability UNKNOWN and secondary documented event sources; historical constituents are not asserted as ordinary settlements individually observed in all three censuses.

| Year | Finite ordinary + partitions + qualified + FED | Named lineage net exclusive source-ID gain | Extended lineage population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 142,141,187 | 607,784 | 142,748,971 | 98.33449 |
| 2010 | 140,679,069 | 317,161 | 140,996,230 | 98.69778 |
| 2021 | 143,671,650 | 0 | 143,671,650 | 99.28955 |

The individual lineage observations, complete constituent source IDs, scope points and event relations are exported separately in named_merger_lineage_*.csv. Ordinary NP3 and the qualified physical register remain separate. No group sum is added on top of constituent credits.

Separate complete territorial scopes: 37 scopes with 111 observed census-year values. Published city territories and transferred municipality grains remain explicit; boundary comparability, legal annexation and historical individual NP point coverage are not asserted. Native constituent IDs are credited once; secondary municipal aggregates are descriptive.

| Year | + complete territorial scopes | Common control % | Gap to 99% |
|---|---:|---:|---:|
| 2002 | 143,401,907 | 98.78428 | 313,157 |
| 2010 | 141,166,702 | 98.81711 | 261,269 |
| 2021 | 143,682,075 | 99.29675 | 0 |

Separate dated-year display register: 38 trajectories and 114 actual source observations. Their secondary2002 calendar-year counts lack explicit census designation. They add zero population to every census-coverage axis and remain outside qualified census series.

Separate direct inclusion transformation paths: 18 dated events connect independently observed historical localities with their own points to actual receiving-city census context. The included_in relation does not assert ordinary same-place identity, a complete whole-city roster, comparable boundaries or an individual child2021 population. Original final mixed census coverage and its goal status remain unchanged.

| Year | Original mixed census population | Direct historical native ID gain | Separate transformation path population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 143,401,907 | 152,733 | 143,554,640 | 98.88949 |
| 2010 | 141,166,702 | 45,109 | 141,211,811 | 98.84869 |
| 2021 | 143,682,075 | 0 | 143,682,075 | 99.29675 |

["Lopatinskyeventyear2004fromcachedownentityliteralrudescription+P131receivingcity, noexactdayorprimarylawclaimed", ["Secondary own-Wikipedia inclusions; no primary law reopened", "BelyeStolbybody2004/intro2005conflictpreserved", "Barybinoexplicitnamedintermediatepath", "Citedactdatesnotverifiedoperativedates", "Gikalo2020countyjurisdictiondistinctfrom2021cityinclusion", "Roslyakovo2010legacyoriginalDOCunmounted; exactrawparserledgeronlyverified"], {"candidate_agent_original_claim": "not mounted in searched location; exact primary raw-parser ledger only reopened", "ROOT_actual_path": "/workspace/settlements-work/sources/r2-missing/murmansk_population.doc", "ROOT_bytes": 384000, "ROOT_sha256": "d4bdb36d541ed3f90594ba95ee209fabafc5f02088758e46a143e1155f5fbc57", "ROOT_binary_available_and_bytes_verified": true, "ROOT_fresh_DOC_parser_rerun_asserted": false, "native_population_8696_retained_from_existing_primary_raw_parser_ledger": true}]

Imported empty population quality values remain unknown, unchanged: 2002: 0 export rows, 2010: 3 export rows, 2021: 0 export rows.
