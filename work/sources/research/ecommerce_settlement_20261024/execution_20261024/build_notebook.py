"""Build the reproducible research companion; execute with nbclient afterwards."""
from pathlib import Path
import nbformat as nbf

OUT = Path(__file__).resolve().parent
nb = nbf.v4.new_notebook()
nb.metadata.kernelspec = {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}
nb.cells = [
    nbf.v4.new_markdown_cell('''# Маркетплейсы и система расселения: национальный эмпирический этап

## Результат и границы
Проверяем современное распределение инфраструктуры и селективность её размещения.
Положительные записи хотя бы одной сети обнаружены в 18 311 из 144 151 НП принятой
базы (12,70%); в этих НП жило 89,91% её населения по переписи 2021 года.
Распределение точек резко зависит от людности. Эти числа не измеряют изменение
системы во времени, торговый оборот или причинное влияние на население.

Данные: WB 21.10.2026; сторонний архив Ozon с заявленной датой 06.08.2026;
переписи 2002/2010/2021; официальная городская панель 2023–2025.
Территория: 81 обычный регион принятой сопоставимой базы, федеральные города
отдельно. Это не утверждение полного охвата всех современных территорий.'''),
    nbf.v4.new_markdown_cell('''## Метод и допущения
Единица — зачтённый физический населённый пункт переписи2021. Нулевая принятая
запись означает отсутствие подтверждения в выбранном источнике, а не отсутствие ПВЗ.
Для Ozon используется однозначное совпадение имени и проверка координат в пределах
1/5/10км: это правило привязки, а не радиус обслуживания. Источники платформ
неравноценны, их даты различаются, поэтому рыночные доли не оцениваются.
Популяционные веса относятся к 2021 году. Пространственная близость — по прямой,
не по дорогам; реальные поездки и ареалы обслуживания не наблюдаются.

Демографические сравнения — ассоциации нынешних записей сети с историческими
траекториями; год2021 не принимается универсальным началом воздействия.
Размерные и региональные страты показываются с явной общей поддержкой.
Границы поселений независимо не проверены на неизменность.'''),
    nbf.v4.new_markdown_cell('''## Данные и воспроизведение
Запускать из папки `execution_20261024`. Нужны локальные исходные parquet в соседней
`national/`; они не включены повторно в этот результат. `input_manifest.json`
содержит размеры и SHA256. Скрипты ниже заново выполняют все четыре блока.
Среда текущего запуска: `PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3`.
Для другой машины установить pandas, numpy, pyarrow, matplotlib, nbformat,
nbclient и ipykernel в обычное Python-окружение.'''),
    nbf.v4.new_code_cell('''from pathlib import Path
import contextlib
import io
import json
import runpy
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display

ROOT = Path.cwd()
assert (ROOT.parent / 'national').is_dir(), 'Нужен cwd=execution_20261024'
plt.rcParams.update({'figure.figsize': (10, 5), 'font.size': 11,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.axisbelow': True, 'savefig.dpi': 150})
for script in ['geography/analyze_geography.py', 'demography/analyze_demography.py',
               'accessibility/analyze_accessibility.py', 'audit/audit.py',
               'audit/peer_review.py']:
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(ROOT / script), run_name='__main__')
    print('Выполнен:', script)
'''),
    nbf.v4.new_markdown_cell('''## Современная конфигурация
Таблица сохраняет знаменатели: все НП принятой базы, в том числе нулевой людности;
доля жителей рассчитывается по собственному населению НП2021.'''),
    nbf.v4.new_code_cell('''geo = json.loads((ROOT/'geography/summary.json').read_text())
g = geo['national']
display(pd.DataFrame([
    {'Положительные записи': label, 'Число НП': g[key+'_positive_np_n'],
     'Доля всех НП, %': 100*g[key+'_positive_np_share'],
     'Доля населения2021, %': 100*g[key+'_positive_population2021_share']}
    for label,key in [('WB','WB'),('Ozon, экспериментально','Ozon'),
                      ('Хотя бы одна сеть','either'),('Обе сети','both')]
]).round(2))
sizes = pd.read_csv(ROOT/'geography/by_size.csv')
sizes = sizes[~sizes.size2021.eq('00_zero')].copy()
labels = {'01_1_100':'1–100','02_101_500':'101–500',
          '03_501_1000':'501–1000','04_1001_3000':'1001–3000',
          '05_3001_10000':'3001–10 000','06_10001_50000':'10 001–50 000',
          '07_50001_100000':'50 001–100 000','08_100001_500000':'100 001–500 000',
          '09_over_500000':'Более 500 000'}
fig, ax = plt.subplots(figsize=(10, 5))
ax.barh(sizes.size2021.map(labels).fillna(sizes.size2021),
        100*sizes.either_positive_np_share, color='#426b97')
ax.set_xlim(0, 105)
ax.set_xlabel('Доля НП с положительной записью хотя бы одной сети, %')
ax.set_ylabel('Людность НП по переписи2021')
ax.set_title('Размерный градиент современного размещения')
ax.grid(axis='x', alpha=0.2)
ax.invert_yaxis()
fig.tight_layout()
fig.savefig(ROOT/'presence_by_size.png')
plt.show()
'''),
    nbf.v4.new_markdown_cell('''## Потенциальная близость
Здесь другой знаменатель: только 123 137 населённых НП с координатами.
График сопоставляет два набора известных точек. Добавление Ozon — арифметическое
расширение набора, а не наблюдаемый переход от прошлого к настоящему.'''),
    nbf.v4.new_code_cell('''p = pd.read_csv(ROOT/'accessibility/proximity_thresholds.csv')
p = p[p.dimension.eq('national')]
fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
for ax,unit,title in zip(axes, ['np','population'],
                         ['Доля населённых НП', 'Доля населения2021']):
    x = range(len(p))
    ax.bar([v-0.18 for v in x], p[f'wb_near_{unit}_pct'], width=0.36,
           color='#426b97', label='Известные WB')
    ax.bar([v+0.18 for v in x], p[f'either_near_{unit}_pct'], width=0.36,
           color='#d79533', label='WB + архив Ozon')
    ax.set_xticks(list(x), [f'≤{int(r)} км' for r in p.radius_km])
    ax.set_title(title)
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.2)
    ax.set_xlabel('Расстояние по прямой до известной точки')
axes[0].set_ylabel('% своего знаменателя')
axes[1].legend(loc='lower right')
fig.suptitle('Близость жителей и поселений — разные пространственные картины')
fig.tight_layout()
fig.savefig(ROOT/'proximity_comparison.png')
plt.show()
display(p[['radius_km','inhabited_settlements','census_population2021',
           'wb_near_np_pct','either_near_np_pct',
           'wb_near_population_pct','either_near_population_pct']].round(2))
'''),
    nbf.v4.new_markdown_cell('''## Историческая траектория и отбор
Показываем частоту убыли, а не среднее процентных приростов, чувствительное к
малой исходной людности. Стандартизация по исходной людности2002, региону и типу
поселения ограничена стратами, где есть хотя бы пять НП в каждой сравниваемой группе.
Она не устраняет эндогенность размещения и не является оценкой эффекта.
Подробные численности и варианты правил привязки находятся в CSV.'''),
    nbf.v4.new_code_cell('''raw = pd.read_csv(ROOT/'demography/trajectory_raw.csv')
display(raw[(raw.period=='2002_2021') &
            (raw.exposure=='either_5km_positive')][
    ['positive_evidence','n','decline_n','decline_share_pct',
     'median_population_change_pct','median_population_2021']].round(2))
standardized = pd.read_csv(ROOT/'demography/trajectory_baseline2002_standardized.csv')
selected = standardized[(standardized.exposure=='either_5km_positive') &
                        (standardized.strata=='region_size2002') &
                        (standardized.endpoint_filter=='all_observed2021')]
display(selected[['min_n_per_group','supported_n','supported_pct',
                  'standardized_decline_positive_pct','standardized_decline_no_positive_pct',
                  'difference_percentage_points','overlap_weighted_decline_positive_pct',
                  'overlap_weighted_decline_no_positive_pct',
                  'overlap_weighted_difference_pp']].round(2))
'''),
    nbf.v4.new_markdown_cell('''## Что установлено и что пока не проверено
Сеть имеет выраженный размерный градиент: высокая доля жителей с положительными
записями сочетается с гораздо меньшей долей поселений. Инфраструктура обнаружена
и вне городов, но это не доказывает потерю центрами покупателей или возникновение
новых действительных обслуживающих ареалов.

Без повторных сопоставимых срезов сети нельзя установить рассредоточение во
времени. Без независимой истории физических магазинов нельзя измерить их
закрытие; регистрационные организации — отдельный показатель. Для населения
сельских НП полного ежегодного постпериода не получено. Городская панель2023–2025
сопоставляется с будущим срезом2026 лишь описательно.

Аудит и точные ограничения: `audit/findings.txt`; содержательная сводка:
`RESEARCH_RESULTS.txt`. Полный литературы план: соседняя
`literature_plan_20261024/RESEARCH_PLAN.txt`. Вычисления выполнены; причинная
оценка трансформации не выполнена из-за отсутствия подходящей истории.'''),
]
nbf.validate(nb)
nbf.write(nb, OUT/'national_research.ipynb')
print(OUT/'national_research.ipynb')
