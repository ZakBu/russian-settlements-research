# Динамическая типология СГРТ: восстановленный научный результат

Основной научный текст: [report/REPORT.md](report/REPORT.md). Полный PDF, атлас12карт и воспроизводимый архив поставляются отдельно. Это новый фактический расчёт, а не переименование раннего пилота.

Главный результат — [supervision/final_typology/sgrt_dynamic_functional_typology.parquet](supervision/final_typology/sgrt_dynamic_functional_typology.parquet):15377обычных районов,101поле. К нему сохранены CSV, покрытие, описание происхождения и отдельные реестры2пустых внешних якорей и2неназначенных НП. Все142570НП и21246наблюдаемых нулей2010 остаются в первичной исследовательской панели. Кандидатные центры с ненулевой массой, ближайший низовой бассейн и верхнее потенциальное вложение — расчётная операционализация, а не доказанные потоки.

Модель2010 и самостоятельная модель2002 разделены. Каждая сохраняет нижние уровни и симметрично отделяет переразметку границ от изменения населения. Основная демографическая типология:8681совместная убыль,1136убыль центра/неубыль окружения,931неубыль центра/убыль окружения,991совместная неубыль;68нулевых переходов окружения и3570систем без населённого окружения сохранены отдельно.

Аграрные функциональные профили построены из шести наблюдаемых групп культур официального муниципального массива. Измерена композиция профилей по НП внутри СГРТ, а не расположение полей. RFSDвключает проверенный справочный слой2011–2025 (63308662организация-лет) и отдельное новое присоединение2016/2021 к модели2010. Юридический адрес не измеряет рабочие места, филиалы или производство.

МоделиM1/M2/M3 сравниваются на4262одинаковых районах. RMSE:0.171079/0.170997/0.166550. Аграрный прирост информации не подтверждён выбранными интервалами. Преимущество RFSDдля общей динамики зависит от масштаба пространственных блоков: при600км интервал пересекает ноль. Ретроспективные ассоциации не являются причинными эффектами.

Внешняя проверка13институциональных случаев дала4совпадения цепочки и9отрицательных случаев. Они опубликованы, а не исключены. Прямой национальнойOD-матрицы нет.1989 — частичная неоднородная когорта19863связей, не полная перепись.

## Воспроизведение

Рабочая версия Python3.12; точные установленные зависимости в [requirements.txt](requirements.txt). Структура автономного архива: `repo/research/sgrt_recovered_20261019/`, необходимые неизменённые исходники `repo/publication/` и `repo/research_rebuild/`, колоночные входы в соседнем `recovery_inputs/`. Книги проекта не перепубликуются. Контрольные суммы и локаторы сохраняются.

Из каталога `repo`:

```bash
python -m pip install -r research/sgrt_recovered_20261019/requirements.txt
python research/sgrt_recovered_20261019/replay_pipeline.py --out ../fresh_replay --inputs ../recovery_inputs
```

Эта команда требует пустой выходной каталог, заново читает исходныйstage71, строит географию, сканирует8.8млнагрострок и колоночные RFSD2016/2021, затем сравнивает12полных таблиц со снабжёнными результатами. Реальный выполненный запуск: [REPLAY.json](REPLAY.json),12PASS,rtol0,atol1e-9. Большая сетка чувствительности не повторяется этим сокращённым контрольным запуском; её отдельное фактическое исполнение отражено вmodel/manifest.json.

Самостоятельная полная география и отдельная база2002:

```bash
python research/sgrt_recovered_20261019/model/run_model.py --panel research/sgrt_recovered_20261019/data/panel.parquet --out ../fresh_model2010
python research/sgrt_recovered_20261019/model/run_2002.py --panel research/sgrt_recovered_20261019/data/panel.parquet --out ../fresh_model2002 --skip-sensitivity
python research/sgrt_recovered_20261019/check_model2002.py
```

Независимые проверки сохранённой поставки и повтор статистики:

```bash
python research/sgrt_recovered_20261019/statistics/independent_core.py
python research/sgrt_recovered_20261019/statistics/incremental_models.py
python research/sgrt_recovered_20261019/statistics/buffer50_models.py
python research/sgrt_recovered_20261019/statistics/verify_reproduction.py
python research/sgrt_recovered_20261019/supervision/check_actual.py
python research/sgrt_recovered_20261019/supervision/check_functional.py
python research/sgrt_recovered_20261019/supervision/check_statistics.py
python research/sgrt_recovered_20261019/validation/check_validation.py
```

Повтор не должен автоматически трактоваться как новое чтение интернет-источников: географические случаи и литература имеют собственные source-checks/read-status. Статистик ранее создавал входную панель, но не GIS/аграрную/RFSDреализацию. Супервизор независимо воспроизвёл модели и проверял исправления. Фактические назначения и результаты: [AGENT_NETWORK.csv](AGENT_NETWORK.csv), [JOURNAL.md](JOURNAL.md).

Карты и отчёт (после проверки готовности текста):

```bash
python research/sgrt_recovered_20261019/build_maps.py --background ../recovery_inputs/enrichment/world.geojson
python research/sgrt_recovered_20261019/report/plot_statistics.py
python research/sgrt_recovered_20261019/render_report.py
```

PNG6000×3750, SVG/PDFс векторными текстами/границами и растровым плотным точечным слоем250dpi. Все контуры российского фонового слоя и наблюдаемые точки включены в рамку. Цвет пропуска отделён от низкого значения. Структурные и визуальные проверки фиксируются вmaps/.

Все сильные утверждения, источники, вычислительные локаторы и уровни доказательности: [report/claim_registry.csv](report/claim_registry.csv). Матрица требований и неизмеренных свойств: [report/requirements_coverage.csv](report/requirements_coverage.csv). Источники и фактически прочитанные страницы: [literature/bibliography.csv](literature/bibliography.csv). ЧерновойPR4не сливается,mainи первичные данные не изменяются.
