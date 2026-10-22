# Независимое воспроизведение R

Отдельный исследовательский агент до чтения основного кода/точных итогов самостоятельно вычислил rawchecks и пространственные запросы. Это независимая реализация на тех же данных, а не внешний эмпирический материал; одинаковая модельLLM и sklearnlibrary ограничивают независимость.

## Вычислено и проверено
- blind_initial/receipt.json: stdlib CSV/gzip/Decimal, SHAвхода,142570строк,135полей,уникальностьUID,суммы,нули,переходы,качество2010,диапазонкоординат.
- geometry_comparison.json:200bruteforcequeries(100хеш+100populationstrata),4600checks; counts/mass/history/normalizedexact; nearestNNerror<=3.55e-15км. Первичная planar/sphericaldensityконвенция не совпала; отрицательныйreceiptсохранён,послесогласования явнойсферическойплощади0ошибок.
- nearest_comparison.json:100origins,800checksnearestlarge/larger/federalanchors,0ошибок,maxdistanceerror9.09e-13км.
- components_comparison.json:development3региона×3радиуса,90checksedges/components/LCC/isolationinitial/surviving,точно.
- sensitivity_mass_comparison.json:14origins×2population/neighborvariants×4радиусаmass/count=224checksточно. Это толькоmass/count,неполнаярепликацияvariantfeatures.
- development_metric_comparison.json:первичныеdevelopmentE1Brier/E2MAEпересчитаныизsavedpredictionsбезимпортаосновныхфункций,точность1e-12.
- independent_fit/:самостоятельныйE1featurematrix/split/buffer/fitкод,train77832/test19731,labels2021толькоtrain. Сравнениеfinalpredictionбудетпослеосновногозапуска.

## Исправления и ограничения

statistics_review/ содержитfreezegates идваreviewrunnerдоlabelreveal. Выявленныйусечённыйdriftgzipзаблокировалпервыйlock; recoveryполученуникальносatomicwrite/CRC;причинапорчинеустановлена. `sensitivity_failure.md`содержитошибкуиуточненияappend-only.

Не подтверждены независимость200кмблоков,калибровкаp/CI,внешняяпереносимость,причинность,национальныйcensusuniverse. Федеральныеякоря — ретроспективныеpointanchors,ихисторическаягеографиянепроверенарасстояниями. Источники2010имеютсильнуюнеоднородностькачества;numericнеравноточныйпереписнойитог.

## Финальная проверка завершена

`final_replication_report.json` и `final_review.md`: все18 финальных метрик воспроизведены; первичныйE1 самостоятельно переобучен доholdoutlabels и совпал побитово; prelabel/final predictions неизменны. Независимые описательные bootstrap-интервалы находятся в`e1_independent_bootstrap.json`,`e2_independent_bootstrap.json`. Совпадение вычислений не снимает ограничения дизайна.
