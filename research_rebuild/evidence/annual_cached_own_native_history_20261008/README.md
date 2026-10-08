# Cached observed historical counts, strict native full3 current places

Final positive register: **9,880 literal dated population statements for 3,028
current native full3 ordinary settlements**, across **179 observed years
(1646–2025)**. Before 2002: 5,735 statements for 1,728 places. This is a
source-bounded secondary register, not nationwide historical population coverage.

The final compressed files are external:

- `/workspace/settlements-work/annual_cached_own_native_history_20261008/v3/observations.csv.gz`
- `/workspace/settlements-work/annual_cached_own_native_history_20261008/v3/current_bindings.csv.gz`

`receipt.json` pins these final bytes. Root-level first-pass gzip files are a
superseded draft; `v2` was an empty over-held diagnostic. Only **v3** is final.
Combined final compressed size is 969,320 bytes; Git metadata is about 104 KB.

| Literal year | Unique current entities | Descriptive sum of one amount per entity |
|---|---:|---:|
| 1959 | 274 | 537,773 |
| 1970 | 144 | 425,990 |
| 1979 | 294 | 606,030 |
| 1989 | 386 | 683,968 |
| 2025 | 50 | 247,133 |

These sums are descriptive only. `by_year.csv` includes every observed year;
entities with multiple amounts within a year are excluded from its sum. Same
item/date conflicting statements would remain separate observations; none occur
in this admitted cached subset. Sixty-five source-literal zero observations are
preserved; no missing population has been replaced with zero.

All current identities have canonical selected native 2002/2010/2021 rows,
finite native populations and accepted own points in every year. The current
native 11-digit OKTMO must be unique among **all** current selected NP rows, and
the item's nondeprecated P764 must be unique among **all** scanned cached QIDs.
Literal own names, physical settlement type and absence of explicit subtype
contradiction are required. The item's own unique P625 must agree with the
accepted current own point within 5 km. Current points and their accepted origin
provenance are preserved separately from Wikidata provider-code binding.

Full raw entity snapshots supply normal/preferred P1082 statements. Exactly one
literal P585 with usable actual year and consistent original date precision is
required; literal raw amount, calendar, date, rank, GUID and raw file SHA/locator
are retained. P518 subsets are held. P248 IDs, reference URLs/titles and method
IDs are recorded without asserting independent verification of those sources.
Every observation remains `primary_unverified`, dated secondary population
observation, with boundary comparability `UNKNOWN`. Coordinate reuse is explicit
retrospective continuity inference, not an earlier coordinate measurement.
Former urban status does not override an exact current native populated-place
binding; it does not establish historical grain or boundary comparability.

The parsed source inventory was checked first: 488,532 historical rows, but
424,207 legacy rows lacked raw statement precision/provenance. They were not
converted into verified literal dates. The bounded raw route scanned 194 files,
9,624 latest cached item snapshots. It does not meet the aspirational 5,000-entity
scale under the strict own-code/name/type/point rule. No network was used and no
rule was weakened for scale. Q649/Q656 were absent from this raw cache scope, so
no federal-city extra was manufactured.

No native census count, chosen source, identity edge, point ledger, loader or
coverage denominator was changed. Native census years 2002/2010/2021 are excluded
from these secondary observations. `native_state_input_manifest.json` and
`raw_source_manifest.json` pin inputs. The working loader stage is explicitly 37.

Validation: `python research_rebuild/evidence/annual_cached_own_native_history_20261008/validate.py`
replayed **all 9,880 statements**, GUID/date/precision/quantity/rank/P518 and own
P764/P625 bindings against 193 pinned raw files. It passed; see
`validation_receipt.json`. `collect.py` refuses overwriting a preexisting output;
change its output path to a new version before reproducing the collection.
