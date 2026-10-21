# Как читать и воспроизводить текущую семью СГРТ477

Документ относится к `model/cycle07_scale_hierarchy/source477_adminall_v2`, а не к прежней четырёхуровневой модели цикла 06 и не к контрольному проходу со старым геометрическим правилом ядра. Основные пять лесов и 50 повторений, шесть отдельных сценариев чувствительности и реестр четырёх устойчивых вложенных срезов уже рассчитаны. Готовность всех последующих таблиц, карт и отчёта определяется отдельными допусками.

**Это инструкция по сохранённой фактической конфигурации, а не обещание переносимого полного запуска одной командой.** В контрактах нормализации, предварительных регистрациях и квитанциях есть зафиксированные абсолютные пути `/workspace/russian-settlements-research/...`. Замена этих строк меняет байты конфигурации, её SHA и область допуска. Установка Python-пакетов не восстанавливает научные данные и не заменяет источниковые проверки.

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
| Принятый статистический срез 120 минут | `analysis/cycle07_newsource120_admitted_handoff_v1.json`, `analysis/cycle07_newsource120_interpretation_v1.md`, `analysis/cycle07_newsource120_baseline_v1/` | Отдельные источниковый, numerical, spatial и visual допуски в handoff; остальные семь представлений ещё не объявляются готовыми. |
| Фактический картографический просмотр 60 минут | `maps/cycle07_newsource060_preview_v1/actual060_preview.pdf` | `maps/cycle07_newsource060_preview_binding_v1/map_config.json`, `reviews/cycle07_newsource060_preview_independent/admission.json`, последующая визуальная проверка. Это предварительный просмотр одного сценария, а не полный итоговый атлас. |
| Библиография | `literature/cycle07_classics_final/READOUT_RU.md`, `bibliography.csv` | `source_receipts.json`; выборочное чтение первичных материалов не объявляется чтением всех книг. |

На момент составления инструкции полный атлас всех четырёх вложенных срезов и пяти лесов и итоговый отчёт **ещё не имели закрытых фактических input bundles и выходов**. Их нельзя заменить старым атласом или объявить готовыми по наличию скрипта. Актуальные пути после сборки должны быть указаны в текущем выпуске/его manifest; см. последнюю секцию этого документа.

## Среда и зависимости

Фактическая среда: Python3.12.14, Linux x86_64. Наблюдённые версии даны в [requirements_actual.txt](requirements_actual.txt), полная квитанция — [runtime_actual.json](runtime_actual.json). Перечень получен из установленного окружения и сверки импортов, а не из предположений о зависимостях. Это не проверенный lock для другой ОС/архитектуры. Отдельный чистый `pip install` в этом аудите не выполнялся.

Пример создания нового окружения, если нужного ещё нет:

```bash
python3.12 -m venv /workspace/scratch/sgrt-replay-venv
source /workspace/scratch/sgrt-replay-venv/bin/activate
python -m pip install -r research/sgrt_word_completion_20261021/coordination/cycle07_reproduction/requirements_actual.txt
```

Перед установкой requirements пример предполагает рабочий каталог корня репозитория; переменные ниже определяются там же.

Для PDF-отчёта фактический общий renderer использует шрифт `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. Matplotlib также должен располагать кириллическим DejaVu Sans. Для чтения готовых CSV/Parquet и расчёта модели не требуется компиляция дорожного графа. Для повторного извлечения первичных OSM/растров используются дополнительные пакеты из второй части requirements; некоторые upstream-стадии требуют системных инструментов и C++-компилятора, указанных в собственных receipts. Эти upstream-проходы не запускались при подготовке инструкции.

Фактические справки CLI сохранены в [cli_help/](cli_help/) с кодами возврата и SHA исполнителей в [cli_help_receipt.json](cli_help_receipt.json). В этом аудите выполнялись `--help`, чтение метаданных, контроль кэша и два свежих `--prepare-only`; иерархия, регрессии и карты заново не рассчитывались. Подготовка в исходной базе и в другой базе с новым путём к кэшу дала тот же SHA `c4ce5d42…`; подробности и точные команды — [dry_prepare_receipt.json](dry_prepare_receipt.json).

## Зафиксированные источники и код

Основной binding содержит восемь входов, протокол и SHA семи исполнителей. Полная машинная копия — [source_binding_snapshot.json](source_binding_snapshot.json); исходный binding остаётся неизменным. Главные источники:

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

## Карты и отчёт: фактический просмотр и ещё не закрытый полный выпуск

Воспроизводимый фактический просмотр 060:

```bash
cd "$SGRT_BASE"
python "$SGRT_BASE/maps/cycle07_tools/render_newsource060_preview_v1.py" \
  --config "$SGRT_BASE/maps/cycle07_newsource060_preview_binding_v1/map_config.json" \
  --output "$SGRT_REPLAY/map060_preview"
```

Он создаёт `actual060_preview.pdf`, CSV полных типов/членств и собственный `preview_receipt.json`. Его независимый binding admission — `reviews/cycle07_newsource060_preview_independent/admission.json`. Это не команда создания полного итогового атласа. Карты показывают точечный состав единиц; сплошные доказанные границы между поселениями не восстанавливаются автоматически.

`maps/cycle07_tools/render_atlas_v6.py` имеет CLI `--config FILE --output FRESH --stage preregister|render`; кандидатv7 добавляет новые страницы/индекс и нуждается в собственном допуске. Нельзя использовать старый map admission для изменившегося renderer или другой конфигурации. Для полного атласа нужны фактически принятые все представления, точный config, frozen renderer, предварительная регистрация и actual binding admission, затем визуальная проверка выходов.

`delivery/cycle07_tools/build_report_v4.py` имеет CLI:

```text
python .../build_report_v4.py --inputs EXACT_ACTUAL_INPUTS.json --output FRESH_DIRECTORY --stage preregister
python .../build_report_v4.py --inputs EXACT_ACTUAL_INPUTS.json --output ANOTHER_FRESH_DIRECTORY --stage build
```

Это **синтаксис кандидата**, не готовая команда принятого итогового отчёта: на момент проверки его фактический input config и полный output ещё не существовали. Старый допуск reportv3 не распространяется наv4. После появления итогового bundle здесь должны быть указаны конкретные пути, SHA renderer/config, соответствующие prospective/actual admissions и реальные PDF/DOCX/MD-выходы. Наличие `--help` подтверждает CLI, но не научную или визуальную приёмку отчёта.

## Перенос на другую машину

1. Сохранить структуру репозитория и точные байты опубликованных артефактов; восстановить numeric cache из архива в новый каталог.
2. Основной model executor связывает входы путями относительно вычисленного `BASE`, а четыре файла кэша — именами и SHA. Фактическая проверка `--prepare-only` с копией неизменённого кода в другом `BASE` и новым путём к кэшу сохранила exact SHA `c4ce5d42…`. В тесте исходные каталоги и кэш подключены symlink к существующим frozen bytes; независимое повторное скачивание и сам расчёт не выполнялись. При сохранении структуры и байтов перенос базы и кэша сам по себе не требует менять основной допуск. Downstream normalization/analysis/map/report bundles также содержат исторические абсолютные ссылки; переносимость главного исполнителя не означает переносимости всей семьи.
3. В отдельном воспроизводящем окружении можно сохранить тот же исторический mount path. Если пути меняются, создать **новые** конфигурации/квитанции, сохранив originals; заново проверить источник и связывание. Не делать массовую замену строк внутри принятых документов и не переименовывать чужой допуск в новый.
4. Повторить `--prepare-only`/preregistration и сравнить SHA с областью допуска. Совпадение входов и кода позволяет повторить вычисление; новые артефакты должны быть проверены независимо перед выпуском.
5. Изменения ОС, BLAS, Python, PyArrow или кодеков могут затронуть младшие разряды и/или байты сериализации. Различать математическое совпадение и побайтовое тождество; не переписывать manifest, чтобы скрыть различие.

Инструкция не содержит команд удаления, перезаписи принятых результатов, отключения проверок или повторного скачивания многогигабайтных первичных файлов без необходимости.

Проверка состояния при завершении этого аудита: независимый статистический пакет 120 минут уже закрыт отдельно (handoff v1 выше); 030/045/090 и четыре вложенных среза ещё не объявлены полностью готовыми. Исполнители полного атласа и отчёта продолжают prospective review; SHA их CLI в этой папке — снимок, который не превращает кандидата в принятый выпуск.

Исправление v2: downstream-команды явно переходят в базу исследования; исходный снимок инструкции и её квитанций сохранён в `history_v1/`. Синтаксис всех shell-примеров проверен без запуска расчётов.
