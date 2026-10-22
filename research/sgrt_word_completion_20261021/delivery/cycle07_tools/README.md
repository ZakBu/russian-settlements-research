# Cycle07: реальный черновик для научного руководителя

`build_report.py` создаёт MD/DOCX/PDF полного отчёта и короткой записки из **реальных зафиксированных входов**. Окончательная приёмка Word не требуется для REVIEWDRAFT; уже рассчитанные числовые источники/новые единицы/полные типы требуют собственных независимых допусков. Эти два условия не смешиваются. Здесь пока нет реального отчёта: иерархия/типология ещё исполняются.

Картограф и отчёт согласованы по `unit_id`; оба сохраняют полный тип и все роли. Просмотр `candidate_cap×partition_role` должен иметь явныйview_id, чтобы две альтернативные разметки одного состава не стали одним населением. Все фактические представления описываются в `view_semantics`, значенияkind: operational_forest/empirical_resolution/atomic_source. Леса60мин не названы уровнемL60; число эмпирических уровней не задано.

CLI:

```
python delivery/cycle07_tools/build_report.py --inputs <actual_source_bound_inputs.json> --output <new_prereg> --stage preregister
python delivery/cycle07_tools/build_report.py --inputs <actual_source_bound_inputs.json> --output <new_delivery> --stage build
```

Пути относительно исследовательского namespace. Новая выходная папка обязательна. Каждая запись artifacts: path,sha256,manifest:{path,sha256},admission:{path,sha256,required_values:[[[json,key,path],exact_expected_value],...]}; опциональныйbinding_chain — точная цепочкаJSONманифестов. ОригинальныйWord, библиография и методическая записка могут бытьreference_only; числовые артефакты — нет. ТолькоactualderivedmapPNG/atlas_receipt могут иметьcomputed_draft:true, поскольку сам REVIEWDRAFT ещё будет рецензироваться; ихreceipt должен ссылаться на точные новыеunits/types. Данные и научные результаты этим обходом не принимаются.

`analysis_status` — отдельныйJSON: PENDING_NOT_REPORTED либо COMPUTED_CYCLE07_SOURCE_BOUND. В последнем случае нужны новыеanalysis_metrics/analysis_receipt с точной привязкой новогоunitsSHA и явнойcomparison_family; старыеcoefficients/OOF не переносятся. Пустой раздел не заполняется правдоподобными числами.

Обязательные ключи перечислены в REQUIRED кода; новыеunits должны нести колонкуview_column, а configзадаётprimary_view_id/view_semantics. Популяционные поля/траектории — принятая схема normalizer и complete_typology. Для летописи изменений нужны источниковые353/477таблицы, не числа из свободного текста. `functional_case_receipt` закрепляет независимыйboundedsourcecaseаудит.

Повторно используется толькоgenericContent/render из принятого22-страничного генератораcycle06, SHA которого явно закреплён. Егоproduce(), контракты старой модели и числовые результаты не вызываются. В отдельном модуле в памяти увеличен мелкий шрифт таблиц6→8pt; исходник не менялся. Производныйкод тоже хешируется. Синтетический тест проверяет реальныеPDF/DOCX/кириллицу и полныйэкспорттипов/траекторий, но не является новым исследовательским результатом.
