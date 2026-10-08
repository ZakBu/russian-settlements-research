# Working coverage receipt, 2026-10-07

Reproduce from repository root:

```bash
python research_rebuild/evidence/working_full_chain_20261007/build_report.py --stage 55
```

Frozen State() baseline and working_state_20261007.load(stage=selected_stage) reproduce their pinned population totals. Population is credited by exclusive source-ID union, never by summing successive receipts.

The leading table requires admitted point uses and finite source populations on all three census rows in every ordinary identity component. The one unknown-2010 component is excluded for every year; the separate all-three-point axis retains it with its unknown flag. Whole partitions and federal territories use their separately admitted representative-point scopes.

| Year | Ordinary full3, all three points and finite numbers | + whole partitions + Moscow/SPB territories | Common control % | + qualified physical scopes | Common control % | Qualified gap to 99% |
|---|---:|---:|---:|---:|---:|---:|
| 2002 | 126,913,772 | 142,071,955 | 97.86812 | 142,361,601 | 98.06765 | 1,353,463 |
| 2010 | 124,056,798 | 140,547,095 | 98.38338 | 140,871,307 | 98.61033 | 556,664 |
| 2021 | 124,669,530 | 143,386,500 | 99.09248 | 143,838,446 | 99.40482 | 0 |

Companion axis: an ordinary row has its own point use and a three-year identity component, while another census row in that component may lack a point use. These totals are not labelled as all-three-point coverage.

| Year | Ordinary own-point + full3 identity | + partitions + FED | Common control % | + qualified physical scopes | Common control % |
|---|---:|---:|---:|---:|---:|
| 2002 | 126,914,004 | 142,072,187 | 97.86828 | 142,361,833 | 98.06781 |
| 2010 | 124,057,075 | 140,547,372 | 98.38358 | 140,871,584 | 98.61053 |
| 2021 | 124,669,578 | 143,386,548 | 99.09252 | 143,838,494 | 99.40485 |

The ordinary point_and_full_three_census_identity axis requires a point on the row being counted and a three-year identity component. The stricter full_three_census_with_all_component_points axis requires an admitted own-point use on each of its three census source rows. The small difference is listed explicitly in own_point_full3_components_missing_other_year_points.csv.

Coordinate origin and claimed quality counts are recorded separately. Seven proximity candidates remain held for physical source county contradictions. For example, Курилово (2,371 in the historical Подольский source) was near a 33-person Солнечногорск namesake because the earlier accepted coordinate itself was wrongly bound; that candidate edge remains excluded. See the pinned root_review_physical_county_context.csv evidence.

The mixed-grain exclusive source-ID union reaches 99% of common control for 2021; 2002, 2010 remains below 99%. Ordinary settlement full3 coverage and the all-three-census-year goal remain unmet. Official national and common controls are explicit in the JSON; 2021 common excludes Crimea and Sevastopol. The 2010 selected-source population shortfall remains 493,512. Regional rankings include both selected-population gaps and a separate 2010 official-control reconciliation with 83 explicit region mappings folded to 80 disjoint controls. Nenets folds into Arkhangelsk; Khanty-Mansi and Yamalo-Nenets fold into Tyumen. This is a region-level check, not a full municipal audit.

Qualified physical scopes contain 2429 three-observed-year series, including two secondary-supported 2021 children and one dated secondary 2002 observation. Nine unpointed candidate series are held and excluded. Later Norilsk districts and auxiliary 2010 observations contribute zero additive population. Existing primary source IDs are credited once in the sidecar union.

Accepted points are reviewed representative point uses, including retrospective continuity inferences. Coordinate calibration, census-date measurements, boundary equivalence and ordinary NP grain equivalence for physical sidecars are not asserted. Source population values and quality flags are unchanged. Candidate-only paths, 2014-only paths and absorption-only receiving-parent context never count as full3.

The existing strict top100 and regional ranking files retain ordinary full3 + point semantics. regional_final_mixed_residual_rank.csv and top100_final_mixed_residual_YEAR.csv rank actual remaining native source IDs after all finite ordinary, partition, qualified, named and territorial credits. Regional denominators use selected known native population; national control shortfalls are not assigned to individual settlements. Growth flags describe accepted adjacent ordinary census pairs; zero and unknown populations are not imputed.

Wall time: 204.261 seconds. Exact graph, point, delta, sidecar and code hashes are in input_hash_manifest.json.

Separate named merger/event lineage extension: 10 complete named rosters, 30 census-year group observations and 10 receiving-parent representative scope points. This different grain retains boundary comparability UNKNOWN and secondary documented event sources; historical constituents are not asserted as ordinary settlements individually observed in all three censuses.

| Year | Finite ordinary + partitions + qualified + FED | Named lineage net exclusive source-ID gain | Extended lineage population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 142,361,601 | 607,784 | 142,969,385 | 98.48633 |
| 2010 | 140,871,307 | 317,161 | 141,188,468 | 98.83235 |
| 2021 | 143,838,446 | 0 | 143,838,446 | 99.40482 |

The individual lineage observations, complete constituent source IDs, scope points and event relations are exported separately in named_merger_lineage_*.csv. Ordinary NP3 and the qualified physical register remain separate. No group sum is added on top of constituent credits.

Separate complete territorial scopes: 37 scopes with 111 observed census-year values. Published city territories and transferred municipality grains remain explicit; boundary comparability, legal annexation and historical individual NP point coverage are not asserted. Native constituent IDs are credited once; secondary municipal aggregates are descriptive.

| Year | + complete territorial scopes | Common control % | Gap to 99% |
|---|---:|---:|---:|
| 2002 | 143,622,321 | 98.93611 | 92,743 |
| 2010 | 141,358,940 | 98.95168 | 69,031 |
| 2021 | 143,848,871 | 99.41202 | 0 |

Separate dated-year display register: 38 trajectories and 114 actual source observations. Their secondary2002 calendar-year counts lack explicit census designation. They add zero population to every census-coverage axis and remain outside qualified census series.

Separate direct inclusion transformation paths: 39 dated events connect independently observed historical localities with their own points to actual receiving-city census context. The included_in relation does not assert ordinary same-place identity, a complete whole-city roster, comparable boundaries or an individual child2021 population. Original final mixed census coverage and its goal status remain unchanged.

| Year | Original mixed census population | Direct historical native ID gain | Separate transformation path population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 143,622,321 | 266,805 | 143,889,126 | 99.11991 |
| 2010 | 141,358,940 | 53,202 | 141,412,142 | 98.98892 |
| 2021 | 143,848,871 | 0 | 143,848,871 | 99.41202 |

["Lopatinskyeventyear2004fromcachedownentityliteralrudescription+P131receivingcity, noexactdayorprimarylawclaimed", ["Secondary own-Wikipedia inclusions; no primary law reopened", "BelyeStolbybody2004/intro2005conflictpreserved", "Barybinoexplicitnamedintermediatepath", "Citedactdatesnotverifiedoperativedates", "Gikalo2020countyjurisdictiondistinctfrom2021cityinclusion", "Roslyakovo2010legacyoriginalDOCunmounted; exactrawparserledgeronlyverified"], {"candidate_agent_original_claim": "not mounted in searched location; exact primary raw-parser ledger only reopened", "ROOT_actual_path": "/workspace/settlements-work/sources/r2-missing/murmansk_population.doc", "ROOT_bytes": 384000, "ROOT_sha256": "d4bdb36d541ed3f90594ba95ee209fabafc5f02088758e46a143e1155f5fbc57", "ROOT_binary_available_and_bytes_verified": true, "ROOT_fresh_DOC_parser_rerun_asserted": false, "native_population_8696_retained_from_existing_primary_raw_parser_ledger": true}, "Secondary own-place Wikipedia dated inclusions; year or stated day precision retained, primary legal-operative dates not asserted. Former own locality point continuity inferred; no reconstructed fixed-boundary counts.", "Own secondary source reports incorporation and former PGT status; exact municipal-law day and historical-boundary equivalence remain unverified."]

Separate formation and direct lifecycle source-ID union: authentic historical Kievsky/Kokoshkino PGT observations retain their own physical points; whole municipalities have independently observed 2010/2021 quantities and municipal representative points. Mosrentgen retains two existing whole2002 predecessor references and its complete2010 published native roster at municipal grain. The 4,654 difference remains unallocated. No own2002 Mosrentgen municipality, individual NP2021 count, ordinary NP3 identity or comparable boundaries are asserted.

| Year | Direct lifecycle population | Additional formation UID gain | Lifecycle plus formation population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 143,889,126 | 18,156 | 143,907,282 | 99.13241 |
| 2010 | 141,412,142 | 32,044 | 141,444,186 | 99.01135 |
| 2021 | 143,848,871 | 0 | 143,848,871 | 99.41202 |

["Cached secondary formation/transfer statements, primary legal-operative dates unverified; municipal source-year boundaries and protected2010 leaf-control differences unknown and unallocated. Modern point continuity inferred, not censusday measurements.", "Cached secondary formation/transfer statements, primary legal-operative dates unverified; municipal source-year boundaries and protected2010 leaf-control differences unknown and unallocated. Modern point continuity inferred, not censusday measurements."]

EAO source namespace: 98 original2002 rows use the source header Sheet1!A1 Еврейская АО for effective regional context. Export keeps the imported region values and separately records the effective namespace and pinned interpretation input. Original source populations, quality, row locators and metadata remain unchanged; the interpretation alone adds no finite three-year histories.

Imported empty population quality values remain unknown, unchanged: 2002: 0 export rows, 2010: 3 export rows, 2021: 0 export rows.
