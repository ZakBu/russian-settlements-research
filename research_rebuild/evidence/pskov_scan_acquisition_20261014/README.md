# Pskov scan acquisition — 2026-10-14

Result: **0 target locality population rows extracted; 0 admissions**. Public scans of Pskov 1990 Сб.6 (С298,86pp) and Сб.2 (Ч671,60pp) were not obtained in this bounded search. Existing catalog evidence and excluded 2002 ATD viewer were not reprocessed. Accepted data and Git were untouched.

## New primary-source locator

Public article by A. I. Krasnov, 2021, directly cites **Государственный архив Псковской области, Ф. Р-1493, оп.2, д.68,69**, *Таблица численности наличного и постоянного населения по каждому населенному пункту на территории Псковской области (табл.2с),1989 (абсолютные данные), тт.1 и2,396с.* Source: https://sciencejournals.ru/view-article/?a=IzvRGO2105005Krasnov&j=izvrgo&n=5&v=153&y=2021 ; HTML text locator Table1 note, raw text lines593–597. This explicitly establishes locality grain and both population concepts for the referenced archive document, but is not a scan of those rows.

Independent public conference PDF corroborates the same archive locator: https://pureportal.spbu.ru/files/108652142/_IV_100_.pdf ; printed p63 bibliography item1 (PDF page must be resolved independently if extracting a row). Printed p61 describes an author-built GIS dataset of 8486 rural localities with coordinates, administrative membership and 1989/2002/2010 populations; that dataset is not attached here. Neither8486 nor396 is a recovered observation count.

The article reports mismatches between published aggregate NP totals and manual counting, and excludes seven places because institutional/military personnel counting changes between censuses: Смуравьево-2,Крюки-2,Хилово,Середка,Череха,Кострецы,Владимирский Лагерь. These are interpretive cautions, not rejected population records or identity findings.

## Bounded discovery

Web searches covered exact titles, С298/Ч671, Сб.6,86pages, archive1493/68/69/table2с, comparative2002 material and current regional Rosstat listings. Search hits for general RSFSR rural distributions, district totals, current OKATO lists and nineteenth-century digitized Pskov censuses were excluded. Smolensk journal PDF contains regional distribution and newly created locality tables, not verified individual1989 population rows. Modern wiki hits for individual places are secondary and were not admitted as target scans.

The RAS mirror https://new.ras.ru/upload/iblock/d4d/48zxath4kqzotylxymhwek0iu80eix3x.pdf returned HTTP503. Sciencejournals web-tool open timed out, but ordinary public urllib GET succeeded (200); SPBU PDF succeeded(200). Access outcomes do not prove absence of digital copies.

Raw assets/text derivatives: /workspace/shared/pskov_scan_acquisition. SHA256/URLs in asset_manifest.json. No contact,purchase,authentication or download-restriction bypass was attempted. No redistribution license established: raw documents stay outside Git.

Next useful source-specific lead is an already public image/scan of ГАПО Р-1493/2/68 or69. Census columns must be inspected before extraction; choose наличное versus постоянное explicitly and preserve page/name/admin hierarchy/date.1979 still lacks verified rural-locality grain.
