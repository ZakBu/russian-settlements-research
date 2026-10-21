#!/usr/bin/env python3
"""New bottom-up cycle07 review draft; exact bound results, never old ranks promoted."""
from pathlib import Path
import argparse,importlib.util,json,hashlib,datetime,shutil
import pandas as pd,numpy as np
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'delivery/cycle06_tools/v3/build_scientific_report.py'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def resolve(p):
 p=Path(p);return p if p.is_absolute() else ROOT/p
def read(p):return pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p)
def at(j,keys):
 for k in keys:j=j[k]
 return j
def pin(spec,watches):
 p=resolve(spec['path']);assert p.is_file() and sha(p)==spec['sha256'],f'Unbound or changed input:{p}';watches[str(p)]=spec['sha256'];return p
REQUIRED=['units','types','trajectory','hierarchy_protocol','hierarchy_receipt','hierarchy_admission','typology_receipt','typology_admission','source2010_changes','source2010_receipt','coordinate_changes','coordinate_admission','knees','bootstrap','prior_extents','atlas_receipt','word_text','bibliography','analysis_status','functional_case_receipt']
def verify(c):
 assert c['family']=='cycle07_bottomup' and c['release']=='REVIEWDRAFT' and c['scientific_final_allowed'] is False
 assert set(REQUIRED)<=set(c['artifacts']);paths={};watched={}
 assert sha(OLD)==c['generic_renderer_sha256'];watched[str(OLD)]=sha(OLD)
 for role,spec in c['artifacts'].items():
  p=pin(spec,watched);paths[role]=p
  if spec.get('reference_only'):
   assert role in ['word_text','bibliography','method_note'],'Numeric data cannot be reference_only';continue
  if role=='analysis_status':
   state=json.loads(p.read_text());assert state['status'] in ['PENDING_NOT_REPORTED','COMPUTED_CYCLE07_SOURCE_BOUND'];continue
  manifest=pin(spec['manifest'],watched);assert spec['sha256'] in manifest.read_text(),f'Artifact not in manifest:{role}'
  if spec.get('independent_review'):
   assert role.endswith('_admission') or role=='functional_case_receipt'
   review=json.loads(p.read_text());assert spec.get('required_values')
   for pointer,expected in spec['required_values']:assert at(review,pointer)==expected
   continue
  if spec.get('computed_draft'):
   assert role.startswith('map_') or role=='atlas_receipt','Draft permission restricted to actual derived graphics';continue
  admission=pin(spec['admission'],watched);r=json.loads(admission.read_text())
  for pointer,expected in spec['admission']['required_values']:
   assert at(r,pointer)==expected,f'Admission status:{role}'
  reachable=admission.read_text()
  for link in spec.get('binding_chain',[]):
   assert link['sha256'] in reachable;lp=pin(link,watched);reachable+='\n'+lp.read_text()
  assert spec['sha256'] in reachable or spec['manifest']['sha256'] in reachable,f'Unrelated admission:{role}'
 for m in c['maps']:
  assert m['role'] in paths and m['caption'] and m['purpose'] in ['hierarchy','types','coverage','extent','objective','city'];assert paths[m['role']].suffix=='.png'
 assert {'hierarchy','types','coverage'}<=set(m['purpose'] for m in c['maps'])
 # Actualderived maps must bind actualselected unit+type bytes or exact manifest chain.
 atlas=paths['atlas_receipt'].read_text();assert c['artifacts']['units']['sha256'] in atlas and c['artifacts']['types']['sha256'] in atlas
 state=json.loads(paths['analysis_status'].read_text())
 if state['status']=='COMPUTED_CYCLE07_SOURCE_BOUND':
  assert 'analysis_metrics' in paths and 'cycle07' in str(paths['analysis_metrics'])
  assert c['artifacts']['units']['sha256'] in paths['analysis_receipt'].read_text()
 return paths,watched

def prepare(c,paths,out,mod):
 C=mod.Content;fmt=mod.fmt;u=read(paths['units']);ty=read(paths['types']);ev=read(paths['trajectory'])
 for d in [u,ty]:assert d.unit_id.is_unique and d.unit_id.notna().all()
 assert set(u.unit_id)==set(ty.unit_id) and ty.primary_type_id.notna().all();assert ev.unit_id.isin(u.unit_id).all()
 viewcol=c['view_column'];assert viewcol in u and c['primary_view_id'] in set(u[viewcol]);u=u.copy();u['view_label']=u[viewcol].astype(str)
 assert ty.unit_role.notna().all();extra=[x for x in ty if x not in u or x=='unit_id'];u=u.merge(ty[extra],on='unit_id',validate='one_to_one')
 primary=u[u[viewcol]==c['primary_view_id']];sourcechanges=read(paths['source2010_changes']);coord=read(paths['coordinate_changes']);knees=read(paths['knees']);boot=read(paths['bootstrap']);prior=read(paths['prior_extents'])
 assert sourcechanges.id.is_unique and coord.id.is_unique
 assert set(boot.candidate_cap)==set(knees.candidate_cap) and boot.groupby('candidate_cap').size().eq(50).all(),'All50outcomes ofalltestedcaps required'
 assert c['view_semantics'] and set(u[viewcol].astype(str))==set(c['view_semantics']),'Everyactualview requires explicit operational/empirical meaning'
 assert all(x['kind'] in ['operational_forest','empirical_resolution','atomic_source'] for x in c['view_semantics'].values())
 registry_cols=[x for x in ['unit_id','view_label','unit_role','center_scope','core_id','unit_name','primary_type_id','primary_type_name','complete_profile_id','structural_class','trajectory_class','trajectory_all_periods','classification_confidence','source_quality_flags','primary2010_population_share','protected_secondary2010_population_share','population2010_known_denominator','2010_missing_population_count'] if x in u]
 u[registry_cols].to_csv(out/'complete_units_and_types.csv.gz',index=False,compression='gzip')
 ev.to_csv(out/'trajectory_all_objects_periods.csv.gz',index=False,compression='gzip')
 for d,name in [(knees,'all_candidate_knee_decisions'),(boot,'all50_bootstrap_outcomes')]:d.to_csv(out/(name+'.csv'),index=False)
 counts=u.groupby(['view_label','unit_role','primary_type_id','primary_type_name'],dropna=False).size().reset_index(name='n_units');counts.to_csv(out/'full_type_counts.csv',index=False)
 content=C();content.title('Сельско-городские районы тяготения России\nНовая bottom-up иерархия и полная измеренная типология')
 content.p('ЧЕРНОВИК ДЛЯ НАУЧНОГО ОБСУЖДЕНИЯ · REVIEWDRAFT. Данные и расчёты закреплены SHA; окончательная научная приёмка исходной концепции не заявляется. Документ предназначен для обсуждения с научным руководителем. Количество технических проверок не является процентом выполнения Word.')
 content.h('1. Что получено в этом проходе')
 summary=u.groupby(['view_label','unit_role'],dropna=False).agg(n_units=('unit_id','size'),n_types=('primary_type_id','nunique')).reset_index();content.t(summary,'Фактические представления/роли; население и единицы не суммируются между альтернативными охватами.')
 content.p(f'Основное представление: {c["primary_view_id"]}. В нём {fmt(len(primary))} записей всех ролей, полные измеренные типы присвоены каждой записи. Территориальные союзы и переносимые атомы ниже разделены. Район с внешним контекстным ядром и обычными сельскими членами остаётся территориальной единицей; неизвестно собственное население его ядра, а не сама принадлежность сельских членов. Операционный дорожный охват не назван эмпирической географической ступенью.')
 content.h('2. Исходная концепция и принятое уточнение')
 content.p('Единица исследования — собственное ядро и связанная с ним сельская зона, их совместная демография и функциональный контекст. По указанию пользователя круговая калибровка массы центра по его же предсказанному окружению исключена: собственные Mi фиксированы до делимитации. Новый запрос требует bottom-up объединения целых детей и типа для каждой реально построенной единицы. Девять сюжетов Word используются для интерпретации, а не как обязательный фильтр, оставляющий большинство единиц без типа.')
 content.h('3. Источники: новые первичные сведения2010 года')
 content.p(f'Добавлено {fmt(len(sourcechanges))} новых первичных источниковых подтверждений относительно предыдущей базы. Это не обязательно {fmt(len(sourcechanges))} новых чисел: часть подтверждает прежнее значение. Национальная таблица и полный региональный источник Адыгеи приняты отдельными независимыми проверками. Прочерки не превращены в нули, спорные идентичности не включены. Подтверждение идентичности НП2010 не доказывает неизменность границ к2021.')
 if 'region' in sourcechanges:content.t(sourcechanges.groupby('region',dropna=False).size().reset_index(name='новые_первичные_подтверждения'))
 content.p('Полный журнал применённых изменений и старые значения закреплены исходным overlay-манифестом; новые доказательства качества и реальные изменения чисел — разные показатели.')
 content.h('4. Координаты и географический кадр')
 content.p(f'В новую координатную версию допустимы {fmt(len(coord))} независимых источниковых точек. Их происхождение/точность и дата измерения не выдуманы. Ранее удержанные одноимённые спорные точки остаются вне допуска до отдельного доказательства; близость к дороге не использована для выбора удобной координаты.')
 content.p('Исходная наблюдаемая точка позволяет локализовать НП, но не является точным полигоном его застройки или сельско-городской функциональной территории. Ненаблюдаемые координаты, дороги и роли отражаются отдельными счётчиками, а не исчезают из знаменателя.')
 content.h('5. Как строится новая иерархия')
 proto=json.loads(paths['hierarchy_protocol'].read_text());content.p('Низовой состав образуется из датированных реальных поселений/поставщиков. Далее допускаются только объединения целых дочерних единиц. Для каждого кандидата проверяется прямой дорожный охват всех наблюдаемых членов из существующего ядра; цепь коротких соседних связей не заменяет эту проверку. Масса не переоценивается через новый состав района.')
 content.p('Силы связей — условный модельный потенциал по собственным функциям/массе и дорожному времени, а не наблюдаемая маятниковая миграция. Для двух федеральных контекстных якорей действует отдельно объявленный масштабный прокси массы: он не становится собственным наблюдением населения города. Взвешенная модульность агрегируется по всем исходным междочерним связям; выбранное положительное допустимое слияние и изменение цели сохраняются. Это наша инженерная адаптация, не буквальная процедура Райсиха/OECD.')
 content.p('Райсих2020 разделяет морфологическое ядро и функциональную периферию, ограничивает длинные цепочки объединений. OECD/EC требует реальных долей занятых, направляющихся к городу, и однократной проверки городских ядер. Без OD наша модель показывает потенциальное тяготение; она не выдаётся за наблюдаемый рынок труда. Плотностная/морфологическая непрерывность не выводится из центроидов НП.')
 content.h('6. Фактический выбор разрешений и неудачные исходы')
 show=[x for x in ['candidate_cap','knee_status','retained','median_ari','p10_ari','knee_fraction_iqr'] if x in knees];content.t(knees[show],'Все испытанные охваты; отсутствие перегиба и неустойчивость не удалены.')
 content.t(boot.groupby(['candidate_cap','status'],dropna=False).size().reset_index(name='n_replicates'),'Все50повторов каждого охвата, включая недоступные/неудачные. ARI с отсутствующим знаменателем не равен нулю.')
 content.p('Если устойчивые эмпирические разрезы не выделены, итог сохраняется как явно названный ограниченный лес при операционном охвате. Это содержательный результат, не повод присвоить старые ранги или продолжить объединения до желаемого числа уровней. Минимальное число пригодных повторов и строгое50/50сравнение берутся из замороженного протокола, не выбираются по красивой карте.')
 content.h('7. Протяжённость: прежний checkpoint и новая защита')
 oldcols=[x for x in ['level','geodesic_max_km','all_member_direct_max_minutes','all_member_direct_missing'] if x in prior]
 if oldcols:content.t(prior[oldcols].sort_values('geodesic_max_km',ascending=False).head(5),'Пять наиболее протяжённых прежних систем: историческая диагностика, не новая иерархия и не пять отобранных успешных случаев.')
 ext=[x for x in ['max_member_direct_minutes','max_member_geodesic_km','n_member_direct_known_unknown'] if x in u]
 if ext:
  tab=u.groupby('view_label')[ext].agg(['max','median']).reset_index();tab.columns=[' · '.join(x).strip(' ·') if isinstance(x,tuple) else x for x in tab.columns];content.t(tab,'Новые измерения охвата на полном составе; дорожные минуты и прямые километры не смешиваются.')
 content.p('Старые системы могли растягиваться через цепочки связей. В новых выходах допустимость каждого объединения проверяется на всём объединённом составе. Исторический максимум не является нормативом для подгонки нового результата; отсутствующий маршрут отдельно от превышения предела.')
 content.h('8. Три объекта демографии и три периода')
 content.p('Для центрального объекта, внешних статистически сельских членов и целого рассматриваются2002–2010,2010–2021,2002–2021. Нулевой начальный знаменатель оставляет темп неопределённым. Неизвестная сельская роль запрещает объявлять частичную сельскую сумму полной. Прочие поставщики внутри союза не исключаются из сельской зоны только потому, что они тоже являются provider-seeds.')
 table=ev.groupby(['object','period','state'],dropna=False).size().reset_index(name='n_unit_periods');content.t(table,'Все единицы, объекты и периоды; таблица не объявляет девять объект-периодов независимыми наблюдениями.')
 content.h('9. Полная измеренная типология')
 content.p('Каждый первичный тип — наблюдаемая структура и допустимое сочетание демографических состояний. Неполная траектория сохраняет структурный тип и явный признак недоступности, а не фиктивный нулевой рост. Функциональный контекст — отдельные положительные свидетельства; отсутствие записи в каталоге не доказывает физического отсутствия функции.')
 content.t(u.groupby(['view_label','unit_role','classification_confidence'],dropna=False).size().reset_index(name='n_units'),'Различная полнота измерений не скрыта обязательной выдачей типа.')
 content.p(f'Все полные коды/названия и частоты — full_type_counts.csv ({fmt(len(counts))} строк). В тексте ниже приведены наиболее частые коды основного представления; это явно объявленная выборка для чтения, остальные не переименованы в «прочее».')
 content.t(counts[counts.view_label==str(c['primary_view_id'])].sort_values(['n_units','primary_type_id'],ascending=[False,True]).head(12))
 content.h('10. Девять интерпретаций Word и границы объяснения')
 names=['Пригородные','Региональные аграрно-сервисные узлы','Плодородный пояс','Периферийный баланс','Дачные/рекреационные','Этнические анклавы','Нечернозёмная депрессия','Старопромышленные','Северные ресурсные']
 content.t(pd.DataFrame({'сюжет_Word':range(1,10),'краткий_смысл':names,'статус':['Интерпретация; не причинный класс']*9}))
 content.p('Сходство демографической комбинации не подтверждает механизм: дачную миграцию, этнокультурные факторы, сокращение добычи или переработку. Для этнических/ресурсных объяснений нужны собственные прямые свидетельства; они не выводятся из названия региона. В одном измеренном типе возможны несколько сюжетов Word либо отсутствие уверенной аналогии.')
 content.h('11. Проверяемые функциональные случаи')
 content.p('Выполнен конечный posthoc-поиск по Псебаю, Ипатову и Ровенькам Белгородской области. Датированная продукция и сообщённый производственный адрес поддерживают документальное описание переработки Ипатова/Ровенек; это не утверждение о проверке предприятия на месте. Сообщение Роспотребнадзора о фальсифицированной партии доказывает наличие маркировки изготовителя, а не безусловно происхождение партии. Независимый акт отбора и сведения о трудоустройстве рассматриваются раздельно.')
 content.p('Отчёт Псебая2021 подтверждает открытие «Доброцена» на Промышленной, пунктаOZON на Советской и работу администрации. Гипс/лесопромышленность не превращены в агропереработку. Крупный формат торговли по этим документам остаётся неизвестным. Эти случаи — аннотации, не обучение типов, не независимая валидация52меток и не причина задерживать измеренный классификатор.')
 content.h('12. Качество2010 и внешние контексты')
 qcols=[x for x in ['primary2010_population_share','protected_secondary2010_population_share','2010_missing_population_count','unknown_nonadditive_central_population_slots2010'] if x in u]
 if qcols:
  tab=u.groupby('view_label')[qcols].median().reset_index();content.t(tab,'Медианы по единицам, не суммарные доли населения страны. Индивидуальные знаменатели сохранены в полном реестре.')
 content.p('Знаменатель источниковых долей — известное неотрицательное аддитивное население членов. Нулевой/отсутствующий знаменатель остаётсяNA. Собственное население контекстных ядер Москвы/Петербурга неизвестно: сумма сельских/обычных членов не доказывает полноту целого города с системой. В территориальное население не подставляется население субъекта федерации.')
 content.h('13. Аграрный, природный и сервисный контекст')
 content.p('Муниципальные сведения об урожайности/землях и региональный природный контекст не названы собственной производительностью каждого НП. Повтор одного муниципального показателя у множества НП не увеличивает число независимых источников. Исторические коды/интервалы проходят собственную проверку; недостоверные присоединения удержаны. Реестр функций и дорожные времена измеряют доступный источниковый кадр, а не исчерпывающую национальную экономику.')
 content.h('14. Количественная проверка объяснений')
 state=json.loads(paths['analysis_status'].read_text())
 if state['status']=='PENDING_NOT_REPORTED':content.p('Новая регрессионная семья ещё не рассчитана/не принята: результатов в этом черновике НЕТ. Старые коэффициенты и OOF cycle06 сюда не перенесены. Раздел будет заменён новой версией после фактического анализа на новых единицах.')
 else:
  metrics=read(paths['analysis_metrics']);metrics.to_csv(out/'new_cycle07_analysis_metrics.csv',index=False);assert 'comparison_family' in metrics
  keys=[x for x in ['comparison_family','scenario','outcome','level','model','n','groups','train_r2','cv_r2','cv_rmse'] if x in metrics];content.t(metrics[keys]);content.p('Сравниваются только одинаковые исходные строки и folds внутри объявленной семьи. Рост trainR² не означает улучшения на отложенных регионах. Отрицательный эффект/неудачный gate сохранён. Типы, включающие демографический исход, не используются как независимая причина того же исхода.')
 content.h('15. Карты и точность границ')
 content.p('Карта устанавливает принадлежность точки НП, но не мелкую функциональную границу между НП. Схематические связи с ядром не дороги и не наблюдаемые потоки; сплошные выпуклые оболочки/Voronoi не объявлены реальными районами. Полные составы, типы и роли доступны в таблицах. Дальние члены не обрезаны ради убедительного городского фрагмента.')
 for m in c['maps']:content.image(paths[m['role']],m['caption'])
 content.h('16. Что можно обсуждать с научным руководителем')
 content.p('На этих данных можно воспроизводимо сравнить ограниченные потенциальные районы, их структуру и доступные траектории. Предварительный вывод должен выдержать собственное источниковое качество и устойчивость состава. Наблюдаемые трудовые/сервисныеOD, полностью сопоставимые исторические территории, точная национальная специализация и географические границы по-прежнему не выдумываются.')
 content.p('Следующий научный шаг — оценить содержательность реально полученных объединений и типовых сочетаний, затем уточнять конкретные источниковые разрывы. Техническая успешность сборки не является окончательным одобрением Word; окончание проекта этим черновиком не объявлено.')
 content.h('17. Источники, код и литература')
 content.p(paths['bibliography'].read_text());content.p('Делимитация: РайсихА.Э.(2020),Демографическое обозрение7(2),54–96; Dijkstra,Poelman,Veneri(2019),OECDRegionalDevelopmentWorkingPapers2019/11; ApplyingtheDegreeofUrbanisation2021,раздел7.2. Точная первичная литература и границы заимствования — literature/cycle07_delimitation/. Собственные алгоритмические решения помечены как адаптации.')
 return content,summary

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',required=True);ap.add_argument('--output',required=True);ap.add_argument('--stage',choices=['preregister','build'],default='preregister');a=ap.parse_args();c=json.loads(Path(a.inputs).read_text());out=Path(a.output);assert not out.exists(),'Fresh delivery required';paths,watch=verify(c);out.mkdir(parents=True)
 binding={'status':'PREREGISTERED_ACTUAL_SOURCE_BOUND_REVIEWDRAFT' if a.stage=='preregister' else 'COMPUTED_REVIEWDRAFT_PENDING_REPORT_REVIEW','code_sha256':sha(__file__),'generic_renderer_sha256':sha(OLD),'config_sha256':sha(a.inputs),'input_sha256':watch,'scientific_final_allowed':False,'word_approval':None,'family':'cycle07_bottomup'}
 (out/'report_input_binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n')
 if a.stage=='preregister':print(out);return
 sp=importlib.util.spec_from_file_location('frozen_cycle06_generic_render',OLD);mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod)
 # Readability-only adaptation of accepted generic renderer; original file stays immutable.
 import inspect
 source=inspect.getsource(mod.render).replace('fontSize=6,leading=8','fontSize=8,leading=11')
 exec(compile(source,'cycle07_readable_generic_render','exec'),mod.__dict__)
 binding['generic_readability_override']='RuSmall font6/8→8/11 only; no scientific calculations changed'
 binding['derived_generic_render_sha256']=hashlib.sha256(source.encode()).hexdigest()
 content,summary=prepare(c,paths,out,mod);mod.render(content,out,'SGRT_CYCLE07_REVIEWDRAFT')
 brief=mod.Content();brief.title('СГРТ: записка научному руководителю · Cycle07');brief.p('Предварительный исход на зафиксированных источниках. Полный отчёт и атлас сопровождают эту записку. Окончательная научная приёмка не заявлена.');brief.t(summary);brief.p('Новые представления — bottom-up потенциальные районы либо явно обозначенные операционные ограниченные леса, не старые четыре ранга. Полный измеренный тип есть у каждой записи; функциональные механизмы Word остаются отдельными проверяемыми интерпретациями. Источники2010 и координаты исправлены по новым принятым свидетельствам. Неизвестность состава/качества/полноты сохраняется.');mod.render(brief,out,'SUPERVISOR_BRIEF_CYCLE07')
 assert all(sha(p)==v for p,v in watch.items()) and sha(__file__)==binding['code_sha256'] and sha(a.inputs)==binding['config_sha256'],'Input/code/config changed during report'
 shutil.copyfile(a.inputs,out/'report_inputs.json');binding['files']={str(p.relative_to(out)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()};(out/'report_receipt.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n');print(out)
if __name__=='__main__':main()
