# Russian settlement census research archive

Private, versioned research archive for reconstructing settlements in the 2002, 2010 and 2021 Russian censuses. It preserves the legacy project as a baseline and contains a source-corrected, reproducible Karelia pilot. Neither is a validated national settlement database.

## National source-selection and reviewed-link checkpoint

The private release `national-reviewed-checkpoint-r1-r2-2026-09-30` contains four hash-listed bundles: source-selection R1 inputs and outputs, plus reviewed-admissions R2 inputs and outputs/reviews. Download all four bundles and `asset_manifest.json` while signed in to an account with repository access. Verify archive hashes before extraction:

```sh
mkdir -p national-assets
gh release download national-reviewed-checkpoint-r1-r2-2026-09-30 --repo ZakBu/russian-settlements-research --dir national-assets
python3 scripts/verify_release_assets.py --manifest national-assets/asset_manifest.json --asset-dir national-assets
for asset in national_source_selection_r1_inputs.tar.zst national_source_selection_r1_outputs.tar.zst national_reviewed_admissions_r2_reproduction_inputs.tar.zst national_reviewed_admissions_r2_outputs.tar.zst; do
  zstd -dc "national-assets/$asset" | tar -xf - -C .
done
```

The bundle manifest records SHA-256 and byte length for every archived member. From a copy of the repository code and the extracted inputs, source selection can be rebuilt with `python3 research_rebuild/linkage/build_national_selection_r1.py --output /tmp/source-selection-r1-rebuilt`; R2 can be rebuilt with `python3 research_rebuild/linkage/build_national_admission_release_r2.py --output /tmp/admissions-r2-rebuilt`. The four R2 unit tests are run with `python3 -m unittest research_rebuild.tests.test_national_admission_release_r2 -v`. These releases report reviewed case coverage only, not national matching accuracy.

## Reproduce the Karelia pilot

The releases are private: download them while signed in to a GitHub account with read access to this repository, or authenticate the GitHub CLI with `gh auth login`. The commands below stage the exact source and review files checked by the build. The baseline source files and forensic outputs come from separate release archives; the supplemental bundle supplies the Karelia DOCX, fixed reviews and compact processed evidence.

```sh
mkdir -p baseline baseline-assets r6-assets r6-inputs r6-release
gh release download baseline-2026-09-29 --repo ZakBu/russian-settlements-research --pattern asset_manifest.json --dir baseline-assets
gh release download baseline-2026-09-29 --repo ZakBu/russian-settlements-research --pattern raw_interim_20260929.tar.zst --dir baseline-assets
gh release download baseline-2026-09-29 --repo ZakBu/russian-settlements-research --pattern forensic_outputs_20260929.tar.zst --dir baseline-assets
python3 scripts/verify_release_assets.py --manifest baseline-assets/asset_manifest.json --asset-dir baseline-assets --asset raw_interim_20260929.tar.zst --asset forensic_outputs_20260929.tar.zst
zstd -dc baseline-assets/raw_interim_20260929.tar.zst | tar -xf - -C baseline
zstd -dc baseline-assets/forensic_outputs_20260929.tar.zst | tar -xf - -C baseline
mkdir -p baseline/research_audit/evidence baseline/research_audit/output
mv baseline/evidence/* baseline/research_audit/evidence/
mv baseline/output/* baseline/research_audit/output/
rmdir baseline/evidence baseline/output
gh release download karelia-pilot-r6-2026-09-30 --repo ZakBu/russian-settlements-research --pattern asset_manifest.json --dir r6-assets
gh release download karelia-pilot-r6-2026-09-30 --repo ZakBu/russian-settlements-research --pattern karelia_pilot_inputs_r6.tar.xz --dir r6-assets
gh release download karelia-pilot-r6-2026-09-30 --repo ZakBu/russian-settlements-research --pattern karelia_pilot_release_r6.tar.xz --dir r6-assets
python3 scripts/verify_release_assets.py --manifest r6-assets/asset_manifest.json --asset-dir r6-assets --asset karelia_pilot_inputs_r6.tar.xz --asset karelia_pilot_release_r6.tar.xz
tar -xJf r6-assets/karelia_pilot_inputs_r6.tar.xz -C r6-inputs
tar -xJf r6-assets/karelia_pilot_release_r6.tar.xz -C r6-release
```

After confirming the downloaded release assets against their SHA-256 entries in each `asset_manifest.json`, install the pinned runtime dependencies and run from a clean checkout:

```sh
python3 -m pip install -r requirements-pilot.txt
python3 scripts/reproduce_karelia_pilot.py --data-root ./baseline --inputs-root ./r6-inputs/inputs-r6b --output-root ./new-output
```

The output directory must be new or empty. The runner extracts the official 2010 rural DOCX and the actual Rosstat Volume 1 Table 5 PDF, builds the pilot, then validates it again from outside the checkout. It stops on absent or altered inputs, broken observation bindings, or output integrity failures. Source and code hashes are recorded in the manifests. It also writes `linkage_review_portable.duckdb`, a materialized copy of the Parquet tables with a sidecar manifest that checks every table's typed contents and queries the copied database from another directory. Use that portable database when sharing the results; the builder's `linkage_review.duckdb` contains local Parquet-backed views.

## What the R6 pilot establishes

The 2010 Karelia selected population slice has 800 rows and 643,548 people: 24 urban rows from Rosstat Volume 1 Table 5 (502,217) and 776 rural rows from the regional census volume (141,331), including 109 zero-population rural rows. The corrected DOCX extraction preserves smart-tagged names and their raw row evidence. Its first download had a local TLS certificate-chain validation failure; the file is checksum-pinned and its values reconcile to independent controls, but that transport limitation remains open.

The pilot contains 24 case-reviewed urban/urban-type identity chains and 72 observation-level point admissions. It distinguishes current representative points from earlier-year `inferred_continuity` uses; those historical point uses are not measurements made during the censuses. By population, these 24 chains cover 537,395 of 716,284 selected people in 2002 (75.0254%), 502,217 of 643,548 in 2010 (78.0388%), and 423,680 of 533,121 in 2021 (79.4716%). These figures describe the selected Karelia snapshots only. They do not measure national accuracy or validate an automated national matching rule.

The 2002 Karelia selected slice exceeds its regional control by 3 people; that residual remains unassigned. The R6 2010 source slice reconciles to its published regional total. A separate audit found that 2010 NW workbook population values are confidentiality-protected and are not authoritative settlement counts.

## National status and limits

Two national evidence checkpoints now sit above the preserved baseline. Source-selection R1 replaces one 2002 Moscow parent aggregate with five disjoint city/subordinate-settlement rows while preserving the parent total, and replaces the 2010 Karelia legacy slice with the corrected official-source slice (+4,784 people). The 2021 selected snapshot is unchanged. Reviewed-admissions R2 records 51 accepted same-place edges and 81 point claims with typed identity/publication dependencies. These are a small, reviewed lower bound, not a national reconstruction.

Source-selection R1 contains 158,072 selected 2002 rows / 145,155,005 people; 152,313 selected 2010 rows / 142,172,038 people; and 155,414 selected 2021 rows / 147,182,123 people. These are selected-data denominators, not proof of completeness against every official census total. R2's admitted-coordinate coverage within those denominators is 0.3702% of 2002 population, 0.3532% of 2010, and 6.3558% of 2021; identity-linked population shares are 2.6615%, 0.3532%, and 2.8170%, respectively. Row coverage is reported separately in the release. Historical point uses are explicitly `inferred_continuity`; the provider-coordinate measurement date is unknown. Four direct Karelia points have an additional byte-preserved OSM attic geometry check as of 2021-10-01; OSM is not an official census boundary.

The national crosswalk outside these reviewed slices remains unvalidated baseline material. A present coordinate does not certify place identity or historical applicability. Aggregate population rows must not be attached to a physical settlement. The 2002 Moscow parent issue is resolved for the new selected snapshot only: Table 4 row 2154 is the Moscow-plus-subordinate-settlements aggregate (10,382,754), while its five disjoint children include the city-only Moscow row (10,126,424); the component migration preserves the aggregate sum and does not assert cross-year identity with current administrative boundaries.

The 99.9% population coverage goal has not been met or demonstrated. Coverage by population and coverage by settlement count must be reported separately; unresolved cases remain visible. Historical coordinates are inferred only when a reviewed continuity decision supports that use.

## Research documents and provenance

- [Current status](STATUS.md)
- [Data model and audit policy](METHODOLOGY.md)
- [Source inventory and use conditions](SOURCES.md)
- [Identity and coordinate methodology](research_rebuild/docs/LINKAGE_METHODOLOGY.md)
- [National source-selection and reviewed-admissions checkpoint](research_rebuild/evidence/releases/national_reviewed_checkpoint_r1_r2_20260930/asset_manifest.json)
- [Independent source-selection review](research_rebuild/evidence/reviews/national_source_selection_r1_independent_validation_20260930.json)
- [Independent reviewed-admissions review](research_rebuild/evidence/reviews/national_reviewed_admissions_r2_independent_review_20260930.json)
- [Karelia geometry evidence supplement](research_rebuild/evidence/reviews/geometry_refresh_r1_20260930/independent_geometry_review.json)

This repository and its attached assets are private. There is no blanket license for mixed-source material; rights and reuse conditions vary by source. A private archive upload does not imply permission for public redistribution.
