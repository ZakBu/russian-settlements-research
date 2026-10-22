#!/usr/bin/env python3
"""Build a Russian readout from completed immutable analysis and independent receipts; no refit."""
from pathlib import Path
import json,hashlib,datetime
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[4];B=R/'research/sgrt_word_completion_20261021';A=B/'analysis/cycle06_access_v2_baseline';H=B/'analysis/cycle06_access_v2_baseline_readout'
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def table(frame):
 def value(x):
  if pd.isna(x):return '—'
  return str(x).replace('|','/')
 return '| '+' | '.join(frame.columns)+' |\n| '+' | '.join(['---']*len(frame.columns))+' |\n'+'\n'.join('| '+' | '.join(value(x) for x in row)+' |' for row in frame.itertuples(index=False,name=None))
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
assert not H.exists();H.mkdir()
source=[A/f for f in ['model_metrics.csv','coefficient_intervals.csv','system_predictions.parquet','sample_gates.csv','grouped_cv_folds.csv','spatial_residual_diagnostics.csv','region_cluster_bootstrap_intervals.csv','whole_system_outcome_scope.csv','system_analysis_features.parquet','effective_analysis_inputs.json','run_receipt.json','output_manifest.json']]+[B/'reviews/cycle06/regression_actual_independent/audit.json',B/'reviews/cycle06/regression_actual_independent/spatial_audit.json',B/'analysis/cycle06_access_v2_baseline_figures/render_receipt.json']
before={str(p.relative_to(R)):sha(p) for p in source};receipt=json.loads((A/'run_receipt.json').read_text());assert receipt['status']=='ACTUALLY_COMPUTED_DESCRIPTIVE_REGRESSIONS' and receipt['source_unchanged_verified']
m=pd.read_csv(A/'model_metrics.csv');g=pd.read_csv(A/'sample_gates.csv');coef=pd.read_csv(A/'coefficient_intervals.csv');fold=pd.read_csv(A/'grouped_cv_folds.csv');sp=pd.read_csv(A/'spatial_residual_diagnostics.csv');boot=pd.read_csv(A/'region_cluster_bootstrap_intervals.csv');features=pd.read_parquet(A/'system_analysis_features.parquet');config=json.loads((A/'effective_analysis_inputs.json').read_text())
assert len(m)==30 and len(g)==88 and len(boot)==183 and boot.full_rank_replicates.eq(499).all();assert m.comparison_family.eq('A_M1_M2').all()
primary=m[m.scenario.eq('A_M1_M2__primary')];summary=[]
for level,z in primary.groupby('level'):
 z=z.set_index('model');gg=g[g.scenario.eq('A_M1_M2__primary')&g.level.eq(level)].iloc[0];f=fold[fold.scenario.eq('A_M1_M2__primary')&fold.level.eq(level)];f1=f[f.model.eq('M1')].sort_values('fold');f2=f[f.model.eq('M2')].sort_values('fold');assert f1[['level','fold','n_train','n_test','train_regions','test_regions']].reset_index(drop=True).equals(f2[['level','fold','n_train','n_test','train_regions','test_regions']].reset_index(drop=True))
 summary.append({'Уровень':int(level),'N':int(z.loc['M1','n']),'Регионов':int(z.loc['M1','regions']),'Фолдов':len(f1),'Тест-N по фолдам':'; '.join(map(str,f1.n_test.tolist())),'Доля всех систем':f'{100*z.loc["M1","n"]/gg.all_systems:.2f}%','R² train M1→M2':f'{z.loc["M1","r2"]:.4f} → {z.loc["M2","r2"]:.4f}','R² OOF M1→M2':f'{z.loc["M1","group_oof_r2_train_mean_baseline"]:.4f} → {z.loc["M2","group_oof_r2_train_mean_baseline"]:.4f}','ΔR² OOF':f'{z.loc["M2","group_oof_r2_train_mean_baseline"]-z.loc["M1","group_oof_r2_train_mean_baseline"]:+.4f}','RMSE OOF M1→M2':f'{z.loc["M1","group_oof_rmse"]:.3f} → {z.loc["M2","group_oof_rmse"]:.3f}'})
summary=pd.DataFrame(summary);summary.to_csv(H/'primary_A_summary.csv',index=False)
fold[fold.scenario.eq('A_M1_M2__primary')].to_csv(H/'primary_A_exact_folds.csv',index=False)
coef[coef.scenario.eq('A_M1_M2__primary')&coef.model.eq('M2')].to_csv(H/'primary_A_M2_all_coefficients.csv',index=False)
g[g.scenario.str.endswith('__primary')].to_csv(H/'primary_A_B_gates.csv',index=False)
m.to_csv(H/'all30_models.csv',index=False)
# Univariate availability is overlapping diagnostic, not an additive exclusion decomposition.
availability=[]
for level,z in features.groupby('level'):
 for modelset,models in [('A_M1_M2',['M1','M2']),('B_M1_M2_M3_configuration_observed',['M1','M2','M3'])]:
  for field in dict.fromkeys(t for model in models for t in config['model_terms'][model]):
   vals=pd.to_numeric(z[field],errors='coerce');ok=vals.notna()&np.isfinite(vals);eligible=z.outcome_system_change_pct.notna();availability.append({'comparison_family':modelset,'level':int(level),'field':field,'all_systems':len(z),'outcome_observed':int(eligible.sum()),'field_finite_among_all':int(ok.sum()),'field_finite_and_outcome_observed':int((ok&eligible).sum()),'missingness_reasons_overlap_not_additive':True})
pd.DataFrame(availability).to_csv(H/'primary_required_field_availability.csv',index=False)
spatial=sp[sp.scenario.eq('A_M1_M2__primary')&sp.model.eq('M2')][['level','group_oof_moran_i','group_oof_two_sided_permutation_p']].copy();spatial.to_csv(H/'primary_A_M2_heldout_spatial.csv',index=False)
quality=g[g.scenario.eq('A_M1_M2__primary')][['level','common_sample_median_system2010_secondary_population_share','common_sample_median_rural2010_secondary_population_share']].copy();quality.to_csv(H/'primary_A_source_quality.csv',index=False)
# All actualscenarios, including zero-estimation families, remain in the full gate ledger.
g.to_csv(H/'all88_sample_gates.csv',index=False)
neg=int(m.group_oof_r2_train_mean_baseline.lt(0).sum());assert neg==0
numbers=[]
for level in [1,2,3]:
 z=coef[(coef.scenario=='A_M1_M2__primary')&coef.model.eq('M2')&coef.level.eq(level)&coef.term.eq('log_own_mass2021')].iloc[0];numbers.append(f'уровень{level}: {z.beta:.2f} [{z.ci95_lower:.2f}; {z.ci95_upper:.2f}]')
text=f'''# Cycle06: фактический описательный регрессионный расчёт

На принятом дорожном сценарии2021 оценены30моделей семействаA (M1/M2). Собственная масса центра положительно связана с демографической динамикой в доступной выборке, но добавление аграрного и агроклиматического контекста не даёт устойчивого улучшения переноса на другие регионы. В основном сравнении прирост OOF R² составляет+0.0112 на первом уровне и−0.0483/−0.0251 на втором/третьем. Модели M3 не оценены из-за недостаточной совместной выборки. Это не нулевой эффект конфигурации.

Все расчёты реально выполнены. Независимо проверены552численных условия (OLS/CR1, фолды, OOF,88gates,183интервала×499парных региональных bootstrap-повторов, исходные агрегаты и защита внешних центров) и109пространственных условий (все60Moran×499перестановок). Это приёмка точных условных вычислений, а не закрытие32Word-требований, подтверждение причинных механизмов или национальная репрезентативность.

## Фиксированный дизайн и фактические выборки

M1 включает logмассы2021, logнаселения исходного состава2010 и log1pпрямого времени от сельского населения к собственному центру. M2 добавляет log1pмуниципальной урожайности зерновых2021, сумму активных температур, летний P/PET и почвенный прокси GAEZ. Контексты агрегированы с известными2010весами сельского населения при пороге покрытия0.8 и требовании известных весов всех наблюдаемых членов. GAEZ не является российским бонитетом. Уровни анализируются раздельно; самостоятельный коэффициент «эффекта порядка» здесь не оценивался.

СемействоA сравнивает M1/M2 на одних строках и фолдах. СемействоB должно сравнивать M1/M2/M3 на собственной общей выборке с известной конфигурацией. МеждуA иB не вычисляется эффект добавления контекста. Низовой структурный уровень имеет неизвестную конфигурацию, а не моноцентрический ноль.

{table(summary)}

Во всех первичных оценённых сравнениях использованы5региональных фолдов. Для каждого уровня M1/M2 имеют абсолютно одинаковые тестовые строки; регионы обучения и теста не пересекаются. Числа тестовых регионов по фолдам: уровень1 —12/11/11/11/12; уровень2 —12/12/11/11/12; уровень3 —8/9/9/9/9. Точные train/testN иG сохранены в `primary_A_exact_folds.csv` для обеих моделей. Числа в таблице — системные строки конкретного уровня; их нельзя складывать как независимые непересекающиеся районы.

OOF R² определён как1−Σ(y−ŷOOF)²/Σ(y−среднее обучения соответствующего фолда)². Это точечные оценки. Интервалы коэффициентов и bootstrap не являются интервалами разности OOF R². Во всех30оценённых моделях абсолютный OOF R² положителен; отрицательный результат здесь означает снижение OOF R² после добавления контекста. На обучении R² растёт во всех трёх основных сравнениях, что само по себе не доказывает улучшение переноса.

На уровне4 первичнаяA имеет только19систем из13регионов и не оценивается. ПервичнаяB имеет N=0/47/32/0 при минимуме140 по числу объявленных предикторов; уровни1–4 соответственно. МинимумA —80; для моделей с дополнительным аграрным/бонитетным предикторомA —90. Пороги не менялись после результатов. Из88сценарно-уровневыхgates15допустили сравнение двух моделей,73остались недостаточными; все44gates семействаB не прошли. Нельзя подменять отсутствующий M3 результатамиA или старым принудительно моноцентрическим расчётом.

## Коэффициенты и пространственная диагностика

Коэффициент logсобственноймассы в M2, в п.п. изменения населения на1SDпредиктора, с95%региональным CR1интервалом: {'; '.join(numbers)}. Это ассоциация при фиксированной модели и источниках. В массу2021входит население2021; сопоставление с динамикой2010–2021 поэтому не является независимым прогнозом или причинным эффектом. Собственнаямасса не обучалась на предсказанном ею же окружении, но отсутствие круговой калибровки не устраняет эту ретроспективную эндогенность. Все коэффициенты, включая интервалы, пересекающие ноль, сохранены в `primary_A_M2_all_coefficients.csv`.

Остатки сохраняют пространственную структуру даже после проверки на других регионах:

{table(spatial.round(6).rename(columns={'level':'Уровень','group_oof_moran_i':'Moran I OOF, M2','group_oof_two_sided_permutation_p':'Перестановочный p'}))}

Диагностика использует симметризованное объединение8ближайших соседей по большой окружности с нормировкой строк. Независимый проверяющий восстановил смежность полным попарным расчётом; граничных ничьих8-го соседа нет. Перестановок499; минимальный ненулевойp=0.002. Это дополнительная причина осторожно интерпретировать региональные связи, а не доказательство отсутствия пространственного смещения.

## Пять содержательных блоков чувствительности, не получивших оценок

| Блок | ОбщаяA-выборка по уровням1/2/3/4 | Причина сохранённого ограничения |
| --- | --- | --- |
| Исторический посевы/угодья2008 |0/0/0/0|Строгие собственные интервалы года и история кода не поддерживают отношение. Не восстановлены прежние нестрогие значения и не требуется будущее измерение ради собственной исторической идентичности.|
| Экспериментальные нижняя/верхняя границы бонитета |15/43/34/4 для каждой границы|Одинаковые наблюдения двух границ, но N меньше90; грубая, не принятая в основную модель геопривязка Атласа не превращается в измерение НП.|
| Только первичные переписные значения |5/16/13/1|Недостаточно совместно первичных источников и контекстов; также мало регионов.|
| Первичные плюс рассмотренные поддерживающие источники |6/17/14/1|Расширение происхождения не обеспечивает минимум80 и10регионов; результат не достроен по вторичным значениям.|
| Сельскохозяйственная перепись2021: собственный муниципальный знаменатель |48/62/26/4|Реально доступен10-региональный корпус, но совместная выборка меньше90; производительская совокупность не смешана с общим региональным земельным фондом.|

Оценены отдельныеA-чувствительности: исходом является только сельская зона (N=298/399/217), положительное логотношение населения (296/397/215), добавлен региональный земельный контекст (296/397/215), использована урожайность2010 (143/203/124). Каждая из них содержит M1/M2 на трёх уровнях; вместе с основным сравнением это30оценок. Историческая урожайность допускается по двум проверенным путям идентичности источника, но юридическая эквивалентность территорий не доказана. Ни одна из этих чувствительностей не заменяет отсутствующий собственный муниципальный знаменатель другим понятием.

## Источники, выборочное покрытие и внешние центры

8504системные строки включены в исходную аналитическую таблицу, но основная общая выборка покрывает только7.39%,13.43% и18.60%систем уровней1–3. Доступность сельских2010весов, муниципальной урожайности, климатических и почвенных контекстов совместно отбирает ограниченный набор районов. Нельзя считать эти пропуски случайными или переносить коэффициенты на всю Россию без отдельного обоснования. `primary_required_field_availability.csv` показывает однопоказательное покрытие; причины исключения перекрываются и не суммируются.

В основнойA-выборке медианная доля вторичного источника в известном населении всей системы2010 составляет33.0%,22.6%,25.9% на уровнях1–3; в известном сельском населении медиана равна100% на всех трёх уровнях. Это не утверждение ошибочности каждого значения, но существенно ограничивает точность, которую можно приписать результату. Поэтому результаты названы условными на исходных значениях, а малые чисто первичные выборки не заменены более удобным допуском после расчёта.

Центрыctx:RU-FED-MOW иctx:RU-FED-SPB не имеют наблюдённого собственного населения города в обоих годах. Их шесть системных строк уровней2–4 исключены из исходов, включающих центр и всю систему; полнота исходного состава не подменяет отсутствующий центр. Территориальные агрегаты Москвы/Петербурга не подставлялись. Реальные сельские члены, их маршруты, сельские исходы и доступность сохранены. На таких сельских чувствительностях базовый контроль населения относится к известному исходному составу, а не к выдуманной полной численности города. Проверяемые флаги находятся в исходной `whole_system_outcome_scope.csv`.

Все183коэффициентных bootstrap-интервала реально вычислены по499полноранговым региональным повторам. В каждом сравнении одни и те же выборки регионов используются обеими моделями; шкала1SD зафиксирована по исходной общей выборке. Эти интервалы условны на зафиксированных источниках и границах: они не распространяют неопределённость связок, дорожного профиля, кандидатов, порядков или модели выделения зон. РегиональнаяCV переоценивает OLS и стандартизацию, а не всю национальную цепочку выделения СГРТ.

## Файлы и граница вывода

Численные первоисточники: `../cycle06_access_v2_baseline/` — все30моделей,88gates, коэффициенты, предсказания, фолды, bootstrap, Moran и подписанныеSHA. Принятые для показа иллюстрации: `../cycle06_access_v2_baseline_figures/` —8рисунков вPNG/PDF/SVG без нового fit. Их карты остатков являются точечной географией фактических выборок, а не полной картой населения России; цвета ограничены общим95-м процентилем абсолютного остатка внутри семьи. Исходные совместимые графики, рассчитанные старой процедурой для отсутствующего M3, не приняты как итоговые иллюстрации.

Независимые проверки: `../../reviews/cycle06/regression_actual_independent/audit.json` и `spatial_audit.json`. Полная пререгистрация и независимый109-пунктовый допуск находятся в источниковом манифесте. Основной код/данные не изменялись в ходе расчёта; это проверено до/после. Настоящая сводка не является новым решением о закрытии Word-матрицы: роль конфигурации статистически не оценена, механизмы типологии не подтверждаются регрессиями автоматически, научная интерпретация национальных конфигураций имеет собственную проверку.
'''
(H/'RESULTS.md').write_text(text)
assert before=={str(p.relative_to(R)):sha(p) for p in source};dump(H/'readout_receipt.json',{'status':'ACTUAL_RUSSIAN_READOUT_FROM_FROZEN_INDEPENDENTLY_AUDITED_TABLES_NO_REFIT','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':before,'source_unchanged':True,'code_sha256':sha(Path(__file__)),'models_actual':30,'unestimated_configuration_effect_not_zero':True,'all183bootstrap_intervals_499draws':True,'no_cross_family_effect_claim':True,'no_new_Word_requirement_approval_or_stop_decision':True,'outputs':{p.name:sha(p) for p in H.iterdir() if p.is_file()}});dump(H/'freeze_manifest.json',{'status':'FROZEN_ACTUAL_REGRESSION_READOUT_WITH_INDEPENDENT_NUMERIC_AND_SPATIAL_RECEIPTS','files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in H.iterdir() if p.is_file()},'source_tables_unchanged':True,'scientific_completion_claim':False});print(json.dumps({'path':str(H),'readout_sha256':sha(H/'RESULTS.md'),'source_unchanged':True}))
