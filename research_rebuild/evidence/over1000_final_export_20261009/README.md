Final full-table export integration proposal (no core/Git edits applied).

1. Insert `integration_hook.txt` at the END of `main()` in the reviewed `apply_batch16.py`, after `application_receipt.json` has been written. No export happens unless SETTLEMENTS_FINAL_EXPORT_DIR is set. The hook consumes that recipe's actual `state`, exact `ids`, `eventids`, `joint`, `scope`, `pins`, and coverage receipt; it does not guess a loader stage or infer credit from ordinary graph alone.
2. On a runner with hydrated inputs, run:

   SETTLEMENTS_FINAL_EXPORT_DIR=/workspace/settlements-delivery/final-full-20261009 python research_rebuild/evidence/over1000_root_20261009/apply_batch16.py

3. Verify with:

   python scripts/verify_release_assets.py --manifest /workspace/settlements-delivery/final-full-20261009/release-assets-manifest.json --asset-dir /workspace/settlements-delivery/final-full-20261009

4. Review `full_export_receipt.json`: primary source UID union equals final recipe `ids`; native UID effective year populations PLUS the separately retained six Moscow/St Petersburg territorial observations equal the final application receipt; ordinary wide header has EXACTLY the existing 135 columns; all ordinary exported IDs are in the final credit union. Missing source-year rows remain absent/unknown. Typed joint associations do not become ordinary identity/count equivalences.

Delivered full assets:
- ordinary_full3_with_primary_population_sources.csv.gz: regenerated strict ordinary wide table, same 135-column schema and np3 source-tuple UID recipe as stage68; current accepted points, separate original 2010 claims and the existing reviewed primary overlay.
- primary_credited_source_year_full.parquet: ALL final credited native source-year records including accepted lifecycle and joint-scope routes, full raw source metadata, raw/effective populations, separate exact admitted point provenance columns, and route flags. This is the companion for records that cannot honestly form an ordinary three-year row.
- applied_primary_credited_UID_roster.csv.gz: exact final source-ID credit union, raw/effective values and route flags.
- applied_state_observations.parquet, applied_component_snapshot.csv.gz, applied_point_snapshot.parquet: complete final State hydration inputs, not increments. Point snapshot reuses the certified68 streaming writer, preserving every field.
- accepted_common_federal_territory_axis.csv: existing six typed territorial observations, totals15043973/16383067/18612023; no ordinary NP conversion or duplicate child credit.
- final recipe scope/joint/exclusion overlays and application receipt, plus the reviewed 2010 population source overlay. Scope reinterpretations remain overlays; raw observations are not deleted.
- full_export_receipt.json, export_receipt.json and export_source_hash_manifest.json, SHA256 release-assets-manifest.json.

Existing builders reused:
`working_full_chain_20261007/export_full3.py`: adapter preserves its actual provenance resolution, stable tuple UID, ordering, raw inference flags, region-namespace interpretation and gzip metadata. Only its obsolete exactly-one-unknown-component assertion is removed. The 135-column header is frozen directly from published stage68. The old standalone primary overlay runner is hard-coded to stage62 and 510 claims, so this hook uses the final stage68 consolidated overlay rather than running that obsolete command.
`main_axis_residual_application68_20261008/stream_point_snapshot.py`: unchanged streaming snapshot writer.

Dependencies: Python 3.12, pandas, pyarrow, duckdb; checkout including this folder, final recipe, State/UnionFind/hydration modules and ALL recipe evidence. External runtime inputs include certified68 parquet/gzip snapshots, legacy accepted point donor ledgers and all actual source caches under /workspace/settlements-work, /workspace/settlements-raw and /workspace/settlements-delivery. Export's source resolution pins some caches not otherwise needed by replay; `export_source_hash_manifest.json` is the resulting complete byte manifest. The final recipe itself validates its source pins before export. A checkout alone cannot supply these data files.

Actions proposal: `publish-final-full.yml.proposal`, new workflow (keep publish-stage68.yml unchanged). Hosted runner requires root's immutable HTTPS runtime archive + SHA256. Archive roots must be external workspace data directories only; repository evidence must already be checked in/restored from a separately verified source, and archive must NOT contain russian-settlements-research. Alternatively run export on a provisioned workspace runner and use the existing generic verify/upload/readback steps to publish the newly generated assets. Proposed release uses a new tag and verifies downloaded remote bytes before marking latest.

Local limits: full export was NOT run (157MB free). No uncompressed CSV is written. Intermediate raw wide gzip is deleted after the effective table is complete; all original selected counts remain in the State snapshot and overlay-original columns. Actual output size depends on final active point schema; prefer Actions runner rather than assume local space suffices.

Validation performed here: Python compilation, schema capture (135 columns), bounded gzip-writer/helper smoke check, reviewed final recipe variable names/hook position, and no changes outside this evidence folder.
