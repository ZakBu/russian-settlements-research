"""Check actual final artifacts and write the independent construct review."""
from pathlib import Path
import json,hashlib
import pandas as pd,pyarrow.parquet as pq
R=Path(__file__).resolve().parent;B=R.parents[1];N=R.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def ck(name,value,basis):checks.append({'name':name,'pass':bool(value),'basis':basis})
core=json.loads((N/'core/MASTER_AUDIT.json').read_text());sc=json.loads((N/'screening/SCREENING_AUDIT.json').read_text());pa=json.loads((N/'places/AUDIT.json').read_text());ra=json.loads((R/'FUNCTIONAL_REFERENCE_AUDIT.json').read_text())
axis=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet',columns=['id']);master=pd.read_parquet(N/'core/feature_master.parquet',columns=['id']);profile=pd.read_parquet(N/'screening/support_point_profiles.parquet',columns=['id','baseline_function_diversity','external_catchment_or_support_centrality_proven']);ref=pd.read_parquet(R/'national_functional_reference.parquet',columns=['id','actual_external_centrality_demonstrated','baseline_listed_function_diversity'])
ck('national_axis_preserved',len(master)==142570 and master.id.is_unique and set(master.id)==set(axis.id),'core/feature_master.parquet native UID readback')
ck('screening_all_UID_preserved',len(profile)==142570 and profile.id.is_unique and set(profile.id)==set(axis.id),'screening/support_point_profiles.parquet')
ck('reference_all_UID_preserved',len(ref)==142570 and ref.id.is_unique and set(ref.id)==set(axis.id),'critic/national_functional_reference.parquet')
ck('actual_final_places_loaded',sc.get('places_loaded') and core.get('places_module'),'screening+core audits')
ck('eleven_primary_groups',len(ra['FUNCTIONS'])==11 and 'trade_access' in ra['FUNCTIONS'],'critic/FUNCTIONAL_REFERENCE_AUDIT.json')
ck('reference_baseline_matches_final_screening',ref.baseline_listed_function_diversity.equals(profile.baseline_function_diversity),'row-order protected source counts')
for owner,audit in [('core',core),('screening',sc)]:
    for path,value in audit['inputs'].items():
        wanted=value['sha256'] if isinstance(value,dict) else value
        ck(owner+'_live_input_'+path,sha(B/path)==wanted,path)
ck('all_scientific_reference_checks_pass',ra['status']=='PASS' and ra['checks_passed']==ra['checks_total'],'critic/FUNCTIONAL_REFERENCE_AUDIT.json')
ck('no_external_centrality_from_count',not ref.actual_external_centrality_demonstrated.any() and not profile.external_catchment_or_support_centrality_proven.any(),'explicit false evidence flags')
ck('Places_actual648242_preserved',pa['source_objects']==648242 and pa['status']=='PASS','places/AUDIT.json')
ck('name_only_PVZ_not_established',len(pd.read_csv(R/'name_signal_counterexamples.csv'))>=2,'critic/name_signal_counterexamples.csv original public POI ID+taxonomy')
ag=json.loads((N/'validation/independent_sources/agriculture/AUDIT.json').read_text());ck('agriculture_external_raw_review_available',ag.get('status')=='PASS','validation/independent_sources/agriculture/AUDIT.json; critic authored agro module, this is external audit')
summary=pd.read_csv(R/'source_bundle_comparison.csv');confidence=pd.read_csv(R/'confidence_sensitivity.csv');grouping=pd.read_csv(R/'trade_pickup_grouping_sensitivity.csv');sensitivity=pd.read_csv(R/'reference_sensitivity.csv');geo=pd.read_csv(R/'geography_and_size.csv');cases=pd.read_csv(R/'positive_negative_cases.csv')
baseline=summary[summary.bundle.eq('baseline')].iloc[0];legal=summary[summary.bundle.eq('legal_native')].iloc[0];cond=summary[summary.bundle.eq('conditional_without_wb_relaxation')].iloc[0];wbcond=summary[summary.bundle.eq('conditional_with_wb_relaxation')].iloc[0];physical=summary[summary.bundle.eq('physical_baseline')].iloc[0]
rr=geo[geo.bundle.eq('baseline')&geo.dimension.eq('region')].sort_values('physical_new_any_vs_legal',ascending=False).head(8)
def table(frame,cols):
    lines=['| '+' | '.join(cols)+' |','|'+'|'.join(['---']*len(cols))+'|']
    for row in frame[cols].itertuples(index=False,name=None):lines.append('| '+' | '.join(str(v) for v in row)+' |')
    return '\n'.join(lines)
verdict='PASS_IN_NATIONAL_DESCRIPTIVE_SCOPE' if all(c['pass'] for c in checks) else 'BLOCKED_FINAL_ARTIFACT_CONSISTENCY'
report={'status':verdict,'checks_passed':sum(c['pass'] for c in checks),'checks_total':len(checks),'checks':checks,'review_scope':'national source integration,source grouping,descriptive residuals;not validation of real catchments','independence_disclosure':'author of agricultural linkage;national construct/source critique performed separately;agricultural numerical independence rests on external statistician raw audit','blocking_claim':'none of these counts identifies actual external service,causal function transfer or proven support-centre rank','inputs':{str(p.relative_to(B)):sha(p) for p in [N/'core/MASTER_AUDIT.json',N/'screening/SCREENING_AUDIT.json',N/'places/AUDIT.json',R/'FUNCTIONAL_REFERENCE_AUDIT.json']}}
(R/'CHECKS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
text=f'''# Критическая проверка национального функционального результата

Статус: **{verdict}**. Проверено{report['checks_passed']}/{report['checks_total']} требований на фактических итоговых файлах, а не на плане. Автор этой проверки реализовал аграрную связку; её численная независимая проверка принадлежит отдельному статистику, прочитавшему полный исходный Parquet. Настоящий обзор независимо проверяет общую исследовательскую конструкцию и новые сравнения источников.

## Главный вывод

Указание сначала массово связать данные со всей осью выполнено:142570 UID сохранены в master, screening и новом сравнении. Локальные кейсы не подменяют этот результат. Получен непустой национальный каталог свидетельств и измерена зависимость кандидатной сетки от источников, правил объединения и качества POI. **Фактические районы внешнего обслуживания этим расчётом не выделены.** Это не повод отрицать сделанные измерения и не основание назвать любые многофункциональные пункты доказанными СГРТ.

Окончательный core содержит{core['columns']} полей. Число полей не является числом независимых измерений: муниципальные признаки повторяются у НП; юридические и физические публикации могут описывать одну организацию, а даты различаются.

## Непустой национальный результат

{table(summary,['bundle','positive_listed_points','multiple_groups','reference_available','above_reference_median'])}

Положительное юридическое свидетельство семи групп есть у{int(legal.positive_listed_points)} НП; физические публикации выбранной таксономии при принятой адресной связи — у{int(physical.positive_listed_points)}. Объединение сWB даёт{int(baseline.positive_listed_points)} пунктов с принятым свидетельством хотя бы одной группы и{int(baseline.multiple_groups)} с несколькими широкими группами. Условная связка без ослабления названийWB даёт{int(cond.positive_listed_points)} и{int(cond.multiple_groups)}, а дополнительное ослаблениеWB —{int(wbcond.positive_listed_points)} и{int(wbcond.multiple_groups)}. Эти сценарии не смешиваются и не называются открытием новых реальных учреждений.

География наибольшего добавления физического свидетельства к юридическому каталогу:

{table(rr,['stratum','points','physical_new_any_vs_legal','physical_adds_any_function_vs_legal','baseline_new_multi_vs_legal'])}

Это география дополнения конкретных источников. Она не измеряет полноту реальной сферы обслуживания по регионам. Отсутствие принятой записи и неизвестность относятся к данным, а не к отсутствию жизни/функций в поселении.

## Что реально проверила критика и как устранены артефакты

1. В текущей фазе был обнаружен отсутствующий исходныйpart00014:421757 доступных строк против648242 в квитанции. Владелец сохранил повреждённый файл отдельно, восстановил его, добавил атомарную запись/fsync и холодное чтение. Финальные исходники и аудит снова согласованы. До этого согласования слой не считался завершённым.
2. permanently_closed не должен становиться положительным современным функциональным сигналом. Каталог сохраняет все публикации; основной функциональный счётчик исключает явно закрытые. Почти все operating_status неизвестны: это не подтверждённая действующая сеть.
3. Источник прямо различаетconfidence и operating_status. Confidence0 исключается из положительного сигнала, а значение0.8 не интерпретируется как80% вероятности. Межпровайдерская строгая сопоставимость шкалы не установлена. По официальной документации порог является относительным фильтром качества. Источник: https://docs.overturemaps.org/guides/places/#confidence-score (прочитано19.10.2026).
4. ОбнаруженныеWB-name публикации с категориейshopping вместе с независимымWB-перечнем могли сделать одинПВЗ двумя содержательными функциями. Основной профиль объединяетretail+pickup→trade_access; аналогичноbank+ATM иpost+mailbox. Сохраняются12-раздельный и brand-retail-filtered варианты;14 исходных POI-категорий и7 группRFSD не уничтожены.
5. В8 публичных POI с точным токеномOzon/ОЗОН исходная категория указывает медицину, фитнес или клуб. Название само по себе не устанавливаетПВЗ. Проверяемые IDs/категории/координаты/SHA — `name_signal_counterexamples.csv`. Это существование контрпримеров, не оценка доли ложных брендов и не независимая проверка аффилиации каждого объекта.
6. Проверяется согласованность живых хэшей входов, core и screening: исправление исходного слоя должно перейти в общий master и последующий расчёт. Прежняя корректная квитанция не удостоверяет новый файл.

## Группировка и уверенность источника

{table(grouping,['semantic_variant','positive_UID','multiple_groups_UID','reference_available','above_reference_median'])}

{table(confidence,['threshold','bundle','positive_listed_UID','multiple_groups_UID','reference_available','above_recomputed_reference_median','above_fixed_primary_reference_median'])}

При повышенииconfidence остаётся подмножество опубликованных функций. Пропавшая из сценария запись не означает закрытие услуги. Набор сравнения тоже меняется: поэтому отдельно показаны остатки относительно пересчитанной и неизменной первоначальной медианы. Остатки не обязаны монотонно падать: их знаменатель/эталон может изменяться. Вероятностные доверительные интервалы не изображаются как средство исправления неизвестного охвата источников.

## Что означает новый описательный остаток

Для каждого источникового варианта и каждого пункта с положительным свидетельством число представленных широких групп сравнивается с медианой **среди пунктов с положительными свидетельствами того же варианта**, в том же регионе и диапазоне людности2021. Основной минимумreferenceN=30; при нехватке региональных наблюдений используется общероссийский диапазон той же людности. Если и он мал — результатNA. Население0/NA и отсутствие положительного свидетельства не получают искусственный нулевой остаток.

Опубликованы альтернативные границы размерных диапазонов иreferenceN=60 в `reference_sensitivity.csv`. Остаток является относительным разнообразием **наблюдаемых публикаций**, а не мощностью сверх местного спроса и не доказанной внешней центральностью. Эталон включает сам описываемый пункт; это описательная референтная статистика, не обученная модель/отложенная валидация. Людность2021 и публикации2025–2026 разновременны. Нормировка не устраняет региональную селективность регистрации иPOI.

## Отрицательные случаи и пределы интерпретации

В `positive_negative_cases.csv` сохранены конкретные пункты выше/ниже собственного размерного эталона и случаи положительной публикации при населении0 в2021. Пункт ниже медианы может быть единственным незаменимым поставщиком одной жизненно важной услуги; пункт выше медианы может обслуживать только себя либо иметь ошибочную/избыточную публикацию. Ни первый не признаётся ненужным, ни второй не признаётся опорным автоматически.

Конкретный отрицательный пример — городКоммунар Ленинградской области,25793жителя2021: baseline содержит одну широкуюtrade_access, а условная связь —7групп, включая образование и медицину. Отрицательный описательный остаток−5 здесь не доказывает утрату шести реальных функций или отсутствие опорности: он чувствителен к идентичности исходных записей. UID `np3:p-LhnKirDV_v-5toCw1SuLxV_fTVDKu7egUwIhwNkT0` позволяет проверить результат без путаницы с одноимённым малым посёлком. Положительный пример — Жуковка Московской области:710жителей,8групп при медиане1 среди сопоставимых положительных публикаций. Это гипотеза пригородной концентрации, совместимая с внешней ролью, но не наблюдение поездок и не установленный район обслуживания.

Медицинская широкая группа объединяет различные уровни и виды помощи; образовательная — различные уровни обучения. Их Boolean-присутствие не устанавливает взаимозаменяемость больницы/ФАПа или школы/колледжа. Рынок и обычная розница сохранены раздельными исходными категориями; широкаяtrade_access не проверяет гипотезу вытеснения вещевого рынка маркетплейсами. ИсторияRFSD остаётся историей юридических свидетельств, а не реальных открытий/закрытий и перехвата поездок.

## Соответствие литературной конструкции

Прочитан ранее подготовленный `anchor_research_20261019/literature/RECOMMENDED_METHOD.md`, где разделены наблюдаемая функция, потенциальный охват, внешнее обслуживание и незаменимость. Национальное описание соответствует первому контуру; относительное разнообразие — новая проверяемая гипотеза возможной внешней роли. Из литературы не следует, что сумма категорий, положительный остаток или близость дают границуСГРТ. Следующий содержательный шаг — раздельные функциональные уровни, независимые внешние связи и проверка альтернатив обслуживания; текущий каталог этого шага не подменяет.

## Воспроизведение

```bash
python national_integration_20261019/critic/build_functional_reference.py
python national_integration_20261019/critic/finalize_review.py
```

Первый запуск допускается только по завершённомуscreening сPlaces=True и неизменными входнымиSHA. Все142570строк сохраняются. Код, таблицы источников, географии, параметрической чувствительности,confidence и контрольные суммы переданы независимому статистику для отдельного воспроизведения. Результаты его независимой проверки не подменяются авторскими инвариантами этого нового расчёта.
'''
(R/'REVIEW.md').write_text(text)
assert verdict=='PASS_IN_NATIONAL_DESCRIPTIVE_SCOPE',[c for c in checks if not c['pass']]
print(verdict,report['checks_passed'],'/',report['checks_total'])
