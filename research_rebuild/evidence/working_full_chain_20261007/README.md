# Working coverage receipt, 2026-10-07

Reproduce from repository root:

```bash
python research_rebuild/evidence/working_full_chain_20261007/build_report.py --stage 68
```

Frozen State() baseline and working_state_20261007.load(stage=selected_stage) reproduce their pinned population totals. Population is credited by exclusive source-ID union, never by summing successive receipts.

The leading table requires admitted point uses and finite source populations on all three census rows in every ordinary identity component. The one unknown-2010 component is excluded for every year; the separate all-three-point axis retains it with its unknown flag. Whole partitions and federal territories use their separately admitted representative-point scopes.

| Year | Ordinary full3, all three points and finite numbers | + whole partitions + Moscow/SPB territories | Common control % | + qualified physical scopes | Common control % | Qualified gap to 99% |
|---|---:|---:|---:|---:|---:|---:|
| 2002 | 127,098,659 | 142,256,842 | 97.99548 | 142,529,907 | 98.18359 | 1,185,157 |
| 2010 | 124,220,368 | 140,710,665 | 98.49788 | 141,018,396 | 98.71330 | 409,575 |
| 2021 | 124,841,065 | 143,558,035 | 99.21103 | 143,963,593 | 99.49131 | 0 |

Companion axis: an ordinary row has its own point use and a three-year identity component, while another census row in that component may lack a point use. These totals are not labelled as all-three-point coverage.

| Year | Ordinary own-point + full3 identity | + partitions + FED | Common control % | + qualified physical scopes | Common control % |
|---|---:|---:|---:|---:|---:|
| 2002 | 127,098,660 | 142,256,843 | 97.99549 | 142,529,908 | 98.18359 |
| 2010 | 124,220,433 | 140,710,730 | 98.49793 | 141,018,461 | 98.71334 |
| 2021 | 124,843,212 | 143,560,182 | 99.21251 | 143,965,740 | 99.49279 |

The ordinary point_and_full_three_census_identity axis requires a point on the row being counted and a three-year identity component. The stricter full_three_census_with_all_component_points axis requires an admitted own-point use on each of its three census source rows. The small difference is listed explicitly in own_point_full3_components_missing_other_year_points.csv.

Coordinate origin and claimed quality counts are recorded separately. Seven proximity candidates remain held for physical source county contradictions. For example, Курилово (2,371 in the historical Подольский source) was near a 33-person Солнечногорск namesake because the earlier accepted coordinate itself was wrongly bound; that candidate edge remains excluded. See the pinned root_review_physical_county_context.csv evidence.

The mixed-grain exclusive source-ID union reaches 99% of common control for 2002, 2010, 2021; no census year remains below 99%. Ordinary settlement full3 coverage and the all-three-census-year goal remain unmet. Official national and common controls are explicit in the JSON; 2021 common excludes Crimea and Sevastopol. The 2010 selected-source population shortfall remains 493,512. Regional rankings include both selected-population gaps and a separate 2010 official-control reconciliation with 83 explicit region mappings folded to 80 disjoint controls. Nenets folds into Arkhangelsk; Khanty-Mansi and Yamalo-Nenets fold into Tyumen. This is a region-level check, not a full municipal audit.

Qualified physical scopes contain 2449 three-observed-year series, including two secondary-supported 2021 children and one dated secondary 2002 observation. Nine unpointed candidate series are held and excluded. Later Norilsk districts and auxiliary 2010 observations contribute zero additive population. Existing primary source IDs are credited once in the sidecar union.

Accepted points are reviewed representative point uses, including retrospective continuity inferences. Coordinate calibration, census-date measurements, boundary equivalence and ordinary NP grain equivalence for physical sidecars are not asserted. Source population values and quality flags are unchanged. Candidate-only paths, 2014-only paths and absorption-only receiving-parent context never count as full3.

The existing strict top100 and regional ranking files retain ordinary full3 + point semantics. regional_final_mixed_residual_rank.csv and top100_final_mixed_residual_YEAR.csv rank actual remaining native source IDs after all finite ordinary, partition, qualified, named and territorial credits. Regional denominators use selected known native population; national control shortfalls are not assigned to individual settlements. Growth flags describe accepted adjacent ordinary census pairs; zero and unknown populations are not imputed.

Wall time: 246.892 seconds. Exact graph, point, delta, sidecar and code hashes are in input_hash_manifest.json.

Separate named merger/event lineage extension: 10 complete named rosters, 30 census-year group observations and 10 receiving-parent representative scope points. This different grain retains boundary comparability UNKNOWN and secondary documented event sources; historical constituents are not asserted as ordinary settlements individually observed in all three censuses.

| Year | Finite ordinary + partitions + qualified + FED | Named lineage net exclusive source-ID gain | Extended lineage population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 142,529,907 | 604,671 | 143,134,578 | 98.60012 |
| 2010 | 141,018,396 | 317,161 | 141,335,557 | 98.93531 |
| 2021 | 143,963,593 | 0 | 143,963,593 | 99.49131 |

The individual lineage observations, complete constituent source IDs, scope points and event relations are exported separately in named_merger_lineage_*.csv. Ordinary NP3 and the qualified physical register remain separate. No group sum is added on top of constituent credits.

Separate complete territorial scopes: 37 scopes with 111 observed census-year values. Published city territories and transferred municipality grains remain explicit; boundary comparability, legal annexation and historical individual NP point coverage are not asserted. Native constituent IDs are credited once; secondary municipal aggregates are descriptive.

| Year | + complete territorial scopes | Common control % | Gap to 99% |
|---|---:|---:|---:|
| 2002 | 143,787,514 | 99.04991 | 0 |
| 2010 | 141,506,029 | 99.05464 | 0 |
| 2021 | 143,974,018 | 99.49851 | 0 |

Separate dated-year display register: 38 trajectories and 114 actual source observations. Their secondary2002 calendar-year counts lack explicit census designation. They add zero population to every census-coverage axis and remain outside qualified census series.

Separate direct inclusion transformation paths: 39 dated events connect independently observed historical localities with their own points to actual receiving-city census context. The included_in relation does not assert ordinary same-place identity, a complete whole-city roster, comparable boundaries or an individual child2021 population. Original final mixed census coverage and its goal status remain unchanged.

| Year | Original mixed census population | Direct historical native ID gain | Separate transformation path population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 143,787,514 | 266,805 | 144,054,319 | 99.23370 |
| 2010 | 141,506,029 | 53,202 | 141,559,231 | 99.09188 |
| 2021 | 143,974,018 | 0 | 143,974,018 | 99.49851 |

["Lopatinskyeventyear2004fromcachedownentityliteralrudescription+P131receivingcity, noexactdayorprimarylawclaimed", ["Secondary own-Wikipedia inclusions; no primary law reopened", "BelyeStolbybody2004/intro2005conflictpreserved", "Barybinoexplicitnamedintermediatepath", "Citedactdatesnotverifiedoperativedates", "Gikalo2020countyjurisdictiondistinctfrom2021cityinclusion", "Roslyakovo2010legacyoriginalDOCunmounted; exactrawparserledgeronlyverified"], {"candidate_agent_original_claim": "not mounted in searched location; exact primary raw-parser ledger only reopened", "ROOT_actual_path": "/workspace/settlements-work/sources/r2-missing/murmansk_population.doc", "ROOT_bytes": 384000, "ROOT_sha256": "d4bdb36d541ed3f90594ba95ee209fabafc5f02088758e46a143e1155f5fbc57", "ROOT_binary_available_and_bytes_verified": true, "ROOT_fresh_DOC_parser_rerun_asserted": false, "native_population_8696_retained_from_existing_primary_raw_parser_ledger": true}, "Secondary own-place Wikipedia dated inclusions; year or stated day precision retained, primary legal-operative dates not asserted. Former own locality point continuity inferred; no reconstructed fixed-boundary counts.", "Own secondary source reports incorporation and former PGT status; exact municipal-law day and historical-boundary equivalence remain unverified."]

Separate formation and direct lifecycle source-ID union: authentic historical Kievsky/Kokoshkino PGT observations retain their own physical points; whole municipalities have independently observed 2010/2021 quantities and municipal representative points. Mosrentgen retains two existing whole2002 predecessor references and its complete2010 published native roster at municipal grain. The 4,654 difference remains unallocated. No own2002 Mosrentgen municipality, individual NP2021 count, ordinary NP3 identity or comparable boundaries are asserted.

| Year | Direct lifecycle population | Additional formation UID gain | Lifecycle plus formation population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 144,054,319 | 18,156 | 144,072,475 | 99.24621 |
| 2010 | 141,559,231 | 32,044 | 141,591,275 | 99.11431 |
| 2021 | 143,974,018 | 0 | 143,974,018 | 99.49851 |

["Cached secondary formation/transfer statements, primary legal-operative dates unverified; municipal source-year boundaries and protected2010 leaf-control differences unknown and unallocated. Modern point continuity inferred, not censusday measurements.", "Cached secondary formation/transfer statements, primary legal-operative dates unverified; municipal source-year boundaries and protected2010 leaf-control differences unknown and unallocated. Modern point continuity inferred, not censusday measurements."]

Separate appearance and publication-absence supplement: only independently observed own-locality source-year populations enter this source-ID union. Parent city contexts add zero credit. Pre-formation years and Star City2002 publication absence keep blank own populations; publication absence does not assert physical birth. Ordinary NP3, original mixed, direct and formation axes retain their definitions.

| Year | Formation plus direct population | Own observed appearance UID gain | Separate primary population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 144,072,475 | 0 | 144,072,475 | 99.24621 |
| 2010 | 141,591,275 | 6,333 | 141,597,608 | 99.11875 |
| 2021 | 143,974,018 | 24,808 | 143,998,826 | 99.51565 |

Separate source63 primary supplements: independently observed former-locality populations and own points enter dated included_in paths; the next lifecycle packet represents only its own actually published source years. Receiving parents remain context with zero new credit. Unknown old own counts remain blank, no child2021 count is invented, and these relations do not create ordinary same-place graph edges.

| Year | Core plus existing appearance population | Additional inclusion UID gain | Additional available-year lifecycle UID gain | Extended primary population | Common control % |
|---|---:|---:|---:|---:|---:|
| 2002 | 144,072,475 | 30,548 | 9,172 | 144,112,195 | 99.27357 |
| 2010 | 141,597,608 | 0 | 700 | 141,598,308 | 99.11924 |
| 2021 | 143,998,826 | 0 | 14,967 | 144,013,793 | 99.52600 |

Source64 adds 128 reviewed secondary compilation observations, preserving their source grade and count witnesses. The explicit Astrakhan parent subtotal retains raw544 but is nonadditive; its own locality child is unchanged. Every ordinary population/row/regional denominator and current credit UID union uses the interpreted additive mask. Source-only observation admission creates no point, identity or automatic population credit. Signed source-control differences are retained without quota allocation: {"2002": -757, "2010": 493512, "2021": 0}. Population source overlays are separate and absent from this raw report.

Source65 preserves all source64 observations, populations, grades and additive interpretations. Current own-point representative supersessions and accepted temporal continuity are separate from the Gorodok17 included_in supplement. Its own5495-person statistical2002 observation is retained despite reported administrative inclusion2001; no exact physical abolition or census-day boundary is inferred. Receiving-city2010/2021 observations are context only, later own counts remain NULL, and no ordinary UF edge is created. Population source overlays remain separate.

| Year | Prior available-year primary population | Additional own inclusion UID gain | Extended raw primary population | Common control % |
|---|---:|---:|---:|---:|
| 2002 | 144,112,195 | 5,495 | 144,117,690 | 99.27735 |
| 2010 | 141,598,308 | 0 | 141,598,308 | 99.11924 |
| 2021 | 144,013,793 | 0 | 144,013,793 | 99.52600 |

Source66 adds 118 reviewed native published-code/alias edges and 652 own-point uses, with no source observation additions, point rejections, new events or population source overlay. Source128 metadata and the parent nonadditive interpretation remain unchanged. Gorodok17 belongs to source65; its inherited own2002 credit remains5495, while new source66 Gorodok17 UID gain and receiver context credit are zero.

Source67 adds 168 reviewed NULL-scope/county/regional continuity edges and 167 admitted own-point uses. Source populations, quality, names, native codes and additive grain remain unchanged, with no source observation additions or new typed inclusion events. Gorodok17 retains its separately admitted source65 identity/grain and existing5495-only2002 contribution. Population source overlays are separate from this raw export.

Source68 adds 16 reviewed railway-NP/former-name continuity edges and 16 admitted own-point uses. Source observations, populations, quality, names, codes and additive grain remain unchanged. Existing typed lifecycle/Gorodok17 source65 credit remains separately defined; population claim overlays are excluded from the raw report.

EAO source namespace: 98 original2002 rows use the source header Sheet1!A1 Еврейская АО for effective regional context. Export keeps the imported region values and separately records the effective namespace and pinned interpretation input. Original source populations, quality, row locators and metadata remain unchanged; the interpretation alone adds no finite three-year histories.

Imported empty population quality values remain unknown, unchanged: 2002: 0 export rows, 2010: 3 export rows, 2021: 0 export rows.
