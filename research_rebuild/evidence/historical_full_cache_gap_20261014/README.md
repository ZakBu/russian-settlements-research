# Historical full-cache gap audit — 2026-10-14

This is a source ceiling and metadata audit, not a new accepted release.

The 29 full Wikidata JSON batches contain 1,450 entities. Their literal P1082/P585 claims contain 227 dated 1979 quantities on 227 QIDs and 239 dated 1989 quantities on 239 QIDs. **Every quantity is already present in the flattened population TSV.** Full claims therefore expose no hidden year/quantity gain. Own native NP code, literal name and accepted current point within 5 km bind 206/216 observations; every bound root is already in the selected historical integration. These bindings remain candidates: source-wide code competition, historical identity and raw P31 interpretation have not been independently admitted by this audit.

All 466 dated full claims preserve GUID, rank, time precision, quantity unit, complete qualifiers, non-date qualifiers, references, raw P31 types, byte hash and JSON locator. This fixes audit visibility lost in the flat cache, rather than providing more observations. Modern points are explicitly continuity inferences. Generic dated P1082 is not automatically a census count.

The full Wikipedia raw cache contains 140,039 pages. Only 5,892 pages mention literal 1979 and 9,533 mention literal 1989 anywhere. Those are deliberately generous *article-level* ceilings for ordinary own-page literal-year extraction; year mention alone is not a population fact. Regional/list articles could contain multiple subjects, so these are not a universal ceiling on all possible table rows.

Reusing the existing extractor's numeric year-template grammar finds only one previously omitted hit: Покровский (Нурлатский район), `| 1989 = 0`. The prior extractor explicitly rejected values <=0. This is a **literal source zero**, not an imputed unknown. It remains an unadmitted candidate with its exact source context/locator. No positive template fact was missing. Other existing extractor patterns were not reinterpreted, and unsupported prose/table forms remain an explicitly unquantified parser risk.

Outputs live outside Git at `/workspace/shared/historical_full_cache_gap/`: `wikidata_full_literal_claims.parquet`, `wikipedia_template_parser_gaps.parquet`, and `receipt.json`. Repository receipt pins every consumed source and output. AppleDouble `._` files are metadata sidecars, not gzip sources; only `batch_*.json.gz` is scanned. No downloads, interpolation, fabricated zeros, primary-census claims or coverage gains were made.

Reproduce with `python research_rebuild/evidence/historical_full_cache_gap_20261014/audit.py`.

Narrow zero follow-up: unique native NP anchor for Покровский Нурлат has root `2010:017_68e0e4537e_9._20Basq_Mari_Mord_Tatar_Udm_Chuv_2010.xls:!!!:9868`; its accepted point differs from the independent article point by 0.091 km. Literal name, region and district agree. No 1989 observation exists on that root in integrated long data; cached Tatarica facts have zero Нурлатский exact-name matches. The Bavлинский homonym37 is a distinct root. `literal_zero_1989_ready_fact.parquet` and `literal_zero_1989_proof.json` retain one explicit source-zero secondary observation ready for root review; the cited encyclopedia URL was not fetched.
