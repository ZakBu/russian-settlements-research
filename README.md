# Russian settlement census research archive

This is a **private research archive** for reconstructing Russian settlements in the 2002, 2010 and 2021 censuses. It preserves the existing project baseline so that the next reconstruction can be compared with its inputs and prior decisions.

The archive is not an endorsed public data release and does not declare its mixed-source contents to have one license. Source terms and known restrictions are recorded in [SOURCES.md](SOURCES.md). Do not redistribute individual source families unless their terms permit it.

## Current state

The attached baseline is a snapshot of the project as of 2026-09-29. It includes raw source files and existing databases as research inputs. The legacy crosswalk and coordinates are hypotheses; they are not a validated final settlement identity or spatial database. The forensic audit identified a dropped-row defect in the 2010 city parser, ambiguous historical matches, and unresolved coordinate provenance. See [STATUS.md](STATUS.md) and [METHODOLOGY.md](METHODOLOGY.md).

No public license is applied to this mixed-source repository. Refer to the original source terms for each artifact family.

## Baseline assets

Large baseline inputs are attached to the [private GitHub Release `baseline-2026-09-29`](https://github.com/ZakBu/russian-settlements-research/releases/tag/baseline-2026-09-29), not stored as Git blobs. It contains the 7,054 raw/interim source files (excluding local `.DS_Store` metadata), the legacy DuckDB, the forensic DuckDB, and the forensic output/evidence tables. The release asset manifest records byte sizes and SHA-256 digests; GitHub's asset digest API was checked against those values. The input archive's file list and hashes were checked against the forensic build manifest.

These assets preserve the working baseline for comparison. The original project remains the working source; neither database is represented as the validated final reference system.

## Reproduction and future releases

The next scientific release will include only the scripts, methodology and tables that have passed the project's independent checks. Preliminary audit products must be labeled as such. Census-year coverage (population with an admitted settlement point) and longitudinal identity coverage will be reported separately.
