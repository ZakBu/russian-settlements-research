# Research status at 2026-09-29

## Baseline preserved

- The existing project contains approximately 3.2 GB across raw, interim and processed data. The private release preserves 7,054 raw/interim files, both the legacy and forensic DuckDB databases, and forensic output/evidence tables. Each uploaded asset's GitHub SHA-256 digest matches the locally computed manifest.
- The legacy database and tables are research inputs, not the final reference system.
- The current audit release has no reviewed coordinate certifications. This means the certification procedure has not yet been applied; it does not mean every existing point is wrong.

## Verified findings

- The old parser replay reproduced 467,349 pre-fix observations and the checked fields. This establishes repeatability of that parser run, not completeness of the publications.
- A parser rule omitted three real city names in 2010, losing 48,319 people. The corrected audit snapshot restores them; 689,282 people remain outside the directly enumerated 2010 settlement rows.
- Two additive 2021 settlement rows (Хийденсельга, 1,054; станция Шуйская, 709) were restored after municipality arithmetic and a separate compilation agreed. This does not independently verify their spatial identity.
- The legacy crosswalk contains identity conflicts and historical-code proposals that need review. No overall identity or reliable-coordinate percentage has been established.

## Not yet established

- Complete source-side demographic coverage for every year.
- A validated all-Russia temporal identity graph.
- The population-weighted share of each census year attached to a reviewed representative settlement point.
- A final release suitable for scientific spatial analysis across all records.

The audit's candidate-screen rates are not certified coverage. See the detailed audit report in the attached baseline assets and the working project's `research_audit/README.md`.
