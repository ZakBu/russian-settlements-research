# Новый атлас cycle07: подготовленный инструмент

Исследовательские результаты ещё не подставлены. `MAP_PROTOCOL.json` задаёт содержание/ограничения. `render_atlas.py` исполняется без старого картографа и не переименовывает четыре старых ранга. Шаблон входов намеренно незаполнен: без фактических SHA и независимых приёмок рисование запрещено.

Команды после фактической привязки:

```
python maps/cycle07_tools/render_atlas.py --config <actual_bound_config.json> --output <new_prereg_folder> --stage preregister
python maps/cycle07_tools/render_atlas.py --config <actual_bound_config.json> --output <new_atlas_folder> --stage render
```

Относительные пути входов считаются от исследовательского namespace `research/sgrt_word_completion_20261021`; абсолютные разрешены. Выходная папка обязана быть новой/пустой. `columns` задаёт соответствие `каноническое_поле: фактическое_поле`. Имена разрешений берутся только изфактического retained_resolutions, в явном порядке; `atomic_level_label` раскрывает nullableatomic при наличии. `zoom_resolution` задаёт одну принятую фактическую резолюцию и не выбирается по привлекательности рисунка.

Входы:

- `nodes`: id,name,lat,lon,population_2021,source_record_id_2021,formal_city2021. Последний флаг — явно привязанный **датированный формальный город**, не произвольный urban2026 и не порогCi. Внешние два контекста задаются отдельно по их уже принятому источнику. Аддитивное население территории вместо населения города не подставляется.
- `units`: unit_id,level(aliasresolution_index),core_id,kind; желательны parent_unit_id,n_children,max_member_direct_minutes,max_member_geodesic_km,extent_complete и счётчики неизвестных geometry/routes.
- `memberships`: unit_id,id,is_overlay_membership. Отсутствующая колонка overlay означает исходный заведомоprimary-onlyконтракт; реальный binder должен передать явную колонку для смешанного набора.
- `types`: точный уникальныйunit_id и primary_type_id/name,structural_class,unit_role. Поля качества2010 могут приходить отсюда или из units: primary2010_population_share,protected_secondary2010_population_share,population2010_known_denominator,2010_missing_population_count,population_quality_share_denominator_scope.
- `merge_diagnostics`: candidate_cap,merge_index,Q. `knee_diagnostics`: candidate_cap,knee_status,retained и при наличии median_ari,p10_ari,knee_fraction_iqr. `bootstrap_diagnostics`: candidate_cap,replicate_id,status,assessable,ari; все50повторов и всеохваты.
- Опциональная береговая линияGeoJSON sourceSHA закрепляется какcoastline; происхождение/дата закрепляются отдельнымsourcecoastline_receipt.

Приёмки задаются `independent_admissions`: path,sha256,status_pointer(массивJSONключей),expected_status. Нужно не менее двух фактических приёмок: новой иерархии и полной типологии. Это проверка существующей независимой приёмки, не самоодобрение.

Полные составные типы не заменены «прочими». На национальной карте цвет — **структурная компонента**, вCSVвсе полные коды/названия/частоты/роли. В графике частот нарисована каждая полная категория; точное прочтение каждого кода черезCSV. Цвет членства может повторяться и не служит уникальным идентификатором. Географические функциональные границы неизвестны: толькоточки и явно схематические связи с ядром. Большие пустые полигоны не закрашиваются.

`test_renderer.py` создаёт отдельные синтетические таблицы, проверяет контракты и реальныеPNG/PDFпути, включая кириллицу, NAкоординаты, роли, недостающую приёмку, все50bootstrap. `synthetic_preview/` — только синтетические превью, не карты России и не готовые результаты. Числовые исходы исследования этим тестом не проверяются.
