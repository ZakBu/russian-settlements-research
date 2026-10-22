# Report builder: final selection pending

Builder code is prepared; final PDF/DOCX rendering intentionally waits for root-selected model (possibly WordCi), repaired hierarchy, recomputed analysis and fresh atlas. `build_research_package.py --model ABS_SELECTED_MODEL_DIR` derives its configuration by exact run configurationSHA, validates analysis belongs to that model and inputSHA still match, then validates required model maps against current manifests. A STALEanalysis has been checked to block rendering before writing deliverables.

`report_enrichment.py` dynamically reads final nodes2010quality/overrides, admitted four-region receipts, all center×level type counts, actual operational named cases, new land2021context and experimental atlasbonitet, selected regression and mass-ablation results, and exact bibliography URLs/pages. It writes full report, named-case tables, all-level type table, source-quality summary, and short supervisor brief. Atlas assembly excludes superseded model names and manifest entries with changed input hashes. Unchanged input bytes are checked before/after rendering.

Expected outputs after final authorized run: SGRT_RESEARCH_REPORT_20261021.pdf/.docx/.md; SGRT_SUPERVISOR_BRIEF_20261021.pdf/.docx/.md; SGRT_ATLAS_20261021.pdf; report_types_all_levels.csv; report_named_type_cases.parquet; report_population_source_summary.json; report_bibliography.txt; render_checks.json; package_inputs.json. Root owns GPKG and medical validation.

Pending integration: modelagent should provide exact WordCi configuration rank-key/formula; root should provide refreshed extended-medical validation receipt schema/path. No report produced from first-pass stale calculations is endorsed by this builder state.
