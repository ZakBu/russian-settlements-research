# Функциональная опорность и динамика СГРТ

Этап от 19 октября 2026 года. Получены документированные фрагменты многопрофильного обслуживания, их функциональная вложенность, отдельные изменения школьного окружения и пятнадцатилетняя история юридических свидетельств функций. **Общероссийская система действительных СГРТ пока не выделена.** Прежние ближайшие геометрические зоны не принимаются за установленные функциональные районы.

## С чего начать

- [Короткое изложение результата](USER_READOUT.md): конкретные территории и смысл для государственной поддержки.
- [Научный отчёт](RESULTS.md): источники, расчёты, альтернативные объяснения и ограничения.
- [Реестр проверяемых утверждений](claim_registry.csv), [библиография](BIBLIOGRAPHY.csv), [проверяемые типологические гипотезы](typology_hypotheses.csv).
- [Журнал](JOURNAL.md), [реально работавшие агенты и их возражения](AGENT_NETWORK.csv).
- PDF научного отчёта и краткого изложения формируются в `output/pdf/` командой `python functional_dynamics_20261019/render_reports.py`.

Полный replay рассчитан на Linux (используется /proc/self/fd). Все команды ниже выполняются из рабочего корня, содержащего `functional_dynamics_20261019/`, `anchor_research_20261019/` и `restored/`. Относительные пути внутри модулей предполагают именно эту структуру.

## Основные результаты и таблицы

| Содержание | Файл или раздел |
|---|---|
| Калуево → Малоказаккулово: школа и ФАП; старшее образование → Уральск | `history/UCHALY_RESULT.md`, `model/results/documented_multifunction_fragments.parquet`, `model/results/documented_functional_nesting.parquet` |
| Школьные назначения разных лет и их изменения | `history/edges_by_year.parquet`, `history/konakovo_transitions.csv`, `model/results/history_positive_assignment_transitions.parquet` |
| Население центра, внешнего окружения и объединения; чувствительность порогов | `model/results/centre_periphery_demography.parquet`, `model/results/demographic_direction_sensitivity.parquet` |
| Разделение демографии и эффекта изменения назначения | `model/results/history_two_axis_accounting.parquet` |
| Расстояниевые градиенты внутри датированных документных окружений | `gradients/gradient_points.parquet`, `gradients/distance_gradients.parquet` |
| ФАП, больничные площадки, кадровые и прикрепительные срезы | `medical/README.md`, `medical/objects.csv`, `medical/tariff_changes.csv` |
| Обслуживание, школьная отчётность, транспорт и перемещения библиотеки | `validation/README.md`, `validation/actual_service_checks.csv`, `validation/source_ledger.csv` |
| Опубликованные места получения заказов и ограничения истории | `marketplaces/README.md`, `marketplaces/wb_delivery_locations_ru_20261019.parquet` |
| RFSD 2011–2025: единая версия, точечные профили и траектории | `economy/PINNED_CALENDAR_READOUT.md`, `economy/pinned_calendar/point_exact_code_witnesses_2011_2025.parquet`, `economy/pinned_calendar/point_witness_trajectories_2011_2025.parquet` |
| Потеря кодовых связей, адреса, даты юридического существования | `economy/address_audit_2021_2025/READOUT.md`, `ADDRESS_AUDIT.json`, `LIFECYCLE.json` в том же каталоге |
| Аграрная статистика сельсоветов и её несовпадение с функциональными контурами | `agriculture/README.md`, `agriculture/functional_municipal_crosswalk.csv`, `agriculture/official_lower_municipal_context_2007_2009.csv` |

В `model/figures/` находятся карты Учалинского фрагмента и смены назначения Новой Туры; в `figures/` — карта опубликованной сети доставки; в `economy/figures/` — календарные диаграммы. Карты сохраняются в PNG/SVG/PDF. Линии документных отношений не являются дорогами или измеренными поездками. Национальная карта мест доставки не является картой границ СГРТ.

## Данные, доступ и покрытие

Исходный `ordinary_full3_with_primary_population_sources.csv.gz` содержит **142 570 строк и 135 полей**; проверенный SHA256 — `d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c`. Производная неподвижная ось `anchor_research_20261019/data/point_axis.parquet` содержит 142 570 строк и 64 поля, SHA256 — `a2b5544c0d3c5581144a5439113a96c4a771697dc87a38c2abf979e1ead1467b`. Подробный входной аудит: `anchor_research_20261019/data/immutable_input_manifest.json`.

Все наблюдаемые нули переписей сохранены, включая **21 246 нулей 2010 года**. Метаданные качества не использованы для исключения группы 2010 года. Покрытие 1989 года частичное: оно не превращено в полную российскую перепись и не заполнено догадками. Современные координаты и кодовая ось не доказывают неизменность исторических границ или функций.

Все 15 годов RFSD 2011–2025 реально получены из одной закреплённой версии: 63 308 662 организационно-годовых строки. Перед загрузкой проверены схемы; основной календарь использует пять выбранных колонок. Отдельно получены адресные и юридические поля 2021/2025. Наблюдаются юридические лица и их коды, а не рабочие места, физические филиалы или полный рынок услуг. Отсутствуют ИП, неполны бюджетные учреждения; юридическое закрытие не тождественно исчезновению обслуживания.

Аграрный исходник содержит 8 832 750 строк; для двух целевых сельсоветов найдены 31 наблюдение 2007–2009 по хозяйствам населения. Они не распределены по деревням произвольными весами. Полные муниципальные значения не объявлены производством СГРТ.

В WB сохранён весь опубликованный источниковый раздел `ru`: он включает разные типы доставки и Баренцбург вне территории РФ. Это не 91 136 подтверждённых общедоступных ПВЗ России. Полная сопоставимая история WB/Ozon и межпоселенческих покупателей не восстановлена. Школьные акты, заявления медицинского поставщика, организационное подчинение, расписания и сведения об использовании различаются по виду доказательства. Ограничения конкретных веб-маршрутов отражены в журналах модулей; недоступная страница не означает отсутствия функции.

## Воспроизведение

Полная поставка должна сохранять соседние каталоги входов: неподвижную ось и предыдущие функциональные входы в `anchor_research_20261019/`, восстановленные аграрные и RFSD 2016/2021 в `restored/extracted/inputs/`, пятнадцать пятиколоночных RFSD-срезов в `economy/remote_selected/`, адресные срезы в `economy/remote_address_selected/`, исходные PDF/HTML/JSON в модулях. Состав готового скачиваемого архива следует сверять с его manifest; одно наличие кода в Git не означает наличие всех больших исходников в Git.

Общий запуск предусмотрен командой:

```bash
python functional_dynamics_20261019/replay_all.py
```

Общий сценарий и итоговый `REPLAY.json` подготавливаются независимым статистиком. На момент составления этого README единый успешный прогон **не заявлен**; окончательный статус следует читать в `REPLAY.json`. Отдельные уже выполненные повторы отражены в `history/REPLAY.json`, `medical/REPLAY.json`, `validation/REPLAY.json` и `model/results/REPRODUCTION.json`.

Индивидуальные команды проверены по исходному коду модулей. Они пересоздают производные результаты по сохранённым входам и не требуют нового сетевого получения:

```bash
python functional_dynamics_20261019/history/build_history.py
python functional_dynamics_20261019/history/build_konakovo.py
python functional_dynamics_20261019/history/build_uchaly.py
python functional_dynamics_20261019/medical/build_medical.py
python functional_dynamics_20261019/marketplaces/build_marketplaces.py --axis anchor_research_20261019/data/point_axis.parquet
python functional_dynamics_20261019/validation/build_validation.py
python functional_dynamics_20261019/model/build_integrated_graph.py
python functional_dynamics_20261019/model/build_history_accounting.py
python functional_dynamics_20261019/model/integrate_change_evidence.py
python functional_dynamics_20261019/model/centre_periphery_demography.py
python functional_dynamics_20261019/model/check_invariants.py
python functional_dynamics_20261019/model/verify_reproduction.py
python functional_dynamics_20261019/build_gradients.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python functional_dynamics_20261019/agriculture/build_functional_agriculture.py
python functional_dynamics_20261019/agriculture/verify_outputs.py
python functional_dynamics_20261019/economy/build_multiyear_exact.py --base . --out functional_dynamics_20261019/economy/pinned_calendar
python functional_dynamics_20261019/economy/audit_addresses.py --base . --out functional_dynamics_20261019/economy/address_audit_2021_2025
python functional_dynamics_20261019/economy/build_alias_cases.py --base .
python functional_dynamics_20261019/build_claim_registry.py
```

Версии фактически использованной среды закреплены в requirements.txt. Нужны Python и зависимости, перечисленные в коде: pandas, numpy, pyarrow, scipy, lxml, matplotlib, pyproj, PyMuPDF; для PDF — reportlab и pypdf. Для повторного извлечения текста оригинальных PDF используется системный `pdftotext` из Poppler. Настройки среды и фактические версии должны сохраняться в итоговой поставке; этот перечень сам по себе не является lockfile.

## Независимая проверка и граница вывода

[Первая проверка](statistics/VERDICT.md) и [расширенная проверка](statistics/wave2/VERDICT.md) выполнены статистиком, не писавшим авторские расчёты. Проверены исходные строки, сопоставления, арифметика, календарь и пространственная чувствительность. Условные кодовые соответствия остаются анализом чувствительности: независимое переобучение этой модели не заявлено. Воспроизводимость таблицы не доказывает полноту наблюдений или причинную связь.

Установлены конкретные документированные сервисные фрагменты. Не установлены полная национальная сеть СГРТ, массовое выпадение малых центров, перехват функций большими, все действительные поездки и эффективность мер поддержки.

Публикация ведётся только в [исследовательской ветке](https://github.com/ZakBu/russian-settlements-research/tree/research/sgrt-final-protocol-20261018); используется [draft PR №4](https://github.com/ZakBu/russian-settlements-research/pull/4), без слияния и изменений main. Исходники и синхронизированные `sources/` не перезаписываются.

## Финальная поставка

`SGRT_FUNCTIONAL_DYNAMICS_REPRODUCIBLE.zip` сохраняет рабочую структуру и необходимые исходные колоночные срезы. Его нужно распаковать целиком, затем установить `python -m pip install -r functional_dynamics_20261019/requirements.txt`. Для полного повтора без сетевых загрузок выполнить `python functional_dynamics_20261019/replay_all.py`; расчёты выполняются в отдельной копии, контрольные суммы исходников проверяются до и после. Результат определяется финальным `REPLAY.json`, а не наличием этой инструкции. `make_package.py` проверяет CRC архива и SHA256 каждого распакованного содержимого. Дублирующие большие CSV.gz при наличии Parquet не включаются: их создают те же сборщики.

В Git этот этап расположен в `research/sgrt_functional_dynamics_20261019/`. Команды выше относятся к рабочей структуре полного архива; один Git checkout без входных данных не является автономным набором данных. Большие исходники, длинные таблицы и оригинальные захваты доступны в архиве, компактные расчёты и реестры — также в Git.

`coverage_summary.csv` показывает действительное покрытие: 1989 год известен для 19 863 записей, 7 778 имеют метку первичного происхождения; для 19 158 наблюдений сопоставимость границ остаётся UNKNOWN. Ещё 705 значений скорректированы источником по последующим административным изменениям. Эти метки не удостоверяют тождество границ и не позволяют распространить динамику на всю РФ. Подробности: `CENSUS1989_COVERAGE_AUDIT.json`. Документный граф образования содержит 74 внешних происхождения, медицины — два; общероссийская репрезентативность этой выборки не заявлена.

Финальный общий replay действительно завершён:27/27 команд exit0,171CSV/Parquet совпали при проверке значений (rtol1e-12,atol1e-10 для чисел с плавающей точкой). Впервые заново обработаны все 63308662 строки 15 годовых исходников в отдельном рабочем каталоге.620 замороженных файлов сохранили SHA256. Продолжительность 604,587 с. Это повтор авторских вычислений; независимые алгоритмы и их отдельные границы проверки находятся в statistics/wave2/. Полный receipt:REPLAY.json; кратко:REPLAY_SUMMARY.json; точные команды и stdout:replay_logs/.
