# Northwest historical rural primary sources — 2026-10-14

Result: **0 extracted 1979/1989 locality population rows; 0 admissions**. This investigation found concrete primary publications but did not obtain a verified named census table. No marginal-coverage claim is made; baseline ledgers were not modified or measured.

## Concrete priority lead: Pskov rural census 1989

Public catalog endpoint: https://pskovlib.ru/katalogi (POST `title=Сельские населенные`). Raw response: `/workspace/shared/rural_northwest_history/pskov_target_0.html`; SHA256 in asset_manifest.json. Locator: the record containing exact title **Сельские населенные пункты Псковской области : (по данным Всесоюзной переписи населения 1989 г.). Сб. N 6 / Госкомстат РСФСР. — Псков : Госкомстат РСФСР, 1990. — 86 с.** Shelfmark **60.7(2Р-4Пс) С 298**; copies in КХ; ОКЛ. Record has no digital Читать link. Publisher/year/census basis are explicit; named grain and source row count remain unverified. Do not mistake 86 pages for 86 settlements, or infer thousands of population observations from the title.

Second primary lead from POST `title=Численность`: **Численность населения Псковской области : (по данным Всесоюзных переписей населения 1959,1970,1979,1989 гг.). Сб. N 2 / Упр. стат. Псков. обл. — Псков : [б. и.], 1990. — 60 с.** Shelfmark **60.7(2Р-4Пс) Ч-671**, КХ. Raw response `pskov_catalog_0.html`, duplicate corroboration `pskov_specific_1.html` with POST `title=населения&data=1990`. No digital link; object grain unresolved, may be regional/district rather than all rural localities. 1979/1989 bases explicit, population rows unavailable.

## Downloadable/viewable source assessed and excluded from target years

https://pskovbook.ru/book/2345 : **Административно-территориальное деление Псковской области (1917–2000 гг.), кн. 1**, 2nd revised edition, archive administration/state archive, Pskov, 2002. Catalog says 464 pages; public viewer reports 462 image pages. View link https://text.pskovbook.ru/MegaProPDF/Download/MObject/2345 redirects to ProtectedView. With normal session cookies the public viewer and GetPage image requests work; bulk PDF download quota is zero (`maxPagesToDownload = floor(pages * 0 / 100)`). This is a viewer restriction, not blanket website inaccessibility.

Inspected viewer image page 4 = printed page 5, saved `pskov_admin_page_4.jpg` (actual PNG). Preface explicitly says section III contains names and population of localities of every district, **provided by district administrations as of 01.01.2001**. It is therefore not a 1979/1989 population source. Images 1–5 and 460 saved; page 460 is printed page 461, historical decrees. Volume 2 https://pskovbook.ru/book/2346 is indexes (496 catalog pages), not population tables. Public pskovbook POST searches: `Численность населения` 0; `перепись` 4, all nineteenth/early twentieth century; `Административно` 12, includes volumes 2345/2346. These result counts are publication hits, not NP counts.

1988 predecessor is present in the public catalog: **Административно-территориальное деление Псковской области (1917–1988 гг.)**, кн.1 411 pages, кн.2 453+[1] pages, Leningrad: Лениздат, 1988, shelfmark 67.300(2Р-4Пс) А313. No digital links. Its population reference date was not inspected; cannot infer 1979 from publication date.

## Novgorod

Public library https://reglib.natm.ru links to https://irbis.nounb.ru/cgi-bin/irbis64r_plus/cgiirbis_64_ft.exe . The guest workflow `IS_FIRST_AUTH=false&Z21ID=GUEST&C21COM=F&I21DBN=AUTHOR&P21DBN=IBIS&Z21FLAGID=1` opens the public search; no personal credentials are used. Preserve hidden search parameters from the SEARCH form. Normal S21FMT=briefHTML_ft produces visible bibliographic results; S21FMT=fullw produced result-count shells and is not evidence of absent records.

RSL record https://search.rsl.ru/ru/record/01007474539 confirms **Предварительные итоги Всесоюзной переписи населения 1979 года по Новгородской области : (Справ. материалы) / Стат. упр. Новгор. обл. — Новгород, 1979. — 17 с.** Shelfmark DSP СХ; explicit note «Для служеб. пользования». No public full text and named rural grain is unverified. Raw responses `rsl_title_5.json`, `rsl_filtered_0.json`. Preparation bulletins for 1989 (1986/1987) are not census results and were excluded.

Regional Rosstat https://60.rosstat.gov.ru/ and https://53.rosstat.gov.ru/ returned HTTP503 in this session; regional2004 census volumes could not be inspected there. Search engine tool errored; direct Google gave redirect shells and DuckDuckGo a bot challenge. These are access outcomes, not evidence that no publication exists.

## Commons search and source conditions

Commons API works with standard urllib and User-Agent RussianSettlementsResearch/1.0 (https://github.com/ZakBu/russian-settlements-research). Queries and full raw responses saved as commons_query_0..3.json. `intitle:Псков filetype:pdf` zero; `intitle:Новгород filetype:pdf` 42 irrelevant historical/Ukraine/title files; quoted regional/census searches likewise yielded no target primary table. This is bounded discovery, not an exhaustive absence claim.

Public bibliographic metadata and individually viewable images were accessed only. No contact, email, purchase, credential bypass, or restricted bulk-download circumvention. Citation of pskovlib content requires a direct site link according to its footer. No source license allowing redistribution of complete scanned books was established; raw captures remain outside Git.

Next useful action: locate an already public scan of Pskov 1990 census **Сб.6** and inspect contents/table headers; if named NP rows exist, OCR with page and row provenance, then link identities/coordinates separately. For 1979 inspect Pskov **Сб.2** only after confirming locality grain. The material inspected here does not justify coordinates or retrospective point reuse.
