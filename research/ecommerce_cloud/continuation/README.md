# Центр и окружение: продолжение национального анализа

Новый результат — совместное расширение наблюдаемого периферийного канала и частая демографическая концентрация среднего центра. Подробные выводы, региональная неоднородность и экономико-географическая модель — в [отчёте](../REPORT_RU.md). Причинный эффект WB/Ozon не идентифицирован.

Панель 564 средних центров в 67 регионах, шесть исторических выходов ATP/WB, три полных официальных публикации ОКТМО и проверка состава обоих уровней дали новые результаты. Старые 170/174 не подменены новой выборкой. Ошибки совместной категории городских округов и подготовки выборки магазинов исправлены; итоговые таблицы получены заново.

## Материалы

[Версионированный выпуск](https://github.com/ZakBu/russian-settlements-research/releases/tag/ecommerce-continuation-20261025-v2) содержит PDF, карты PNG/SVG/PDF, исполненный notebook, все новые производные таблицы, проверяемые исторические тела и манифест SHA256. [Три официальные публикации ОКТМО](https://github.com/ZakBu/russian-settlements-research/releases/tag/ecommerce-rosters-20261025-v1) также сохранены отдельным источниковым выпуском. Старые выпуски не перезаписываются.

Небольшие итоговые сводки находятся в [results/](results/). Полные таблицы и крупные данные размещены в Releases, а не в истории Git.

## Как повторить

Используется корень рабочей ветки. Python 3.12; зависимости переносимы, фактический список пакетов включён в экспорт. Старые пути macOS и старый PYTHONPATH не нужны.

```bash
python3 -m venv .venv-ecommerce
.venv-ecommerce/bin/python -m pip install -r research/ecommerce_cloud/extension/requirements-report.txt
.venv-ecommerce/bin/python research/ecommerce_cloud/fetch_bundle.py
.venv-ecommerce/bin/python research/ecommerce_cloud/check_bundle.py
.venv-ecommerce/bin/python research/ecommerce_cloud/run_checks.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/acquire_bdmo_population.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/nonshop_population_contexts.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/nonshop_source_coverage.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/nonshop_remainder_sensitivity.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/check_nonshop_population.py work/ecommerce_extension_outcomes/nonshop_population_contexts
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/restore_rosters_pinned.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/inspect_roster_schema.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/full_roster_analysis.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/trade_roster_sensitivity.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/restore_atp_pinned.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/analyze_atp_historical_footprints.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/check_atp_historical.py work/ecommerce_atp_analysis work/ecommerce_atp_history
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/audit_atp_ozon_history.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/surveys_probe.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/render_nonshop.py
.venv-ecommerce/bin/python research/ecommerce_cloud/continuation/build_nonshop_notebook.py
```

Для полной сборки PDF дополнительно восстановить две исходные таблицы большого репозитория и построить прежние рисунки:

```bash
.venv-ecommerce/bin/python scripts/research_data.py fetch --profile core --match data/population/settlements_census_long.parquet --match data/population/settlements_census_wide.parquet
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/analyze_national_context.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/render_figures.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/build_pdf.py
```

Полная сборка экспорта зафиксирована в [.github/workflows/ecommerce-publish.yml](../../../.github/workflows/ecommerce-publish.yml). Основная среда сеанса была недоступна; реальные расчёты выполнены GitHub Actions. Это не имитация исполнения и не свидетельство восстановления основной среды.

## Что именно проверено

Контрольные суммы всех 1 071 прежних входов и три старые вычислительные проверки пройдены. Независимый проверяющий восстановил 91 656 строк исторических контекстов, 30 552 парные строки, 24 сводки, 720 выборочных геометрических сопоставлений и соединение с 564 демографическими центрами. Популяционная арифметика проверена на 2 946 муниципальных источниковых значениях и 2 667 годовых наблюдениях. Официальные составы проверены до и после отбора, для центральной и родительской территории отдельно.

Успешный расчёт не удостоверяет полноту каталогов, открытия/закрытия, юридическое состояние на каждое 1 января, координатные границы, фактические услуги/поездки или причинный эффект. Визуальный просмотр всех страниц и изображений не подменяется наличием успешно записанного PNG/PDF; предел визуальной проверки указан в независимой рецензии.
