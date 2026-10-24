# Вход для ИИ-ассистента

Правила работы, порядок чтения и стандарт текстов — в [AGENTS.md](AGENTS.md). Здесь — только как получить данные.

## Клонирование

Полный клон весит около 400 МБ; для работы достаточно последней версии:

```bash
git clone --depth 1 https://github.com/ZakBu/russian-settlements-research.git
cd russian-settlements-research
```

## Данные

Данные лежат в релизах GitHub этого репозитория. Каталог [data/catalog.json](data/catalog.json) связывает каждый файл с архивом, размером, SHA-256 и схемой таблицы. Загрузчик использует только стандартную библиотеку Python; для чтения Parquet нужен PyArrow (`python -m pip install -r requirements-handoff.txt`).

```bash
python scripts/research_data.py list                 # что входит в профиль и сколько весит
python scripts/research_data.py fetch                # скачать
python scripts/research_data.py verify               # сверить контрольные суммы
python scripts/verify_population_base.py             # проверить контрольные числа базы
```

| Профиль | Что скачивается |
|---|---|
| `core` (по умолчанию), `population`, `current` | База населения 2002/2010/2021, около 56 МБ. Описание полей — [POPULATION_BASE.md](POPULATION_BASE.md) |
| `legacy_model` | Таблицы предыдущего расчёта районов (отвергнут, см. [sgrt/README.md](sgrt/README.md)) |
| `legacy_model_full` | Полный пакет предыдущего расчёта |
| `all` | Все сохранённые данные, около 15 ГБ |

Можно скачать только нужное:

```bash
python scripts/research_data.py list --profile all --match '*medical*' --show-files --show-schema
python scripts/research_data.py fetch --profile all --match '*medical*'
```

`--match` сравнивается с путём файла; несколько `--match` объединяются по «или». Архивы обрабатываются по одному и удаляются после распаковки (`--keep-archives` их сохраняет). Скачанные данные и `.research-cache/` не коммить.

### Особые файлы в профиле `all`

В `data/source_special_files.json` описаны четыре символические ссылки и один служебный файл macOS. Две ссылки указывают на существующие таблицы, и загрузчик создаёт их копии. Две другие указывали на отсутствующую папку ещё в исходном снимке. Их цели восстановить нельзя, похожими таблицами их не подменяй. Если `fetch` останавливается с `Existing file differs` на одном из этих путей, сверь SHA-256 файла с `original_sha256` в этом JSON, убери совпавший файл и повтори загрузку.

## Новый пилот СГРТ

Результаты от24.10.2026: [sgrt/pilot/README.md](sgrt/pilot/README.md). Это рассчитанные сценарии образования и медицины с типами кандидатных единиц и картами, не принятая общероссийская делимитация. Данные доступны через отдельный `data/pilot_catalog_20261024.json`; главный каталог и профили core/population/current по-прежнему загружают принятую базу населения. Исходные данные и результаты не надо брать из отвергнутой модели районов.
