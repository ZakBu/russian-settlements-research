# Bashkir Encyclopedia 1989 rural settlement delta

This pass is bounded to the 2,531 article URLs remaining after the first 415-row Bashkir Encyclopedia extract. It does not discover further URLs or change Git, coordinates, frozen outputs, or integrated population tables.

`bashenc_rural_1989_delta.csv` contains exact published person counts for 1989 from individually named rural settlement articles. It retains census year, original and normalized settlement names, positively identified Bashkortostan district, source URL and SHA256, archived raw HTML path, population section, settlement type, grain, license status, and count-basis limitations. `baseline_415_snapshot.csv` and `baseline_receipt.json` fix the original extract for reproducible exclusion of those 415 records.

The extraction excludes:
- Rounded population in thousands.
- Region, district, municipal, and other aggregate populations.
- Settlement names appearing as urban in the archived 1989 census urban table.
- Explicit outside-Bashkortostan administrative identities or unidentified Bashkortostan districts.
- Population series potentially combining more than one settlement.
- Conflicting same-district/same-name articles.
- Any URL or normalized district/name pair already present among the original 415 records.

These are published secondary historical population facts. The census attribution of the specific online Bashkir Encyclopedia articles is inferred from the year sequence; no source-methodology statement confirming their precise presence/permanent-resident basis has been established. Residence basis remains unspecified. These counts are unlinked evidence, not accepted additions to the integrated dataset.

Raw downloads remain outside Git in `/workspace/shared/rsfsr1989_rural_bashenc_delta`. The download manifest preserves each URL, retrieval timestamp, SHA256, bytes, HTTP outcome, and archived path. The corpus is copyrighted by GAUN RB Bashkir Encyclopedia; no open license was observed. The CSV extracts numerical observations and their locality identities, rather than republishing narrative articles.

`requested_urls.json` preserves the exact bounded input. `source_exclusions.json` preserves held observations and their reasons. `extract_summary.json` contains the current export count and hash. The CSV is written atomically; until the download pass is complete it remains a provisional snapshot because a subsequently retrieved article can reveal a same-name conflict. The final `receipt.json` records completion, coverage, and reproducibility checks.

## Completed result

All 2,531 bounded URLs completed with a latest HTTP200 result. Final delta: 2,337 exact published rural settlement counts, totaling 929,251 people before binding and primary-source overlap removal. Final immutable file: `bashenc_rural_1989_delta_final_frozen.csv`; SHA256 `bc2fc0d766c88d32c6756f8a5ff053e576c75be967d12a22037c6e9620117391`. All exported raw SHA256s were verified, canonical urban-name intersections are zero, and the original 415-row snapshot remains unchanged. `chunks_final_reconciliation.json` reconciles all immutable snapshots with the final delta. In chunk001, Улу-Теляк (2,888 people; source ID `bashenc:4199bc43024df35e`) is excluded after Unicode hyphen normalization identifies its 1989 urban status. No crawler remains running.
