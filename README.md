# Russian settlement census research archive

Private, versioned research archive for reconstructing settlements in the 2002, 2010 and 2021 Russian censuses. It preserves the legacy project as a baseline and contains a source-corrected, reproducible Karelia pilot. Neither is a validated national settlement database.

## Reproduce the Karelia pilot

Download and extract the private [baseline inputs](https://github.com/ZakBu/russian-settlements-research/releases/tag/baseline-2026-09-29) and [R6 pilot inputs and outputs](https://github.com/ZakBu/russian-settlements-research/releases/tag/karelia-pilot-r6-2026-09-30). The baseline supplies original census and source files; the supplemental bundle supplies the Karelia DOCX, fixed reviews and compact processed evidence. Install the pinned runtime dependencies, then run from a clean checkout:

```sh
python3 -m pip install -r requirements-pilot.txt
python3 scripts/reproduce_karelia_pilot.py --data-root /path/to/baseline --inputs-root /path/to/karelia-r6-inputs --output-root /path/to/new-output
```

The output directory must be new or empty. The runner extracts the official 2010 rural DOCX and the actual Rosstat Volume 1 Table 5 PDF, builds the pilot, then validates it again from outside the checkout. It stops on absent or altered inputs, broken observation bindings, or output integrity failures. Source and code hashes are recorded in the manifests. It also writes `linkage_review_portable.duckdb`, a materialized copy of the Parquet tables with a sidecar manifest that checks every table's typed contents and queries the copied database from another directory. Use that portable database when sharing the results; the builder's `linkage_review.duckdb` contains local Parquet-backed views.

## What the R6 pilot establishes

The 2010 Karelia selected population slice has 800 rows and 643,548 people: 24 urban rows from Rosstat Volume 1 Table 5 (502,217) and 776 rural rows from the regional census volume (141,331), including 109 zero-population rural rows. The corrected DOCX extraction preserves smart-tagged names and their raw row evidence. Its first download had a local TLS certificate-chain validation failure; the file is checksum-pinned and its values reconcile to independent controls, but that transport limitation remains open.

The pilot contains 24 case-reviewed urban/urban-type identity chains and 72 observation-level point admissions. It distinguishes current representative points from earlier-year `inferred_continuity` uses; those historical point uses are not measurements made during the censuses. By population, these 24 chains cover 537,395 of 716,284 selected people in 2002 (75.0254%), 502,217 of 643,548 in 2010 (78.0388%), and 423,680 of 533,121 in 2021 (79.4716%). These figures describe the selected Karelia snapshots only. They do not measure national accuracy or validate an automated national matching rule.

The 2002 Karelia selected slice exceeds its regional control by 3 people; that residual remains unassigned. The R6 2010 source slice reconciles to its published regional total. A separate audit found that 2010 NW workbook population values are confidentiality-protected and are not authoritative settlement counts.

## National status and limits

The national crosswalk, identity links, and coordinate coverage remain unvalidated baseline material. A present coordinate does not certify the place identity or historical applicability. Aggregate population rows must not be attached to a physical settlement. For example, an independent source check found that 2002 Table 4 row 2154 is a Moscow-plus-subordinate-settlements aggregate (10,382,754), while the nested row 2155 is the city of Moscow (10,126,424); this high-mass source-scope issue remains unresolved in the national baseline.

The 99.9% population coverage goal has not been met or demonstrated. Coverage by population and coverage by settlement count must be reported separately; unresolved cases remain visible. Historical coordinates are inferred only when a reviewed continuity decision supports that use.

## Research documents and provenance

- [Current status](STATUS.md)
- [Data model and audit policy](METHODOLOGY.md)
- [Source inventory and use conditions](SOURCES.md)
- [Identity and coordinate methodology](research_rebuild/docs/LINKAGE_METHODOLOGY.md)

This repository and its attached assets are private. There is no blanket license for mixed-source material; rights and reuse conditions vary by source. A private archive upload does not imply permission for public redistribution.
