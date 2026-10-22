# Таблицы и воспроизведение

В репозитории доступны полный национальный каталог914полей и функциональные профили448полей. Каждая таблица сохраняет142570UID; это свидетельства источников, не доказанные районы внешнего обслуживания.

ОсновнойParquet хранится тремя двоичными частями. После checkout этой ветки выполните изкорнярепозитория:

```bash
python research/sgrt_national_integration_20261019/core/reconstruct_feature_master.py
```

Будет получен `core/feature_master.parquet`; егоSHA2568c98d5a113eec4c3bf131232b1d7e5c6362dc3a50ee484e964420de58c377f85. При несовпадающем существующем файле сценарий останавливается. Состав/хэши частей — `core/master_parts.json`. `screening/support_point_profiles.parquet` хранится целиком.

PDFотчёт — [output/pdf/SGRT_NATIONAL_FUNCTIONS_REPORT.pdf](output/pdf/SGRT_NATIONAL_FUNCTIONS_REPORT.pdf). КартыPNG — вfigures/. ВсеPNG/SVG/PDF,CSV.gz,полныеобъектныекаталоги иавтономныйкомплектсвходамипереданыотдельнымипровереннымиархивамиэтойзадачи;ихсоставзафиксированвARTIFACT_MANIFEST.json. Дляповтораименноновойволнынужнывходыизэтогокомплекта,онинеподменяютсявсемирнымнефильтрованнымPOIдатасетом.

Рабочий корень автономного комплекта используетимя national_integration_20261019/,Gitпубликация—research/sgrt_national_integration_20261019/. Научныйкодвобоиходинаков;папкасзакреплённымивходамираспаковываетсярядомкаквRUN_INSTRUCTIONS.txt.
