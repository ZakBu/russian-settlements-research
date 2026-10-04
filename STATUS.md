## Актуальное состояние: Graph19, 4 октября 2026

Цель 99% по совместной оси «координата + многолетний путь доступных наблюдений» ещё не достигнута. Graph19 принял две связи Локтя 2002–2010–2021 и один прямой point-use за 2021 год; точка 2010 — только маркированная пространственная преемственность, точка 2002 уже была в ledger. Население 12094/10028/8469 сохранено; границы переписей сопоставимыми не объявлены. Независимый readback и полный Parquet обновлены.

| Показатель | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| NP: принятая точка + полная обычная цепочка |86.128977%|85.618701%|83.463738%|
| Координата и путь доступных лет, scope-aware |97.263306%|97.587888%|98.292062%|
| Остаток до 99%, человек |2521102|2017295|1041959|
| Остаток до 100%, человек |3972769|3445860|2513780|

Full long: 865395 строк, включая 465800 переписных; сумма выбранного переписного населения 434700152 сохранена. SHA-256 `7f955d3310c247467037a380855d97bb2edd48d347c80839ff6aa12915b87b21`. Отдельный analysis CSV не обновлялся. Подробные оси и ограничения: `docs/COVERAGE_LIMITS_AND_NEXT_BATCH_20261005.md`; доказательства Graph19 в `research_rebuild/evidence/mass_joint_20261004/graph19_lokot/`. Строгое обычное НП-покрытие отделено от mixed scope-aware показателя; показатели границ остаются непроверенными.

GitHub запись по-прежнему блокируется ответом 403; Graph19 существует только в локальном Git и артефактах этой рабочей среды.

## Исторический срез: Graph18


Цель 99% ещё не достигнута; продолжается увеличение покрытия к 100%.
Цель 99% пока не достигнута. Graph18 добавил одну независимо проверенную связь
2002↔2010 Русского, продолжив существующую цепочку 2010↔2021, и одну точку-преемственность
для 2002 года. Выбранные численности сохранены; 2010 Русского 4428 остаётся значением
защищённого происхождения, отдельным от официальной строки Росстата 4703. Канонический
граф содержит 348645 связей, 132843 обычных полных трёхпереписных компонента и 428156
применений точек. Graph17 Нижнего Нойбера остаётся принятым; его 2010 строка удержана.

| Показатель | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| НП: точка и обычная полная первичная цепочка, доля национального населения |86.120646%|85.611682%|83.457984%|
| Координата и путь доступных лет, с явно обозначенными типами и ограничениями |97.254975%|97.580868%|98.286308%|
| Остаток до 99%, человек |2533196|2027323|1050428|
| Остаток до 100%, человек |3984863|3455888|2522249|

Смешанный показатель включает федеральные территории, реальные доступные даты,
типизированные преобразования и обозначенные вторичные свидетельства. Он не
доказывает сопоставимость численности в одинаковых границах. Частичные суммы в
современных границах не реконструируются. Численность исходных строк не изменена.
31 столкновение текущих точек и вопрос флага Струг Красных оставлены для разбора.
Сходня и Никольско-Архангельский: +37756 старых жителей в типизированных
вторичных пространственных референсах; это не переписные цепочки и не новая
численность нынешних Химок/Балашихи.

Полная выгрузка на 865395 строк обновлена для Graph18 точечной пересборкой трёх
записей Русского по observation ID; остальные 865392 строки взяты из полной Graph17
выгрузки. Все 465800 переписных строк и их сумма 434700152 сохранены.
SHA-256: `32ed77b69ecc9522b55924545b1cdc01b72fac87b0ad199097ce00d98dad2e0e`.
Подробные отдельные показатели наличия координат, принятых координат, временной
связи, полной цепочки и совместных осей записаны в
`docs/COVERAGE_LIMITS_AND_NEXT_BATCH_20261005.md`.
Анализный CSV отдельно не обновлялся и не подходит для нового состояния. Аудит роста
пока относится к графу15. Контроли 2021 сверены для 82 обычных регионов, трёх
федеральных территорий и 2336 муниципальных итогов.
Недостачи выбранных сумм 2002/2010 остаются 11726/493512 человек.

GitHub отклоняет запись приложения с HTTP403; новый внешний репозиторий не создан.
Локальный Git работает. Токены в исследовательские файлы и дневник не записываются.
Биофабрики: 2021 точка (45.0822595,39.1995747), население 3302 как контекст,
совпали собственная строка локального уровня, уникальное ОКТМО и UUID ФИАС-6
источника/ответа; подпись ответа «п Пригородный» сохранена как оговорка. Точка
не переносилась назад и не меняла население/связи. Зеленоградский и Сосновка
остаются удержанными.
Квитанции: `research_rebuild/evidence/mass_joint_20261004/graph16_points_and_large_paths/`
и `research_rebuild/evidence/mass_joint_20261004/graph16_skhodnya_nikolskoe_inclusion2/`.
Полный long: `/workspace/settlements-work/continuation_20261004/root/long_graph16_complete_20261005_streamed2/`
Координатная application receipt: `/workspace/settlements-work/continuation_20261004/accepted_graph16_biofabriki_point_20261005/`

## Предыдущее состояние: 4 октября 2026, граф 15 и первичные дополнительные даты

Цель 99% ещё не достигнута. Канонический граф: 348639 связей,
132840 полных трёхпереписных компонентов, 421141 применений точек.
Применены 71 связь ЕАО и 879 текущих + 1827 ретроспективных точек;
две конфликтующие старые точки ЕАО удержаны отдельно от принятых связей.
Чтение результата подтвердило ноль изменений старых научных полей.

| Доля национального населения | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| НП: точка и полная первичная цепочка |86.098162%|85.586814%|83.429980%|
| Координата и путь доступных лет, с ограничениями состава |97.178429%|97.536516%|98.258304%|
| Остаток до 99%, человек |2644316|2090683|1091644|

Смешанный показатель включает отдельно обозначенные федеральные территории,
реальные даты Крыма, преобразования и вторичные датированные утверждения.
Он не доказывает сопоставимость границ. Первичная обычная цепочка НП показана
отдельно. Последние 16 путей используют точную дополнительную публикацию
2010 года на существующем месте 2002/2021: её числа не добавлены к национальной
сумме 2010 и неоднозначные защищённые строки не заменены.

2021: 82 обычных региона и три федеральные территории совпали с официальными
итогами; 2336 непересекающихся муниципальных сравнений покрывают все 128022280
жителей обычных регионов, с нулевыми различиями. В 2002/2010 остаются недостачи
11726/493512. Рост: 6554 пары отмечены для разбора, из них 3124 с защищённым
источником; это признаки риска, а не доказанные ошибки.

Подробности: [состояние и проверки](docs/TEMPORAL_SCOPE_AND_CONTROL_UPDATE_20261004.md),
замороженные квитанции в `research_rebuild/evidence/mass_joint_20261004/`.
Большая выгрузка 865395 строк пока отражает граф 11; актуальный расчёт использует
граф 15 и все применённые слои из конфигурации. GitHub отклоняет запись с HTTP403;
локальный коммит не является загрузкой в GitHub.

## Предыдущее состояние: 4 октября 2026, граф 14 и применённые исторические пути

Цель 99% ещё не достигнута. Канонический граф содержит 348568 связей,
132769 полных трёхпереписных компонентов; принято 418435 применений точек.
Последний пакет: 22 связи и 20 ретроспективных применений точек.
Чтение результата подтвердило сохранение старых научных полей.

| Доля национального населения | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| Координата и траектория доступных лет, с явными ограничениями состава |96.970683%|97.433441%|98.117482%|
| Остаток до 99%, человек |2945894|2237932|1298909|

Знаменатели: 145166731 / 142856536 / 147182123. Смешанный показатель
включает отдельно обозначенные федеральные территории, реальные даты Крыма,
исторические преобразования и вторичные датированные утверждения. Это не
доля обычных НП с полной первичной цепочкой и не реконструкция в современных
границах. Все оси и ограничения сохранены в опубликованном в Git описании
[состояния и проверок](docs/TEMPORAL_SCOPE_AND_CONTROL_UPDATE_20261004.md)
и копиях расчётов в `research_rebuild/evidence/mass_joint_20261004/`.

Независимая внешняя проверка 2021: 82 обычных региона и три федеральные
территории совпадают с официальными итогами. 2336 непересекающихся
муниципальных сравнений охватывают всё население 82 обычных регионов
(128022280), различия равны нулю. Для 2002/2010 общие недостачи исходного
слоя остаются 11726/493512; защищённые числа 2010 не исправляются
распределением регионального остатка.

Приняты отдельные исторические пути Климовска, Юбилейного, восьми бывших
посёлков, села Дыгулыбгей и остальных ранее принятых преобразований.
Сомово 2010 входит в выбранный исходный слой; его прежняя ошибочная
классификация как вспомогательной записи исправлена отдельным решением.
879 кандидатов на новые текущие точки пока не применены и не включены
в этот процент. Большая выгрузка 865395 строк пока отражает граф 11;
актуальный расчёт использует канонические граф 14, точки и применённые слои.

GitHub отклоняет запись с HTTP403; локальные коммиты доступны. Загрузка
нового состояния на GitHub не утверждается.

## Предыдущее состояние: граф 12 и крупные исторические пути

Цель 99% ещё не достигнута. Приняты 348367 межпереписных связей,
132711 полных трёхпереписных компонентов и 418336 обычных применений точек.

| Доля национального населения | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
|НП: точка и строгая полная цепочка|85.911964%|85.395380%|83.234995%|
|С федеральными территориальными цепочками|96.098625%|96.863576%|95.880568%|
|Пространственные траектории доступных лет|96.618917%|97.074497%|97.621163%|
|Остаток до 99%, человек|3456540|2750707|2029402|

Знаменатели: 145166731 / 142856536 / 147182123. Смешанный показатель
отдельно включает федеральные территории, реальные доступные даты Крыма
и Севастополя, принятые официальные и явно обозначенные вторичные
исторические пути. Он не означает, что каждый НП имеет обычную цепочку
трёх российских переписей или сопоставимые границы.

Пакет12 добавил58 связей,19 прямых и63 ретроспективных применения точек.
Научное чтение результата обнаружило0 изменений старых концов/статусов
связей и0 изменений старых координат/статусов/происхождения точек.
Отдельно принята полная опубликованная двухчастная структура Новой Усмани:
22476 / 29272 / 36540, с одной репрезентативной точкой целого села.
Состав и численности каждой исходной части сохранены; индивидуальные точки
частям не приписаны. Это не реконструкция в современных границах.

Девять старых строк шести включённых посёлков и Железнодорожного получили
отдельные проверенные вторично описанные пути к принимающим городам.
Старые значения учтены один раз; современные значения родителей не
перенесены. Семь применений исторических точек находятся только в этом
пространственном слое, ещё два ссылаются на обычный принятый реестр.
Юридические даты и сопоставимость границ не повышены в статусе.

Проверка роста выявила6532 пары наблюдений для разбора, включая3118 пар
с защищённым источником. Это флаги, а не6532 доказанных ошибочных НП.
Внутренний контроль2021:82 региона и2304 однозначных верхних муниципалитета
совпали с итогами той же публикации;29 муниципальных ключей не найдены,
2 неоднозначны. Независимая проверка по официальному XLSX Росстата выполняется.
Текущий региональный контроль2002/2010 ещё не завершён; национальные
недостачи выбранного источника11726 /493512 /0 не распределяются вручную.

Полный экспорт865395 пока представляет граф11. Для текущих показателей
используются реестры графа12 и проверенные пространственные слои из
`config/mass_joint_20261004.json`; пересборка полного экспорта ожидает
объединённую следующую партию. Исторические вторичные значения и ОКТМО/
ОКАТО сохранены со статусами; снимок кода не становится правовым интервалом.

Квитанции: `research_rebuild/evidence/mass_joint_20261004/primary58_and_large_inclusion_scope/`.
GitHub write остаётся HTTP403; локальный Git не означает загрузку в GitHub.
Работа продолжается с крупными НП, затем с массовыми малыми исключениями.

<details>
<summary>Предыдущие проверенные этапы</summary>

## Актуальное состояние: 4 октября 2026, граф 11 и полный экспорт

Цель 99% ещё не достигнута. Приняты 348309 межпереписных связей,
132692 полные трёхпереписные компоненты и 418254 применения координат.

| Доля национального населения | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
|НП: точка и строгая полная цепочка|85.827432%|85.310340%|83.154155%|
|С федеральными территориальными цепочками|96.014094%|96.778535%|95.799728%|
|Пространственные траектории доступных лет|96.381555%|96.864276%|97.515496%|
|Остаток до 99%, человек|3801112|3051022|2184924|

Знаменатели: 145166731 / 142856536 / 147182123. Показатели используют
полные национальные контроли. Последняя строка покрытия включает
эксклюзивные федеральные территории, Крым2014→2021, Севастополь2021→
2022/23/24, три официальные траектории, Троицк/Щербинку с вторичными
WD2021 утверждениями, Талнах/Кайеркан как города2002→районы2010/2021
и два вторично описанных включения Калинино/Пашковского в Краснодар.
Дети не прибавляются к уже учтённым родителям. Эти пути не объявлены
обычными трёхпереписными цепочками НП; сопоставимость границ неизвестна.

Полный экспорт865395 пересобран по актуальным графу и реестру точек.
Все465800 исходных переписных строк и их численности сохранены; добавлены
1016 реальных наблюдений Крым2014 и27 первичных наблюдений Украина2001.
309 контекстов современных субъектов WD остаются только отображением.
Восьмистрочный пространственный слой старых городов/посёлков применяется
соединением по идентификатору исходной строки и году без дублирования
населения. Датированные ОКТМО/ОКАТО ещё не являются правовыми интервалами;
старые снимки идентификаторов требуют отдельного обновления entity_id.

Две ошибочные старые привязки Таёжного (0 человек) выведены из активного
реестра: точка другого района находилась в522км от нужного места. Исходные
строки и отклонённые утверждения сохранены. Новый сканер исходных блоков
прошёл20 контрольных строк, но дал0 кандидатов: ограничения и повторы
описаны в квитанции; массового прироста от него не заявлено. Новые
кандидаты WD/DaData пока не входят в покрытие.

Конфигурация: `config/mass_joint_20261004.json`. Проверенные квитанции:
`research_rebuild/evidence/mass_joint_20261004/scoped_and_long_consolidation/`.
Запись GitHub по текущему подключению возвращает HTTP403; локальный
Git и bundle не означают публикацию. Работа по остатку продолжается.



## Текущее состояние — 4 октября 2026: граф 9, точки и реальные исторические годы

Цель 99% ещё не достигнута. Приняты 347164 межпереписные связи;
131562 компоненты содержат по одной записи 2002, 2010 и 2021.
Реестр принятых пространственных применений содержит 414890 записей.

| Координата и связь лет вместе, доля населения | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| НП, строгая полная цепочка | 85.411697% | 84.888412% | 82.717339% |
| С отдельными федеральными территориальными цепочками | 95.598358% | 96.356608% | 95.362912% |
| С принятыми траекториями доступных лет | 95.811724% | 96.391722% | 97.078681% |
| Остаток населения до 99% | 4628317 | 3726096 | 2827839 |

Знаменатели — национальные контроли 145166731 / 142856536 / 147182123.
Смешанный показатель использует федеральные территориальные цепочки,
реальные Крым2014→2021 и Севастополь2021→2022/23/24, эксклюзивный итог
Москвы2002, а также три принятые официальные траектории Кущёвская,
Калининец, Трудовое. Родители, части, альтернативные публикации и повторно
принятые связи исключаются из двойного счёта. Идентичность не означает
гармонизированные границы или точность защищённой численности2010.

Пакет9: 202 новые связи, 12 переносов точки. Две остальные рекомендации
удержаны по флагам исторических преобразований: Хорлово и Шаталово.
Принят следующий отдельный пакет: 5 текущих точек GeoNames и 10 переносов
по принятым путям. Фактический ZIP, член RU.txt и локаторы исходных строк
сохранены; согласующиеся Tochno-точки не названы источником выбранных точек.

Добавлены 27 первичных украинских переписных наблюдений на 2001-12-05,
845627 человек, с принятыми путями 2001→2014→2021 и ретроспективными
современными точками. Это расширение реальных лет, без фиктивных российских
2002/2010 и без нового прироста российского показателя. Вторичные
утверждения Wikidata сохранены как альтернативы.

Последний полный экспорт865368 ещё отражает граф8 и35 дополнительных
точек. Актуальные граф9/414890точек, три официальные траектории и27строк2001
хранятся в указанных конфигурацией отдельных принятых слоях; полный экспорт
ожидает одного консолидированного обновления. ОКТМО2021 и контексты2011 —
датированные снимки источников, не придуманные юридические интервалы.

Конфигурация: `config/mass_joint_20261004.json`. Квитанции и доказательства:
`research_rebuild/evidence/mass_joint_20261004/ninth_reviewed_and_scoped_history/`.
177 следующих точек прошли независимую проверку, приложение выполняется;
834 административно различённых одноимённых НП и пакет1545 временных
кандидатов пока не считаются приростом. Крупные остатки разбираются отдельно.
GitHub запись блокируется403; локальный Git и bundle не означают публикации.

<details>
<summary>Предыдущее состояние граф8 с дополнениями</summary>

## Текущее состояние — 4 октября 2026: граф 8 и проверенные дополнения

Цель 99% ещё не достигнута. В графе 346962 связи и 131376 полных
компонент 2002 → 2010 → 2021. Приняты координаты для 414863 записей:
после восьмого пакета добавлены 35 точек и 3 точки Межгорья.

| Координата и связь лет вместе, доля населения | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| НП, строгая полная цепочка | 85.232600% | 84.719291% | 82.555576% |
| С отдельными федеральными территориальными цепочками | 95.419261% | 96.187486% | 95.201150% |
| С принятыми траекториями доступных лет | 95.595837% | 96.187486% | 96.879239% |
| Остаток населения до 99% | 4941712 | 4017860 | 3121382 |

Знаменатели — национальные контроли 145166731 / 142856536 / 147182123.
Траектории доступных лет используют реальные 2014 → 2021 для Крыма,
2021 → 2022/23/24 для Севастополя и эксклюзивный родительский итог Москвы
2002. Родитель и дети не суммируются. Строгая российская цепочка показана
отдельно; сопоставимость границ не выводится из идентичности.

Всего принято 1016 официальных наблюдений 2014; 11 дополнительных
прочерков означают неизвестную численность, не ноль. Пять новых официальных
утверждений о населении крупных НП и пять наблюдений исторических
преобразований хранятся отдельно; они пока не увеличивают этот показатель.
Прежние переписные численности сохранены, разница с контролями
11726 / 493512 / 0 и защищённые вторичные значения 2010 остаются явными.

Афипский2002: ошибочная точка заменена по независимой проверке, полная
прежняя запись архивирована. Афипский2010 уже был принят; прирост населения
от этой операции равен нулю. Все 414862 остальные строки реестра неизменны.

Последний полный экспорт содержит 865368 строк: граф 8, 35 новых точек,
1016 официальных наблюдений 2014 и 309 современных контекстов вторичных
исторических утверждений. Три последующие точки Межгорья уже приняты
в координатном реестре и расчёте; их проекция в полном экспорте ещё ожидается.
ОКТМО: 155414 собственных кодов публикации 2021; 81226 отдельных
контекстов исторического классификатора 2011. Юридические интервалы
и недоказанные изменения кодов не создаются.

Конфигурация: `config/mass_joint_20261004.json`. Проверочные квитанции:
`research_rebuild/evidence/mass_joint_20261004/reviewed_increments_after_eighth/`.
Запись GitHub остаётся заблокирована 403; локальные коммиты и Git bundle
не означают удалённой публикации. Продолжается приоритет крупных НП
и массовая проверка исторических кодов, названий и исходных строк.

<details>
<summary>Предыдущие проверочные состояния</summary>

## Текущее состояние — 4 октября 2026, восьмой применённый пакет

Цель99% пока не достигнута. Принято346962 межпереписных решения,131376 полных
компонент2002→2010→2021;414825 записей имеют принятую точку. Новая партия:
10650 связей и10623 переноса точки по принятому пути. НезависимыйDFS воспроизвёл
компоненты и совместное покрытие; прежние проверяемые научные поля не изменены.

| Доля населения от национального контроля |2002|2010|2021|
|---|---:|---:|---:|
|ФизическийНП: координата+строгая полная цепочка|85.166355%|84.547056%|82.521717%|
|С отдельными федеральными территориальными цепочками|95.353016%|96.015252%|95.167290%|
|Доступные годы: принятые территориальные/Крым2014 связи|95.529592%|96.015252%|96.702409%|
|Остаток населения до99% последнего показателя|5037878|4263908|3381643|

Последний показатель: для обычныхНП сохраняется полная русская трёхпереписная
цепочка; для Крыма используются реально принятые2014→2021 связи, дляСевастополя
реальные2021→2022/23/24 территориальные связи. Москва2002 представлена точным
родительским итогом10382754 вместо пяти дочерних строк; двойного счёта нет.
Строгая трёхлетняя цепочка показана отдельно; российские2002/2010 дляКрыма
не создаются. Территориальная точка не доказывает численность каждого дочернегоНП
и не гармонизирует меняющиеся границы. Все показатели ниже99%.

Национальные контроли145166731/142856536/147182123. Исходные переписные значения
не изменены; расхождения11726/493512/0 сохраняются. Защищённые2010 значения
не становятся точными из-за геокодирования.

Принят отдельный слой994 официальных наблюдений2014 (993 с ретроспективной
современной точкой); источник — точная архивнаяHTTPS копия Росстата, а не
повышение качестваWikidata. У993 точек сохранено фактическое происхождение:
972Tochno/DaData и21Wikidata.309 проверенных датированныхWikidata утверждений
получили контекст современного субъекта; неизвестный исторический уровень
населения и границ не улучшен. Длинный экспорт865346 строк относится к графу7;
экспорт8 выполняется отдельно. Конфигурация `config/mass_joint_20261004.json`
и квитанции `research_rebuild/evidence/mass_joint_20261004/eighth_reviewed/`.

33 теста приложения/исключений/экспорта прошли; независимыйDFS и проверка
сохранности научных полей подтверждают конкретный выпуск. Аппликация8:
61.873сек,peakRSS14484048KiB. Сбой первого запускаCSV128KiB сохранён;
полные поля доказательств читаются без усечения.

GitHub запись всё ещё403; выполненные локальные коммиты не являются удалённой
публикацией. Продолжается приоритетный разбор крупныхНП и массовых правил
для остатка; кандидаты новых точек и официальных2010 замен не включены
в достигнутое покрытие до применения.

<details>
<summary>История предыдущего состояния</summary>

## Текущее применённое состояние — 4 октября 2026

Цель —99% населения с координатой и связью доступных лет вместе — пока
не достигнута. Конфигурация: `config/mass_joint_20261004.json`; точные квитанции
и история: `docs/MASS_JOINT_RUN_20261004.md`, `docs/DECISION_DIARY.md`.
Опубликованные исходные контрольные состояния сохраняются неизменными.

Актуальный седьмой граф:336312 принятых решений,120747 полных компонент
2002→2010→2021;404202 выбранные переписные записи имеют принятую точку.
В седьмой партии добавлены8353 связи и8304 переноса точки по принятому пути;
2306 дополнительных подтверждений сохранены отдельно. Это разные единицы,
не8353 новых трёхлетних цепочки.89 прежних неоднозначностей crosswalk разрешены
только для конкретных пар с проверкой248 исходных и конкурирующих строк.

| Доля населения от полного национального контроля | 2002 | 2010 | 2021 |
|---|---:|---:|---:|
| Физический НП: принятая точка и полная цепочка | 84.496109% | 83.949327% | 81.967466% |
| Вместе с отдельной преемственностью федеральных территорий | 94.682770% | 95.417523% | 94.613039% |
| Остаток населения до99% второго показателя | 6267182 | 5117803 | 6456823 |

Полные национальные знаменатели:145166731/142856536/147182123. Федеральные
итоги представлены отдельным территориальным слоем: родитель и дочерние НП
не суммируются; сопоставимость населения при изменении границ не утверждается.
Крым/Севастополь не получают фиктивных российских наблюдений2002/2010.
Потолок строгой национальной трёхпереписной цепочки2021 —98.313348%; реальные
иные годы и доказанные события учитываются отдельной траекторией доступных лет.

Два независимых способа построения компонент (union-find при применении,
DFS при readback) согласуются. Все проверяемые научные поля прежних решений
и точек сохранены; численность исходных465800 переписных записей не изменена.
Применение заняло60.897с, пикRSS13495508KiB.32 относящихся к текущим изменениям
теста прошли, включая точную область исключения старой неоднозначности,
сохранение настоящих конфликтов и качество координат в экспорте.

Седьмой полный длинный экспорт завершён:500320 исходных наблюдений и364032
вторичных утверждения, всего864352 строки. ПолныйParquet: `3c24c716…17c0`;
core: `101c133f…7c53`. Историческая численность не заменяет переписные значения.
Снимки кодов:155414 буквальных строк2021 года и81234 исходных контекста
GeoKLADR2011;21708 последних не содержат ОКТМО и остаются неизвестными.
861 проверенная замена старых GeoKLADR-точек сохранена вместе с861 полным
предшественником.309 дополнительных реальных P1082-утверждений сохраняют
вторичное качество; неизвестная область численности не повышена до точного НП.

Диагностика седьмого состояния:1072 компоненты с расхождением точек>5км,
721>20км. Это экран противоречий, а не доля доказанных ошибок. Буквальные
снимкиОКТМО и происхождение кодов сохраняются; юридические переходы не придуманы.
Новые кандидаты по изменению типа, структуре исходников и реальным2014
наблюдениям Крыма не включены в достигнутые проценты до применения.

Удалённой публикации нет: последняя проверка записи через GitHub-приложение
вернула403, CLI-токен недействителен. Работа сохраняется в локальномGit
и проверяемых bundles. Следующие разделы — история предыдущих состояний.

# Research status

## User decisions after the audit — 2026-10-03, 23:49 MSK

[Scope and working-series decisions](docs/FEDERAL_CITIES_AND_WORKING_SERIES_DECISIONS_20261003.md)
allow federal-territory reference points in the primary spatial measure, with
exclusive parent-or-child counting and separate atomic-NP coverage. Dated
Wikidata secondary observations may be displayed before independent primary
verification, with quality flags and no replacement of exact census values.
These decisions alone add no accepted points/edges or validated coverage.
The frozen scientific checkpoint and prior audit below remain unchanged.

## Rule audit and revised priority, 2026-10-03 evening MSK

[The audited 99% plan](docs/AUDIT_AND_PLAN_99_20261003.md) keeps the scientific
checkpoint below unchanged. The user prioritizes reliable interyear series and
places >=2000 people, then the remaining population needed for99%. That threshold
covers81.984502%/83.173177%/85.291474% of the full census controls, not95%.
A Wikidata rule-extension candidate pool has12803rows/3320225people after
preserving known city holds. Historical8/11digit urban-code bridges and1138
candidate2021continuations of accepted older pairs require scoped review.
No new coordinate/identity admissions are claimed by this audit. Federal-territory
representation remains a separately labeled spatial metric. Cached dated Wikidata
population claims are being extracted with full statement and source provenance.

## Local working checkpoint, 2026-10-03

The current local checkpoint contains465800 selected census records,177707 accepted
identity edges,44758 full census chains and332005 accepted census point uses.
1400 independently reviewed2010 publication replacements are applied; the
known2010 sum is142363024,493512 below the primary national control. The original
published R2/R5b snapshots below remain preserved and have not been republished.

Accepted point coverage weighted by recorded population and divided by verified
national controls is83.081300%/71.607647%/81.685925% for2002/2010/2021. The99.9%
target remains unmet. Coordinate availability, identity, full chains, source-count
quality and comparability are separate. The final working long table has500320
observations, including516 official2022–2024 observations and34004 literal
Wikipedia assertions that have no accepted historical coordinates.

See [consolidated result](docs/CONSOLIDATED_LOOP_RESULT_20261003.md),
[active run](docs/ACTIVE_RESEARCH_RUN.md) and [decision diary](docs/DECISION_DIARY.md).
Large outputs are under `/workspace/settlements-delivery/continuation-consolidated-20261003`.
The actual execution manifest and an independently checked metadata-correction
manifest are distinct; the latter claims no re-execution. The federal aggregate
grain guard caps current-source point coverage below99.9% in every year.
Legacy optional status/nested-ID limitations are disclosed in the final review.
GitHub is public and readable; branch pushes last returned403, so new work is
recorded locally and supplied as a Git bundle. The following2026-09-30 sections
describe preserved published states and their then-current limitations.

## Latest national state: reviewed R5b over the current R2 source snapshot

R5b is an independently reviewed Yearbook 4.9 identity bridge over the selected R1 endpoints. It contains 1,162 graph edges: 159 new 2010–2021 edges and four supporting decisions for pairs already connected in R4. Its coordinates and publication bindings are byte-identical to R4; it adds no point claims. Nine Yearbook exceptions remain held. The 24-case check validates the rule family and does not estimate national matching precision.

Regional source-selection R2 is the current 2010 population snapshot and supersedes R1 for current endpoint selection. It selects 152,314 rows and 142,202,712 people for 2010, compared with 152,313 rows and 142,172,038 people in R1. Its endpoint projection leaves 1,108 identity edges active and holds 54 pre-existing edges attached to displaced 2010 endpoints. An independent review accepts 50 replacement publication bindings for those 54 edges, making them eligible for migration; that migration has not been integrated into a published graph. Do not count those edges as restored or active.

The archived R5b graph remains a verified R1-based checkpoint. Its 2010/2021 bridge is not represented as the current R2 graph until the endpoint migration is integrated and independently checked. Experimental point candidates, including the 8-point component, remain quarantined and are not coordinate admissions. The 99.9% population-linked goal remains unproven.

The private release `national-reviewed-checkpoint-r5b-r2-selection-2026-09-30` carries R5b evidence, the full R2 selection/projection output, and an experimental current research code/docs snapshot. See the [release asset manifest](research_rebuild/evidence/releases/national_reviewed_checkpoint_r5b_r2_20260930/asset_manifest.json) and [snapshot inventory](research_rebuild/evidence/releases/research_code_docs_snapshot_20260930/source_snapshot_manifest.json). The snapshot excludes raw data, evidence, generated outputs, and caches while listing each omitted file with its size and hash; prior baseline bundles are referenced instead of duplicated.

## Preserved baseline

The private baseline snapshot contains 7,054 raw and interim files, legacy and forensic DuckDB databases, and original audit outputs. These are retained as comparison inputs. The historic crosswalk and coordinates remain hypotheses, not a validated national identity or spatial database. Files in each asset are verified against SHA-256 manifests.

## R6 source-corrected Karelia pilot

R6 uses the actual Rosstat Volume 1 Table 5 PDF for the 2010 urban rows. Older R4b/R5 linkage releases that mislabeled this PDF as the separate Volume 11 Table 1.4 source are superseded and should not be cited as source-correct releases. Volume 11 Table 1.4 is retained as separate comparison evidence. A row-level reconciliation checks prior case citations against the correct publication.

The 2010 Karelia selected slice contains 800 source rows and 643,548 people: 24 urban Table 5 rows and 776 official rural-volume rows, including 109 zeros. It reconciles to the official regional control. The corrected DOCX parser preserves the full row evidence for two names previously damaged by smart-tag extraction. The original download had a local TLS certificate-chain failure; its bytes, SHA-256, and independent content controls are preserved, but transport verification remains open.

The pilot has 24 case-reviewed urban and urban-type identity chains and 72 observation-level point admissions. Earlier-year coordinate uses are explicitly `inferred_continuity`, not direct historical measurements. Population coverage for these reviewed chains is 75.0254% (537,395/716,284) in 2002, 78.0388% (502,217/643,548) in 2010, and 79.4716% (423,680/533,121) in 2021. These percentages apply only to the selected Karelia snapshots; they do not imply matching precision or national accuracy. The 2002 selected slice remains 3 people above its regional control, unassigned.

The distribution includes a self-contained DuckDB copy of all 26 Parquet tables and one analyst-facing view. Its sidecar records table schemas, row counts, and typed-content hashes; a copied database was reopened from a separate directory and queried without access to the original Parquet paths. The Parquet outputs remain authoritative. The builder-created `linkage_review.duckdb` uses local Parquet-backed views and should not be moved independently.

## National audit findings and remaining work

The national database has not been fully rebuilt or independently validated. The 99.9% population-linked goal remains unproven. Candidate names, codes, population similarity, and the presence of coordinates do not independently prove place identity or coordinate applicability.

### Reviewed national identity bridge R4 (2026-09-30)

R4 is a metadata-only correction to the deterministic R3 bridge release. Its selected endpoint provenance now records missing Volume 11 `source_locator` values as typed JSON nulls with an explicit reason and keeps the actual page/line native ID and PDF hash resolvable. All scientific outputs, populations, coordinate claims, and coverage values are unchanged from R3. An independent review verified the pinned source/output hashes, all 965 candidate-to-endpoint bindings, all 965 exact Table 5 settlement-grain bindings, no same-year collisions in connected components, and deduplicated coverage.

The combined identity graph has 1,003 unique temporal edges. R4 added 952 new 2002–2010 pairs and recorded 13 eligible pairs already represented in the parent graph without double-counting them. Identity-linked selected population is 76,546,921/145,155,005 (52.7346%) in 2002; 76,695,785/142,172,038 (53.9458%) in 2010; and 4,146,187/147,182,123 (2.8170%) in 2021. These are identity-linked population shares, not spatial coverage. Coordinate claims are unchanged from R2; this release adds none.

The 965-rule subset is not a probability sample, and the 24-case review validates source-binding implementation rather than estimating national precision. Footnote, competitor, federal-city and other exceptional rows remain held. Table 5 records each matched line as a settlement row with atomic-settlement scope; its broader hierarchy label remains `subject_settlement_or_subject_aggregate`, and 21 rows have layout-only parent context. Those limitations are retained in the review record. See the R4 asset manifest and independent review linked from README.

### Reviewed national checkpoint (2026-09-30)

Source-selection R1 is a versioned population-grain repair. For 2002, it replaces the Moscow-plus-subordinate-settlements aggregate (10,382,754) with five disjoint component rows whose population and sex totals reconcile exactly to that parent; the city-only row is 10,126,424. The selected snapshot adds four rows and preserves the national dataset sum of 145,155,005. For 2010, it replaces the Karelia legacy slice with 800 official-source observations totaling 643,548, a +4,784 change and one additional row. For 2021, selected IDs and values remain unchanged. Independent review and clean reproduction are included in the checkpoint assets.

Reviewed-admissions R2 contains 51 accepted temporal same-place edges and 81 point claims. Among selected snapshot denominators, admitted coordinate population is 537,395/145,155,005 (0.3702%) for 2002, 502,217/142,172,038 (0.3532%) for 2010, and 9,354,610/147,182,123 (6.3558%) for 2021. Identity-linked population shares are 2.6615%, 0.3532%, and 2.8170%; link share and coordinate share are separate measures. All historical point applications are marked `inferred_continuity`; provider-coordinate measurement date is unknown. Four direct Karelia points have captured OSM geometry responses queried as of 2021-10-01, with raw response hashes and point-in-polygon checks. OSM is not a census boundary, and these admissions do not validate a national matching rule.

The 2002 Moscow row-grain problem is handled in the selected R1 snapshot, but the census-specific scope remains distinct from modern administrative boundaries and no temporal identity follows automatically from that migration.

The 2010 NW workbook labels its population column `Всего`, but explicitly warns that values are confidentiality-protected. Direct candidate-key comparisons to final Rosstat Table 5 show many differences; the column remains secondary evidence only. Table 5 is non-exhaustive and has aggregate rows, and St Petersburg data have mixed municipal/locality grain; full-sheet residuals are not allocated to places.

Remaining gates include resolving high-population source-scope conflicts, independently reviewing national identity and coordinate rules, checking historical admin changes and same-name competitors, and reporting population-weighted and row-weighted coverage separately. No map or dashboard should present candidate or unresolved links as certified points.

## Use conditions

The repository stays private. Source rights vary; no blanket license or public redistribution permission is asserted. The national baseline is preserved for comparison, not endorsed as an analytical release.

</details>

</details>

</details>

</details>
