# Active research run: 2026-10-02

The user authorized implementation after the onboarding audit, with an eight-hour
delivery horizon (2026-10-03 05:34:36 UTC), observed population years beyond censuses,
dated OKTMO bindings/history, Git maintenance and economical agents.

The target is reliable spatial coverage of at least 99.9% of population per census
year and supported links to other observed years. It does not override evidence,
source grain, territorial scope or unresolved historical transformations.

## Current authoritative inputs

- Current population/source selection: published R2 selected observations.
- Identity decisions: R5b ledger, projected onto R2 endpoints (1,108 active; 54 held).
- Coordinates: 81 existing admitted point uses; large baseline candidates remain separate.
- Additional candidates: baseline forensic outputs and raw/interim archive, SHA verified.
- Baseline row/population and R2 metrics were recomputed during onboarding.

## Assigned work

- Root: integration, frozen run policy, bulk candidates, acceptance/quality gates,
  progress metrics, diary and Git checkpoints.
- Migration worker: 50 approved publication bindings and 54 displaced identity edges.
- Coordinate worker: source/object-level checks and explicit coordinate rule proposals.
- Source worker: already available additional years, source recovery and OKTMO history.
- Independent checks are scoped to concrete proposed decisions or invariants.

## Working sequence

1. Install and read relevant skills; preserve their source/version/hash registry.
2. Restore approved endpoint bindings without changing original identity evidence.
3. Generate mass candidates from existing sources with explicit competition flags.
4. Validate proposed rule families independently before mass admission.
5. Add verified noncensus observations and dated identifiers, preserving source scope.
6. Iterate on the measured population and systemic-risk residual.
7. Build the final table, evidence/decision tables, coverage receipt and replay commands.

Run policy: `config/mass_linkage_run_20261002.json`. It is fixed for this run;
metric definitions and source scope are not weakened to increase the reported score.
Raw inputs and large working outputs are staged under `/workspace/settlements-*` and
are not copied into Git. Frozen review files keep their original provenance paths.

## Continuation anchors

- Working branch: `research/mass-linkage-2026-10-02`.
- Python: `/workspace/settlements-venv/bin/python`.
- Published checkpoint/code: `/workspace/settlements-data`.
- Forensic outputs: `/workspace/settlements-baseline/output`.
- Raw/interim: `/workspace/settlements-raw`.
- New outputs: `/workspace/settlements-work`.
- Onboarding calculations: `/workspace/scratch/settlements_checkpoint_diagnostics.json`.

See `docs/DECISION_DIARY.md` for decisions; each scientific increment also receives
a machine-readable receipt with inputs, outputs, quality status and unresolved mass.
# Working migration accepted on 2026-10-02

The published R2 snapshot still has 1,108 active / 54 held edges. The new working
projection restores the 54 held endpoints using 50 previously reviewed
same-census publication bindings. It has 1,162 active edges, 982 components,
180 complete census chains, and zero same-year component collisions. Coordinates
remain the original 81 claims. This is not a new GitHub Release.

Replay with the pinned release data root:

```sh
python -m research_rebuild.mass_linkage.migrate_publication_bindings --data-root DATA_ROOT --output-root WORK_ROOT/migration
python -m research_rebuild.mass_linkage.validate_migration --data-root DATA_ROOT --migration-root WORK_ROOT/migration --receipt WORK_ROOT/independent_acceptance.json
```

The committed review is
`research_rebuild/evidence/reviews/mass_publication_migration_20261002/review.json`.
The separate verifier checks original evidence columns, reviewed replacement
fields, source hashes, exact endpoint transfers, and graph components using DFS.
