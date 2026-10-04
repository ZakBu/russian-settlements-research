## Текущий применённый рабочий пакет 4 октября 2026 (МСК)

Цель пользователя — 99% населения с координатой и временной связью вместе.
Она пока не достигнута. Новый пакет применён после независимой проверки правил
и объединённого графа; замороженный `c9abecf` остаётся неизменным входом.
Актуальная конфигурация: `config/mass_joint_20261004.json`; описание и точные
компактные контрольные артефакты: `docs/MASS_JOINT_RUN_20261004.md` и
`research_rebuild/evidence/mass_joint_20261004/manifest.json`.

Рабочий граф: 327745 строк принятых связей/подтверждений, 112577 полных
трёхпереписных компонент; точки 395636 выбранных переписных записей.
Первый пакет: 13813 прямых точек и 45238 переносов по графу.
Второе применение: 151 новая прямая точка и 253 новых переноса.
Третье применение: 729 связей, 621 прямая точка и 974 переноса.
Четвёртое применение: 3650 связей, 107 прямых точек и 2253 переноса.
Пятое применение: 1935 связей, 58 прямых точек и 163 переноса.
Текущий рабочий каталог: `accepted_mass_fifth_canonical_v3`.
Пакет с ошибочным происхождением точек сохранён как superseded, не используется.

| Доля населения от полного национального контроля | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| Точка физического НП и полная цепочка вместе | 83.220428% | 82.769834% | 80.872433% |
| Совместный показатель с отдельной преемственностью федеральных городов | 93.407089% | 94.238030% | 93.518006% |
| Остаток населения до 99% второго показателя | 8119046 | 6802786 | 8068515 |

Федеральные итоги представлены отдельным территориальным слоем; родитель
и дочерние НП не суммируются. Изменение охвата численности явно сохраняется.
Крым и Севастополь не получают фиктивных российских записей 2002/2010.
Проверки применения, происхождения точек и сохранности слоёв прошли. Удалённая публикация пока заблокирована:
GitHub Contents через приложение возвращает 403, CLI-токен недействителен.
Полный экспорт пятого состояния собран: 864043 наблюдения (465800 переписных,
516 официальных годовых, 34004 прежних буквальных и 363723 дополнительных
вторичных). Численность и идентификаторы переписей сохранены; вторичная
история не утверждает исторические координаты или принятую идентичность.
Точный контроль точек выявил1847 компонент с расхождением>5км (1495>20км).
Это диагностический конфликт, не автоматическое опровержение идентичности;
табличные проценты выше отражают допуски правил, а не доказанную правильность
всех точек. Среди них найден фактический дефект координат сырого GeoKLADR2011.
После исключения таких компонент из совместного показателя для проверки
получается92.940371% /93.890453% /93.110595%; отдельные конфликты могут
оказаться допустимыми крупными/полицентричными городами. Требуется разбор
общего источникового правила, затем массовая коррекция по собственным
независимо подтверждённым точкам, а не новые досье каждой деревни.
Следующие разделы описывают предшествующие контрольные состояния.

# Active research run: 2026-10-02

## Adopted scope and display decisions — 2026-10-03, 23:49 MSK

Use [the post-audit decisions](FEDERAL_CITIES_AND_WORKING_SERIES_DECISIONS_20261003.md).
Federal-territory reference points now belong in the primary operational spatial
measure under an exclusive hierarchy; atomic-NP coverage remains separate.
Dated secondary Wikidata observations may enter the working display with
explicit quality/scope limits. Implement these decisions without changing frozen
ledgers, reclassifying source grain, or asserting new historical identity.

## Active next phase — 2026-10-03 evening MSK

Use [AUDIT_AND_PLAN_99_20261003.md](AUDIT_AND_PLAN_99_20261003.md) and proposed
`config/research_rule_audit_20261003.json`. Prioritize large places>=2000 in any
observed year, reliable dated series/interyear identity, then remaining population
to99%. Candidate audits and extracted Wikidata statements are outside the frozen
scientific ledgers. New rules need their scoped independent pilot before admission.
Do not confuse optional old stage flags with canonical `decision_status`.

## Current authoritative working checkpoint — 2026-10-03

The latest consolidated state is described in
[the consolidated result](CONSOLIDATED_LOOP_RESULT_20261003.md).
Current table: `/workspace/settlements-delivery/continuation-consolidated-20261003`;
use its explicit corrected-input manifest alongside the preserved execution manifest.
Selected population and points: `primary_rural_dagestan_application_v1` in the continuation work directory.
Current identity graph: `shared_named_point_region_alias_metadata_correction_v1/accepted_identity_edges.parquet`.
Current source evidence: `primary_rural_dagestan_evidence_id_correction_v1/source_evidence.parquet`.
These two corrections change optional metadata only; original scientific input layers remain intact.
Selected records465800, accepted edges177707, census point uses332005,
full three-census chains44758;1400 same-census publication bindings.
Final export QA passes with the corrected-input manifest and explicit legacy metadata limitations.

The preceding accepted point extension is described in
[the direct historical point loop](DIRECT_HISTORICAL_POINT_LOOP_20261003.md).
Current points: `/workspace/settlements-work/continuation_20261003/accepted_direct_historical_point_2021_delta_v2/accepted_point_uses.parquet`.
Current coverage: `coverage_after_direct_historical_2021_v1.json` in the same continuation work directory.
Its export is `/workspace/settlements-delivery/direct-historical-2021-delta-20261003`; the later consolidated export supersedes it.
Selected records465800, accepted edges176568, accepted census point uses332005,
full three-census chains44758. The selected population, source evidence and identity graph remain those of the frozen mass-loop package below.

The preceding frozen working state is described in
[the mass-loop result](MASS_LOOP_RESULT_20261003.md) and
[its manifest](../research_rebuild/evidence/mass_linkage_loop_20261003/checkpoint_manifest.json).
That package has327430 accepted census point uses and does not include the next4575.
The earlier sections below are historical checkpoints, not current pointers.
Frozen archives remain unchanged.
99.9% has not been reached; source population, point quality, identity, events
and boundary comparability stay separate.


## Historical continuation checkpoint, 2026-10-03

The user requested continuing the work after the first eight-hour delivery.
Current authoritative working selected population/evidence/graph:
`/workspace/settlements-work/continuation_20261003/primary_population_application_v1`.
Current points:
`/workspace/settlements-work/continuation_20261003/accepted_after_podlipkovsky_hold_v1/accepted_point_uses.parquet`.
Current long-table delivery:
`/workspace/settlements-delivery/continuation-20261003`.
These supersede the first working outputs for new calculations; the published
archives, first delivery and historical review files remain byte-preserved.

There are316262 accepted point uses,175448 edges and44758 full census chains;
564 primary2010 publication replacements are applied. See
[continuation result](CONTINUATION_RESULT_20261003.md) for all metric axes,
source-quality constraints, residual priorities and the next loop. New source-only
federal-city rows,25k own-point diagnostics and named-code residual candidates
are not admitted by their existence. The99.9% target remains unmet.

The continuation uses `config/mass_linkage_continuation_20261003.json`, which
references direct primary verification of the same national controls. The original
fixed run config is unchanged. Root integrates; up to three economical agents own
disjoint tasks. Source/model changes enter the documented loop before admission.
The remaining text records the earlier run and its preserved intermediate states.

The user authorized implementation after the onboarding audit, with an eight-hour
delivery horizon (2026-10-03 05:34:36 UTC), observed population years beyond censuses,
dated OKTMO bindings/history, Git maintenance and economical agents.

The target is reliable spatial coverage of at least 99.9% of population per census
year and supported links to other observed years. It does not override evidence,
source grain, territorial scope or unresolved historical transformations.

## Current authoritative inputs

- Current population/source selection: published R2 selected observations.
- Identity decisions: published R2 has 1,108 active / 54 held; the independently accepted working migration restores all 1,162 original edges.
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
## Accepted additional observations

`annual_yearbook.py` reuses the pinned official 2024 yearbook table 4.9. It
recovers 516 January-1 estimates across 2022–2024 with explicit thousand-person
precision. `accept_annual_yearbook.py` applies the independent annual-scope review:
507 settlement links and nine federal-city-region aggregate links. Aggregate
links stay outside the ordinary settlement graph. No coordinates or boundary
harmonization are admitted by these modules.

Outputs: `WORK_ROOT/sources/annual-yearbook-accepted`. Reviews:
`research_rebuild/evidence/reviews/annual_yearbook_20261002`. Replay the candidate
builder, then pass the committed `review_annual_scope.json` to the acceptance
builder. The acceptance builder checks the review and frozen input hashes.

## Mass candidate and coordinate inventory checkpoint (23:05 UTC)

- `candidates/optimized_run`: 627,422 ledger rows; 538,535 unique-key pair
  rows across overlapping families, 47,199 ambiguous groups and no admissions.
  95.66 seconds, sampled peak RSS 3,085,772 KiB; source evidence is stored once.
- `candidates/graph_checks_release`: conflict-constrained hypothetical graphs;
  these are scenario diagnostics, not accepted coverage. The independent rule
  review supports scoped ordinary rules and states its 36-example limitation.
- `coordinates/ledger`: all 155,414 current 2021 rows reconciled to original
  source locators. 152,248 provider points exist; 140,541 rows pass the strict
  named-object candidate screens. Provider scores are not admission evidence.
- `wikidata/wide_v5`: the wider cached code/point/claim inventory; overlaps between
  TSV, truthy claims and module points remain one Wikidata lineage. Exact
  source/provider code equality plus object/uniqueness screens yield 99,377
  candidates carrying 96,519,604 recorded people. City FIAS-level-4 rows with
  absent settlement-specific name fields are a separate checked-rule proposal.
- `sources/admin_context_recovery_national_approved_subset`: 57,474 candidate source
  assertions FAILED independent structural review: broad forward-fill crosses
  actual districts. Do not use this artifact for admissions or enhanced keys.
  Its historical directory name `approved_subset` refers only to row-cell
  reconciliation, not scientific acceptance. Raw sources remain unchanged.
- `coverage/migrated_baseline_inventory.json`: reusable per-axis census receipt.
  Exact current-source point availability does not equal the entire legacy
  geocoding inventory: replacement records need explicit source bindings.
- `sources/federal_scope_probe`: 2021 federal-city-region aggregates remain
  outside settlement-point admission. Municipal sums alone do not establish
  physical city cores; this blocks an honest nationwide 99.9% claim.

The current implementation queue is ordinary identity admission, independent
coordinate-family checks, source-context application, then observed historical
years and dated identifier claims. At most three workers run concurrently.
Additional queued tasks retain their scoped instructions and do not duplicate
active work. The root retains integration, receipts, diary and Git ownership.

## Accepted identity application (2026-10-02 23:58 UTC)

`identity/accepted_ordinary_v4` is the active working graph: 128,569 edges,
251,312 linked observations, 124,681 components, 1,950 complete census chains.
Independent application review and per-axis coverage are committed under
`evidence/reviews/mass_identity_application_20261002`. Only identity is admitted.
Coordinates, population quality and boundary comparability remain separate.
Raw GeoKLADR verification supports reuse of dated source claims; it does not
automatically accept historical code-to-place bindings or legal intervals.

## Final working checkpoint within the requested eight-hour horizon

Authoritative working graph:accepted_historical_v2 (175448 edges,44758 chains).
Authoritative point ledger:accepted_final_v1 (305175 uses). Final table, coverage,
source snapshot candidates, event candidates and independent integration review:
/workspace/settlements-delivery/final. Detailed result/limitations/next iterations:
docs/MASS_LINKAGE_RESULT_20261003.md. The99.9% target was not reached;
no scope changes or candidate upgrades were used to claim it. Git write endpoint
remains403; the local branch and Git bundle retain all commits.
