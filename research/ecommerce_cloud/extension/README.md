# Новый результат: центр, окружение и платформенная торговля

Продолжение 25 октября 2026 года добавило послепереписную демографию окружения, торговую площадь с проверкой крупных разрывов, национальные пространственные варианты и пять ранних архивов официального Ozon API. **Причинный эффект платформ не идентифицирован.** Полный ответ с разделением фактов и объяснения — [научный отчёт](../REPORT_RU.md); критический разбор — [заключение рецензента](review/FINAL_CRITICAL_REVIEW.md).

Главные новые численные результаты:

- 170 средних центров в 34 регионах, 1 января 2023–2025: 141 сокращение центра, 162 сокращения окружения, 152 роста доли центра. Медианы −1,324% / −2,938% / +0,358 п.п. Единицы условно муниципальные, составы 2023/2024 не подтверждены.
- 169 центров с торговой площадью. При снижении числа магазинов площадь сохранялась/росла у 28 из 52; после исключения Орловской области и крупных разрывов — у 27 из 46. Это не оценка оборота, мощности или воздействия платформ.
- Пять Ozon API-архивов 2021–2023, 7 293 объектно-временные записи в отдельных географических окнах. Не общероссийская панель и не даты открытий.
- Национальная проверка окружений 10/20/40/80 км показывает существенную зависимость величины долей и части направлений от рамки. Круги не являются наблюдёнными ареалами.

## Как повторить

Используется корень указанной ветки. Не менять исходники и не использовать старый PYTHONPATH.

```bash
python3 -m venv .venv-ecommerce
.venv-ecommerce/bin/python -m pip install -r research/ecommerce_cloud/extension/requirements-report.txt
.venv-ecommerce/bin/python research/ecommerce_cloud/fetch_bundle.py
.venv-ecommerce/bin/python research/ecommerce_cloud/check_bundle.py
.venv-ecommerce/bin/python research/ecommerce_cloud/run_checks.py
.venv-ecommerce/bin/python scripts/research_data.py fetch --profile core
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/acquire_section.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/outcomes/acquire_bdmo_population.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/history/acquire_pinned_wb.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/history/acquire_derived_ozon.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/build_notebook.py
.venv-ecommerce/bin/python research/ecommerce_cloud/extension/build_pdf.py
```

Для чистого пересчёта уже скачанных новых входов достаточно `run_extension.py`. `build_notebook.py` выполняет те же расчёты и сохраняет их таблицы в [исполненном notebook](national_extension.ipynb). Из-за запрета привязки TCP/IPC-сокетов в данной среде стандартный ZMQ kernel не запустился; реальные ячейки выполнены IPython в одном процессе с захватом фактических результатов и остановкой при ошибке. Это явно указано в metadata. Такой notebook открывается обычным Jupyter и может быть повторён обычным ядром в иной среде. Выполнение через IPython не подменяет код заранее вписанными таблицами.

Фактическая среда — Python 3.12, точные версии в `environment-lock.txt`. Python 3.11 на исполнителе отсутствовал. Требования не привязаны к путям локальной macOS. Для PDF используются шрифты, поставляемые Matplotlib; системный пакет нестандартных шрифтов не требуется. Карты и PDF создаются в `work/ecommerce_cloud_extension/`, крупные исходники — в `work/ecommerce_extension_history/` и `work/ecommerce_extension_outcomes/raw/`.

## Источники и границы проверки

[История](history/HISTORY_EXTENSION.md) содержит точные даты, коды операторов, географические пределы, хеши и документированные отрицательные результаты. Пять Ozon тел можно повторно получить прямо по версионированному `derived_ozon_acquisition.json`, без повторного поиска CDX. [Новые исходы](outcomes/RESULTS.md) содержат URL двух закреплённых архивов БДПМО, отдельные исходы центра/остатка района, условность границ, выбросы и селекцию.

[Методология](methods/METHODOLOGY_AND_COMPARATIVE_EVIDENCE.md) сопоставляет Китай, США и Россию по реальному воздействию и исходу, а [аудит российского предшественника](methods/RUSSIAN_PREDECESSOR_AUDIT.md) проверяет первичный текст. Полные статьи не переопубликованы. Восьми новым источникам присвоены идентификаторы `ECOM_*` в общем `references/sources.json`, а объём прочтения указан в карточках.

Независимые проверки проверяют 1 020 значений населения, 1 956 значений площади, арифметику остатков и восемь вариантов чувствительности; прямые расстояния проверяют 63 пары «центр–радиус» у 16 центров. Они не удостоверяют статистическую истину исходных публикаций, неизменность границ, полноту каталогов и причинность. Статус восстановления исходного комплекта и трёх прежних расчётных проверок фиксируется отдельно в `reproduction_status.json`.
