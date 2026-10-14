# Kirov oblast 1989 census public mass tables

Acquisition date: 2026-10-14. Source: https://rodnaya-vyatka.ru/vpn1989-kirov .
The site's transcription credits volume 1 (urban places/district totals; Kirov, 1990, 264 pp.) and volume 3 (rural settlements; Kirov, 1990, 236 pp.) of *Итоги Всесоюзной переписи населения 1989 года по Кировской области*.

Acquisition stopped on root instruction after a source terms-of-use prohibition on automated collection was found. All retained facts are partial, not admitted, and not authorized for publication. Network acquisition in `extract.py` is disabled. Use `python snapshot_cache.py` for local-only forensic diagnosis. `validate.py` is for a hypothetical complete dataset and was not run. Python dependencies: pandas, pyarrow, beautifulsoup4. The extractor traverses public district-search pagination, 30 localities per page. Two workers, 0.65-second delay before each uncached request, four attempts, URL-keyed byte caches. No login, circumvention, individual-place article crawl, or writes to source.

Raw HTML, receipts, large outputs and progress are outside Git at `/workspace/shared/vyatka1989_mass_extract`. `facts.parquet` stores localities only; `index_aggregates.parquet` separately stores district/region aggregates from the public index. Locality records preserve source row code as a string including leading zeroes, raw cells, type/name, district/selsovet, linked-place URL (a source pointer, not independently admitted identity), category, six separate present/permanent male/female/both-sex counts, exact printed-page URL, mass-table URL/hash/row index. Unknown counts remain null. Site editorial comments are `source_note_raw`; the transcribed table can explicitly correct original printed values. Raw transcribed cells and editorial comments remain separate.

`table_sha256` hashes acquired public table HTML, not the printed scan. `source_page_url` is the site's exact printed-page locator. Only four exemplar printed-page HTML files were fetched (3024,3028,3044,3198); the full set of scan images was not downloaded or audited. Full table extraction and published-aggregate reconciliation do not establish transcription accuracy or locality continuity.

Source-specific use: public read-only factual transcription, attributed to Родная Вятка and the cited census volumes. No permission for redistribution of scan images is inferred. Do not claim the site's linked modern-place identifiers as reviewed historical linkage.

Current authoritative local snapshot: `facts_partial_not_admitted.parquet`, `receipts_partial.json`, `summary_partial.json`. Earlier `facts_progress.parquet` is only a progress checkpoint and not the complete retained cache snapshot. This record does not claim permitted automated collection or reuse.
