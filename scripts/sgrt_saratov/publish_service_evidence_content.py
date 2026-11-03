"""Publish the inspected service-evidence result in the existing atlas."""
import json
import subprocess
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

BODY="## Почему 511 ещё не число систем\n\nДля каждого кандидата теперь сохранены отдельные признаки: сколько жилых поселений направляется к нему за каждой базовой услугой, совпадают ли направления разных функций, сохраняются ли связи при изменении состава источников и насколько дальше находится известная альтернатива. Эти признаки описывают роль пункта, но сами по себе не делают его доказанным центром. [@data:saratov-service-evidence-20261103-v1]\n\nПри исключении исключительно исторических свидетельств среди кандидатов остаются 430 из прежних 511. При этом у **397 из 511** сохраняются все прежние прямые базовые связи. Это разные проверки: пункт может сохраниться среди кандидатов, но получить другое окружение. Ни 430, ни 397 не являются новым числом установленных систем. Источники остаются неполными, а совпадение вариантов не доказывает их истинность.\n\nСравнение исходного и дополненного каталога сохраняет 3 407 из 3 518 прежних прямых базовых связей, или 96,8%. Здесь связь — тройка «жилой НП — пункт назначения — функция»; включены и российские назначения за границей Саратовской области. Это не число людей или поездок. Добавление исторических школьных записей оставляет лишь 2 468 таких связей, или 70,2%: состояние каталога способно сильно изменить географическую картину.\n\n## Проверка на школьном закреплении\n\nВ документе Питерского района на 2025 год разобраны 40 упоминаний населённых пунктов. Из них 12 относятся к собственным школьным местам, семь — к пунктам с нулевой или неизвестной численностью 2021 года, одно осталось без принятого соответствия. Для проверки внешних направлений использованы **20 других жилых поселений**, а не все 40 строк.\n\n:::visual saratov-school-assignment-test\n\nВ исходном каталоге ближайшая известная школа совпала с документированным местом в **2 из 20** случаев. После добавления документированных школьных мест — в **17 из 20**. Сравнение с головной организацией даёт совсем другую картину: 16 совпадений в исходном варианте и лишь одно в дополненном. Если перепутать филиал с головной школой, первоначальная плохая модель могла бы показаться более точной.\n\nЭто не независимая проверка реальных поездок. Из того же распоряжения использованы сведения о местных школьных площадках; направления закрепления не заставляли алгоритм выбирать нужную школу. Документ описывает 2025 год, население — 2021-й, дороги — 2021-й. Численность всех жителей не равна числу учеников.\n\n:::visual saratov-school-documented-relations-map\n\nНа карте показаны документированные внешние отношения поверх уже обобщённых школьных зон. Прямая линия означает отношение между поселением и школьным местом; это не автомобильный маршрут, не линия автобусного подвоза и не граница школьного участка. Цвет различает совпадение с ближайшим известным предложением и расхождение. Все линии проходят внутри принятого контура России.\n\n| Поселение | Закреплённое школьное место | Ближайшее известное место в модели |\n|---|---|---|\n| Доронкин | Питерка | Агафоновка |\n| Первопитерский | Агафоновка | Запрудное |\n| Шлягин | Нива | Агафоновка |\n\nЭти три расхождения не исправлялись принудительным переназначением. Для Доронкина выигрыш модели относительно прежнего направления составляет около 1,8 минуты — слабое основание предпочесть расчёт закреплению. Для остальных необходимо проверить возрастные ступени обучения, фактическое место филиала и подвоз. Наличие школы не означает, что она обучает детей любого возраста.\n\n## Малый пункт может быть важен одной функцией\n\nРоль центра удобнее проверять через альтернативы, сохраняя функции раздельно. Условный опыт исключает все известные предложения одной функции в данном НП и снова обращается к ранее рассчитанным альтернативам. Это не прогноз закрытия учреждения или поведения жителей.\n\n:::visual saratov-service-removal-examples\n\nВ Новозаволжском по переписи 2021 года было 357 жителей. В модели три других жилых пункта направляются туда за школой; после исключения известного школьного предложения медианная добавка к времени составляет 48,8 минуты. По базовой медицине два внешних пункта получают медианную добавку 24,6 минуты. В Перелюбе с 4 575 жителями соответствующие добавки — 28,2 и 6,1 минуты.\n\nЭто показывает, почему нельзя оценить роль пункта только его численностью, числом учреждений или количеством функций. Но большой расчётный ущерб может быть следствием отсутствующих в каталоге альтернатив. Например, торговая добавка Перелюба достигает медианных 55,9 минуты для 42 внешних пунктов. При неполной сельской торговой базе это повод искать магазины, а не объявлять существующую территорию зависимой от единственного узла.\n\n## Граница России: проблема есть и в дорожной сети\n\nПроверены исходные геометрии **124 333 дорожных отрезков** сохранённого окна вокруг шести центров. **23 отрезка** не целиком покрываются используемым контуром России. Их части вне контура имеют суммарную длину **47,6 км**; самый длинный такой фрагмент — 11,7 км.\n\nЭто уже не площадь расширенного рисунка. Однако используемый картографический контур не является точным юридическим описанием границы. Проверено только сохранённое окно, а не вся национальная сеть. Нельзя утверждать, что конкретные прежние кратчайшие пути проходили через эти фрагменты.\n\nДобавлено правило допуска для дальнейшего пересчёта: внутри контура должна находиться вся исходная геометрия дорожного ребра, а не только его концы. Список отрезков сохранён. Прежняя матрица времени ещё не пересчитана по этому правилу, поэтому транспортная часть остаётся незавершённой.\n\n## Экономика, сельское хозяйство и следующий расчёт\n\nВыпуск содержит отдельные экономические описания центра, внешнего окружения и его сельской части. Наблюдаемые работники организаций, скрытые значения и отсутствие данных сохранены раздельно. Это частичная статистика работников, не полное число рабочих мест и не занятость жителей. Муниципальные сельскохозяйственные показатели остаются характеристиками территории; они не распределены искусственно между сёлами.\n\nСледующий расчёт должен показать, какие направления меняются после исключения дорожных фрагментов вне страны. Одновременно проверяются три школьных расхождения и неизвестные местные альтернативы. После этого можно сопоставлять отдельные функциональные роли с полем населения и демографической динамикой. [[saratov-functional-method|Общая методика]] и [[saratov-functional-systems|предыдущий областной расчёт]] сохранены: иерархия и число уровней пока не установлены.\n"
NEW_SOURCE=json.loads("{\"id\":\"NOVOUZENSK_SCHOOL_ASSIGNMENT2026_33\",\"accessed_client_date\":\"2026-11-03\",\"title\":\"Приказ управления образования администрации Новоузенского муниципального района от 20.02.2026 №33 о закреплении территорий\",\"url\":\"https://novuprobr.ucoz.ru/_tbkp/2026/Prikazi/o_zakreplenii_terr-2026.pdf\",\"reading_scope\":\"Прочитано машинное извлечение раздела общеобразовательных организаций на страницах 1–3; дополнительно просмотрен снимок страницы 3. Дошкольная часть не использована. PDF указан как шестистраничный; полного визуального чтения не заявляем.\",\"source_pdf_binary_archived\":false,\"use\":\"Методическое ограничение: административное закрепление за организацией не принимается за доказанное место физического обучения или поездку к головной школе. В поставщиков и матрицу назначения данные этого приказа не добавлены.\",\"cautions\":[\"Новое содержание не является источником прежнего алгоритма.\",\"В индексированной новости 2023 года упомянуты филиалы; при открытии новости получено Tariff Expired. Эта новость не используется как свидетельство текущей работы филиалов.\"]}")
def write(path,x):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def read(path):return json.loads(Path(path).read_text())
def main():
    now=datetime.now(ZoneInfo('Europe/Moscow'));date=now.date().isoformat()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    summary=read('research_context/analysis_snapshots/saratov_service_evidence_20261103.json')
    details=read('research_context/analysis_snapshots/saratov_native_country_details_20261103.json')
    manifest=read('research_context/analysis_snapshots/saratov_service_manifest_20261103.json')
    assert summary['school_assignment_comparison']['external_positive']['preferred_campus_matches']==17
    assert details['not_entirely_inside_count']==23
    assert round(details['outside_length_metres']/1000,1)==47.6
    dataset='saratov-service-evidence-20261103-v1';geo=dataset+'-school-relations'
    datasets=read('web/content/datasets.json')
    if any(d['id'] in {dataset,geo} for d in datasets):raise ValueError('Do not overwrite registered data')
    common={'release':manifest['release'],'sourceCommit':manifest['source_commit'],
        'period':'Население и дороги 2021; школьное закрепление 2025; функции разных лет',
        'limitations':summary['limitations']}
    archive,layer_asset=manifest['assets']
    datasets.extend([{**common,'id':dataset,'title':'Саратов: роли кандидатов, источники, школьные отношения и альтернативы',
        'url':archive['url'],'sha256':archive['sha256'],'scope':'Результаты из сохранённых данных v2, без нового общероссийского моделирования.'},
        {**common,'id':geo,'title':'Питерский район: документированные школьные отношения и совпадение с моделью',
        'url':layer_asset['url'],'sha256':layer_asset['sha256'],'scope':'20 внешних жилых поселений; линии отношений, не дороги и не границы зон.'}])
    write('web/content/datasets.json',datasets)
    layer={'id':'saratov-school-documented-relations','researchId':'sgrt',
        'title':'Школьное закрепление: где ближайшая площадка совпала с документом',
        'description':'Внешние отношения из распоряжения 2025 года для жилых НП по переписи 2021. Прямые линии не изображают маршруты; цвет показывает совпадение с моделью.',
        'datasetId':geo,'adapter':'geojson','geometry':'line',
        'fields':{'id':'id','name':'name','value':'class_index'},'palette':'categorical',
        'valueLabels':{'0':'Совпало с ближайшим известным местом','1':'Расходится с ближайшим известным местом'},
        'unit':'документированное отношение; не число поездок','period':common['period'],
        'evidence':'model','visibility':'published'}
    write('web/content/layers/'+layer['id']+'.json',layer)
    visual={'id':'saratov-school-documented-relations-map','template':'service-links',
        'title':'Где школьное закрепление отличается от ближайшего предложения',
        'caption':'Линия — отношение «поселение — документированная площадка», не маршрут. Цвет показывает совпадение с ближайшим известным предложением; обобщённые школьные зоны оставлены для сравнения.',
        'datasetId':geo,'palette':'categorical','unit':'документированное отношение',
        'mapState':{'research':'sgrt','layers':['saratov-school-enriched-zones',layer['id'],'regions'],'period':'2021','lat':50.6,'lng':47.3,'zoom':8},
        'limitations':['Прикрепление не измеряет поездки; ступени обучения не проверены.','Сведения о наличии школьных площадок взяты из того же документа: это не независимая контрольная выборка.']}
    write('web/content/visuals/'+visual['id']+'.json',visual)
    v={'id':'saratov-school-assignment-test','template':'comparison','title':'Совпадение со школьным закреплением: один и тот же состав 20 внешних жилых НП',
        'caption':'Сравниваются физические школьные места и места головных организаций. Сведения о школьных местах использованы при дополнении каталога; это не независимая проверка реальных поездок.',
        'datasetId':dataset,'palette':'categorical','unit':'совпадений из 20 отношений',
        'categories':['Исходный каталог','С документированными школьными местами'],
        'series':[{'name':'С документированной площадкой','values':[2,17]},
                  {'name':'С местом головной организации','values':[16,1]}],
        'limitations':['Знаменатель 20 исключает собственные школьные места, нулевую или неизвестную численность и непринятое соответствие.']}
    write('web/content/visuals/'+v['id']+'.json',v)
    v2={'id':'saratov-service-removal-examples','template':'comparison',
        'title':'Как меняется известная альтернатива при исключении предложения пункта',
        'caption':'Медианная добавка времени для внешних жилых НП по каждой функции отдельно. Исключены все известные предложения одной функции в выбранном НП; это не прогноз закрытия или переезда.',
        'datasetId':dataset,'palette':'categorical','unit':'модельные минуты',
        'categories':['Новозаволжский','Колено','Перелюб'],
        'series':[{'name':'Школьное предложение','values':[48.8099406946,43.6014088695,28.2349655527]},
                  {'name':'Базовая медицина','values':[24.5824539953,13.5910988766,6.1095356379]}],
        'limitations':['Медианы относятся к разным наборам внешних НП; функции и население между ними не суммируются.','Неизвестная альтернатива не означает отсутствие услуги; доступная вместимость не установлена.']}
    write('web/content/visuals/'+v2['id']+'.json',v2)
    sources=[{'title':'Распоряжение Питерского района от 07.04.2025 №34-р: школьные территории','url':'https://piterka-r64.gosweb.gosuslugi.ru/netcat_files/46/469/34r.docx','referenceId':'PITERSKY_SCHOOL_TERRITORIES_2025_34R','year':2025},
        {'title':'Новый выпуск расчётных описаний ролей и альтернатив','url':'https://github.com/ZakBu/russian-settlements-research/releases/tag/'+manifest['release']},
        {'title':NEW_SOURCE['title'],'url':NEW_SOURCE['url'],'referenceId':NEW_SOURCE['id'],'year':2026},
        {'title':'Численный аудит исходных дорожных геометрий','url':'https://github.com/ZakBu/russian-settlements-research/blob/'+commit+'/research_context/analysis_snapshots/saratov_native_country_details_20261103.json'}]
    material={'id':'saratov-service-evidence','researchId':'sgrt','title':'Кого можно считать местным центром: проверка внешних связей',
        'summary':'Из 20 документированных внешних школьных отношений совпали 17 после добавления филиалов и два в исходном каталоге. У 397 из 511 кандидатов все прежние базовые связи сохраняются без исключительно исторических свидетельств; это ещё не число установленных систем.',
        'kind':'finding','topic':'Роль центров и проверка связей','territory':'Саратовская область; Питерский район',
        'period':common['period'],'publishedAt':date,'updatedAt':date,'visibility':'published','evidence':'model','currency':'current',
        'sourceCommit':commit,'sources':sources,'datasetIds':[dataset,geo,'saratov-school-enriched-zones-20261029-v2-russia-display-v1'],
        'visualIds':[visual['id'],v['id'],v2['id']],'parentId':'saratov-functional-systems','order':20,
        'tags':['data-quality','services','demography'],'body':BODY}
    # Reuse tags already accepted on the parent instead of inventing new ones.
    parent=read('web/content/materials/saratov-functional-systems.json')
    material['tags']=parent.get('tags',[])[:3]
    write('web/content/materials/'+material['id']+'.json',material)
    parent['body']='## Новая проверка внешних связей\n\n[[saratov-service-evidence|Проверены школьное закрепление, устойчивость окружений и известные альтернативы]]. 511 по-прежнему обозначает кандидатов, а не установленное число систем.\n\n'+parent['body']
    parent['updatedAt']=date
    write('web/content/materials/saratov-functional-systems.json',parent)
    write('references/provenance/saratov_school_legal_scope_20261103.json',NEW_SOURCE)
    registry=read('references/sources.json')
    record={'id':NEW_SOURCE['id'],'title':NEW_SOURCE['title'],'year':2026,'publication_type':'official_local_administrative_document',
        'url':NEW_SOURCE['url'],'reading_url':NEW_SOURCE['url'],'reading_status':'primary_machine_extraction_selected_sections_read',
        'read_scope':NEW_SOURCE['reading_scope'],'locator':'Страницы 1–3, раздел общеобразовательных учреждений; снимок страницы 3',
        'use':NEW_SOURCE['use'],'retrieved_date_moscow':date,'observed_journeys':False,'source_pdf_binary_archived':False}
    if any(r['id']==record['id'] for r in registry['records']):raise ValueError('Source ID already exists')
    registry['records'].append(record);registry['record_count']=len(registry['records']);registry['review_date']=date
    write('references/sources.json',registry)
    usage=read('references/usage.json');usage['updated']=date
    usage['uses'].append({'source_id':record['id'],'used_in':['web/content/materials/saratov-service-evidence.json','references/provenance/saratov_school_legal_scope_20261103.json'],
        'purpose':record['use'],'implementation_status':'methodological_scope_warning_not_route_or_supply_input','implementation_paths':[]})
    for u in usage['uses']:
        if u['source_id']=='PITERSKY_SCHOOL_TERRITORIES_2025_34R':
            for p in ['scripts/sgrt_saratov/service_evidence.py','web/content/materials/saratov-service-evidence.json']:
                if p not in u['used_in']:u['used_in'].append(p)
    write('references/usage.json',usage)
    bibliography=read('web/content/materials/literature-bibliography.json')
    articles=[r for r in registry['records'] if r.get('publication_type')=='journal_article']
    abstracts=sum(r.get('reading_status')=='abstract_and_metadata' for r in articles)
    full=sum(r.get('reading_status')=='full_text' for r in articles)
    primary=len(articles)-abstracts
    lead=f"Реестр содержит {len(registry['records'])} источника, включая {len(articles)} научные статьи. Для {primary} статей изучен первичный текст: {full} полностью, {primary-full} — отдельными частями. Для остальных {abstracts} — аннотации и метаданные."
    bibliography['summary']=lead;bibliography['updatedAt']=date
    additions=[]
    for r in registry['records'][145:]:
        additions.append('### '+r['id']+'\n\n'+r.get('authors','')+(' ('+str(r['year'])+'). ' if r.get('year') else '')+'['+r['title']+']('+r['url']+').\n\nОбъём чтения: '+r.get('read_scope',r.get('reading_status','не указан'))+'\n\nИспользование: '+r.get('use','см. реестр использования')+'\n')
    bibliography['body']='## Текущее дополнение реестра\n\n'+lead+'\n\nНиже сохранён обзор на 29 октября; последующие записи приведены отдельно. Исправлен устаревший служебный счётчик: до этого дополнения в массиве было 173 записи при значении record_count 145. Научные результаты от исправления счётчика не меняются.\n\n'+bibliography['body']+'\n\n## Дополнение после 29 октября\n\n'+'\n'.join(additions)
    write('web/content/materials/literature-bibliography.json',bibliography)
    state=read('research_context/current_state.json');state['updated_moscow']=now.isoformat(timespec='seconds')
    sg=state['parts']['sgrt'];sg['status']='saratov_external_service_evidence_assessed_domestic_rerouting_pending'
    sg['summary']='Сохранены 511 кандидатов с отдельными описаниями внешних функций, устойчивости и альтернатив. У 397 все прежние базовые связи сохраняются без исключительно исторических свидетельств. Для 20 документированных внешних школьных отношений совпали 17 после добавления филиалов и два в исходном каталоге; это не независимые наблюдения поездок. В исходном дорожном окне 23 отрезка выходят за принятый контур России, суммарно на 47,6 км. Пересчёт путей с исключением этих геометрий ещё не выполнен.'
    sg['current_task']['status']='service_role_evidence_progress_domestic_routes_and_observed_links_pending'
    sg['service_evidence_20261103']={'summary':'research_context/analysis_snapshots/saratov_service_evidence_20261103.json',
        'report':'web/content/materials/saratov-service-evidence.json','release':manifest['release'],
        'documented_external_school_records':20,'preferred_matches':17,'baseline_matches':2,
        'candidate_all_edges_retained_nonhistorical':397,'native_country_segments_outside':23,
        'native_country_outside_km':details['outside_length_metres']/1000,
        'common_hierarchy_established':False,'old_cost_matrix_rerouted_inside_country':False}
    state['next_steps'][0]='Исключить дорожные геометрии вне России до поиска путей; измерить изменения ближайших услуг и альтернатив, сохраняя прежнюю версию. Проверить три школьных расхождения, ступени обучения и фактический подвоз. Не подменять эту проверку обрезкой карты или новым порогом числа центров.'
    write('research_context/current_state.json',state)
    diary=Path('research_context/diary')/(date+'.md')
    text=diary.read_text() if diary.exists() else '# '+date+'\n'
    text+='\n## '+now.strftime('%H:%M')+' МСК — внешнее обслуживание и проверка школьных отношений\n\nСравнены четыре состава источников, прямые базовые направления и последствия исключения предложения по каждой функции отдельно. У 397 из 511 кандидатов все исходные связи сохраняются без только исторических свидетельств; это не 397 доказанных центров. Для 20 внешних жилых школьных отношений Питерского района совпадений 2 в исходном и 17 в дополненном каталоге. Три расхождения: Доронкин, Первопитерский, Шлягин. Места филиалов взяты из того же документа, поэтому независимой проверкой поездок этот результат не объявляется.\n\nВ сохранённом окне исходных дорог шести центров 23 из 124 333 геометрий не целиком покрыты контуром России; длина частей вне контура 47,6 км, максимальная 11,7 км. Принято правило полной исходной геометрии ребра; старые пути по нему ещё не пересчитаны. Добавлены частичные экономические описания из уже опубликованных таблиц, без выдуманных рабочих мест и распределения муниципального сельского хозяйства по сёлам.\n\nОсновная вычислительная среда недоступна; расчёт выполнен в GitHub Actions по закреплённым публичным таблицам, без нового общероссийского моделирования. Небольшой ZIP 96 296 байт и карта отношений опубликованы, публичные байты сверены. Исправлена относительная передача пути каталога; научные параметры не менялись. Зарегистрирован новый документ Новоузенского района 2026 года как методическое свидетельство различия организации и места обучения, не как новые направления поездок. Исправлен устаревший счётчик библиографии: 174 записи, 82 научные статьи; объём чтения каждого сохранён. Следующий шаг — пересчёт путей внутри страны и проверка школьных контрпримеров.\n'
    diary.write_text(text)
    for name in ['README.md','AI_START_HERE.md']:
        p=Path(name);text=p.read_text()
        p.write_text('> Новое продолжение Саратовского пилота: [проверка внешних школьных отношений, роли кандидатов и альтернатив](https://zakbu.github.io/russian-settlements-research/materials/saratov-service-evidence/). Совпали 17 из 20 документированных внешних направлений после добавления филиалов. Найдены дорожные фрагменты вне принятого контура; пути ещё требуют пересчёта.\n\n'+text)
    Path('sgrt/saratov/SERVICE_EVIDENCE_20261103.md').write_text('# Проверка внешнего обслуживания\n\n'+material['summary']+'\n\n'+BODY+'\n\nДанные: '+archive['url']+'\n')
    print(json.dumps({'source_count':len(registry['records']),'journal_articles':len(articles),'primary_text_articles':primary,'full_text_articles':full,'diary':str(diary)},ensure_ascii=False))

if __name__=='__main__':main()
