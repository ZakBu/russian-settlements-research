# Как читать и воспроизводить текущую семью СГРТ477

Документ относится к `model/cycle07_scale_hierarchy/source477_adminall_v2`, а не к прежней четырёхуровневой модели цикла 06 и не к контрольному проходу со старым геометрическим правилом ядра. Основные пять лесов и 50 повторений, шесть отдельных сценариев чувствительности и реестр четырёх устойчивых вложенных срезов уже рассчитаны. Готовность всех последующих таблиц, карт и отчёта определяется отдельными допусками.

**Это инструкция по сохранённой фактической конфигурации, а не обещание переносимого полного запуска одной командой.** В контрактах нормализации, предварительных регистрациях и квитанциях есть зафиксированные абсолютные пути `/workspace/russian-settlements-research/...`. Замена этих строк меняет байты конфигурации, её SHA и область допуска. Установка Python-пакетов не восстанавливает научные данные и не заменяет источниковые проверки.

## Лёгкая проверка готового пакета

Обычному читателю не нужно заново рассчитывать модель или пересобирать PDF. Достаточно прочитать готовые материалы и проверить сохранённые байты:

```bash
cd /workspace/russian-settlements-research
export SGRT_BASE="$PWD/research/sgrt_word_completion_20261021"
python "$SGRT_BASE/coordination/cycle07_reproduction/verify_release.py" \
  --root "$SGRT_BASE" \
  --manifest "$SGRT_BASE/delivery/cycle07_current_primary_v1/final_bundle_manifest.json"
```

`verify_release.py` использует только стандартную библиотеку Python и читает файлы: он проверяет существование, размеры и SHA256 путей из manifest, ничего не создаёт и не меняет. `PASS` означает совпадение сохранённых байтов, а не новую научную проверку. При lazy Git checkout чтение отсутствующих опубликованных blobs может потребовать доступа к origin. Финальный manifest формируется после закрытия выходов; до его появления эта команда закономерно не даёт приёмку. Финальный акт стейкхолдера — `coordination/cycle07_release_contract/final_release_verdict_v1.json`. Manifest и акт не включают сами себя в свои SHA-списки; их вместе фиксирует Git.

Ниже отдельно приведена тяжёлая пересборка: она нужна для воспроизведения вычислений или документов, использует исходные данные и зависимости и пишет исключительно в свежие каталоги. Верификатор не запускает эти стадии.

## Сначала читать готовые результаты

Все пути в таблице отсчитываются от `research/sgrt_word_completion_20261021/`.

| Материал | Где читать | Что проверять рядом |
|---|---|---|
| Текущее состояние выпуска | `coordination/cycle07_release_contract/release_progress_current_v1.json` | Это текущий перечень требований; исторические `pending` в неизменённых авторских receipts не заменяют более поздний независимый допуск. |
| Основная модель | `model/cycle07_scale_hierarchy/source477_adminall_v2/output_primary_v1/` | `pre_execution_binding.json`, `run_receipt.json`, `baseline_export_manifest.json`; отдельные независимые допуски ниже. |
| Состав единиц | В том же каталоге: `cap_XXX_raw_units.parquet` и `cap_XXX_raw_memberships.parquet` | В каждом файле различать `supported_end_forest` и `candidate_knee_or_fallback`; они не взаимозаменяемы. |
| Все 50 повторений | `output_primary_v1/all_50_bootstrap_ledger.parquet`, `retained_resolution_stability.csv` и 250 файлов `rep_XX_cap_XXX_numeric_witnesses.npz` | `reviews/cycle07_primary477_units_independent/all250_stability_admission.json`. |
| Устойчивые вложенные срезы | `model/cycle07_scale_hierarchy/empirical_registry_source477_v1/empirical_level_registry.csv` и `level_00N_raw_*.parquet` | `reviews/cycle07_empirical_registry_independent/audit.json`; это устойчивые пространственные разрешения, не доказанные функциональные порядки. |
| Нормализованное население и контексты пяти лесов | `typology/cycle07_complete/normalized_source477_v1/capXXX_supported_end_forest/` | Собственный `receipt.json` и допуск соответствующего `capXXX` в `reviews/cycle07_source477_normalization_independent/`. |
| Полная измеренная типология | `typology/cycle07_complete/classified_source477_v1/capXXX_supported_end_forest/complete_typology.parquet`, `type_counts.csv` | Допуск соответствующего представления в `reviews/cycle07_typology_independent/`. Наличие Parquet само по себе не означает, что независимая проверка уже завершена. |
| Принятый статистический срез 60 минут | `analysis/cycle07_newsource060_admitted_handoff_v2.json`, `analysis/cycle07_newsource060_interpretation_v3.md`, `analysis/cycle07_newsource060_baseline_v1/` | Handoff связывает конкретные источники, результаты, численные и визуальные проверки. Другие срезы не считаются готовыми по аналогии с 60 минутами. |
| Принятый статистический срез 120 минут | `analysis/cycle07_newsource120_admitted_handoff_v1.json`, `analysis/cycle07_newsource120_interpretation_v1.md`, `analysis/cycle07_newsource120_baseline_v1/` | Отдельные источниковый, numerical, spatial и visual допуски в handoff; сводка остальных принятых лесов приведена ниже; вложенные срезы проверяются отдельно. |
| Принятая статистика остальных лесов 030/045/090 | `analysis/cycle07_newsource030045090_admitted_handoff_v1.json` | Все пять лесов вместе: `analysis/cycle07_supported_forests_numeric_summary_v1/receipt.json` и `interpretation_ru.md`; 97 фактических fits. |
| Все четыре нормализованных и классифицированных вложенных среза | `typology/cycle07_complete/normalized_empirical_source477_v1/level_000..003/`, `classified_empirical_source477_v1/level_000..003/` | Каждый нормализованный срез проверен 670 проверками, типология — 39; соответствующие contracts в `contracts_empirical_source477_v2/`. |
| Популяционная чувствительность: 31 представление | `typology/cycle07_complete/normalized_sensitivity_light_source477_v2/`, `classified_sensitivity_light_source477_v1/` | `reviews/cycle07_sensitivity_population_types_independent_v1/combined_admission.json`, 4557 проверок; контекстные слои не проецировались. |
| Все девять принятых статистических представлений | `analysis/cycle07_all9_admitted_handoff_v1/handoff.json` | 177 fits, 108 gates, 1307 интервалов; единый перечень точных директорий результатов, графиков и ограничений. |
| Основной итоговый атлас | `delivery/cycle07_current_primary_v1/atlas_v3/main/atlas_cycle07.pdf` | Основной том: четыре вложенных разрешения и городские фрагменты; общий `atlas_v3/atlas_receipt.json`, затем final manifest/verdict. |
| Операционное картографическое приложение | `delivery/cycle07_current_primary_v1/atlas_v3/operational_supplement/atlas_cycle07.pdf` | Все пять отдельных operational forests, собственный `render_receipt.json`; не складывать их как уровни одной иерархии. |
| Исследовательский отчёт | `delivery/cycle07_current_primary_v1/report_v2/SGRT_RESEARCH_REPORT.pdf` (также `.docx`, `.md`) | `report_v2/report_input_binding.json`, итоговый manifest и акт стейкхолдера. |
| Записка научному руководителю | `delivery/cycle07_current_primary_v1/report_v2/SUPERVISOR_BRIEF.pdf` (также `.docx`, `.md`) | Тот же exact input bundle; короткое изложение не меняет ограничений исследования. |
| Фактический картографический просмотр 60 минут | `maps/cycle07_newsource060_preview_v1/actual060_preview.pdf` | `maps/cycle07_newsource060_preview_binding_v1/map_config.json`, `reviews/cycle07_newsource060_preview_independent/admission.json`, последующая визуальная проверка. Это предварительный просмотр одного сценария, а не полный итоговый атлас. |
| Библиография | `literature/cycle07_classics_final/READOUT_RU.md`, `bibliography.csv` | `source_receipts.json`; выборочное чтение первичных материалов не объявляется чтением всех книг. |

Конечная семья выпуска — `delivery/cycle07_current_primary_v1/`. Основной атлас и операционное приложение находятся в `atlas_v3/`, отчёт и записка руководителю — в `report_v2/`. Выходы атласа и документов сформированы и связаны конкретными receipts. Наличие файлов не заменяет финальную проверку manifest и акта стейкхолдера: общий выпуск считается закрытым по этим двум документам. Старый `atlas/` — отклонённая по оформлению attempt01, не итоговый атлас.

## Среда и зависимости

Фактическая среда: Python3.12.14, Linux x86_64. Наблюдённые версии даны в [requirements_actual.txt](/archive/README.md#удалённые-материалы), полная квитанция — [runtime_actual.json](/archive/README.md#удалённые-материалы). Перечень получен из установленного окружения и сверки импортов, а не из предположений о зависимостях. Это не проверенный lock для другой ОС/архитектуры. Отдельный чистый `pip install` в этом аудите не выполнялся.

Пример создания нового окружения, если нужного ещё нет:

```bash
python3.12 -m venv /workspace/scratch/sgrt-replay-venv
source /workspace/scratch/sgrt-replay-venv/bin/activate
python -m pip install -r research/sgrt_word_completion_20261021/coordination/cycle07_reproduction/requirements_actual.txt
```

Перед установкой requirements пример предполагает рабочий каталог корня репозитория; переменные ниже определяются там же.

Для PDF-отчёта фактический общий renderer использует шрифт `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. Matplotlib также должен располагать кириллическим DejaVu Sans. Для чтения готовых CSV/Parquet и расчёта модели не требуется компиляция дорожного графа. Для повторного извлечения первичных OSM/растров используются дополнительные пакеты из второй части requirements; некоторые upstream-стадии требуют системных инструментов и C++-компилятора, указанных в собственных receipts. Эти upstream-проходы не запускались при подготовке инструкции.

Фактические справки CLI сохранены в [cli_help/](cli_help/) с кодами возврата и SHA исполнителей в [cli_help_receipt.json](/archive/README.md#удалённые-материалы). В этом аудите выполнялись `--help`, чтение метаданных, контроль кэша и два свежих `--prepare-only`; иерархия, регрессии и карты заново не рассчитывались. Подготовка в исходной базе и в другой базе с новым путём к кэшу дала тот же SHA `c4ce5d42…`; подробности и точные команды — [dry_prepare_receipt.json](/archive/README.md#удалённые-материалы).

## Зафиксированные источники и код

Основной binding содержит восемь входов, протокол и SHA семи исполнителей. Полная машинная копия — [source_binding_snapshot.json](/archive/README.md#удалённые-материалы); исходный binding остаётся неизменным. Главные источники:

| Файл относительно базы исследования | SHA256 |
|---|---|
| `reviews/cycle07_mass_pool477_v2_independent/combined_admission.json` | `596155ea79b0bdd4eb4c6ea5102eeb582098e1746b6170e9eb20cdc81ed81481` |
| `reviews/cycle07_matrix477_independent/combined_admission.json` | `f3d2c6b6cdc8a62346b5ea92728610c9c60c7010decfe4c251124751447bdcd8` |
| `model_inputs_cycle07/cycle07_source_mass_pool_admitted_handoff.json` | `ddb391b3918c4be431c63b0638e4683f1d632d1a77872b28f9a619982179c36a` |
| `model_inputs_cycle07/institutional_mass477_v2/computed/effective_full_nodes.parquet` | `e006d91a1250576020131da66a1a420f76f55cf3a9b8cae5fd5009f36889ad04` |
| `model_inputs_cycle07/institutional_mass477_v2/computed/fixed_own_mass_components.parquet` | `64a2684e998ff1d44ae8028683623c42a60019022f421dcd2b5ba38d8fbe6bd4` |
| `transport/cycle07_geography_recovery_extension/candidate_travel_times_manifest.json` | `11c0be3a5b9c2dd6e8980e254352f93bd971b08493c570b6734b1d616d2102f5` |
| `model/cycle07_scale_hierarchy/source477_adminall_v2/source_provider_pool/active_provider_pool.parquet` | `328247bfaee753e84a6e63fc8d4285347708426bd1e7183d6f0d882834b42c5b` |
| `model/cycle07_scale_hierarchy/source477_adminall_v2/source_provider_pool/provider_pool_receipt.json` | `a56576d70fa410eb6bbd51a7947f47fc64fbcf36eb633ff42fb98017d7419542` |

Самостоятельная масса центра берётся из `fixed_own_mass_components.parquet`, а не оценивается по получившемуся району. Изменение этих источников — новая исследовательская семья, а не технический повтор. В snapshots историческая строка `pending` протокола сохраняется побайтово; позднейший controller admission `e5abc939…` связывает принятый код и протокол.

## Безопасная область повторного запуска

Переменные ниже задаются из корня репозитория. Основной model executor самостоятельно определяет базу исследования. Для нормализации, типологии, анализа и карт рабочий каталог должен быть `$SGRT_BASE`: некоторые относительные пути допусков внутри замороженных контрактов разрешаются относительно текущего каталога, даже когда сам `--contract` задан абсолютным путём. Перед каждым downstream-примером ниже явно указан `cd "$SGRT_BASE"`. Все новые выходы находятся в отдельном каталоге. Имена переменных не заменяют системные `$HOME` или `$CODEX_HOME`.

```bash
cd /workspace/russian-settlements-research
export SGRT_BASE="$PWD/research/sgrt_word_completion_20261021"
export SGRT_MODEL="$SGRT_BASE/model/cycle07_scale_hierarchy/source477_adminall_v2"
export SGRT_ARCHIVE="$SGRT_BASE/model/cycle07_scale_hierarchy/source477_numeric_cache_archive_v1"
export SGRT_REPLAY="$(mktemp -d /workspace/scratch/sgrt-replay-XXXXXX)"
```

Не удалять принятые каталоги, не менять их receipts и не использовать их как `--output`. Флаг модели `--resume` означает запуск после подготовленного допуска; **это не универсальное продолжение прерванного numerical checkpoint**. Исполнитель не восстанавливает произвольный незавершённый bootstrap. Для независимого повтора нужен новый каталог.

Новые выходы не подключаются автоматически к следующей стадии: сохранённый downstream-контракт продолжает указывать на свои исходные принятые файлы. Для замены входов новым расчётом требуется явное связывание и проверка SHA, а при изменении байтов — новый соответствующий допуск. Ниже показаны повторы стадий от их зафиксированных исходных входов, а не скрытая автоматическая перепривязка всего конвейера.

## Точный кэш потенциальных связей без пересчёта маршрутов

Архив сохраняет четыре точных файла принятого кэша: `cache_receipt.json`, `origin_mapping.parquet`, `provider_mapping.parquet`, `routes_180.npz`. В маршрутах 77479271 запись, размер матрицы 155606×26680; NPZ имеет SHA256 `7e492de3853ac3a1fe74ed503ea94ac4c3188d18841c4857857b8edf6954d997`. Часть mappings берётся из сохранённых исходных таблиц по путям `manifest.json`.

```bash
# Проверка частей архива: ничего не восстанавливает и не меняет.
python "$SGRT_ARCHIVE/restore.py" --verify-only

# Восстановление в новый каталог. Иной существующий файл не перезаписывается.
python "$SGRT_ARCHIVE/restore.py" --output "$SGRT_REPLAY/cache"

# Отдельная read-only проверка именно четырёх восстановленных файлов.
python "$SGRT_BASE/coordination/cycle07_reproduction/verify_cached_files.py" \
  --cache "$SGRT_REPLAY/cache"
```

`restore.py --verify-only` проверяет **архивные части**, а не произвольный существующий каталог назначения. Последняя команда проверяет SHA и размер самих файлов восстановленного кэша. Полный независимый допуск источника—CSR: `reviews/cycle07_source_cache_numeric_independent/audit.json`; источник матрицы — `transport/cycle07_geography_recovery_extension/candidate_travel_times_manifest.json` и `reviews/cycle07_matrix477_independent/combined_admission.json`.

Для этой стадии нужны сохранённые части архива и mappings, а не повторное скачивание полного OSM PBF. Если локальный checkout использует Git `blob:none`/promisor, отсутствующие опубликованные blobs будут загружаться Git по требованию; для этого нужен доступ к origin. Не следует запускать очистку объектов или `git repack` ради воспроизведения. Локальные первичные файлы вне Git могут потребоваться для upstream-проверок и полного восстановления исходников; их URL, SHA и условия доступа содержатся в исходных receipts. Они не появляются от установки requirements.

## Повтор основной модели и 50 проверок устойчивости

```bash
python "$SGRT_MODEL/run.py" --prepare-only \
  --output "$SGRT_REPLAY/primary" --cache "$SGRT_REPLAY/cache" --scenario primary

python - "$SGRT_REPLAY/primary/pre_execution_binding.json" \
  "$SGRT_BASE/reviews/cycle07_controller_independent/controller_source477_v2_admission.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]);review=json.loads(Path(sys.argv[2]).read_text())
assert hashlib.sha256(p.read_bytes()).hexdigest()==review['accepted_pre_execution_binding_sha256']
assert review['all_checks_passed'] is True
print('Exact prepared input bundle matches existing independent admission')
PY

python "$SGRT_MODEL/run.py" --resume \
  --output "$SGRT_REPLAY/primary" --cache "$SGRT_REPLAY/cache" --scenario primary \
  --admission "$SGRT_BASE/reviews/cycle07_controller_independent/controller_source477_v2_admission.json"
```

Последняя команда выполняет настоящий национальный расчёт, включая 50 условных географических повторений, и может занять значительное время. `--prepare-only` не рассчитывает иерархию. Ожидаемый SHA неизменённого основного bundle — `c4ce5d42c086c78447afb9593fbd0eebe4b5db20e624e17f608979684c8a0ed5`. Допуск связывает точные код, протокол, исходные данные и кэш. При несовпадении SHA остановиться и выяснить источник отличия; не переписывать поле допуска ради запуска.

Для проверки только основного пути допустим отдельный новый `--output` и `--baseline-only`; этот результат не содержит завершённых 50 повторений. Не подписывать его полным результатом устойчивости.

Фактический исходный результат имеет `run_receipt.json`, пять `cap_XXX_*` наборов,250numeric witnesses и `all_50_bootstrap_ledger.parquet`. Независимые проверки: `reviews/cycle07_primary477_units_independent/baseline_combined_admission.json` и `all250_stability_admission.json`. Сохранённые подписи на исходный результат не являются автоматическим независимым допуском нового расчёта: сначала сравнить его выходы/значения.

### Шесть сценариев чувствительности

Они фактически рассчитаны как отдельные **baseline-only** пути: `tau30`, `tau90`, `gamma0.5`, `gamma2`, `directed_max`, `extended180`. У них нет обещанных по аналогии 50 собственных повторений. Полные исходные bundle и пути допусков перечислены в `prepared_sensitivity_bindings.json` и `reviews/cycle07_controller_independent/sensitivity_source477_v2/index.json`.

Пример для `tau30`:

```bash
python "$SGRT_MODEL/run.py" --prepare-only --scenario tau30 \
  --cache "$SGRT_REPLAY/cache" --output "$SGRT_REPLAY/tau30"
# Перед запуском проверить SHA нового bundle против tau30.json тем же способом, что выше.
python "$SGRT_MODEL/run.py" --resume --baseline-only --scenario tau30 \
  --cache "$SGRT_REPLAY/cache" --output "$SGRT_REPLAY/tau30" \
  --admission "$SGRT_BASE/reviews/cycle07_controller_independent/sensitivity_source477_v2/tau30.json"
```

Для остальных использовать их собственный scenario и допуск: `tau90.json`, `gamma0p5.json`, `gamma2.json`, `directed_max.json`, `extended180.json`. Не переносить основной допуск в другой scenario. Готовые исходные чувствительности находятся в `output_sensitivity_*_v1/`; `baseline_stage_receipt.json` отличает их от полной основной серии.

## Нормализация населения и источниковых контекстов

Фактические исполнители смешаны по версиям с отдельной проверкой эквивалентности. Их нельзя задним числом объявить одним запуском v6.

| Представление | Фактически использованный исполнитель | Контракт |
|---|---|---|
| Лес 060/120 | `normalize_unit_populations_source477_v4.py` | `contracts_source477_v1/normalize_cap060_supported_end_forest.json` и аналогичный 120 |
| Лес 030/045/090 | `normalize_unit_populations_source477_v5_fast.py` | `contracts_source477_fast_v1/normalize_capXXX_supported_end_forest.json` |
| Вложенные срезы 000–003 | `normalize_unit_populations_source477_v6_fast.py` | `contracts_empirical_source477_v2/normalize_level_00N.json`; готовность каждого выхода проверять отдельно |

Все эти пути находятся в `typology/cycle07_complete/`. Пример повтора 060 из его исходного контракта:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/typology/cycle07_complete/normalize_unit_populations_source477_v4.py" \
  --contract "$SGRT_BASE/typology/cycle07_complete/contracts_source477_v1/normalize_cap060_supported_end_forest.json" \
  --output "$SGRT_REPLAY/normalized060"
```

Пример фактического типа команды для вложенного среза:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/typology/cycle07_complete/normalize_unit_populations_source477_v6_fast.py" \
  --contract "$SGRT_BASE/typology/cycle07_complete/contracts_empirical_source477_v2/normalize_level_000.json" \
  --output "$SGRT_REPLAY/normalized_level000"
```

Контракты связывают исходную рамку e006…,353 первичных уточнения 2010, принятые 477 координат и отдельные обновлённые климатические/почвенные/тематические слои. Старый effective source view a3d6… не подставляется вместо новой семьи. Неизвестное население любого контекстного города запрещает полноту всей системы; известные обычные и сельские суммы остаются отдельно.

Нужны реальные `raw_units_path`, `memberships_path`, `base_nodes_path`, контекстные слои и **все** допуски из контракта. Исполнитель откажется при несовпадении источников, кода или prospective admission. Ускорители v5/v6 имеют отдельные допуски в `reviews/cycle07_controller_independent/fast_source477_normalizer*_admission_v1.json`; фактический построчный source/math review каждой новой таблицы остаётся самостоятельным требованием.

### Популяционная чувствительность: отдельная light-стадия

31 представление фактически нормализовано V7 fast и классифицировано тем же frozen классификатором. Полные контекстные функции для этой проверки не проецировались; пустой реестр контекстов означает `NOT_PROJECTED`, а не наблюдаемое отсутствие функций. Эта стадия не заменяет полный функциональный сравнительный анализ.

У batch-исполнителя `--output` задаёт только каталог логов: каталоги данных берутся из `normalized_output_path` каждой записи manifest. Поэтому исходный manifest нельзя передать для нового запуска поверх принятых результатов. Для повтора создаётся отдельная копия manifest, меняющая только назначения выходов, с сохранением exact контрактов/SHA:

```bash
cd "$SGRT_BASE"
python - "$SGRT_BASE" "$SGRT_REPLAY" <<'PYMANIFEST'
import json,sys
from pathlib import Path
base,replay=map(Path,sys.argv[1:])
data=json.loads((base/'typology/cycle07_complete/contracts_sensitivity_light_source477_v2/execution_manifest.json').read_text())
for entry in data['entries']:
    entry['normalized_output_path']=str(replay/'light_normalized'/entry['scenario']/('cap%03d_supported_end_forest'%entry['cap_minutes']))
(replay/'light_execution_manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
PYMANIFEST
python "$SGRT_BASE/typology/cycle07_complete/run_light_sensitivity_batch.py" \
  --manifest "$SGRT_REPLAY/light_execution_manifest.json" \
  --normalizer "$SGRT_BASE/typology/cycle07_complete/normalize_unit_populations_source477_v7_fast.py" \
  --output "$SGRT_REPLAY/light_logs" --workers 2
```

Новая light-нормализация не получает автоматически фактический допуск старых результатов. Для классификации свежих файлов нужен contract binder V4 с соответствующей источниковой проверкой и точным совпадением admitted units/nodes SHA, как описано ниже. Оригинальный manifest и принятые каталоги остаются неизменными.

## Полная измеренная классификация

Пример повтора классификации из готового принятого контракта 060:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/typology/cycle07_complete/classify_complete.py" \
  --contract "$SGRT_BASE/typology/cycle07_complete/contracts_source477_v1/classify_cap060_supported_end_forest.json" \
  --output "$SGRT_REPLAY/classified060"
```

Этот контракт читает сохранённую исходную нормализацию, а не автоматически `$SGRT_REPLAY/normalized060`. Для связывания нового normalized-каталога служит отдельный builder:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/typology/cycle07_complete/bind_classification_contract_source477_v4.py" \
  --normalized "$SGRT_REPLAY/normalized060" \
  --admission "$SGRT_BASE/reviews/cycle07_source477_normalization_independent/cap060_final_v2/audit.json" \
  --hierarchy-admission "$SGRT_BASE/reviews/cycle07_primary477_units_independent/baseline_combined_admission.json" \
  --output "$SGRT_REPLAY/classify060_contract.json"
```

Повторное применение старого допуска допустимо только если новые нормализованные units/nodes **побайтово совпали с принятыми SHA**; builder это проверяет и откажется при ином результате. Если значения или байты изменились, нужна новая фактическая проверка, а не редактирование старой квитанции. Для иных cap/эмпирических срезов используются именно их исходные договоры и источниковые проверки.

Для графиков типов из новой классификации:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/typology/cycle07_complete/render_case_charts_v3.py" \
  --classification "$SGRT_REPLAY/classified060" --output "$SGRT_REPLAY/type_case_charts060"
```

Выходы классификатора: `complete_typology.parquet`, `type_counts.csv`, `trajectory_evidence.parquet`, `case_chart_selection.parquet`, `receipt.json`. Не подменять измеренный тип доказанным механизмом Word. Графики случаев строит `render_case_charts_v3.py`; его фактический CLI сохранён в справках.

## Статистика: воспроизводимый принятый срез 060

Источники и метод текущего 060 закреплены в `analysis/cycle07_newsource060_admitted_handoff_v2.json`. Принятый агрегат — `analysis/cycle07_newsource060_aggregates_v1/receipt.json`; входной контракт — `analysis/cycle07_tools/newsource060_input_contract_v1.json`. Новый nearest-large-city контекст имеет единое поле≤180 минут и берётся из `cycle07_source477_city_context180_v2`, а не из отвергнутогоv1 или старой 360-минутной версии.

Источник можно агрегировать отдельно в новый каталог:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/analysis/cycle07_tools/new_adapter_source477.py" \
  --contract analysis/cycle07_tools/newsource060_input_contract_v1.json \
  --output "$SGRT_REPLAY/analysis060_sources"
```

Это source preparation, а не регрессия. При использовании **нового** source receipt последующая регистрация содержит новый абсолютный путь и может получить иной SHA; тогда старый execution admission автоматически не переносится. Для точного повтора принятых 060 метрик ниже используется сохранённый исходный принятый агрегат:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" \
  --source-receipt analysis/cycle07_newsource060_aggregates_v1/receipt.json \
  --source-proof model/cycle07_scale_hierarchy/city_context180_independent_v1/v2_admission.json \
  --source-proof reviews/cycle07_source477_normalization_independent/cap060_final_v2/audit.json \
  --source-proof reviews/cycle07_analysis_prospective_independent/code_protocol_v2_admission.json \
  --output "$SGRT_REPLAY/analysis060" --stage preregister

python - "$SGRT_REPLAY/analysis060/preregistration.json" \
  "$SGRT_BASE/reviews/cycle07_analysis_new060_source_independent/preregistration_execution_admission.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
assert hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()==json.loads(Path(sys.argv[2]).read_text())['preregistration_sha256']
print('Exact preregistration matches admitted060 execution')
PY

python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" \
  --source-receipt analysis/cycle07_newsource060_aggregates_v1/receipt.json \
  --source-proof model/cycle07_scale_hierarchy/city_context180_independent_v1/v2_admission.json \
  --source-proof reviews/cycle07_source477_normalization_independent/cap060_final_v2/audit.json \
  --source-proof reviews/cycle07_analysis_prospective_independent/code_protocol_v2_admission.json \
  --output "$SGRT_REPLAY/analysis060" --stage full \
  --review reviews/cycle07_analysis_new060_source_independent/preregistration_execution_admission.json
```

Ожидаемый SHA исходной регистрации 060 — `b5646f20182a9757a81db89f83953fe5df10ee09ba3269e193694ac69db32bc4`. Если совпадения нет, готовые метрики можно читать, но нельзя обходить execution guard. `started_guard.json` запрещает повторно писать поверх начатого анализа. Выходы включают gates, коэффициенты, общие выборки, региональнуюCV,499 региональных bootstrap и 499Moran перестановок согласно фактическому протоколу; недостаточные выборки сохраняются как gates, а не как фиктивные оценки.

Для графиков из сохранённого принятого результата:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/analysis/cycle07_tools/render_analysis.py" \
  --analysis analysis/cycle07_newsource060_baseline_v1 \
  --review reviews/cycle07_newsource060_regression_independent/audit.json \
  --output "$SGRT_REPLAY/analysis060_figures"
```

Новый повторный расчёт потребует собственного пострасчётного numerical review или проверки точного совпадения с исходным принятым результатом перед использованием его review. Другие четыре леса и четыре вложенных среза не включаются в 060 по умолчанию и требуют собственных источниковых контрактов/регистраций.

### Остальные принятые статистические проходы и единая сводка

Для 120 минут, совместного прохода 030/045/090 и четырёх вложенных срезов ниже приведены точные источники и proof-флаги из их сохранённых регистраций. Это самостоятельные прогоны: выполнение `--stage full` действительно запускает соответствующие оценки. Сначала выполнить только `preregister` в свежем выходе; сверка SHA обязательна. Команды не перепривязывают новые агрегаты автоматически.

Проход `120`, ожидаемая регистрация `e25f99495256d6ccbf350cccd166ad97a66c4755ee060eb78ad7399e3e394eff`:

```bash
cd "$SGRT_BASE"
SGRT_ANALYSIS_FLAGS=(
  --source-receipt "analysis/cycle07_newsource120_aggregates_v1/receipt.json"
  --source-proof "model/cycle07_scale_hierarchy/city_context180_independent_v1/v2_admission.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/cap120_v1/audit.json"
  --source-proof "reviews/cycle07_analysis_prospective_independent/code_protocol_v2_admission.json"
  --output "$SGRT_REPLAY/analysis120"
)
python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" "${SGRT_ANALYSIS_FLAGS[@]}" --stage preregister
python - "$SGRT_REPLAY/analysis120/preregistration.json" "reviews/cycle07_analysis_new120_source_independent/preregistration_execution_admission.json" <<'PYREG'
import hashlib,json,sys
from pathlib import Path
assert hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()==json.loads(Path(sys.argv[2]).read_text())["preregistration_sha256"]
PYREG
python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" "${SGRT_ANALYSIS_FLAGS[@]}" \
  --stage full --review "reviews/cycle07_analysis_new120_source_independent/preregistration_execution_admission.json"
```

Проход `030045090`, ожидаемая регистрация `51b89b2bed4f384baba6465a1bf05a895080ebec84617b4a21f55ad99b82566b`:

```bash
cd "$SGRT_BASE"
SGRT_ANALYSIS_FLAGS=(
  --source-receipt "analysis/cycle07_newsource030045090_aggregates_v1/receipt.json"
  --source-proof "model/cycle07_scale_hierarchy/city_context180_independent_v1/v2_admission.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/cap030_v1/audit.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/cap045_v1/audit.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/cap090_v1/audit.json"
  --source-proof "reviews/cycle07_analysis_prospective_independent/code_protocol_v2_admission.json"
  --output "$SGRT_REPLAY/analysis030045090"
)
python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" "${SGRT_ANALYSIS_FLAGS[@]}" --stage preregister
python - "$SGRT_REPLAY/analysis030045090/preregistration.json" "reviews/cycle07_analysis_new030045090_source_independent/preregistration_execution_admission.json" <<'PYREG'
import hashlib,json,sys
from pathlib import Path
assert hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()==json.loads(Path(sys.argv[2]).read_text())["preregistration_sha256"]
PYREG
python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" "${SGRT_ANALYSIS_FLAGS[@]}" \
  --stage full --review "reviews/cycle07_analysis_new030045090_source_independent/preregistration_execution_admission.json"
```

Проход `empirical`, ожидаемая регистрация `794812f5387849425bec690db1f2d311c76425c014fe856c9fa6d1c89791d14b`:

```bash
cd "$SGRT_BASE"
SGRT_ANALYSIS_FLAGS=(
  --source-receipt "analysis/cycle07_newsource_empirical_aggregates_v1/receipt.json"
  --source-proof "model/cycle07_scale_hierarchy/city_context180_independent_v1/v2_admission.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/level_000_v1/audit.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/level_001_v1/audit.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/level_002_v1/audit.json"
  --source-proof "reviews/cycle07_source477_normalization_independent/level_003_v1/audit.json"
  --source-proof "reviews/cycle07_analysis_prospective_independent/code_protocol_v2_admission.json"
  --source-proof "reviews/cycle07_partition_analysis_adapter_independent/admission.json"
  --source-proof "reviews/cycle07_empirical_registry_independent/audit.json"
  --output "$SGRT_REPLAY/analysisempirical"
)
python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" "${SGRT_ANALYSIS_FLAGS[@]}" --stage preregister
python - "$SGRT_REPLAY/analysisempirical/preregistration.json" "reviews/cycle07_analysis_empirical_source_independent/preregistration_execution_admission.json" <<'PYREG'
import hashlib,json,sys
from pathlib import Path
assert hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()==json.loads(Path(sys.argv[2]).read_text())["preregistration_sha256"]
PYREG
python "$SGRT_BASE/analysis/cycle07_tools/run_analysis.py" "${SGRT_ANALYSIS_FLAGS[@]}" \
  --stage full --review "reviews/cycle07_analysis_empirical_source_independent/preregistration_execution_admission.json"
```

Графики вложенных срезов и единая сводка из сохранённых принятых результатов:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/analysis/cycle07_tools/render_analysis_empirical_v1.py" \
  --analysis analysis/cycle07_newsource_empirical_baseline_v1 \
  --review reviews/cycle07_newsource_empirical_regression_independent/audit.json \
  --output "$SGRT_REPLAY/empirical_figures"
python "$SGRT_BASE/analysis/cycle07_tools/assemble_all9_handoff_v1.py" \
  --output "$SGRT_REPLAY/all9_handoff"
```

Новый численный результат требует самостоятельной фактической приёмки; renderer/assembler выше читают исходные уже принятые расчёты. Исходные captions и ограничения хранят различие между пятью operational forests и четырьмя retained candidate partitions.

## Пересборка итогового атласа и отчёта

Это создание новых документов из сохранённых принятых результатов; оно не требует повторного национального расчёта модели и 177 fits. Чтение больших Parquet и отрисовка десятков страниц всё равно требуют времени и памяти. Сначала завершить раздел переменных (`SGRT_BASE`, свежий `SGRT_REPLAY`), затем перейти в базу исследования. Не передавать исходные `atlas_v2/`, `atlas_v3/` или `report_v2/` как новые выходы.

### Атлас V8: два тома

Конфигурация `maps/cycle07_current_primary_binding_v1/map_config.json` имеет SHA256 `85a60267b7b1642ca41d0ca9cc7299843b44a01baa8cb673919ec8e2e1be2476`. Для окончательной косметической правки используется source config с теми же входами; exact V8 delta admission хранится в финальном source manifest/акте. Wrapper `render_volumes_v2.py` импортирует `render_atlas_v8.py`, а не старый V7.

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/maps/cycle07_tools/render_volumes_v2.py" \
  --config "$SGRT_BASE/maps/cycle07_current_primary_binding_v1/map_config.json" \
  --output "$SGRT_REPLAY/atlas_v2"
```

Команда создаёт `main/atlas_cycle07.pdf`, `operational_supplement/atlas_cycle07.pdf`, общую квитанцию `atlas_receipt.json`, машиночитаемые индексы страниц, полные таблицы типов и членств. Для основного тома сохраняется бюджет 20–30 страниц. Эта полная отрисовка воспроизводит родительский `atlas_v2/`; конечный атлас — `atlas_v3/` после описанной ниже версионной правки одной страницы. Новая отрисовка не подменяет исходные файлы. Визуальная и binding-приёмка нового результата — отдельная стадия. Точечное членство не доказывает сплошные географические границы или реальные поездки.

### Версионная правка одной страницы: atlas_v2 → atlas_v3

На странице 10 родительского атласа обнаружен недоступный столбец с `nan`. `patch_quality_page_v1.py` удаляет этот столбец и соответствующее утверждение, сохраняя 39 остальных PNG побайтово; в PDF заменяется одна страница, её таблица качества и квитанции получают новые SHA. Численные источники и типология не меняются. Parent receipt SHA и код patch сохраняются в новом `atlas_receipt.json`.

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/maps/cycle07_tools/patch_quality_page_v1.py" \
  --parent "$SGRT_REPLAY/atlas_v2" \
  --config "$SGRT_BASE/maps/cycle07_current_primary_binding_v1/map_config.json" \
  --output "$SGRT_REPLAY/atlas_v3"
```

Это продолжение команды полной отрисовки выше. Можно вместо свежего parent указать сохранённый `delivery/cycle07_current_primary_v1/atlas_v2`, сохранив свежий output. Patch проверяет точный config SHA родителя и научные source pins, но не требует исторического SHA его PDF, поэтому новый родитель допускается при совпавших источниках и конфигурации. Он использует hard links: parent и output должны находиться на одной файловой системе; изменяемые копии перед записью отвязываются от родителя. Инвариант 39 остальных PNG проверяется самим инструментом. Фактическая итоговая приёмка исходного `atlas_v3/` остаётся отдельной от запуска новой копии.

### Отчёт: фактический конечный builder V7

Конечный entrypoint — `delivery/cycle07_tools/build_report_v7.py`: он сохраняет Word crosswalk и полные агрегатные CSV, добавляет читательские названия и компактное представление таблиц. Исходные числа и научные входы не менялись. Ранний 57-страничный `report/` сохранён как история; итоговый `report_v2/` содержит 25 страниц отчёта и одну страницу записки. Справки V4–V6 сохранены как исторические снимки и не подставляются вместо V7. Точный actual input bundle — `delivery/cycle07_current_primary_v1/report_inputs_v1.json`. Он связывает принятые типы, результаты всех девяти анализов, фактический итоговый атлас и библиографию. SHA exact bundle — `fec489225955d20119a143bf104907ff04a4a8399b167603a93a10f4914cb15d`. При несовпадении source guards пересборка останавливается; не создавать фиктивный config из шаблона.

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/delivery/cycle07_tools/build_report_v7.py" \
  --inputs "$SGRT_BASE/delivery/cycle07_current_primary_v1/report_inputs_v1.json" \
  --output "$SGRT_REPLAY/report_v2_prereg_v1" --stage preregister

python "$SGRT_BASE/delivery/cycle07_tools/build_report_v7.py" \
  --inputs "$SGRT_BASE/delivery/cycle07_current_primary_v1/report_inputs_v1.json" \
  --output "$SGRT_REPLAY/report_v2" --stage build
```

Обе стадии требуют нового каталога, поэтому для preregister и build заданы разные выходы. В build создаются `SGRT_RESEARCH_REPORT.pdf/.docx/.md` и `SUPERVISOR_BRIEF.pdf/.docx/.md`, полный реестр единиц/типов и собственная input binding квитанция. Конечные сохранённые документы лежат в `delivery/cycle07_current_primary_v1/report_v2/`. Пересборка из исходного input bundle использует исходный принятый atlas, а не автоматически `$SGRT_REPLAY/atlas_v3`: новое изображение нужно отдельно проверить и перепривязать с SHA, если планируется включить именно его.

Состояние научной приёмки и допусков не определяется названием `REPORT`: конечный пакет остаётся предварительным исследовательским результатом с явной неполнотой наблюдений и гипотезами Word. Для приёмки сохранённого выпуска использовать final manifest/verdict, а не исторические `pending` внутри неизменённых авторских receipts.

## Перенос на другую машину

1. Сохранить структуру репозитория и точные байты опубликованных артефактов; восстановить numeric cache из архива в новый каталог.
2. Основной model executor связывает входы путями относительно вычисленного `BASE`, а четыре файла кэша — именами и SHA. Фактическая проверка `--prepare-only` с копией неизменённого кода в другом `BASE` и новым путём к кэшу сохранила exact SHA `c4ce5d42…`. В тесте исходные каталоги и кэш подключены symlink к существующим frozen bytes; независимое повторное скачивание и сам расчёт не выполнялись. При сохранении структуры и байтов перенос базы и кэша сам по себе не требует менять основной допуск. Downstream normalization/analysis/map/report bundles также содержат исторические абсолютные ссылки; переносимость главного исполнителя не означает переносимости всей семьи.
3. В отдельном воспроизводящем окружении можно сохранить тот же исторический mount path. Если пути меняются, создать **новые** конфигурации/квитанции, сохранив originals; заново проверить источник и связывание. Не делать массовую замену строк внутри принятых документов и не переименовывать чужой допуск в новый.
4. Повторить `--prepare-only`/preregistration и сравнить SHA с областью допуска. Совпадение входов и кода позволяет повторить вычисление; новые артефакты должны быть проверены независимо перед выпуском.
5. Изменения ОС, BLAS, Python, PyArrow или кодеков могут затронуть младшие разряды и/или байты сериализации. Различать математическое совпадение и побайтовое тождество; не переписывать manifest, чтобы скрыть различие.

Инструкция не содержит команд удаления, перезаписи принятых результатов, отключения проверок или повторного скачивания многогигабайтных первичных файлов без необходимости.

Текущее состояние вычислительного блока: все девять представлений независимо приняты; `analysis/cycle07_all9_admitted_handoff_v1/handoff.json`, SHA `1d3fb616d06503bc24b86898e81ca48640e8a04031f050c045911c4f45a725b1`. Всего 177 fits, 108 gates (71 вычисленный, 37 не оценены) и 1307 интервалов. Все 31 light-представление нормализованы и классифицированы с отдельной независимой приёмкой. Индексы пространственного разрешения 0–3 не являются наблюдаемыми функциональными порядками.

Инструкция v6 фиксирует фактические закрытые выходы: atlas_v3 (29 страниц основного тома и 11 страниц приложения), report_v2 (25 страниц отчёта и одна страница записки). Точные конечные SHA и source-owner receipts — [delivery_bindings_v6.json](/archive/README.md#удалённые-материалы). Final manifest и verdict закрывают выпуск в целом; они формируются root после финального reader review. Исходные инструкции и квитанции v1–v5 сохранены в `history_v1/`–`history_v5/`. Проверки этой инструкции ограничены CLI, синтаксисом команд, чтением исходников/контрактов и ранее выполненными prepare-only; расчёты и отрисовка здесь не запускались.
