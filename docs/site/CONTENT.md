# Контракт контента атласа, версия 1

Контент декларативный. ID — `lowercase-kebab`. Каждое поле выполняет научную или навигационную роль. Произвольные HTML, MDX, JavaScript, CSS, функции и настройки ECharts не допускаются.

## Реестры

`web/content/research.json` — массив объектов:

```text
id, title, description, status, summary, nextStep, order
```

`web/content/datasets.json` — массив источников:

```text
id, title, release, sourceCommit, url, sha256?, period, scope, limitations[]
```

Версия источника закрепляется явно; ссылка ведёт на существующий выпуск или точный файл коммита. `limitations` описывает область применимости, пропуски и ограничения интерпретации. Поле `sha256`, если есть, содержит 64 шестнадцатеричных символа.

`web/content/materials/ID.json`:

```text
id, researchId, title, summary, kind, topic, territory, period,
publishedAt, updatedAt, visibility, evidence, currency, sourceCommit,
sources: [{title,url}], datasetIds: [ID], visualIds: [ID], body,
supersedes?: ID, featured?: boolean
```

- `kind`: finding / method / note / correction.
- `visibility`: draft / published / archived — состояние публикации.
- `evidence`: observation / calculation / model / hypothesis / method — основание утверждений.
- `currency`: current / known-issues / superseded — актуальность.
- `publishedAt`, `updatedAt`: ISO дата или дата-время; человекочитаемые даты показываются по Москве.
- `body`: обычный Markdown. Заголовки, абзацы, ссылки, списки и таблицы; без выполнения кода.

Публикация требует заполненной территории, периода, коммита, источников и текста. Публикационный статус не доказывает научную правильность. Исследовательская модель может быть опубликована с явным названием и ограничениями.

## Визуализации

`web/content/visuals/ID.json`:

```text
id, template, title, caption, datasetId, palette, unit,
categories?: [string], series?: [{name,values:[number|null]}],
data?: array, mapState?: object, limitations?: [string]
```

Шаблоны: `census-trend`, `bars`, `comparison`, `scatter`, `table`, `settlement-map`, `service-links`.

Палитры: `population-change`, `categorical`, `service-type`, `blue`. Единица обязательна, например `человек`, `%`, `км`, `ед.`. Число категорий совпадает с числом значений каждой серии. Пропущенное наблюдение — `null`, а не ноль и не строка.

`mapState`: `research`, `layers`, `period`, необязательные `selection`, `lat`, `lng`, `zoom`. Состояние используется ссылкой «Исследовать на карте». Функциональная связь должна иметь указание основания; модельное направление не подписывается как наблюдаемая поездка.

Поле `data` применяется к таблице/точечной диаграмме по поддерживаемой реализации компонента. Новый формат данных сначала согласуется в инженерном PR с примером, рендерером и проверкой; нельзя передавать код под видом данных.

## Адреса и версии

Дополнительные слои карты: `web/content/layers/ID.json` с полями `id`, `researchId`, `title`, `description`, `datasetId`, `adapter`, `geometry`, `fields`, `palette`, `unit`, `period`, `evidence`, `visibility`. Адаптеры `geojson`, `csv-points`, `csv-settlement`; CSV поддерживает только точки. Для источника обязательны pinned HTTPS и SHA-256. Подробности и исполняемый пример — [LAYERS.md](LAYERS.md). В `mapState.layers` разрешены базовые ID и ID опубликованных дополнительных слоёв.

- Материал: `/materials/ID/`.
- Исследование: `/research/ID/`.
- Самостоятельная визуализация для экспорта: `/visuals/ID/`.
- Опубликованный префикс GitHub Pages: `/russian-settlements-research/`; настройка `PUBLIC_BASE_PATH`. Локальный сервер по умолчанию работает от `/`; CLI использует ту же переменную окружения.

Стабильный ID сохраняет ссылку после исправления. Источник в опубликованном материале обновляют содержательно, вместе с выводами и ограничениями. Нельзя подменить ZIP старого научного выпуска новыми данными. Для новых принятых данных нужен новый выпуск; контрольная сумма проверяется существующим загрузчиком.
