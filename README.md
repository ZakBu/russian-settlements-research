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

## National identity-bridge checkpoint R4

The private release `national-reviewed-checkpoint-r4-2026-09-30` publishes the reviewed identity bridge through R4. R4 is a metadata-only correction to R3: 952 selected Volume 11 endpoint locators are now represented as explicit JSON nulls with an explanation; 13 existing Karelia endpoints retain their separate Volume 1 Table 5 locators. The identity edges, populations, coverage, and coordinate claims are unchanged from R3.

The release contains a minimal input bundle (the R3 parent outputs and the selected R1 observations needed for the metadata correction) and the R4 output bundle. From a fresh checkout, download and verify both bundles while signed in to the private repository:

```sh
mkdir -p national-r4-assets
gh release download national-reviewed-checkpoint-r4-2026-09-30 --repo ZakBu/russian-settlements-research --pattern asset_manifest.json --dir national-r4-assets
gh release download national-reviewed-checkpoint-r4-2026-09-30 --repo ZakBu/russian-settlements-research --pattern national_reviewed_admissions_r4_inputs.tar.zst --dir national-r4-assets
gh release download national-reviewed-checkpoint-r4-2026-09-30 --repo ZakBu/russian-settlements-research --pattern national_reviewed_admissions_r4_outputs.tar.zst --dir national-r4-assets
python3 scripts/verify_release_assets.py --manifest national-r4-assets/asset_manifest.json --asset-dir national-r4-assets
zstd -dc national-r4-assets/national_reviewed_admissions_r4_inputs.tar.zst | tar -xf - -C .
zstd -dc national-r4-assets/national_reviewed_admissions_r4_outputs.tar.zst | tar -xf - -C .
python3 -m pip install -r requirements-pilot.txt
python3 research_rebuild/linkage/build_national_reviewed_admissions_r4_metadata.py --output /tmp/national-admissions-r4-rebuilt
python3 -m unittest research_rebuild.tests.test_national_reviewed_admissions_r4_metadata -v
```

The built R4 artifact is an identity-coverage checkpoint, not spatial coverage. It has 1,003 accepted temporal same-place edges: 952 newly applied 2002–2010 bridges and 13 supporting decisions for pairs already present. Among selected R1 denominators, unique linked population is 76,546,921/145,155,005 (52.7346%) in 2002, 76,695,785/142,172,038 (53.9458%) in 2010, and 4,146,187/147,182,123 (2.8170%) in 2021. This release adds no coordinates; R2 coordinate claims are unchanged.

The 965 rule-eligible candidates comprise 952 newly admitted edges and 13 supporting decisions for pairs already represented. This rule-defined subset is not a probability sample of all settlements. The fixed 24-case review checked endpoint and source bindings across population bands; it does not estimate national matching precision. The matching rule uses an official Table 1.4 row with both census counts, exact selected endpoint bindings for both years, and an exact 2010 Table 5 settlement row. Held competitor, footnote, type-change and federal-city cases remain excluded. Census-year populations remain year-specific; same-place edges do not harmonize boundaries or population scope.

A Table 5 hierarchy limitation remains explicit: all 965 rows are `row_kind=settlement` and `aggregate_scope=atomic_settlement`, but the parser's broader `hierarchy_level` label is `subject_settlement_or_subject_aggregate`; 21 rows have only layout-level parent controls. This checkpoint preserves that evidence rather than treating parent layout as identity proof. The independent R4 review is in [the review record](research_rebuild/evidence/reviews/national_reviewed_admissions_r4_independent_validation_20260930/review.json), and the exact release hashes are in [the asset manifest](research_rebuild/evidence/releases/national_reviewed_checkpoint_r4_20260930/asset_manifest.json).

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

National source-selection R1 and reviewed-admissions R2 remain the parent checkpoint. Reviewed-admissions R4 adds a rule-defined official comparative-table identity bridge: 1,003 unique temporal edges, with 952 new 2002–2010 pairs and 13 already-represented pairs. The release reports unique identity-linked population by year separately from the unchanged R2 coordinate claims. It is a partial lower bound, not a national reconstruction or 99.9% spatial linkage.

Source-selection R1 contains 158,072 selected 2002 rows / 145,155,005 people; 152,313 selected 2010 rows / 142,172,038 people; and 155,414 selected 2021 rows / 147,182,123 people. These are selected-data denominators, not proof of completeness against every official census total. R2's admitted-coordinate coverage within those denominators is 0.3702% of 2002 population, 0.3532% of 2010, and 6.3558% of 2021; identity-linked population shares are 2.6615%, 0.3532%, and 2.8170%, respectively. Row coverage is reported separately in the release. Historical point uses are explicitly `inferred_continuity`; the provider-coordinate measurement date is unknown. Four direct Karelia points have an additional byte-preserved OSM attic geometry check as of 2021-10-01; OSM is not an official census boundary.

The national crosswalk outside these reviewed slices remains unvalidated baseline material. A present coordinate does not certify place identity or historical applicability. Aggregate population rows must not be attached to a physical settlement. The 2002 Moscow parent issue is resolved for the new selected snapshot only: Table 4 row 2154 is the Moscow-plus-subordinate-settlements aggregate (10,382,754), while its five disjoint children include the city-only Moscow row (10,126,424); the component migration preserves the aggregate sum and does not assert cross-year identity with current administrative boundaries.

The 99.9% population coverage goal has not been met or demonstrated. Coverage by population and coverage by settlement count must be reported separately; unresolved cases remain visible. Historical coordinates are inferred only when a reviewed continuity decision supports that use.

## Research documents and provenance

- [Current status](STATUS.md)
- [Data model and audit policy](METHODOLOGY.md)
- [Source inventory and use conditions](SOURCES.md)
- [Identity and coordinate methodology](research_rebuild/docs/LINKAGE_METHODOLOGY.md)
- [National source-selection and reviewed-admissions checkpoint R1/R2](research_rebuild/evidence/releases/national_reviewed_checkpoint_r1_r2_20260930/asset_manifest.json)
- [National reviewed-admissions checkpoint R4](research_rebuild/evidence/releases/national_reviewed_checkpoint_r4_20260930/asset_manifest.json)
- [Independent R4 review](research_rebuild/evidence/reviews/national_reviewed_admissions_r4_independent_validation_20260930/review.json)
- [Independent source-selection review](research_rebuild/evidence/reviews/national_source_selection_r1_independent_validation_20260930.json)
- [Independent reviewed-admissions review](research_rebuild/evidence/reviews/national_reviewed_admissions_r2_independent_review_20260930.json)
- [Karelia geometry evidence supplement](research_rebuild/evidence/reviews/geometry_refresh_r1_20260930/independent_geometry_review.json)

This repository and its attached assets are private. There is no blanket license for mixed-source material; rights and reuse conditions vary by source. A private archive upload does not imply permission for public redistribution.
