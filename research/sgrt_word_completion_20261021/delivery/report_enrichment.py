"""Dynamic scientific narrative and source references. No source/model mutation."""
from pathlib import Path
import json,re,hashlib
import pandas as pd

def number(v):return f'{int(v):,}'.replace(',',' ')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ensure_fresh(root,model):
    a=read(root/'analysis/run_receipt.json')
    if not (str(a.get('status','')).startswith('COMPUTED') or a.get('status')=='ACTUALLY_COMPUTED_DESCRIPTIVE_REGRESSIONS'):raise ValueError('Final analysis not ready: '+str(a.get('status')))
    repo=root.parents[1]
    selected_systems=str((model/'systems.parquet').relative_to(repo))
    if selected_systems not in a.get('source_sha256',{}):raise ValueError('Analysis belongs to another selected model: '+selected_systems)
    for name,h in a.get('source_sha256',{}).items():
        p=repo/name
        if not p.exists() or sha(p)!=h:raise ValueError('Analysis source changed: '+name)
    manifest=read(root/'maps/map_manifest.json');required=['03_road_hierarchy_','04_nine_word_types_','11_regional_sgrt_']
    for stem in required:
        e=next((e for e in manifest if e['figure']==stem+model.name),None)
        if e is None:raise ValueError('Current model map missing from manifest: '+stem+model.name)
        for name,h in e.get('inputs',{}).items():
            p=root/name
            if not p.exists()or sha(p)!=h:raise ValueError('Map source changed: '+name)
    vp=model/'independent_medical_validation_receipt.json'
    canonical=typology_source(root,model)
    if canonical.parent!=model:
        entry=next(e for e in manifest if e['figure']=='04_nine_word_types_'+model.name)
        expected=str(canonical.relative_to(root))
        if entry.get('inputs',{}).get(expected)!=sha(canonical):raise ValueError('Types map has not been rebuilt from canonical Word typology')
    if vp.exists():
        v=read(vp)
        for field,filename in [('membership_sha256','memberships.parquet'),('candidate_sha256','candidate_centers.parquet'),('healthcare_function_assignments_sha256','function_specific_memberships.parquet')]:
            if field in v and sha(model/filename)!=v[field]:raise ValueError('Stale medical validation: '+filename)
    return a

def typology_source(root,model):
    canonical=root/'typology/canonical'/model.name
    if canonical.exists() or 'word_ci' in model.name:
        receipt=canonical/'receipt.json'
        if not receipt.exists() or not str(read(receipt).get('status','')).startswith('COMPUTED'):raise ValueError('Canonical Word typology not ready: '+str(canonical))
        manifest=read(canonical/'manifest.json')
        if manifest.get('receipt_sha256')!=sha(receipt):raise ValueError('Canonical receipt changed after freeze')
        if manifest.get('model_output_manifest_sha256')!=sha(model/'output_manifest.json'):raise ValueError('Canonical typology belongs to another physical model manifest')
        for name,entry in manifest['files'].items():
            if sha(canonical/name)!=entry['sha256']:raise ValueError('Canonical typology input changed: '+name)
        path=canonical/'word_type_hypotheses.parquet'
        if not path.exists():raise FileNotFoundError(path)
        return path
    return model/'word_type_hypotheses.parquet'

def configuration_for_model(model,receipt):
    expected=receipt.get('configuration_sha256')
    exact=[p for p in model.parent.glob('model_inputs*.json')if sha(p)==expected]
    if exact:return read(exact[0]),exact[0]
    raise ValueError('No configuration with exact model run SHA256')

def rank_narrative(configuration,model):
    txt=(json.dumps(configuration,ensure_ascii=False)+' '+model.name).lower()
    if any(x in txt for x in ['wordci','word_ci','wordcentrality','word_centrality','provisional_rural']):
        text='Центральность варианта WordCi задана формулой Ci=0,5·minmax(logMi)+0,5·minmax(log(1+R2021)), гдеR2021 — предварительная сельская людность. Для основногоCi предварительная сельская людность берётся по наблюдаемому перечню переписи2021. Исторические записи, не входящие в этот перечень, исключены только из данногоR2021 и не превращены в нули; они сохранены в полной источниковой оси и отдельных агрегатах. Строгая полнота по всем историческим источниковым единицам сохранена только в диагностических колонках; полного альтернативного расчёта иерархии по такомуCi не выполнялось. Ранги варианта WordCi учитывают собственную массуMi и объём предварительного сельского окружения в явной формуле центральностиCi. Сначала выполняется один предварительный выбор среди всех центров; известный сельский объём и UNKNOWN сохраняются отдельно. Затем рассчитываютсяCi и монотонные ранги, после чего строится окончательная иерархия снизу вверх. СобственнаяMi на притянутом населении не переобучается и остаётся гравитационным весом. Для родительской связи WordCi требуются большийCi и старший монотонный порядок; меньшая собственнаяMi у такого родителя допустима, поскольку вCi включено предварительное сельское окружение. Предварительный и окончательный составы не смешиваются; исходный вариант рангов по собственной массе остаётся сравнительным сценарием. Статистические границы рангов берутся в точке пересечения взвешенных плотностей соседних компонентGMM между их средними; если пересечения нет, применяется явно заданная середина между средними. Они не объявляются наблюдаемыми ступенями обслуживания. Поскольку людность2021 участвует вMi иCi, геометрия районов и ретроспективный демографический исход статистически связаны конструкцией; это дополнительное основание описательной, а не причинной интерпретации.'
        rank_file=model/'empirical_ranks.json'
        if rank_file.exists():
            details=read(rank_file).get('ordinal_boundary_details',[]);fallback=sum('midpoint_fallback'in x.get('method','')for x in details)
            text+=f' В выбранном расчёте правило середины применено для {fallback} из {len(details)} границ; остальные используют пересечение плотностей.'
        provisional=configuration.get('rank_provisional_receipt')
        if provisional:
            receipt=read(model.parents[3]/provisional)
            text+=f' В предварительном реестре: {number(receipt["native2021_axis_units"])} единиц наблюдаемого перечня переписи2021, включая {number(receipt["native2021_actual_observed_zero_rows"])} наблюдаемых нулей; неизвестных значений в этом перечне — {number(receipt["native2021_records_with_missing_population"])}. Компонента наблюдаемого перечня полна у {number(receipt["observed2021_frame_complete_centers"])} центров. В диагностических колонках требование полноты по всем историческим источниковым единицам выполняется у {number(receipt["centers_with_complete_zone"])} центров; неполнота затрагивает {number(receipt["centers_missing_zone_population"])} центров и {number(receipt["missing_population_units_in_assigned_provisional_zones"])} единиц в предварительно назначенных окружениях.'
        return text
    return 'Ранги данного сравнительного варианта выделены по собственной функциональной силе центра. В данном intrinsic-варианте родительская связь требует большегоMi и старшего монотонного порядка. Окружение объединяется целиком, вложенные составы не разрезаются. Это отдельная проверка чувствительности к ранговому правилу исходной концепции.'

def atlas_sources(root,model):
    selected=[];skipped=[];allowed={model.name,model.name.removesuffix('_baseline')+'_inclusive'}
    for e in read(root/'maps/map_manifest.json'):
        related={Path(k).parts[1]for k in e.get('inputs',{})if k.startswith('model/output_')}
        if related and not related.issubset(allowed):continue
        stale=[k for k,h in e.get('inputs',{}).items()if not(root/k).exists()or sha(root/k)!=h]
        if stale:skipped.append({'figure':e['figure'],'reason':'input changed','inputs':stale});continue
        selected.extend(root/'maps'/v['path']for v in e['outputs']if v['path'].endswith('.pdf'))
    return list(dict.fromkeys(selected)),skipped

def scenario_blocks(root,model):
    directory=root/'model/scenario_comparison';receipt=directory/'receipt.json'
    if not receipt.exists():return []
    r=read(receipt)
    if r.get('status')!='COMPUTED_DESCRIPTIVE_SENSITIVITY_NOT_PARAMETER_SELECTION':raise ValueError('Scenario comparison not computed')
    for name,h in r['input_sha256'].items():
        source=Path(name) if Path(name).is_absolute() else root.parents[1]/name
        if sha(source)!=h:raise ValueError('Stale scenario comparison: '+name)
    for name,entry in r.get('files',{}).items():
        if sha(directory/name)!=entry['sha256']:raise ValueError('Scenario output changed: '+name)
    coverage=pd.read_csv(directory/'scenario_coverage.csv');stability=pd.read_csv(directory/'membership_stability.csv')
    if model.name not in set(coverage.scenario):raise ValueError('Scenario comparison does not include selected model')
    rows=[]
    for scenario,g in coverage.groupby('scenario',sort=False):
        for row in g[g.level.isin([g.level.min(),g.level.max()])].itertuples():
            rows.append([scenario.removeprefix('output_'),str(row.level),number(row.n_assigned_population_axis),number(row.n_unassigned_population_axis),number(row.assigned_known_population2021)])
    ss=stability[(stability.scenario_a.eq(model.name)|stability.scenario_b.eq(model.name))].copy()
    if ss.empty:return []
    relation_rows=[[r.scenario_a.removeprefix('output_')+' → '+r.scenario_b.removeprefix('output_'),('Низший'if r.view=='lowest'else'Высший')+f' {r.level_a}→{r.level_b}',number(r.n_both_assigned),f'{100*r.same_center_fraction_among_both_assigned:.1f}%',f'{r.directional_a_best_partition_jaccard_weighted:.3f}']for r in ss.itertuples()]
    low=ss[ss.view.eq('lowest')];low_same=low.same_center_fraction_among_both_assigned;low_j=low.directional_a_best_partition_jaccard_weighted
    b=[('head','7в. Фактически пересчитанная чувствительность районов'),('text','Каждый перечисленный сценарий рассчитан целиком. Покрытие учитывает исходную ось, а людность — известную сумму2021, без превращения неизвестных значений в нули. Сравниваются низший и высший доступный уровни; одинаковый номер уровня сам по себе не доказывает одинаковую функциональную ступень, а разные высшие порядки не гомологичны.'),('table',(['Сценарий','Ур.','Назначено НП','Без назначения','Известная P2021 назначенных'],rows)),('table',(['Направление A → B','Уровни A→B','Оба назначены','Тот же центр','Jaccard A→B'],relation_rows)),('text',f'На низшем уровне доля совпадающих центров среди назначенных в обоих сценариях составляет {100*low_same.min():.1f}–{100*low_same.max():.1f}%; направленное совпадение состава районов по лучшему Jaccard — {low_j.min():.3f}–{low_j.max():.3f}. Это измеренная чувствительность границ к выбору сценария, а не внешняя проверка правильности районов. Jaccard сопоставляет каждый районA с наиболее похожим райономB и взвешивает по размеруA; обратное направление может дать другой результат. Смена неназначенного статуса не входит в знаменатель совпадения центров и показана отдельно в исходной таблице.')]
    tp=directory/'operational_type_shifts.csv'
    if tp.exists():
        t=pd.read_csv(tp);t=t[t.scenario_a.eq(model.name)|t.scenario_b.eq(model.name)]
        type_frames=r.get('uses_canonical_typology',{})
        b.append(('text','Основание типовых сравнений: '+', '.join(k.removeprefix('output_')+' — '+('каноническая операционализация'if v else'широкие прототипы')for k,v in type_frames.items())+'. Сравнения с различающимися основаниями типов читаются как дополнительная чувствительность определения, а не как тождественная классификация.'))
        b.append(('table',(['Сценарии A → B','Срез','Типы A / B','Сохранились','Только A / B'],[[r.scenario_a.removeprefix('output_')+' → '+r.scenario_b.removeprefix('output_'),r.view,f'{r.n_center_type_pairs_a} / {r.n_center_type_pairs_b}',str(r.n_same_center_type_pairs),f'{r.n_a_only_center_type_pairs} / {r.n_b_only_center_type_pairs}']for r in t.itertuples()])))
        b.append(('small','Канонические типы и широкие прототипы различены по сценариям в предыдущей подписи. Совпадение классификации у того же центра отражает устойчивость описательной гипотезы; оно не доказывает тождество изменившихся составов СГРТ.'))
    return b

def enrich(root,model,blocks,systems,types,axis,output_directory=None):
    out=Path(output_directory)if output_directory is not None else root/'delivery';out.mkdir(parents=True,exist_ok=True);nodes_path=model/'nodes.parquet'
    import pyarrow.parquet as pq
    cols=pq.ParquetFile(nodes_path).schema.names
    keep=[c for c in cols if c in ['id','population_2010','population_value_quality_2010','original_population_2010','original_population_value_quality_2010','recovered2010_reviewed_primary2010_override_allowed']]
    nodes=pd.read_parquet(nodes_path,columns=keep);nodes=nodes[nodes.id.isin(set(axis.id))]
    qualities=nodes.population_value_quality_2010.value_counts(dropna=False).to_dict();protected=int(nodes.population_value_quality_2010.eq('secondary_confidentiality_protected_value_exact_scope_unverified').sum())
    admission=read(root/'demography2010_recovery/root_four_regions_admission_receipt.json')
    applied=int(nodes.get('recovered2010_reviewed_primary2010_override_allowed',pd.Series(False,index=nodes.index)).eq(True).sum())
    numeric=int((nodes.population_2010.ne(nodes.original_population_2010)&nodes.original_population_2010.notna()).sum())if'original_population_2010'in nodes else 0
    source_summary={'model_directory':str(model),'axis_node_rows':len(nodes),'quality_counts_2010':qualities,'admitted_source_rows':admission['rows'],'applied_to_model_axis_nodes':applied,'numeric_value_changes_applied':numeric,'admission_control_derived_zeros':admission['control_derived_zeros'],'remaining_protected_secondary_nodes':protected}
    (out/'report_population_source_summary.json').write_text(json.dumps(source_summary,ensure_ascii=False,indent=2)+'\n')
    region=pd.read_parquet(root/'land2021_recovery/regional_sown_share_farmland2021.parquet');land=read(root/'land2021_recovery/compatible_pair_receipt.json');bon=read(root/'soil_bonitet_recovery/recovery_receipt.json')
    edu=read(root/'education/history_build_receipt.json');med=read(root/'medical/validation_receipt.json')
    climate=pd.read_parquet(root/'context/climate_settlement_features.parquet',columns=['climate_gaez_sat_above10_cday_1981_2010'])
    soilpath=root/'context/soil_settlement_features.parquet';soilcols=pq.ParquetFile(soilpath).schema.names;sc=next(c for c in soilcols if c.endswith('class_rating_lower'));soil=pd.read_parquet(soilpath,columns=[sc])
    cov=[['Переписная ось',number(len(axis)),'Источниковые единицы и пропуски сохранены'],['Образование2021',number(edu['groups']['school'])+' школьных записей','Явный адрес и географический кандидат раздельны'],['Медицина2021',number(med['history_20210101']['unique_osm_objects'])+' объектов','Подтипы и картографическая наблюдаемость разделены'],['Торговля/финансы/администрация2021','Датированный слой OSM','Количество записей не равно мощности'],['САТ >10°C FAO',number(climate.iloc[:,0].notna().sum())+' НП','Суточный показатель, норма1981–2010'],['Почвенные рейтинги FAO',number(soil.iloc[:,0].notna().sum())+' НП','Агрономические классы, отдельны от российского бонитета'],['Доля посевов/угодий2021',str(land['valid_ratio_rows'])+' субъекта','Совместимые региональные первоисточники, не муниципальные площади'],['Российский бонитет',number(bon['nonnull_experimental_intervals'])+' интервалов','Экспериментальное восстановление по мелкомасштабному атласу']]
    for j,(k,b) in enumerate(blocks):
        if k=='table' and b[0][0]=='Блок':blocks[j]=('table',(['Блок','Фактический массив','Смысл и ограничение'],cov));break
    addition=[('head','2а. Восстановленные первичные данные и новые контексты'),('text',f'В четырёх региональных переписных публикациях восстановлено и принято {number(admission["rows"])} однозначных связок НП2010. Из них {number(admission["new_primary_previously_secondary"])} ранее имели защищённые вторичные значения; {number(admission["changed_numeric_values"])} чисел изменены, {number(admission["control_derived_zeros"])} нулей отдельно выведены из исчерпывающих перечней, точных сумм и контрольных чисел безнаселённых НП. В данном финальном модельном файле применено {number(applied)} связок и {number(numeric)} численных изменений. Исходные значения и первичные локаторы сохранены, ось не перезаписана.'),('text',f'Качество2010 читается из окончательных model/nodes.parquet: {number(protected)} осевых единиц сохраняют статус защищённого вторичного значения с неподтверждённым точным охватом. Опубликованное число и доказанная переписная истинность остаются разными уровнями свидетельства. Нули, доказанные контролями, имеют собственный quality-класс.'),('table',(['Регион','Принято НП','Численных изменений','Доказанных нулей'],[[{'bashkortostan':'Башкортостан','tver':'Тверская область','vologda':'Вологодская область','novgorod':'Новгородская область'}.get(r['region'],r['region']),number(r['rows']),number(r['changed_numeric_values']),number(r['control_derived_zeros'])]for r in admission['source_regions']])),('text',f'Современный аграрный контекст восстановлен из двух первоисточников: Росреестр, приложение2 к докладу2021, страницы174–179, угодья всех категорий на01.01.2022; Росстат, бюллетень посевных площадей2021, листT_1440, хозяйства всех категорий. Знаменатель покрывает {len(region)} субъектов, совместимая доля — {land["valid_ratio_rows"]}. Сумма угодий {land["national_farmland_thousand_ha"]:,.1f} тыс.га совпала с общероссийской контрольной суммой; посевы {land["national_sown_thousand_ha"]:,.3f} тыс.га, отношение {100*land["national_sown_share"]:.2f}%. Это региональная посевная нагрузка, включающая в знаменатель сенокосы и пастбища: низкая доля не равна заброшенности. Санкт-Петербург остаётсяNULL; повторяемые региональные значения не превращены в площади НП или СГРТ.'),('text',f'Дополнительно восстановлены {number(bon["nonnull_experimental_intervals"])} экспериментальных интервалов российского бонитета по атласной карте масштаба {bon["source_scale"]}. Интервалы выделены только при устойчивом классе в пределах ошибки геопривязки; техническая неслепая проверка контрольных точек дала RMSE около {bon["heldout_rmse_approx_km"]:.1f}км. Это не независимая оценка точности геопривязки. Смешанные классы и экстраполяция вне опорных точек оставлены неизвестными. Это отдельная чувствительность, а не точечная кадастровая оценка и не замена FAO-рейтинга в основной спецификации.')]
    idx=next(i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('3.'));blocks[idx:idx]=addition
    cfg,_=configuration_for_model(model,read(model/'run_receipt.json'))
    blocks[:]=[(k,rank_narrative(cfg,model) if k=='text' and str(b).startswith('Ранги выделяются') else b)for k,b in blocks]
    ri=next(i for i,(k,b)in enumerate(blocks)if k=='text'and str(b).startswith(('Ранги ','Центральность варианта WordCi')))
    blocks.insert(ri+1,('text','Раздельные функциональные сети позволяют расходиться образовательным, медицинским и интегральным назначениям. Негеолоцированные, недоступные и неопределённые единицы сохраняют собственные статусы. Несколько сопоставимых центров характеризуют модельный полицентрический потенциал; подтверждение реальных взаимодействий требует независимых потоков и данных о разделении функций.'))
    # Replace stale original-axis statement and L1-only typology with final model source quality/all levels.
    blocks[:]=[(k,(f'Качество демографии2010 анализируется на окончательных модельных узлах. Сохранилось {number(protected)} защищённых вторичных значений с неподтверждённым точным охватом; подробная первичная ревизия и принятые замены приведены ниже.'if k=='text'and str(b).startswith('Отдельный существенный риск демографии:')else b))for k,b in blocks]
    table=[]
    for level in sorted(types.level.unique()):
        for typ in sorted(types.word_type.unique()):
            g=types[types.level.eq(level)&types.word_type.eq(typ)].drop_duplicates(['center_id','level','word_type']);name=g.word_type_name.iloc[0]if len(g)else str(typ)
            table.append([str(int(level)),f'{int(typ)}. {name}',number(g.rule_status.eq('satisfied_observed_indicators').sum()),number(g.operational_hypothesis.fillna(False).sum()),number(g.rule_status.eq('unknown_missing_required_indicators').sum())])
    for i,(k,b)in enumerate(blocks):
        if k=='table'and b[0][0]=='№':blocks[i]=('table',(['Ур.','Тип исходной концепции','Расшир. AND','Описательные','UNKNOWN'],table));break
    for stem,before,caption in [('03_road_hierarchy_','4.','Вложенная дорожная иерархия выбранного расчёта; точки НП и связи не являются непрерывными территориальными полигонами.'),('04_nine_word_types_','6.','Девять описательных типов и неизвестные признаки; уровни и сила свидетельства читаются вместе с таблицей.')]:
        fig=root/'maps'/f'{stem}{model.name}.png'
        if fig.exists():
            at=next((j for j,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith(before)),len(blocks));blocks.insert(at,('image',(fig,caption)))
    summary=types.groupby(['level','word_type']).agg(center_level_pairs=('center_id','nunique'),operational=('operational_hypothesis','sum'),strict=('rule_status',lambda v:int(v.eq('satisfied_observed_indicators').sum()))).reset_index();summary.to_csv(out/'report_types_all_levels.csv',index=False)
    blocks.insert(next(i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('5.'))+1,('text','В таблице проверяется каждая пара центр×уровень: один центр может участвовать в системах разных уровней, которые нельзя сливать в одну строку. Числа описательных типов не образуют взаимоисключающего разбиения; пересечения и UNKNOWN сохранены. РасширеннаяAND-проверка содержит дополнительные иллюстративные признаки и механизмы и не отменяет описательную классификацию по измеренному ядру.'))
    canonical=typology_source(root,model)
    broad_path=canonical.parent/'broad_prototypes.parquet'
    if broad_path.exists():
        broad=pd.read_parquet(broad_path)
        broad_count=int(broad.operational_hypothesis.fillna(False).sum())if'operational_hypothesis'in broad else len(broad)
        canonical_count=int(types.operational_hypothesis.fillna(False).sum())
        at=next(i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('5.'))
        canonical_receipt=read(canonical.parent/'receipt.json')
        blocks.insert(at+1,('text',f'После буквального аудита исходной концепции широкие демографические прототипы ({number(broad_count)} положительных сочетаний центр×уровень) сохранены отдельно. Основные названия и таблицы ниже относятся к канонической операционализации ({number(canonical_count)} положительных сочетаний у {number(types.loc[types.operational_hypothesis.fillna(False),'center_id'].nunique())} уникальных центров). Проверяются тип центра, сценарная граница малых городов до50тыс.жителей, близость рекреационно-дачных систем к городу от100тыс.жителей и географическое свидетельство Нечерноземья. Неизвестный обязательный признак не превращается в положительный тип. Это адаптация определения типов при замороженных массах, рангах и составах районов.'))
        near=canonical_receipt.get('literal_type5_candidate_counts_by_near_threshold',{})
        if near:blocks.insert(at+2,('text','Для рекреационно-дачного типа близость к крупному городу — явный дорожный сценарий, не установленный поведенческий порог. Основная граница90минут сопоставлена с60/120/180минутами; фактическое число канонических сочетаний центр×уровень типа5 по сценариям: '+', '.join(str(k)+'мин — '+str(v)for k,v in near.items())+'. Классификационная центральностьCi заморожена до окончательного районирования; вычисленная по финальному окружению центральность остаётся только постфактум-диагностикой.'))
    ops=types[types.operational_hypothesis.fillna(False)].merge(systems[['center_id','level','name','region','system_population_known_sum_2010','system_population_known_sum_2021']],on=['center_id','level'],validate='many_to_one')
    cases=ops.sort_values(['word_type','level','name']).groupby(['word_type','level'],group_keys=False).head(3);cases.to_parquet(out/'report_named_type_cases.parquet',index=False)
    def rate(x):return '—'if pd.isna(x)else f'{100*x:+.2f}%'
    case_rows=[[r.name+' ('+r.region+')',str(r.level),str(r.word_type),rate(r.center_annual_rate),rate(r.rural_annual_rate),f'{number(r.system_population_known_sum_2010)} → {number(r.system_population_known_sum_2021)}']for r in cases.itertuples()]
    caseblocks=[('head','5а. Именные примеры выделенных описательных типов'),('text','Примеры выбираются из фактически рассчитанных положительных описательных типов каждого уровня, до трёх на сочетание. Темпы — среднегодовые изменения центра и сельского окружения; население всей СГРТ (центр и всё включённое окружение), а не только центра, показано известной суммой и читается вместе с флагами полноты. Таблица не устанавливает причин наблюдаемой динамики.')]
    if case_rows:caseblocks.append(('table',(['Центр и регион','Ур.','Тип','Центр/год','Село/год','Население всей СГРТ:2010 → 2021'],case_rows)))
    commuting_path=root/'typology_commuting_cases/explicit_mobile2015_named_shares.parquet'
    if commuting_path.exists():
        commute=pd.read_parquet(commuting_path)
        caseblocks.extend([('head','5б. Независимое функциональное свидетельство маятниковых связей'),('text','Махрова и Бочкарев (2017) публикуют результаты мобильных данных за ноябрь2015: долю работающих в Москве среди всех выезжающих на работу из муниципалитета. В статье приведены следующие именные значения (PDFс.11); муниципальная карта показана на рис.7, PDFс.13. Это самостоятельная функциональная опора для исследования маятникового типа, с другим годом и муниципальным зерном. Муниципалитет не приравнивается к переписному НП, а проценты не являются долей всех жителей или занятых. Значения не перенесены на национальную сеть и автоматически не присваивают тип1.'),('table',(['Названная территория','Доля выезжающих, работающих в Москве','Период'],[[r.named_area,f'{r.moscow_share_of_outbound_commuters_percent:.1f}%','Ноябрь2015']for r in commute.itertuples()])),('small','Железнодорожная таблица2014 в той же статье относится к пассажирским поездкам, включая повторные поездки и иные цели; она сохранена отдельно и не смешивается с мобильным показателем2015. Географические ID в реестре служат справочными связками, а не доказанным историческим соответствием границ муниципалитета и НП.')])
    industrial=pd.read_parquet(root/'literature/industrial_case_evidence.parquet')
    for r in industrial.itertuples():caseblocks.append(('small',f'Независимое промышленное свидетельство: {r.settlement_name}, {r.enterprise}, {r.affected_industry}, событие{r.event_year}. {r.own_paraphrase} Источник: {r.source_title}; {r.excerpt_locator}; {r.source_url}. Это свидетельство отдельного производства, без автоматического вывода о хозяйственном крахе всей СГРТ.'))
    ix=next(i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('6.'))if any(k=='head'and str(b).startswith('6.')for k,b in blocks)else next(i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('7.'));blocks[ix:ix]=caseblocks
    blocks[:]=[(k,'В исходной рукописи определения типов соседствуют с формулировками «как правило», «нередко», «зачастую». Операциональное демографическое и функциональное ядро задаёт измеренные описательные исследовательские типы; расширеннаяTRUE/FALSE/UNKNOWN-матрица отдельно проверяет иллюстративные признаки и недоказанные механизмы. Нулевое число полностью выполненных расширенныхAND-наборов не означает отсутствия выделенных типов. Маятниковая миграция не выводится из дорожной близости, вахтовость — из наличия шахты; механистические утверждения требуют отдельных данных.'if k=='text'and str(b).startswith('Строгая матрица TRUE/FALSE/UNKNOWN')else b)for k,b in blocks]
    wm=root/'reviews/word_core_typology_operationalization.csv'
    if wm.exists():
        roles=pd.read_csv(wm);counts=roles.role.value_counts().to_dict()
        blocks.append(('text',f'Независимая матрица операционализации сверяет {len(roles)} точных фрагмента исходногоWord (строки65–96) и разделяет определяющее ядро, необходимую для утверждений о потоках функциональную опору, поддерживающие признаки, иллюстрации и механизмы. Полная таблица с буквальными цитатами: reviews/word_core_typology_operationalization.csv; это основание различия описательных типов и расширенногоAND-профиля.'))
    blocks.append(('text','Функциональные типы опираются на разновременные признаки: демография2010–2021 сопоставляется, в частности, с рекреационными свидетельствами и дорогами2026. Поэтому они не объявляются исторически доказанной функцией территории именно в2021году.'))
    blocks.append(('text','Для этнического (анклавного) типа ответы переписи о национальной принадлежности отражают самоописание населения. Они не являются измерением языка, языковой преемственности или индивидуального поведения. Для типа7 температурныйпорог сам по себе не устанавливает принадлежность к Нечерноземью; для типа9 ресурсныйобъект сам по себе не устанавливает вахтовую функцию.'))
    # Remove superseded missing2021 assertion while preserving frozen primary design.
    blocks[:]=[(k,str(b).replace('Неизвестная площадь сельхозугодий2021 не заменяется площадью2008; российский бонитет не заменяется рейтингом FAO.','Совместимая региональная доля посевов2021 и экспериментальные интервалы бонитета вынесены в отдельные сценарии; основной дизайн М1–М3 сохраняет первоначальный набор признаков.'))if k=='text'else(k,b)for k,b in blocks]
    medp=model/'independent_medical_relation_audit.parquet'
    if medp.exists():
        relations=pd.read_parquet(medp);ext=relations[relations.origin_id.ne(relations.destination_id)];N=len(ext)
        pairs=[('Поставщик наблюдается в OSM2021','provider_has_observed_healthcare'),('Медицинский лидер до порога','healthcare_raw_leader_agreement'),('Ближайший по дорожной сети поставщик','nearest_healthcare_provider_agreement'),('Медицинское назначение после порога','healthcare_assignment_agreement'),('Интегральное низовое назначение','lowest_level_agreement')]
        vrows=[[label,number(ext[field].fillna(False).sum()),number(N),f'{100*ext[field].fillna(False).mean():.1f}%']for label,field in pairs if field in ext]
        ix=next((i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('7.')),len(blocks))
        medical=[('head','6а. Покрытие медицинских поставщиков и независимый ориентир'),('table',(['Проверка','Числитель','Пар','Доля'],vrows)),('text','Главное ограничение этой проверки — слабая наблюдаемость поставщиков в датированном слое2021 и несовпадение дат с нормативным прикреплением2024. Совпадение среди наблюдаемых поставщиков и совпадение по всем исходным парам имеют разные знаменатели. Ближайший дорожный поставщик служит независимым простым ориентиром; превышение качества над ним не предполагается заранее. Нормативное прикрепление не является наблюдаемой поездкой. Низкие показатели не скрыты и не выданы за подтверждённую точность национальной сети.')]
        if 'provider_has_observed_healthcare'in ext and'healthcare_assignment_agreement'in ext:
            observed=ext[ext.provider_has_observed_healthcare.fillna(False)]
            medical.append(('text',f'После ограничения на наблюдаемых поставщиков: {number(observed.healthcare_assignment_agreement.sum())} совпадений из{number(len(observed))}; по всем исходным внешним отношениям: {number(ext.healthcare_assignment_agreement.sum())} из{number(N)}. Ограниченная подвыборка не заменяет общий результат.'))
        if 'provider_is_candidate'in ext:
            elig=ext[ext.provider_is_candidate.fillna(False)];medical.append(('text',f'Для интегрального назначения среди источниковых поставщиков, попавших в кандидатный набор: {number(elig.lowest_level_agreement.sum())} из{number(len(elig))}. Это отдельный тест многозадачной интегральной модели, а не замена теста специализированной медицинской сети.'))
        blocks[ix:ix]=medical
    holdout=root/'validation/holdout2021_independent_source_review.json'
    if holdout.exists():
        hr=read(holdout);hf=read(holdout.with_name('holdout2021_source_freeze_receipt.json'));ha=read(holdout.with_name('holdout2021_sourceclass_amendment.json'))
        hb=[('head','6б. Новый корпус2021 после замораживания модели'),('text',f'Прямо получен официальный акт Правительства Калужской области от30.07.2021 №493, публикация4000202108050001: {hf["official_pdf"]["pages"]} страницы, таблица прикрепления на PDFс.29–94. Все {hf["transcription"]["all_data_rows"]} строки сохранены, включая неоднозначные и неразрешённые. Источниковый протокол дополнен явной поправкой класса источника: официальный региональный правительственный/правовой портал допущен наряду с Минздравом/ТФОМС. Поправка внесена после получения и осмотра документа, до связывания ID и сравнений; исходный протокол неизменён. Это новое испытание после замораживания модели, а не первоначально слепой эксперимент.'),('text',f'Независимо визуально сверены {hr["reviewed_rows"]} строки с разрешённым местом поставщика на {len(hr["visual_physical_pages"])} страницахPDF; остальные {hf["transcription"]["all_data_rows"]-hr["reviewed_rows"]} строки не прошли эту независимую визуальную сверку и не имеют принятых связок поставщика; отрицательный вывод на весь документ не переносится. Исключены {hr["household_rows_excluded"]} домохозяйственных записей; оставшиеся {hr["nonhousehold_local_provider_records"]} реальных записей поставщиков локальны. Во всей рассмотренной подвыборке {hr["resolved_identical_origin_destination_rows"]} пар имеют одинаковые origin/destination, {len(hr["origin_unresolved_rows"])} происхождения не разрешены, {len(hr["conflicting_type_rows"])} запись содержит конфликт типа НП. Принятых межпоселенческих сопоставимых пар — {hr["accepted_intersettlement_comparable_pairs"]}. Поэтому метрика точности назначений не рассчитывается: это непригодность полученной подвыборки для проверки межпоселенческой геометрии, а не0%точности и не доказательство успешности модели. Модель и параметры не подгонялись.'),('small','Первоисточник: http://publication.pravo.gov.ru/file/pdf?eoNumber=4000202108050001; SHA256 '+hf['official_pdf']['sha256']+'. Протокол, поправка класса источника, полный реестр и независимая рецензия доступны в validation/holdout2021_*.')]
        hp=holdout.with_name('holdout2021_healthcare_presence_review.json')
        if hp.exists():
            pr=read(hp);hb.append(('text',f'Отдельная проверка наблюдаемости: {pr["source_independently_reviewed_real_provider_rows"]} реальных записей соответствуют {pr["unique_source_positive_provider_NP_locations"]} уникальным НП. Положительное медицинское свидетельство в замороженном слоеOSM2021 есть у {pr["present_physical_healthcare_positive_witness"]}; у {pr["false_witness_not_evidence_of_absent_healthcare"]} положительное свидетельство отсутствует. Эта непредставительная подвыборка показывает наблюдаемость присутствия на уровнеНП, не национальную полноту, совпадение конкретного учреждения, мощность, прикрепление или поездки. Отсутствие свидетельства не означает отсутствия учреждения.'))
        address=holdout.with_name('holdout2021_address_feasibility_receipt.json')
        if address.exists():
            ar=read(address);hb.append(('text',f'Последующий поиск адресов в том же акте дал {ar["newly_resolved_vs_frozen_rows"]} дополнительных кандидатных связок сверх исходного реестра. Они ещё не приняты независимой проверкой и не меняют вывод по исходной проверенной подвыборке40 строк. Кандидатный адрес не доказывает прикрепление, функционирование учреждения или точность модели.'))
        at=next((i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('7.')),len(blocks));blocks[at:at]=hb
    cv_at=next((i for i,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('7.')),len(blocks))
    blocks.insert(cv_at+1,('text','Межрегиональная перекрёстная проверка переоценивает регрессию и масштабирование признаков на обучающих регионах. Исходные массы, рангиCi и составы районов остаются фиксированными результатами общероссийского расчёта. Полная вложенная проверка всего алгоритма на регионах, не участвовавших в построении сетки, здесь не заявляется; участие людности2021 вMi/Ci сохраняет конструктивную зависимость от ретроспективного исхода.'))
    analysis_addition_start=len(blocks)
    ap=root/'validation'/model.name/'mass_block_ablation_summary.csv'
    if ap.exists():
        ar=read(ap.with_name('mass_block_ablation_receipt.json'))
        for rel,h in ar.get('input_sha256',{}).items():
            if sha(root.parents[1]/rel)!=h:raise ValueError('Stale mass ablation: '+rel)
        ab=pd.read_csv(ap); labels={'block_demographic_z':'Собственная людность','block_demographic_context_2021_z':'Демографический контекст','block_economy_z':'Экономический прокси','block_housing_z':'Жильё','block_service_z':'Сервисы'}
        blocks.extend([('head','7б. Чувствительность собственной массы'),('text','Исходная формула массы независимо воспроизведена. При фиксированных кандидатах поочерёдно исключён каждый из пяти блоков; корреляция относится к порядку масс, Jaccard — к пересечению верхнего дециля. Районы тяготения и иерархия в этом тесте повторно не рассчитывались; проверка не измеряет точность притяжения.'),('table',(['Исключён блок','Кандидатов','Spearman порядка масс','Jaccard верхнего дециля'],[[labels.get(r.dropped_block,r.dropped_block),number(r.candidate_centers),f'{r.spearman_mass_order:.3f}',f'{r.top_decile_jaccard:.3f}']for r in ab.itertuples()]))])
    mp=root/'analysis/model_metrics.csv'
    if mp.exists() and mp.stat().st_size>2:
        met=pd.read_csv(mp);met=met[met.scenario.eq('primary') & met.outcome.eq('outcome_system_change_pct')]
        for lev,g in met.groupby('level'):
            vals=g.set_index('model').group_oof_rmse
            if 'M1'in vals and'M3'in vals:
                delta=float(vals['M3']-vals['M1']);direction='выше' if delta>0 else'ниже'
                blocks.append(('text',f'На уровне{int(lev)} ошибкаM3 на отложенных регионах {direction} ошибкиM1 на{abs(delta):.3f} процентного пункта. Это фактическое сравнение на общей полной выборке; изменение ошибки не доказывает причинную роль новых переменных.'))
    blocks.extend(scenario_blocks(root,model))
    model_extra=blocks[analysis_addition_start:];del blocks[analysis_addition_start:]
    pos=next((j for j,(k,b)in enumerate(blocks)if k=='head'and str(b).startswith('8.')),len(blocks));blocks[pos:pos]=model_extra
    bib=pd.read_csv(root.parent/'sgrt_word_replication_20261021/literature/bibliography.csv');new=pd.read_csv(root/'literature/new_primary_bibliography.csv');bibliography=[]
    for r in bib[bib.current_read_status.str.startswith('original',na=False)].itertuples():bibliography.append(f'{r.author} ({r.year}). {r.title}. Прочитано: {r.read_locator}. {r.url}')
    for r in new.itertuples():bibliography.append(f'{r.author} ({r.year}). {r.title}. Печатные страницы {r.printed_pages}; выборочное чтение первоисточника/авторской архивной записи, вся книга не заявлена прочитанной. {r.source_url}')
    if commuting_path.exists():bibliography.append('Махрова А.Г., Бочкарев А.Н. (2017). Маятниковая миграция в Московском регионе: новые данные. Демоскоп Weekly №727–728, 1–21 мая2017. PDFс.4: методика; с.6: ноябрь2015; с.11: четыре именных доли; с.13, рис.7: муниципальная карта. http://demoscope.ru/weekly/2017/0727/demoscope727.pdf')
    blocks.extend([('head','9. Проверяемые литературные и статистические источники'),('text','Литература ниже задаёт основания анализа связей, иерархии и функций. Она не объявляется эмпирическим доказательством наших порогов, сервисных мощностей или причин динамики.')]+[('small',f'{i+1}. {b}')for i,b in enumerate(bibliography)])
    blocks.extend([('small','Росреестр. Государственный национальный доклад2021: приложение2, PDF174–179, колонки3–5. SHA25646b0e2c130645bcb2aee50ffccc315e735a806977123e9d5b75434e9130c8a08. Архивный URL и точные строки сохранены в land2021_recovery/regional_farmland2021_primary.parquet.'),('small','Росстат. Посевные площади РФ в2021году. Бюллетень,06.03.2023; XLSлистT_1440, колонка6, региональная строка. https://rosstat.gov.ru/storage/mediabank/posev_2021.xls. SHA2569648c0144304d884085dfdfcad68648844cc6bfe631621d35ae4ac30c68b3c38.'),('small','Национальный атлас почв РФ. Бонитет почвенного покрова, разворот240–241. https://soil-db.ru/soilatlas/razdel-6-funkcii-pochv/bonitet-pochvennogo-pokrova. Изображение https://files.soil-db.ru/soilatlas/3600x2400/240-241-min.jpg. Геопривязка и интервальное извлечение экспериментальны.')])
    (out/'report_bibliography.txt').write_text('\n\n'.join(bibliography)+'\n')
    return source_summary,summary,cases

def supervisor_brief(root,model,systems,types,axis,source_summary,case_summary):
    land=read(root/'land2021_recovery/compatible_pair_receipt.json');bon=read(root/'soil_bonitet_recovery/recovery_receipt.json');audit=read(root/'reviews/strict_gate_receipt.json');levels=[]
    for level,g in systems.groupby('level'):levels.append([str(level),number(len(g)),number(g.n_rural_external_settlements.gt(0).sum()),number(types.loc[types.level.eq(level),'operational_hypothesis'].fillna(False).sum())])
    b=[('title','СГРТ России: записка научному руководителю'),('small','Результат автоматизированного прохода по исходной концепции. Срез расчётов определяется модельным manifest;21октября2026.'),('text',f'На оси {number(len(axis))} единиц рассчитаны дорожные районы тяготения и вложенная иерархия. Фиксированная масса использует собственную людность, наблюдаемые сервисы, организационный прокси и явно помеченный муниципальный контекст, без обратного обучения на притянутом населении. Границы представлены составом НП и дорожной доступностью; администрация служит внешним контекстом.'),('table',(['Уровень','Системы','С сельским окружением','Описательные типы'],levels)),('text','Содержательная типология охватывает девять типов рукописи. Проверка выполняется для центра на каждом уровне; описательный тип по наблюдаемому ядру и расширенная проверка всех иллюстраций/механизмов учитываются раздельно. Численность по годам, UNKNOWN и исходные данные доступны для каждого результата.'),('text',f'Источниковый ремонт2010 применил {number(source_summary["applied_to_model_axis_nodes"])} проверенных первичных связок. В конечных модельных узлах остаётся {number(source_summary["remaining_protected_secondary_nodes"])} защищённых вторичных значений с неподтверждённым точным охватом. Динамика и регрессии остаются описательными; отдельная проверка на первичной подвыборке показывает чувствительность к качеству источника.'),('text',f'Аграрный блок теперь содержит совместимую долю посевов2021 по {land["valid_ratio_rows"]} регионам: Росстат, хозяйства всех категорий / фактические угодья Росреестра на01.01.2022. Российский бонитет добавлен как {number(bon["nonnull_experimental_intervals"])} экспериментальных интервалов по мелкомасштабному атласу. Оба дополнения используются как явные сценарии чувствительности; региональная доля не названа собственной площадью поселения.'),('head','Что можно обсуждать по этому результату'),('text','Сопоставлять динамику центра, сельского окружения и системы; видеть иерархические связи и описательные типы; сравнивать массы и доступность на одной выборке; выбирать конкретные территории для независимой содержательной проверки. Карты и именные примеры сопровождаются исходными ID, годами и источниками.'),('head','Что определяет следующий научный шаг'),('text','Приоритет — уточнить повседневные связи и реальные мощности учреждений, расширить первичное подтверждение2010 и проверить устойчивость районов к ранговой схеме, скоростям и правилам географической привязки. Низкая посевная доля не означает заброшенность, рост OSM-записей не означает открытие учреждений, промышленное свидетельство не объясняет автоматически демографию всей системы.'),('small','Статус независимого гаранта: '+str(audit.get('decision',audit.get('state',audit.get('verdict',audit.get('status','см.receipt')))))+'. Полные таблицы, научный отчёт, атлас и GPKG читаются вместе с ограничениями источников.')]
    selected=types[types.operational_hypothesis.fillna(False)]
    if len(selected):
        typ_counts=selected.groupby('word_type').size().sort_index()
        b.insert(5,('text',f'Каноническая операционализация выделила {number(len(selected))} положительных сочетаний центр×уровень: '+', '.join('тип'+str(int(k))+' — '+number(v)for k,v in typ_counts.items())+'. Это описательные кандидаты с проверенным ядром и разновременными функциональными признаками (включая рекреационные данные и дороги2026), а не исторически доказанная функция2021; число сочетаний не является числом непересекающихся районов или доказанных механизмов.'))
    low=systems[systems.level.eq(1)]
    complete=low.system_population_complete_2010&low.system_population_complete_2021&low.rural_external_population_complete_2010&low.rural_external_population_complete_2021&low.center_population_2010.gt(0)&low.rural_external_population_known_sum_2010.gt(0)
    observed=low[complete]
    if len(observed):
        cc=observed.center_population_2021/observed.center_population_2010-1;rr=observed.rural_external_population_known_sum_2021/observed.rural_external_population_known_sum_2010-1
        b.insert(6,('text',f'На численно полной низовой подвыборке {number(len(observed))} систем центр и сельское окружение одновременно сокращаются в {number(((cc<0)&(rr<0)).sum())} случаях, центр растёт при сокращении окружения — в {number(((cc>0)&(rr<0)).sum())}. Это измеренная асимметрия демографической динамики в условно фиксированной сетке районов; историческая сопоставимость границ не установлена; она сама по себе не устанавливает миграционный или хозяйственный механизм.'))
    stability_path=root/'model/scenario_comparison/membership_stability.csv'
    if stability_path.exists():
        st=pd.read_csv(stability_path);st=st[(st.scenario_a.eq(model.name)|st.scenario_b.eq(model.name))&st.view.eq('lowest')]
        statements=[]
        inc=st[st.scenario_a.str.contains('inclusive')|st.scenario_b.str.contains('inclusive')]
        if len(inc):
            row=inc.iloc[0];statements.append(f'При включении географических кандидатов низовой центр совпадает в {100*row.same_center_fraction_among_both_assigned:.1f}% случаев среди {number(row.n_both_assigned)} НП, назначенных в обоих сценариях.')
        p0=st[st.scenario_a.str.contains('p0')|st.scenario_b.str.contains('p0')]
        if len(p0):
            row=p0.iloc[0];coverage=pd.read_csv(stability_path.with_name('scenario_coverage.csv'));cov=coverage[coverage.level.eq(1)].set_index('scenario').n_assigned_population_axis
            other=row.scenario_b if row.scenario_a==model.name else row.scenario_a
            added=int(cov[other]-cov[model.name]);statements.append(f'Снятие вероятностного порога (P0) сохраняет {number(row.n_same_center)} прежних назначений и добавляет {number(added)} новых низовых назначений. Сохранение старой подвыборки не означает100%устойчивости всей национальной сетки.')
        if statements:b.insert(7,('text',' '.join(statements)+' Различия охвата и типов приведены в отчёте; внешняя точность выбранных границ не установлена.'))
    cfg,_=configuration_for_model(model,read(model/'run_receipt.json'))
    if cfg.get('rank_index',{}).get('uses_modeled_catchment'):
        b.insert(3,('text','Ранги WordCi учитывают фиксированную массу и предварительную сельскую людность по наблюдаемому перечню переписи2021. После одного предварительного расчёта центральности строится окончательная вложенная иерархия. Исторические записи вне перечня переписи2021 не обнулены; неполнота по всем историческим единицам отражена диагностическими колонками, без полного альтернативного расчёта иерархии.'))
    return b
