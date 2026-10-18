# E3: проверенные разведочные результаты

В development при10км доля крупнейшей компоненты среди активных узлов растёт в33/81регионов; в20изних доля с фиксированным исходным знаменателем одновременно уменьшается. Это эффект знаменателя, не свидетельство восстановления.

810кривых:81регион×2сетки×5радиусов. Нарушений монотонности LCC после удаления вершин нет.

Уменьшение LCC при удалении вершин математически ожидаемо; без conditionalnull не доказывает избирательность пространственной фрагментации.

development: developmentMAE baseline=0.39687904;augmented=0.39806669;ΔMAE=-0.00118765;условный95%CI=[-0.0028034187334511594, 0.00033127648467704636]. Разведка, неholdout.

development_nn: developmentMAE baseline=0.39683433;augmented=0.39853765;ΔMAE=-0.00170332;условный95%CI=[-0.0032758916150407687, -0.00020571896984794284]. Разведка, неholdout.

Ограничения: Development-only induced graphs lose cross-holdout and cross-region edges.; Fixed baselinepositive2010 nodes; zero2021 is census zero, not proven physical loss.; Normalization median globalpositive2010 fifth-neighbor distance of region development points; fixed across dates.; No conditional-risk null simulation or p-value.; LCC population shares weight surviving baseline2010 population, not2021 population.; Первая версия загрузила2021numeric целиком, затем доагрегаций стёрлаholdout;процедурное отклонение раскрыто,повтор используетdevelopment-onlyparsing.; Разведочная модель не доказывает причинность или отсутствие географических эффектов;нужныfinalfreeze и независимая репликация.
