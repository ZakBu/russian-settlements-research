# Existingrawhistoricalcolumn reserve check (2026-10-13)

**Result: no usable bulk1989NPpopulation columns found; new1989coverage0.** No population claims were ingested or modified. No current-populationvalue equal to1989/1979 was interpreted as a historical year.

| Cached source group | Files | Worksheets | Scan scope | HistoricalNPcolumn headers found |
|---|---:|---:|---|---:|
| Regional2002 |87XLS|193|First100headers plus every text and numericcell in all219,922worksheetrows|0|
| Official2002Tom1XLS |1|1|Header andtextyearcheck,10,581rows|0|
| Regional/aggregate2010 |21XLS+1XLSX|29|First100rows of everyworksheet;first15rowsretained|0|
| Regional2021 |82XLSX|82|First100rows of everyworksheet;first15rowsretained|0|

The2002memberinventory matches all87regional `.xls` files in `/workspace/settlements-raw/data/raw/2002`. There are no `.xlsx/.doc/.docx` regional2002files in thatdirectory/archivegroup. Allworkbook sheets, including auxiliary/hidden sheets, were enumerated. The scan found19textcells containing1989/1979 and50numericcells equal to those years; they were inspected with surrounding row/header context. Most were current2002population/sexcounts or rowindices. For example, `029_fe8710371d_02c_Dagestan.xls`, sheet`2002`,row184C contains1989 **men in2002** forУсиша; it is not a1989censuscolumn. Row282C similarly contains the2002male count of anadministration. Bashkiria's yearlike numbers are rowindices.

Oneactual historicalpopulationcomment was found: `018_25c6f5e960_02c_Karelia.xls`, Sheet1,row746J, saysХетоламбина had400people in1989, followed by several noncensusyearcounts. It is an unattributedcomment, not a comparativecensustable or bulkcolumn, and it was not accepted as a censuspopulationclaim. TwoDagestancomments concern founding/resettlementyears, not populationcounts.

Thelaterheader scan found10yearlikecells. Inspectionclassified these as2010/2021currentcensuspopulation/languagecounts orcontrolcounts, not yearheaders. The82cached2021workbooks containcurrentcensuslanguage tables; copies were extracted once from the suppliedbaselinearchive to externalcache. The2010sourcefiles were alreadylocal and reused. Thislater scan establishes absence of historicalheaders in the inspected first100rows; it is not a claim to have audited every laterfilecell or everyPDF.

Official2002Tom1PDF was selectivelyextractedfrom the existingarchive into externalcache and its foreword/tablelayoutchecked. ItsindividualNPtable is2002-only, matching `1_TOM_01_04.xls`; historicalcomparisons relate toaggregates/methodology. No fullPDFaudit was undertaken.

Evidence files:

- `scan_summary.json`: counts andboundedscan scope.
- `scan_manifest.json`: every2002worksheet, filehash, dimensions, visibility, first8rows.
- `historical_year_hits.json` and `allrow_numeric_year_value_hits.json`: all2002text/numericmatches withrowcontext.
- `later_header_scan_manifest.json`: every2010/2021worksheet, hash, dimensions, first15rows.
- `later_header_historical_year_hits.json` and `reviewed_hits.csv`: latermatches andreviewclassifications.
- `source_file_manifest.json`: perfilelocalgenealogy/hash/year/grain/license-auditnotes.
- `scan_existing.py` and `scan_later_headers.py`: reproducible read-onlyscanners.

Rawregional2002/2010files remain in `/workspace/settlements-raw/data/raw/`. External2021/PDFcache: `/workspace/shared/rsfsr1989_existing_source_columns/`. Existingarchive reused: `/workspace/shared/downloads/raw_interim_20260929.tar.zst`; memberlist `/workspace/scratch/baseline_members.txt`. No redownloads, no Git operations, no edits to input/rawsources.
