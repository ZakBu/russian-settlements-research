# Supplemental native-source provenance recovery

Recovered exact physical source bytes and literal name/count witnesses for all14 assigned records: five ARK2010 archived HTML rows, eight KAL2010 official workbook rows, and Kulitskaya2002. All14 population values match exactly. Original selected types and population qualities remain unchanged; no point or identity admission was made.

`recovered_direct_native_witnesses.csv` provides exact source paths, SHA256 hashes, cell/HTML row locators, original row cells, printed county and immediate subcounty headers. Source-native codes are unknown in these inspected rows and headers; no classifier or provider code is silently substituted.

ARK UIDs use **zero-based HTML tr indexes**. The recovered archive hash matches the original ingestion parser's pinned729fecf5845bd9f1e049c85b2659bfd077dfd2d2a01fecbc9d21cb83b7b9e486. Sorovo and Samkovo are explicitly `посёлок` in the source while selected types are `село`; this discrepancy is documented, not repaired. Ivaksha and Lepsha Novy retain the literal `населённый пункт Лесной Поселок ...` labels and selected missing types.

KAL UIDs use **one-based Excel rows**, sheet `4`. Exact workbook hash7e17a4bdb54e3ee8ff014c4311396f84c01b7f3ed38d12f4f9c1f9e6b100705f matches the ingestion source manifest. County headers have source indent1; immediate rural district headers have indent3; locality rows indent4. Thus the two Sadovoe records are explicitly distinguished by Nesterovsky/Ilyushinsky versus Ozersky/Krasnoyarsky source context.

Kulitskaya is source sheet `!!!`, D2583=`ж/д ст. Кулицкая`, E2583=977, B2583=`Калининский район`; C2582:D2582 identifies `Кулицкий СО`. Its selected quality `verified_count_in_secondary_census_compilation` is retained.

Run `recover.py` to reproduce the bounded checks. `source_manifest.json` pins source bytes; `receipt.json` records completeness and documented type discrepancies. This packet proves source provenance and printed context only; it supplies no cross-year matching decision.
