# Динамика организационных свидетельств функций: завершённый расчёт

Обработан весь реально опубликованный календарь RFSD **2011–2025** из одного commit `bde9b8b129a8be582b66de4e30ed79c9187a8515`: 63 308 662 исходные строки. Получены 2 138 550 наблюдений «тот же НП × год» на неизменной оси 142 570 НП, семь узких сервисных групп, три дополнительных группы и все 21 секция ОКВЭД. Основная связка — только точный уникальный код НП, приведённый к словарю 2021 года. Исторические границы и преемственность всех кодов не объявлены установленными.

**Важный научный результат — количественно выявлен кодовый эффект.** Между 2021 и 2025 годами у 77 646 общих ИНН исчезает точное присоединение к оси, хотя сообщённые координаты совместимы в пределах 100 м и имеют house/street в обе даты. Условный crosswalk, обученный минимум на трёх ИНН и проверенный другими ИНН, принимает 1 114 кодовых соответствий. Он меняет число НП с сервисными свидетельствами 2025 года с 12 097 до 12 876; у 561 из 5 725 НП меняется конечное наличие свидетельства в типе «последнее исчезновение». Поэтому эти записи нельзя автоматически называть выпавшими центрами.

Годовая запись также не равна организации, действующей на 31 декабря. Даты создания/ликвидации проверены отдельно. И все эти наблюдения относятся к юридической регистрации: физические объекты, рабочие места, клиенты и внешние связи не измерены. Сами СГРТ этим слоем не размечены.

## Что читать

- `PINNED_CALENDAR_READOUT.md` — полный пятнадцатилетний ряд, траектории и ограничения.
- `address_audit_2021_2025/READOUT.md` — адреса, даты, проверенные соответствия и понятные примеры Косулина/Тарногского Городка.
- `pinned_calendar/coverage_2011_2025.csv` — все годы и покрытие.
- `pinned_calendar/point_exact_code_witnesses_2011_2025.parquet` и CSV.gz — основной полный ряд; `point_witness_trajectories_2011_2025.parquet` — классификация наблюдаемых свидетельств.
- `pinned_sector_calendar/` — по одному файлу на год, все секции A–U и неизвестная секция; агрегирование основной отрасли юридического лица, не занятость.
- `address_audit_2021_2025/point_code_alias_sensitivity_2025.parquet` — отдельная чувствительность, первичный ряд не заменён.
- `documented_provider_annual_profiles/` — фактически выполненное присоединение к 17 документированным провайдерам: 255 записей, 15 лет; исторические физические функции/границы этим не восстановлены.
- `figures/` — PNG/SVG/PDF; на графике календаря треугольники отдельно показывают условную кодовую сверку 2025 года. Визуальная проверка зафиксирована в `FINAL_VISUAL_QA.json` верхнего уровня.
- `READOUT.md` и `results/` — самостоятельный старый двухдатный аудит 2016/2021. Не использовать его как замену новому pinned-календарю. Полное сравнение пяти колонок старых и новых 2016/2021 дало точное совпадение; протокол `legacy_vs_pinned.json`.

## Фактически завершённые проверки

Новый календарь: 100 авторских инвариантов (`pinned_calendar/AUDIT.json`); широкий отраслевой ряд: 15 (`pinned_sector_calendar/AUDIT.json`); согласование отдельно вычисленных узких и широких слоёв: 180 (`CALENDAR_CROSSCHECK.json`); адреса/соответствия/даты: 16 (`address_audit_2021_2025/ADDRESS_AUDIT.json`). Все PASS. Старый двухдатный аудит: 25 основных и 30 пространственных проверок, все PASS.

Это проверки реализации и внутренней согласованности. Независимые статистические и содержательные проверки оформляются другими агентами отдельно и не заменяются числом этих инвариантов. Пространственные блоки опубликованы как чувствительность к географическому составу наблюдаемых пунктов, без псевдо-p-value и без обещания восполнить пропущенные учреждения.

## Минимальные входы для самостоятельного воспроизведения без сети

Все пути ниже отсчитываются от рабочего корня проекта:

1. `restored/extracted/research/sgrt_recovered_20261019/data/panel.parquet` — неизменная ось, SHA256 `a2b5544c0d3c5581144a5439113a96c4a771697dc87a38c2abf979e1ead1467b`.
2. `functional_dynamics_20261019/economy/remote_selected/rfsd_{2011..2025}_identity_function_selected.parquet` и соответствующие `{year}_acquisition.json` — пятнадцать пятиколоночных срезов и подтверждение одного pin/контрольных сумм.
3. `functional_dynamics_20261019/economy/remote_address_selected/rfsd_{2021,2025}_address_lifecycle_selected.parquet` и два `{year}_acquisition.json` — отдельные адреса/даты. Первые пять колонок и их файлы этим не перезаписаны.
4. Для присоединения к документированным провайдерам дополнительно нужен уже замороженный `functional_dynamics_20261019/model/results/documented_provider_profiles.parquet` и скрипт `model/join_annual_profiles.py`. Основные модельные результаты этот запуск не меняет.
5. Все скрипты этой папки; `build_dynamics.py` используется новыми скриптами как библиотека точного кодового присоединения. Полный финансовый исходник RFSD не нужен. Служебные `*_metadata.footer` и пробный `2025_footer_probe.bin` не нужны для офлайн-пересчёта и не должны включаться в публичный пакет.

Для повторной сетевой выгрузки либо проверки возобновления также сохранены `RFSD_PINNED_TREE.json`, `RFSD_PINNED_DATASET_INFO.json`, schema и все проверенные диапазоны в acquisition-аудитах. Подписанные URL в файлы не записывались. Известный SHA полного upstream-файла — метаданные репозитория; проверка SHA всего нескачанного финансового массива не заявлена.

## Реально выполненные команды

```bash
python3 functional_dynamics_20261019/economy/fetch_remote_columns.py --tree functional_dynamics_20261019/economy/RFSD_PINNED_TREE.json --out functional_dynamics_20261019/economy/remote_selected --years 2011 2012 2013 2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 --parallel-years 1
python3 functional_dynamics_20261019/economy/build_multiyear_exact.py --base . --out functional_dynamics_20261019/economy/pinned_calendar
python3 functional_dynamics_20261019/economy/build_sector_calendar.py --base . --out functional_dynamics_20261019/economy/pinned_sector_calendar
python3 functional_dynamics_20261019/economy/crosscheck_calendars.py --root functional_dynamics_20261019/economy
python3 functional_dynamics_20261019/economy/compare_legacy_inputs.py --base . --out functional_dynamics_20261019/economy/legacy_vs_pinned.json
python3 functional_dynamics_20261019/economy/fetch_remote_columns.py --tree functional_dynamics_20261019/economy/RFSD_PINNED_TREE.json --out functional_dynamics_20261019/economy/remote_address_selected --years 2021 2025 --parallel-years 1 --columns inn oktmo creation_date dissolution_date lat lon geocoding_quality --output-stem address_lifecycle_selected --footer-cache-dir functional_dynamics_20261019/economy/remote_selected
python3 functional_dynamics_20261019/economy/audit_addresses.py --base . --out functional_dynamics_20261019/economy/address_audit_2021_2025
python3 functional_dynamics_20261019/economy/build_alias_cases.py --base .
python3 functional_dynamics_20261019/model/join_annual_profiles.py --input functional_dynamics_20261019/economy/pinned_calendar/point_exact_code_witnesses_2011_2025.parquet --out functional_dynamics_20261019/economy/documented_provider_annual_profiles
python3 functional_dynamics_20261019/economy/plot_calendar.py --data functional_dynamics_20261019/economy/pinned_calendar --out functional_dynamics_20261019/economy/figures --address-audit functional_dynamics_20261019/economy/address_audit_2021_2025
python3 functional_dynamics_20261019/economy/write_pinned_readout.py --root functional_dynamics_20261019/economy
```

Оба годовых сборщика первоначально выполнялись с `--wait-for-inputs`, пока загрузка шла последовательно; с полностью сохранёнными срезами этот ключ не нужен. Загрузчик выполнялся с возобновлением: готовый файл сначала перепроверяется SHA, а не скачивается повторно. Отмена одного сетевого решения среды и восстановленный обычный маршрут описаны в `ACCESS_LOG.md`; повышенные разрешения не использовались.

Старый двухдатный аудит отдельно воспроизводится командами из `READOUT.md`; для него нужны прежние агрегаты `anchor_research_20261019/economy/coded_results/{2016,2021}/` и исходные legacy-срезы. Для нового пятнадцатилетнего расчёта они не требуются.
