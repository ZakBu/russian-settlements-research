"""Combine source-backed pilot observations; no impact estimation or inferred opening dates."""
from pathlib import Path
import json,re
import pandas as pd
P=Path(__file__).resolve().parent
centres=pd.read_csv(P/'candidate_centres.csv')
neighbours=pd.read_csv(P/'candidate_neighbours.csv')
outcomes=json.loads((P/'outcome_evidence.json').read_text())
history=json.loads((P/'history_evidence.json').read_text())
rows=[]
for i,c in centres.iterrows():
 name=c['name'];g=neighbours.loc[neighbours.centre_id==c.id]
 a=next(e for e in outcomes['evidence_records'] if e.get('indicator')=='Численность населения административного центра' and e['territory'].endswith(name))
 b=next(e for e in outcomes['evidence_records'] if e['document_id']==a['document_id'] and 'observations' in e)
 doc=next(d for d in outcomes['documents'] if d['document_id']==a['document_id'])
 r={'centre':name,'population_census_2002':c.population_2002,'population_census_2010':c.population_2010,'population_census_2021':c.population_2021,'population_centre_2024_thousand_rounded':a['value'],'population_2024_exact_reference_date_known':False,'wb_focus_records_20261021':int(c.commerce_wb20261021_baseline_focus_count),'geodesic20km_neighbours':len(g),'neighbours_inhabited2021':int((g.population_2021>0).sum()),'neighbours_wb_positive':int((g.commerce_wb20261021_baseline_focus_count.fillna(0)>0).sum()),'neighbours_unknown_wb':int(g.commerce_wb20261021_baseline_focus_count.isna().sum()),'official_outcome_url':doc['url'],'population_source_page':a['page_1based']}
 for observation in b['observations']:
  if observation['indicator']=='Объём розничного товарооборота':r['municipal_nominal_retail_billion_rub_'+str(observation['year'])]=observation['value']
 for platform in ['Wildberries','Ozon']:
  events=[e for e in history['events'] if e['settlement']==name and e['platform']==platform]
  r[platform+'_found_presence_by']=min((e['presence_not_later_than'] for e in events),default=None)
 rows.append(r)
pd.DataFrame(rows).to_csv(P/'pilot_comparison.csv',index=False)
u=neighbours.drop_duplicates('id')
assert len(centres)==6 and len(u)==455
assert all(not e['opening_date_confirmed'] for e in history['events'])
wb='commerce_wb20261021_baseline_focus_count'
positive=u.loc[u[wb].fillna(0)>0]
lines=[
'Первый эмпирический пилот: маркетплейсы и локальные центры Нижегородской области',
'24 октября 2026 года. География WB: снимок21.10.2026. Демография: переписи2002/2010/2021; новые официальные сведения2024 отдельно.',
'',
(
'Главный результат: в выбранных шести центрах подтверждены положительные привязки узкого профиля WB. Среди455 разных НП в их двадцатикилометровом окруж'
'ении положительные записи есть у3: Пижмы, Усты и Арьи. Эти три НП сами насчитывали2,5–4,9тыс. жителей в2021 году. В этом скрининге наблюдаемая сеть WB'
' сосредоточена в центрах и более крупных вторичных узлах. Данных о повсеместной самостоятельности мелких деревень здесь пока нет. Полнота WB и сеть Oz'
'on требуют отдельной проверки; по этому срезу нельзя доказывать реальное отсутствие услуг или изменение поездок.'
),
'',
(
'Основание исправлено относительно первой разведки: использована актуальная принятая база населения из релиза sgrt-census-population-20261022-v1, а не '
'локальная ось прежней модели. Архив и каждый объект сверены по хешам. Современный WB присоединён по точным исходным записям переписи2021; старые межго'
'довые группы не перенесены как ключи новой базы. Прежнее районирование не используется.'
),
'',
'Центры: население2021; записи WB типов8/34 в2026; положительные записи WB в окружении / число НП окружения. Радиус20км — наш геодезический скрининг, не зона реального обслуживания.'
]
for r in rows:lines.append(f"{r['centre']}: {int(r['population_census_2021'])}чел.; WB={r['wb_focus_records_20261021']}; окружение={r['neighbours_wb_positive']}/{r['geodesic20km_neighbours']}, неизвестно={r['neighbours_unknown_wb']}.")
lines+=['',f"Суммировать круги нельзя: всего486пар центр–НП и455разных НП, из них356с положительной численностью2021. WB:3с положительной записью,445без принятой записи (это не доказанное отсутствие),7с неизвестной привязкой. Вне координатного скрининга54региональные строки. Все6центров уже имеют WB; необработанной контрольной группы здесь нет.",
'',
(
'Официальные постпереписные данные найдены. Инвестиционные профили на региональном портале отдельно указывают население центра и округа2024, а также му'
'ниципальный товарооборот2023/2024. Численность округлена до0,1тыс., оборот — до0,1млрд рублей. Точная дата внутри2024 неизвестна. Формировать точные т'
'емпы по таким числам и считать номинальный рост оборота физическим ростом спроса нельзя. Ошибки перепечатки зарплат замечены; зарплаты исключены. Сопо'
'ставимость границ, статистического круга торговли и методологии с переписью требует проверки.'
),
'',
(
'История прихода пока не восстановлена. Найдены6сочетаний НП×платформа с датированными пользовательскими свидетельствами в5независимых карточках источн'
'ика. Урень/WB работал по сообщению не позднее17.08.2022, Ветлуга/Ozon —07.05.2023, Шаранга/WB —25.10.2023, Пижма/Ozon —19.05.2024. Это даты найденных '
'сообщений, не открытия; нынешний адрес карточки не доказывает исторический адрес. Две дополнительные строки по Кировской области — Арбаж/Тужа — служат'
' поисковыми кейсами, не независимым контролем для Нижегородской области. Дат открытия и закрытия не подтверждено.'
),
'',
(
'Национальная описательная проверка на142765строгих переписных рядах:7991положительная привязка WB; из них4678имели сокращение населения2002–2021,3303р'
'ост и10неизменность. Это показывает присутствие сети и в давно убывающих местах, но не эффект сети. При строгом пространственном варианте5км, положите'
'льном населении2021 и исключении сдвинутых более1км точек остаётся7971положительная привязка, из них4671со спадом. Поразмерные знаменатели и пропуски '
'— в placement_by_size_and_prior_trend.csv. Весь период2002–2021 не является универсально довоздействующим, поскольку e-commerce существовал раньше.'
),
'',
(
'Новая проверяемая гипотеза: в малолюдной периферийной сети ПВЗ сначала усиливают цепочку центр–вторичные узлы, а при дальнейшем проникновении в неболь'
'шие сёла могут сокращать торговую зависимость от этой цепочки. Предположение о разных этапах требует датировок; текущая карта не доказывает последоват'
'ельности.'
),
'',
(
'Решение по пилоту: оставляем Шарангу как исторически растущий центр, Ветлугу/Тонкино как убывающие, Урень/Тоншаево как системы с вторичными узлами. Эт'
'о рабочие контрасты, не причинные пары treatment/control. Следующий необходимый слой — история присутствия по каждому объекту и независимо наблюдаемая'
' торговая связь деревня–центр. Статистика округа не заменит потоки внутри него.'
),
'',
'Повтор: fetch_population.py получает принятую базу; build_candidate_profiles.py строит геодезический скрининг; describe_placement.py — национальное описание размещения; summarize_pilot.py объединяет результаты. Даты публикаций, URL, страницы и исходные PDF сохранены в outcome_evidence.json и history_evidence.json. Платный доступ и сообщения владельцам ПВЗ/исследователям не использовались. Исходные данные и опубликованный репозиторий не изменялись.'
]
text='\n'.join(lines)+'\n'
text=re.sub(r'(?<=\d)(?=[А-Яа-яЁёA-Za-z])|(?<=[А-Яа-яЁёA-Za-z])(?=\d)', ' ', text)
(P/'pilot_results.txt').write_text(text,encoding='utf-8')
print(pd.DataFrame(rows)[['centre','population_census_2021','population_centre_2024_thousand_rounded','wb_focus_records_20261021','neighbours_wb_positive','geodesic20km_neighbours']].to_string(index=False))
print('Created pilot_comparison.csv and pilot_results.txt')
