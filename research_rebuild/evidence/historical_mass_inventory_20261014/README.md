# National historical rural source inventory, 14 October 2026

No new named locality population observations for 1979/1989 were obtained in this bounded pass. No rows or coordinates were admitted. This does not establish absence of unpublished, archived or separately hosted datasets.

The actual baseline `observations.parquet` was loaded with PyArrow: 467,349 rows, census_year only 2002 (158,175), 2010 (153,423), 2021 (155,751). Schema contains one population and census_year column, no hidden 1979/1989 columns. Its hash and complete source-file inventory are retained in receipt.json.

The 7,162-member baseline raw/interim archive inventory was examined beyond the current extracted tree. Its explicit 1989 directory contains urban_scan.pdf; historical_geography contains the 2011 OKATO DBF. No standalone national historical rural database asset is identified by member names; Wikipedia caches were not reclassified as new sources.

Lingvarium's requested national database page was successfully retrieved over HTTP, following HTTPS certificate errors. It explicitly says complete databases are available for 2002/2010/2020–21 and partial data for 1897/1926/1959. The 1979/1989 census names are plain text in the HTML, not active dataset hyperlinks. Twelve direct/legacy paths were tested; Census1979.shtml and Census1989.shtml return404; BD/ returns403. These are endpoint findings, not proof of dataset nonexistence.

The live Russia index has a legacy example hyperlink. The actual `settlem-database_example.shtml` was retrieved: a locality table for Dahadaevsky district, Dagestan, with 2002,1959 present/permanent and1926 population columns, no1979/1989. Author, project, atlas and document indexes were also followed. Public document downloads found concern1926/1886/1895; author Yandex shares are linguistic libraries, not identified settlement databases. No2002 workbook rescan was done.

Practical next steps: obtain a named historical1979/1989 export from Lingvarium's author/archive, or acquire complete regional rural1989 census books. There is no usable new massive historical count table to bind from the public links actually retrieved here. Region residuals must not be allocated to localities. Raw HTML, probes, errors, archive inventory and executable probe script are under `/workspace/shared/historical_mass_inventory`; publication/license permissions remain unestablished.
