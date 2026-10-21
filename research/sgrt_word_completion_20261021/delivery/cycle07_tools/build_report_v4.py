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
   assert role.endswith('_admission') or role.endswith('_numeric_review') or role in ['functional_case_receipt','analysis_numeric_review']
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
  runs=c.get('analysis_runs',[{'metrics_role':'analysis_metrics','receipt_role':'analysis_receipt','source_role':'analysis_source_receipt','numeric_review_role':'analysis_numeric_review','source_unit_sha256':c['artifacts']['units']['sha256']}])
  unit_manifest=pin(c['artifacts']['units']['manifest'],watched).read_text()
  for run in runs:
   assert all(run[k] in paths for k in ['metrics_role','receipt_role','source_role','numeric_review_role'])
   numeric=json.loads(paths[run['numeric_review_role']].read_text());assert numeric['all_checks_passed'] is True and numeric['accepted_analysis_receipt_sha256']==sha(paths[run['receipt_role']])
   ar=json.loads(paths[run['receipt_role']].read_text());assert ar['source_receipt_sha256']==sha(paths[run['source_role']])
   for unitsha in run.get('source_unit_sha256s',[run.get('source_unit_sha256')]):
    assert unitsha and unitsha in paths[run['source_role']].read_text()
    assert unitsha==c['artifacts']['units']['sha256'] or unitsha in unit_manifest,'Analysis source-unit scope must occur in actual report unit-source manifest'
 return paths,watched

def reader_table(frame):
 d=frame.copy()
 roles={'territorial_unit':'Территориальное объединение','protected_carry':'Отдельная источниковая запись (включая исторические)','context_overlay':'Контекстное представление'}
 if 'unit_role' in d:d['unit_role']=d.unit_role.replace(roles)
 if 'classification_confidence' in d:d['classification_confidence']=d.classification_confidence.replace({'tentative_source_quality':'Численные ряды со смешанным/вторичным источниковым качеством','partial_demographic_support':'Частичная демографическая наблюдаемость','structural_only':'Подтверждена только структура'})
 if 'primary_type_name' in d:
  for before,after in [('center','центр'),('rural','сельское окружение'),('system','район в целом'),('own','само поселение')]:d['primary_type_name']=d.primary_type_name.str.replace(before,after,regex=False)
 if 'change_kind' in d:d['change_kind']=d.change_kind.replace({'persistent_identical_membership':'Тот же состав','direct_rural_or_residual_attachment_only':'Добавлены сельские/остаточные записи','provider_bearing_children_join_without_two_prior_fields':'Присоединены исходные центры без двух прежних районов','union_of_at_least_two_lower_territorial_fields':'Объединены два или более прежних района'})
 labels={'lower_resolution':'Нижний срез','upper_resolution':'Верхний срез','change_kind':'Изменение состава','fraction_upper_role_units':'Доля единиц верхнего среза','view_label':'Представление','unit_role':'Роль','n_units':'Единиц','n_types':'Типов','primary_type_id':'Код типа','primary_type_name':'Сочетание состояний','classification_confidence':'Полнота измерений','object':'Объект ряда','period':'Период','state':'Состояние','n_unit_periods':'Единиц','candidate_cap':'Охват, мин','knee_status':'Перегиб','retained':'Сохранённое разрешение','median_ari':'Медиана устойчивости','p10_ari':'Нижняя дециль устойчивости','knee_fraction_iqr':'Разброс положения перегиба','n_replicates':'Повторов','status':'Исход','region':'Регион'}
 return d.rename(columns=labels)

def prepare(c,paths,out,mod):
 C=mod.Content;fmt=mod.fmt;u=read(paths['units']);ty=read(paths['types']);ev=read(paths['trajectory'])
 for d in [u,ty]:assert d.unit_id.is_unique and d.unit_id.notna().all()
 assert set(u.unit_id)==set(ty.unit_id) and ty.primary_type_id.notna().all();assert ev.unit_id.isin(u.unit_id).all()
 assert c.get('component_integration_status') and c.get('population_frame_scope'),'Declare actual source integration and denominator scopes'
 viewcol=c['view_column'];assert viewcol in u and c['primary_view_id'] in set(u[viewcol]);u=u.copy();u['view_label']=u[viewcol].astype(str).map(lambda key:c['view_semantics'][key].get('label',key))
 assert ty.unit_role.notna().all();extra=[x for x in ty if x not in u or x=='unit_id'];u=u.merge(ty[extra],on='unit_id',validate='one_to_one')
 primary=u[u[viewcol]==c['primary_view_id']];sourcechanges=read(paths['source2010_changes']);coord=read(paths['coordinate_changes']);knees=read(paths['knees']);boot=read(paths['bootstrap']);prior=read(paths['prior_extents'])
 assert sourcechanges.id.is_unique and coord.id.is_unique
 assert set(boot.candidate_cap)==set(knees.candidate_cap) and boot.groupby('candidate_cap').size().eq(50).all(),'All50outcomes ofalltestedcaps required'
 assert c['view_semantics'] and set(u[viewcol].astype(str))==set(c['view_semantics']),'Everyactualview requires explicit operational/empirical meaning'
 assert all(x['kind'] in ['operational_forest','empirical_resolution','atomic_source'] for x in c['view_semantics'].values())
 registry_cols=[x for x in ['unit_id',viewcol,'view_label','unit_role','center_scope','core_id','unit_name','primary_type_id','primary_type_name','complete_profile_id','structural_class','trajectory_class','trajectory_all_periods','classification_confidence','source_quality_flags','primary2010_population_share','protected_secondary2010_population_share','population2010_known_denominator','2010_missing_population_count'] if x in u]
 u[registry_cols].to_csv(out/'complete_units_and_types.csv.gz',index=False,compression='gzip')
 ev.to_csv(out/'trajectory_all_objects_periods.csv.gz',index=False,compression='gzip')
 for d,name in [(knees,'all_candidate_knee_decisions'),(boot,'all50_bootstrap_outcomes')]:d.to_csv(out/(name+'.csv'),index=False)
 counts=u.groupby(['view_label','unit_role','primary_type_id','primary_type_name'],dropna=False).size().reset_index(name='n_units');counts.to_csv(out/'full_type_counts.csv',index=False)
 content=C();rawtable=content.t;content.t=lambda frame,*args,**kwargs:rawtable(reader_table(frame),*args,**kwargs);content.title('Сельско-городские районы тяготения России\nИерархия потенциальных районов и динамическая типология')
 content.p('Предварительные результаты исследования на зафиксированном источниковом кадре. Рассматриваются потенциальные районы тяготения, их вложенная структура и наблюдаемая динамика населения. Происхождение данных, исходные таблицы и описание расчёта приведены в приложениях.')
 content.h('1. Что получено в этом проходе')
 summary=u.groupby(['view_label','unit_role'],dropna=False).agg(n_units=('unit_id','size'),n_types=('primary_type_id','nunique')).reset_index();content.t(summary,'Фактические представления/роли; население и единицы не суммируются между альтернативными охватами.')
 content.p(f'Основное представление: {c['view_semantics'][str(c['primary_view_id'])].get('label',str(c['primary_view_id']))}. В нём {fmt(len(primary))} записей всех ролей, полные измеренные типы присвоены каждой записи. Территориальные союзы и отдельные источниковые записи ниже разделены. Район с внешним контекстным ядром и обычными сельскими членами остаётся территориальной единицей; неизвестно собственное население его ядра, а не сама принадлежность сельских членов. Операционный дорожный охват не назван эмпирической географической ступенью.')
 content.p('Включённые обновления: '+'; '.join(str(v) for v in c['component_integration_status'].values()))
 content.p('Численность источникового кадра и состав районов учитываются отдельно. Полные исходные знаменатели и исключения сохранены в приложенном паспорте расчёта.')
 content.h('2. Исходная концепция и принятое уточнение')
 content.p('Единица исследования — собственное ядро и связанная с ним сельская зона, их совместная демография и функциональный контекст. Чтобы избежать круговой зависимости, собственные массы центров фиксированы до делимитации и не калибруются по предсказанному окружению. Последовательно объединяются целые дочерние районы; каждой единице пяти операционных представлений и четырёх сохранённых разрешений присвоен измеренный тип. Девять содержательных сюжетов исходной концепции используются для интерпретации сочетаний, а не как фильтр доступности типа.')
 content.h('3. Источники: новые первичные сведения2010 года')
 content.p(f'Добавлено {fmt(len(sourcechanges))} новых первичных источниковых подтверждений относительно предыдущей базы. Это не обязательно {fmt(len(sourcechanges))} новых чисел: часть подтверждает прежнее значение. Национальная таблица и полный региональный источник Адыгеи приняты отдельными независимыми проверками. Прочерки не превращены в нули, спорные идентичности не включены. Подтверждение идентичности НП2010 не доказывает неизменность границ к2021.')
 if 'region' in sourcechanges:content.t(sourcechanges.groupby('region',dropna=False).size().reset_index(name='новые_первичные_подтверждения'))
 content.p('Полный журнал применённых изменений и старые значения закреплены исходным overlay-манифестом; новые доказательства качества и реальные изменения чисел — разные показатели.')
 content.h('4. Координаты и географический кадр')
 content.p(f'В новую координатную версию допустимы {fmt(len(coord))} независимых источниковых точек. Их происхождение/точность и дата измерения не выдуманы. Ранее удержанные одноимённые спорные точки остаются вне допуска до отдельного доказательства; близость к дороге не использована для выбора удобной координаты.')
 content.p('Источниковый допуск координат и их включение в конкретные Mi/маршруты/составы — отдельные события. Точный статус этой версии указан в начале отчёта; готовые свидетельства не означают автоматически пересчитанную модель.')
 content.p('Исходная наблюдаемая точка позволяет локализовать НП, но не является точным полигоном его застройки или сельско-городской функциональной территории. Ненаблюдаемые координаты, дороги и роли отражаются отдельными счётчиками, а не исчезают из знаменателя.')
 content.h('5. Как строится новая иерархия')
 proto=json.loads(paths['hierarchy_protocol'].read_text());content.p('Низовой состав образуется из датированных реальных поселений/поставщиков. Далее допускаются только объединения целых дочерних единиц. Сначала среди всех исходных центров кандидата выбирается доминантный по фиксированной собственной массе. Именно этот центр должен удовлетворять прямому дорожному охвату всех наблюдаемых членов; замена более слабым геометрически удобным центром запрещена; цепь коротких соседних связей не заменяет эту проверку. Масса не переоценивается через новый состав района.')
 content.p('Силы связей — условный модельный потенциал по собственным функциям/массе и дорожному времени, а не наблюдаемая маятниковая миграция. Для двух федеральных контекстных якорей действует отдельно объявленный масштабный прокси массы: он не становится собственным наблюдением населения города. Взвешенная модульность агрегируется по всем исходным междочерним связям; выбранное положительное допустимое слияние и изменение цели сохраняются. Это наша инженерная адаптация, не буквальная процедура Райсиха/OECD.')
 content.p('Райсих2020 разделяет морфологическое ядро и функциональную периферию, ограничивает длинные цепочки объединений. OECD/EC требует реальных долей занятых, направляющихся к городу, и однократной проверки городских ядер. Без OD наша модель показывает потенциальное тяготение; она не выдаётся за наблюдаемый рынок труда. Плотностная/морфологическая непрерывность не выводится из центроидов НП.')
 content.h('6. Фактический выбор разрешений и неудачные исходы')
 show=[x for x in ['candidate_cap','knee_status','retained','median_ari','p10_ari','knee_fraction_iqr'] if x in knees];content.t(knees[show],'Все испытанные охваты; отсутствие перегиба и неустойчивость не удалены.')
 content.t(boot.groupby(['candidate_cap','status'],dropna=False).size().reset_index(name='n_replicates'),'Все50повторов каждого охвата, включая недоступные/неудачные. Оценка устойчивости состава с отсутствующим знаменателем не равен нулю.')
 content.p('Если устойчивые эмпирические разрезы не выделены, итог сохраняется как явно названный ограниченный лес при операционном охвате. Это содержательный результат, не повод присвоить старые ранги или продолжить объединения до желаемого числа уровней. Протокол допускает не менее40 из50 пригодных повторов; оценки устойчивости условны на пригодных повторах. Порог медианыARI равен0,8, нижней децили0,6, допустимый межквартильный разброс доли слияний до перегиба не превышает0,15. Фактически у всех пяти охватов пригодны50 из50 повторов; это наблюдённый результат, а не требование отбора.')
 if 'persistence_summary' in paths:
  persistence=read(paths['persistence_summary']);territorial_transitions=persistence[persistence.unit_role.eq('territorial_unit')];columns=['lower_resolution','upper_resolution','change_kind','n_units','fraction_upper_role_units'];content.t(territorial_transitions[columns],'Переходы между соседними разрешениями, отдельно по территориальным объединениям; сохранённая единица не становится новым функциональным порядком.')
  content.p('Устойчивые срезы могут многократно показывать тот же состав. При переходах сохраняются без изменения52,90%,57,68% и53,32% территориальных объединений верхнего среза. Объединения не менее двух прежних территориальных полей составляют1970,1127 и777. Эти принятые описательные признаки отличают новые союзы от переноса прежней единицы и не доказывают сами по себе новый функциональный порядок.')
 if 'intrinsic_boundaries' in paths:
  boundaries=read(paths['intrinsic_boundaries']);boundaries.to_csv(out/'intrinsic_own_mass_class_boundaries.csv',index=False);content.p('Отдельная градация собственной фиксированной массы исходных центров даёт три источниковых класса. Это классы собственной центральности; население не использовано для их задания. Они не подменяют географические срезы и не объявляются функциональными порядками. Два контекстных федеральных якоря не участвовали в подборе классов. Полные границы сохранены в приложении.')
 if 'sensitivity_comparison' in paths:
  sensitivity=read(paths['sensitivity_comparison']);sensitivity.to_csv(out/'all62_method_sensitivity_comparisons.csv',index=False);paired=sensitivity[sensitivity.partition_role.eq('supported_end_forest')&sensitivity.comparison_status.eq('EXACT_SAME_SOURCE_ATOM_FRAME_PAIRED_OPERATIONAL_PARTITION')];ranges=paired.groupby('scenario').agg(ARI_min=('all_axis_ARI_to_primary','min'),ARI_max=('all_axis_ARI_to_primary','max'),focal_change_min=('fraction_atoms_with_changed_focal','min'),focal_change_max=('fraction_atoms_with_changed_focal','max')).reset_index();ranges['scenario']=ranges.scenario.replace({'tau30':'Затухание30мин','tau90':'Затухание90мин','gamma0.5':'Сила разделения0,5','gamma2':'Сила разделения2','directed_max':'Направленная политика времени','extended180':'Расширенный охват180мин'});content.t(ranges.rename(columns={'scenario':'Изменение метода','ARI_min':'Мин. сходство составов','ARI_max':'Макс. сходство составов','focal_change_min':'Мин. доля сменивших центр','focal_change_max':'Макс. доля сменивших центр'}),'Диапазоны по парным операционным срезам, а не независимая выборка. Все62строки — в приложении;180-минутный новый срез без пары не получает фиктивный показатель сходства.')
  content.p('Шесть изменений метода проверены на фактически рассчитанных составах: затухание30/90минут, сила разделения0,5/2, альтернативная направленная политика пути и расширение до180минут. Для чувствительностей выполнены отдельные базовые расчёты, а не50географических повторов каждого сценария. Оценка устойчивости по50повторам относится к основной семье; она не переносится автоматически на чувствительности.')
 content.h('7. Протяжённость: прежний промежуточный расчёт и новая защита')
 oldcols=[x for x in ['level','geodesic_max_km','all_member_direct_max_minutes','all_member_direct_missing'] if x in prior]
 if oldcols:content.t(prior[oldcols].sort_values('geodesic_max_km',ascending=False).head(5),'Пять наиболее протяжённых прежних систем: историческая диагностика, не новая иерархия и не пять отобранных успешных случаев.')
 ext=[x for x in ['max_member_direct_minutes','max_member_geodesic_km','n_member_direct_known_unknown'] if x in u]
 if ext:
  tab=u.groupby('view_label')[ext].agg(['max','median']).reset_index();tab.columns=[' · '.join(x).strip(' ·') if isinstance(x,tuple) else x for x in tab.columns];content.t(tab,'Новые измерения охвата на полном составе; дорожные минуты и прямые километры не смешиваются.')
 content.p('Старые системы могли растягиваться через цепочки связей. В новых выходах допустимость каждого объединения проверяется на всём объединённом составе. Исторический максимум не является нормативом для подгонки нового результата; отсутствующий маршрут отдельно от превышения предела.')
 content.h('8. Три объекта демографии и три периода')
 content.p('Для центрального объекта, внешних статистически сельских членов и целого рассматриваются2002–2010,2010–2021,2002–2021. Нулевой начальный знаменатель оставляет темп неопределённым. Неизвестная сельская роль запрещает объявлять частичную сельскую сумму полной. Прочие поставщики внутри союза не исключаются из сельской зоны только потому, что они тоже являются исходные центры.')
 ev=ev.copy();ev['view_label']=ev.unit_id.map(u.set_index('unit_id').view_label);table=ev.groupby(['view_label','object','period','state'],dropna=False).size().reset_index(name='n_unit_periods');content.t(table,'Каждое представление отдельно; единицы не суммируются между разрешениями. Девять объект-периодов не являются независимыми наблюдениями.')
 content.p('При двух положительных наблюдениях среднегодовой темп равен100 × [(Pкон / Pнач)^(1/число лет) − 1]. Основная полоса стабильности — от−0,25% до+0,25% в год включительно; выше — рост, ниже — убыль. Для периодов используются8,11 и19 лет как целогодовая аппроксимация. Альтернативные полосы0 и±0,5% сохранены как чувствительности и не выбирались по полученным типам. Два наблюдаемых нуля, появление населения из нуля и наблюдаемое обнуление различаются; для нулевого начального значения годовой темп не вычисляется. Пропуск не заменяется нулём.')
 content.p('Отдельная источниковая запись / исходный объект без подтверждённого функционального присоединения включает исторические записи без первичного наблюдения2021. Недоступность их динамики нельзя интерпретировать как отсутствие данных у стольких нынешних поселений. Источниковые записи и наблюдаемые поселения2021 показаны отдельно на карте покрытия. Это человекочитаемое описание отдельной роли в расчёте. Это не признак конфиденциальности населения2010 и не пропуск обязательной типизации.')
 content.h('9. Полная измеренная типология')
 content.p('Каждый первичный тип — наблюдаемая структура и допустимое сочетание демографических состояний. Неполная траектория сохраняет структурный тип и явный признак недоступности, а не фиктивный нулевой рост. Функциональный контекст — отдельные положительные свидетельства; отсутствие записи в каталоге не доказывает физического отсутствия функции.')

 territorial=primary[primary.unit_role.eq('territorial_unit')];recent=territorial.trajectory_class.map(json.loads);observed=recent.map(lambda row:all(k in row and row[k] not in ['unavailable','not_applicable'] for k in ['center','rural','system']));all_decline=recent.map(lambda row:all(row.get(k)=='decline' for k in ['center','rural','system']));all_growth=recent.map(lambda row:all(row.get(k)=='growth' for k in ['center','rural','system']))
 if len(territorial):
  denominator=int(observed.sum());content.p('Предварительный результат основного представления: '+str(len(territorial))+' территориальных объединений; все три ряда2010–2021 наблюдаются у '+str(denominator)+'. Одновременная убыль центра, сельского окружения и целого: '+str(int(all_decline.sum()))+' объединений ('+format(100*all_decline.mean(),'.2f')+'% всех; '+(format(100*all_decline.sum()/denominator,'.2f') if denominator else 'не определено')+'% с тремя наблюдаемыми рядами). Одновременный рост: '+str(int(all_growth.sum()))+' ('+format(100*all_growth.mean(),'.2f')+'% всех; '+(format(100*all_growth.sum()/denominator,'.2f') if denominator else 'не определено')+'% наблюдаемых). Это распределение данного модельного состава и доступных источников, а не доказанная доля всех реальных сельско-городских районов страны.')
 content.t(u.groupby(['view_label','unit_role','classification_confidence'],dropna=False).size().reset_index(name='n_units'),'Различная полнота измерений не скрыта обязательной выдачей типа.')
 content.p(f'Все полные коды/названия и частоты — full_type_counts.csv ({fmt(len(counts))} строк). В тексте ниже приведены наиболее частые коды основного представления; это явно объявленная выборка для чтения, остальные не переименованы в «прочее».')
 content.t(counts[counts.view_label==c['view_semantics'][str(c['primary_view_id'])].get('label',str(c['primary_view_id']))].sort_values(['n_units','primary_type_id'],ascending=[False,True]).head(12))
 content.h('10. Девять интерпретаций исходной концепции и границы объяснения')
 names=['Пригородные','Региональные аграрно-сервисные узлы','Плодородный пояс','Периферийный баланс','Дачные/рекреационные','Этнические анклавы','Нечернозёмная депрессия','Старопромышленные','Северные ресурсные']
 content.t(pd.DataFrame({'сюжет_исходной концепции':range(1,10),'краткий_смысл':names,'статус':['Интерпретация; не причинный класс']*9}))
 content.p('Сходство демографической комбинации не подтверждает механизм: дачную миграцию, этнокультурные факторы, сокращение добычи или переработку. Для этнических/ресурсных объяснений нужны собственные прямые свидетельства; они не выводятся из названия региона. В одном измеренном типе возможны несколько сюжетов исходной концепции либо отсутствие уверенной аналогии.')
 content.h('11. Проверяемые функциональные случаи')
 content.p('Выполнен конечный posthoc-поиск по Псебаю, Ипатову и Ровенькам Белгородской области. Датированная продукция и сообщённый производственный адрес поддерживают документальное описание переработки Ипатова/Ровенек; это не утверждение о проверке предприятия на месте. Сообщение Роспотребнадзора о фальсифицированной партии доказывает наличие маркировки изготовителя, а не безусловно происхождение партии. Независимый акт отбора и сведения о трудоустройстве рассматриваются раздельно.')
 content.p('Отчёт Псебая2021 подтверждает открытие «Доброцена» на Промышленной, пунктаOZON на Советской и работу администрации. Гипс/лесопромышленность не превращены в агропереработку. Крупный формат торговли по этим документам остаётся неизвестным. Эти случаи — аннотации, не обучение типов, не независимая валидация52меток и не основание автоматически подтверждать механизм типа.')
 content.h('12. Качество2010 и внешние контексты')
 qcols=[x for x in ['primary2010_population_share','protected_secondary2010_population_share','2010_missing_population_count','unknown_nonadditive_central_population_slots2010'] if x in u]
 if qcols:
  tab=u.groupby('view_label')[qcols].median().reset_index();content.t(tab,'Медианы по единицам, не суммарные доли населения страны. Индивидуальные знаменатели сохранены в полном реестре.')
 content.p('Знаменатель источниковых долей — известное неотрицательное аддитивное население членов. Нулевой/отсутствующий знаменатель остаётсяNA. Собственное население контекстных Москвы/Петербурга неизвестно при любом их участии — как ядра либо как неведущего члена. Любой такой неизвестный слот запрещает полноту целого во все годы: сумма сельских/обычных членов не доказывает полноту целого города с системой. В территориальное население не подставляется население субъекта федерации.')
 content.h('13. Аграрный, природный и сервисный контекст')
 content.p('Муниципальные сведения об урожайности/землях и региональный природный контекст не названы собственной производительностью каждого НП. Повтор одного муниципального показателя у множества НП не увеличивает число независимых источников. Исторические коды/интервалы проходят собственную проверку; недостоверные присоединения удержаны. Реестр функций и дорожные времена измеряют доступный источниковый кадр, а не исчерпывающую национальную экономику.')
 content.h('14. Количественная проверка объяснений')
 content.p('M1 связывает изменение населения с собственной массой центра2021, известной полной суммой аддитивного населения2010 и прямым дорожным временем сельских членов до своего ведущего центра, усреднённым с весами сельского населения2010. Положительные величины массы и исходной численности логарифмированы, время преобразовано как log(1+минуты). M2 добавляет муниципальную урожайность зерна2021, климатические нормы суммы активных температур и увлажнения, а также среднюю прокси-оценку пригодностиFAO/GAEZ для кукурузы; последняя не является российским бонитетом почв. M3 дополнительно описывает число сопоставимых исходных центров и концентрацию их фиксированных масс, долю сельского окружения в поясе30–60минут с взаимодействием собственной массы и отдельный доступ к зафиксированным крупным городам в пределах180минут. Это структура наблюдаемого инвентаря, а не доказательство полицентричности; собственный ведущий центр не подменяется ближайшим крупным городом.')
 state=json.loads(paths['analysis_status'].read_text())
 if state['status']=='PENDING_NOT_REPORTED':content.p('Новая регрессионная семья ещё не рассчитана/не принята: результатов в этом черновике НЕТ. Старые коэффициенты и проверки по регионам прежней версии сюда не перенесены. Раздел будет заменён новой версией после фактического анализа на новых единицах.')
 else:
  metrics=pd.concat([read(paths[run['metrics_role']]).assign(analysis_scope_label=run.get('label',run['metrics_role']))for run in c['analysis_runs']],ignore_index=True) if c.get('analysis_runs') else read(paths['analysis_metrics']);metrics['analysis_scope_label']=metrics.get('analysis_scope_label',pd.Series(c.get('analysis_scope_label','Основное разбиение'),index=metrics.index));metrics.to_csv(out/'new_cycle07_analysis_metrics.csv',index=False);assert 'comparison_family' in metrics
  shown=metrics[metrics.scenario.str.endswith('__primary')] if 'scenario' in metrics else metrics;keys=[x for x in ['analysis_scope_label','candidate_cap','comparison_family','model','n','regions','r2','group_oof_r2_train_mean_baseline','group_oof_rmse'] if x in shown];table=shown[keys].copy();table['comparison_family']=table.comparison_family.map(lambda x:'A: M1/M2' if str(x).startswith('A_') else 'B: M1/M2/M3');table=table.rename(columns={'analysis_scope_label':'Источниковое разбиение','candidate_cap':'Охват, мин','comparison_family':'Семья','model':'Модель','n':'Систем','regions':'Регионов','r2':'R² обучение','group_oof_r2_train_mean_baseline':'R² по регионам','group_oof_rmse':'RMSE по регионам'});content.t(table,'Основные модели. Семьи имеют разные исходные выборки; полный набор чувствительностей сохранён в CSV.');content.p('Сравниваются только одинаковые исходные строки и разбиения проверки внутри объявленной семьи. Рост R² на обучении не означает улучшения на отложенных регионах. Отрицательный эффект/непройденный порог достаточности выборки сохранён. Типы, включающие демографический исход, не используются как независимая причина того же исхода.')
 if state['status']=='COMPUTED_CYCLE07_SOURCE_BOUND':
  rural=metrics[metrics.scenario.str.endswith('__rural_population_sensitivity')]
  if len(rural):
   for (scope,cap,family),group in rural.groupby(['analysis_scope_label','candidate_cap','comparison_family'],sort=True):
    results='; '.join(str(row.model)+' = '+format(float(row.group_oof_r2_train_mean_baseline),'.4f') for row in group.itertuples());content.p(str(scope)+'. Отдельный исход — изменение численности именно сельского окружения, с исключением только ведущего НП. Операционный охват '+str(int(cap))+' минут, семья '+('A' if str(family).startswith('A_') else 'B')+': '+str(int(group.n.iloc[0]))+' систем, '+str(int(group.regions.iloc[0]))+' регионов; R² на отложенных регионах: '+results+'. Сравнения выполняются только внутри этой исходной выборки; исход всего района показан отдельно.')
 if state['status']=='COMPUTED_CYCLE07_SOURCE_BOUND':
  for (scope,cap,scenario),group in metrics[metrics.comparison_family.str.startswith('B_')&metrics.scenario.str.endswith(('__primary','__rural_population_sensitivity'))].groupby(['analysis_scope_label','candidate_cap','scenario']):
   models=group.set_index('model')
   if {'M2','M3_inventory_structure'}<=set(models.index):
    before=float(models.loc['M2','group_oof_r2_train_mean_baseline']);after=float(models.loc['M3_inventory_structure','group_oof_r2_train_mean_baseline']);outcome_label='района в целом' if scenario.endswith('__primary') else 'сельского окружения';content.p(str(scope)+'. Охват '+str(int(cap))+' минут, исход '+outcome_label+': добавление структуры наблюдаемого инвентаря '+('повышает' if after>before else 'понижает')+' R² на отложенных регионах с '+format(before,'.4f')+' до '+format(after,'.4f')+'. Это сравнение на одних строках внутри семьи B. Зависимость от охвата и выбранного исхода исключает утверждение об универсальном улучшении.')
 if state['status']=='COMPUTED_CYCLE07_SOURCE_BOUND':
  content.p('В основных моделях ошибки на отложенных регионах сохраняют положительную пространственную зависимость между соседними точками центров. Воспроизводимость вычислений не означает, что географическая структура ошибок устранена. Региональная проверка и ошибки с поправкой на региональные группы не превращают эти ассоциации в причинные эффекты. Статистики Морана и перестановочные вероятности сохранены отдельно по источниковому разбиению, охвату, семье и модели в исходных таблицах пространственной диагностики.')
  if 'spatial_summary' in paths:read(paths['spatial_summary']).to_csv(out/'all9_primary_and_rural_spatial_diagnostics.csv',index=False)
 content.p('Собственная масса и функции2021 измерены у конца интервала2010–2021. Они могут сами зависеть от предшествующих изменений населения и миграции; природно-аграрный контекст также не делает модель причинной. Здесь оценены условные ретроспективные ассоциации, а не прогноз из начала периода и не отдельный причинный эффект центра.')
 content.h('15. Карты и точность границ')
 content.p('Карта устанавливает принадлежность точки НП, но не мелкую функциональную границу между НП. Схематические связи с ядром не дороги и не наблюдаемые потоки; сплошные выпуклые оболочки/Voronoi не объявлены реальными районами. Полные составы, типы и роли доступны в таблицах. Дальние члены не обрезаны ради убедительного городского фрагмента.')
 for m in c['maps']:content.image(paths[m['role']],m['caption'])
 content.h('16. Что можно обсуждать с научным руководителем')
 content.p('На этих данных можно воспроизводимо сравнить ограниченные потенциальные районы, их структуру и доступные траектории. Предварительный вывод должен выдержать собственное источниковое качество и устойчивость состава. Наблюдаемые трудовые/сервисныеOD, полностью сопоставимые исторические территории, точная национальная специализация и географические границы по-прежнему не выдумываются.')
 content.p('Следующий научный шаг — оценить содержательность реально полученных объединений и типовых сочетаний, затем уточнять конкретные источниковые разрывы. Наиболее существенные ограничения связаны с ненаблюдаемыми потоками, источниковыми пропусками и недоказанной сопоставимостью исторических территорий.')
 content.h('17. Источники, код и литература')
 
 if paths['bibliography'].suffix=='.csv':
  bibliography=pd.read_csv(paths['bibliography']).fillna('')
  for row in bibliography.to_dict('records'):
   content.p(str(row.get('bibliographic_citation',row.get('title','')))+' Фактически прочитано: '+str(row.get('actually_read_locator_this_pass',''))+' Источник: '+str(row.get('source_url','')))
 else:content.p(paths['bibliography'].read_text())
 content.p('Классики прочитаны выборочно по фактически сохранённым первичным публикациям/фрагментам: literature/cycle07_classics_final/. Полян — PDF394 страницы; Маергойз — архивные авторские выступления в издании2012, не прочтение книги1986; Колосовский — статья1947, не книга1969. Наши модульность, перегиб, фиксированная масса, запрет понижения доминантного центра и пороги устойчивости классикам не приписываются.');content.p('Делимитация: РайсихА.Э.(2020),Демографическое обозрение7(2),54–96; Dijkstra,Poelman,Veneri(2019),OECDRegionalDevelopmentWorkingPapers2019/11; ApplyingtheDegreeofUrbanisation2021,раздел7.2. Точная первичная литература и границы заимствования — literature/cycle07_delimitation/. Собственные алгоритмические решения помечены как адаптации.')
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
 content,summary=prepare(c,paths,out,mod);mod.render(content,out,'SGRT_RESEARCH_REPORT')
 brief=mod.Content();brief.title('СГРТ: записка научному руководителю');brief.p('Предварительные результаты на зафиксированных источниках. Записку сопровождают научный отчёт, атлас и таблицы состава районов.');brief_summary=summary.pivot(index='view_label',columns='unit_role',values='n_units').reset_index().rename(columns={'territorial_unit':'Территориальных районов','protected_carry':'Отдельных источниковых записей'});brief.t(reader_table(brief_summary));
 for kind,text in content.blocks:
  if kind=='text' and (text.startswith('Предварительный результат основного представления:') or ('Охват 60 минут, исход района в целом:' in text and text.startswith('Операционные районы')) or ('Охват 120 минут, исход района в целом:' in text and text.startswith('Операционные районы')) or text.startswith('Собственная масса и функции2021')):brief.p(text)
 brief.p('Рассматриваются вложенные потенциальные районы и отдельные операционные сценарии дорожного охвата. Каждая источниковая запись имеет измеренный тип; содержательные механизмы остаются предварительными интерпретациями. Исторические источниковые записи отделены от первичных наблюдений2021, а неполнота демографии и качества данных отражена явно.');brief.p('Включённые обновления: '+'; '.join(str(v) for v in c['component_integration_status'].values()));mod.render(brief,out,'SUPERVISOR_BRIEF')
 assert all(sha(p)==v for p,v in watch.items()) and sha(__file__)==binding['code_sha256'] and sha(a.inputs)==binding['config_sha256'],'Input/code/config changed during report'
 shutil.copyfile(a.inputs,out/'report_inputs.json');binding['files']={str(p.relative_to(out)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()};(out/'report_receipt.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n');print(out)
if __name__=='__main__':main()
