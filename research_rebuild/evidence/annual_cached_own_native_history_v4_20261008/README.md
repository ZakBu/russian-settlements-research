# Bounded cached v4 history supplement

Final external supplement: `/workspace/settlements-work/annual_cached_own_native_history_20261008/v4_2/`.
Only `v4_2` is final; `v4` and `v4_1` are superseded conservative drafts.
The final two gzip files total **81,821 bytes** and are pinned by `receipt.json`.
Frozen v3 files, receipts and source hashes were left unchanged.

The supplement contributes **1,072 literal dated observations for 167 additional
current native full3 ordinary places**. It has 309 observations before 2002 for
74 places. Frozen v3 plus this supplement totals **10,952 observations for 3,195
places across 180 actual observed years**. These are source-bounded descriptive
register counts, not national historical coverage or census metric credit.

| Actual year | Additional entities | Additional descriptive population sum |
|---|---:|---:|
| 1959 | 17 | 58,863 |
| 1970 | 19 | 75,587 |
| 1979 | 20 | 106,687 |
| 1989 | 25 | 102,349 |

Code-width inventory exposed a real false-negative screen in v3: among strict
all-three finite own-point full3 places before ordinary territorial exclusions,
6,577 current codes have ten digits, representing 16,737,665 native 2021 people;
192 are cities or urban-type settlements, representing 11,092,222 people. Moscow
has an eight-digit code and 13,010,112 people. Details and scope are preserved in
`code_width_inventory.json`. Native current exact widths 8–11 are now permitted;
no arbitrary eight-to-eleven padding is performed.

Every candidate still requires unique current own native code among all current
NP rows, or an independently accepted direct own raw Wikidata P625 QID binding,
literal own name, physical settlement grain/type and unique own P625 agreeing
with the accepted current own point within five kilometers. All native census
years must have finite chosen counts and accepted own points. Organization,
administrative or municipal P31/description scope, explicit subtype conflicts,
contradictory codes, subsets and unresolved competing items remain held. No new
observation used the alternate direct-point binding route in the final supplement.
`current_native_code_competition_cases.csv` is empty: the selected current NP
table had no duplicate literal native codes. Raw nonadditive municipal/region
rows sharing a code are not used as physical NP historical observations.

Five additional bindings use the previously authorized documented decimal
publisher leading-zero preservation rule: native raw ten-digit physical NP code
compares only with the item's literal eleven-digit code beginning with exactly
one zero. The original NP-level source row, printed name, source hash/locator,
original code and item code are preserved separately. NP-level native name and
printed type prefixes/suffixes must support the same current subject; uniqueness
is checked across all current NP codes and cached item codes. No raw identifier
is overwritten. These five are Дивногорск, Новомихайловский, Джубга, Анапская and
Крыловская. This comparison establishes a current own-item binding only; it does
not assert primary verification of historical population or comparable boundaries.

Broader existing raw source inventory: **275 files / 11,344 latest cached item
snapshots**. Only 51 of 2,237 ordinary urban full3 targets have exact or documented
single-leading-zero P764 full cached items; only three independently accepted
own-point urban QIDs have full cached entities. `urban_cached_inventory.csv`
preserves every target and cache availability, including missing large cities.
Tula adds five actual years (2016–18, 2023, 2025); Voronezh adds nine (2012–18,
2023, 2025). Their cached raw P1082 does not provide the hoped-for large 1959
population boost. Moscow Q649 and Saint Petersburg Q656 were absent in this
broader 275-file cache scope, not asserted absent from every possible source.
The nonentity `entity_fetch_summary.json` was ignored as a metadata container;
its parse status is recorded explicitly in the receipt.

All normal/preferred P1082 statements preserve literal P585 precision/date,
amount, GUID, rank, raw file SHA/locator, P248 references, URLs/titles and methods.
P518 subsets are held; generic dated counts are not labeled census. Historical
population remains secondary/`primary_unverified`, boundary comparability
`UNKNOWN`, and coordinate continuity inference is distinct from historical
coordinate measurement. Chosen native 2002/2010/2021 counts, graph, loader,
denominators and census metrics are unchanged. No API or download was used.

Validation replayed every **1,072** supplemental raw statement and binding against
28 pinned cached files and passed. `validate.py` verifies raw P585/precision,
rank/amount/unit/GUID, no P518, preserved primary-unverified/UNKNOWN statuses,
native census-year exclusions, current P764 or documented decimal comparison,
source hashes and own P625. Source manifests and validation receipt are adjacent.
