#!/usr/bin/env python3
"""Static figures for fixed centre/rural-external demography, never causal types."""
import argparse
import json
from pathlib import Path
import pandas as pd

CATEGORY_KEYS = ['unknown', 'decline__decline', 'growth__growth', 'growth__decline',
                 'decline__growth', 'decline__unchanged', 'unchanged__decline',
                 'unchanged__growth', 'growth__unchanged', 'unchanged__unchanged']
CATEGORY_LABELS = ['Недостаточно сопоставимых данных', 'Центр и сельское окружение убывают',
                   'Центр и сельское окружение растут', 'Центр растёт, сельское окружение убывает',
                   'Центр убывает, сельское окружение растёт', 'Центр убывает, окружение без изменения',
                   'Центр без изменения, окружение убывает', 'Центр без изменения, окружение растёт',
                   'Центр растёт, окружение без изменения', 'Обе части без изменения']
COLORS = ['#b9c0c4', '#a26950', '#357b6c', '#3777a3', '#ce9b2d',
          '#985568', '#7c677f', '#539e8b', '#65a3c1', '#343c42']


def figure_values(readout):
    summary = json.loads((Path(readout)/'summary.json').read_text())
    groups = summary['joint_direction_counts']['strict_direct_observed']['joint_centre_rural_external_2002_2021']
    counts = {key: int(groups.get(key, 0)) for key in CATEGORY_KEYS}
    if sum(counts.values()) != summary['centres']:
        raise ValueError('Map category counts must reconcile to all centres')
    comparison = []
    for start in [2002, 2010]:
        for mode in ['strict_direct_observed', 'accepted_values']:
            g = summary['joint_direction_counts'][mode][f'joint_centre_rural_external_{start}_2021']
            unknown = int(g.get('unknown', 0))
            comparison.append({'start': start, 'mode': mode, 'complete': summary['centres']-unknown,
                               'unknown': unknown, 'denominator': summary['centres']})
    return {'classification': 'centre_and_rural_external_2002_2021_strict_primary',
            'counts': counts, 'comparison': comparison,
            'category_schema': [{'code': code, 'key': key, 'label': CATEGORY_LABELS[code], 'color': COLORS[code]}
                                for code, key in enumerate(CATEGORY_KEYS)],
            'observed_population_is_not_observed_trips': True,
            'rural_subset_is_not_all_external_members': True, 'causal_word_types_assigned': False}


def run(readout, registry, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from pyproj import Transformer
    readout, registry, output = Path(readout), Path(registry), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    values = figure_values(readout)
    classes = pd.read_parquet(readout/'centre_demographic_classes.parquet')
    centres = pd.read_parquet(registry/'level0_centres.parquet')
    selected = classes[classes.evidence_mode.eq('strict_direct_observed')]
    data = centres[['star_id', 'centre_settlement_id', 'centre_name', 'centre_region', 'lat', 'lon']].merge(
        selected[['star_id', 'joint_centre_rural_external_2002_2021']], on='star_id', validate='one_to_one')
    if len(data) != sum(values['counts'].values()):
        raise ValueError('Map does not include every centre exactly once')
    data['category'] = data.joint_centre_rural_external_2002_2021.map(dict(zip(CATEGORY_KEYS, range(10))))
    if data.category.isna().any() or data[['lat', 'lon']].isna().any().any():
        raise ValueError('Every map record requires actual coordinates and a category')
    transform = Transformer.from_crs('EPSG:4326', '+proj=laea +lat_0=55 +lon_0=100 +datum=WGS84 +units=m', always_xy=True)
    x, y = transform.transform(data.lon.to_numpy(), data.lat.to_numpy()); data['x'], data['y'] = x/1000, y/1000
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.labelcolor': '#33464e',
                         'text.color': '#263740', 'axes.edgecolor': '#b9c0c4', 'savefig.facecolor': '#fafbf9'})
    fig, ax = plt.subplots(figsize=(16, 11), facecolor='#fafbf9');ax.set_facecolor('#fafbf9')
    for code in range(10):
        part = data[data.category.eq(code)]
        ax.scatter(part.x, part.y, s=4 if code == 0 else 5, c=COLORS[code], alpha=.65 if code == 0 else .85,
                   linewidths=0, rasterized=True, zorder=1 if code == 0 else 2)
    ax.set_aspect('equal');ax.set_xlabel('Километры к востоку от центра проекции');ax.set_ylabel('Километры к северу')
    ax.grid(color='#e1e6e5', linewidth=.6);ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle(f'У {values["counts"]["decline__decline"]:,} центров убывают и центр, и сельское окружение'.replace(',', ' '), x=.06, y=.96, ha='left', fontsize=20, weight='bold')
    fig.text(.06,.918,'Население 2002–2021 годов · фиксированный состав окружений 2021 года · все 28 512 центров',fontsize=12)
    handles = [Line2D([], [], marker='o', linestyle='', color=COLORS[i], markersize=7,
                     label=f'{CATEGORY_LABELS[i]} — {values["counts"][key]:,}'.replace(',', ' '))
               for i,key in enumerate(CATEGORY_KEYS)]
    fig.legend(handles=handles, loc='lower left', bbox_to_anchor=(.05,.048), ncol=2, frameon=False,fontsize=10,
               columnspacing=2, handletextpad=.5, labelspacing=.65)
    fig.text(.06,.026,'Точки центров; равновеликая азимутальная проекция Ламберта. Серый — неизвестная динамика, а не отсутствие населения.',fontsize=10)
    fig.text(.06,.009,'Источник: связанная база переписей и расчёт прямых окружений 26.10.2026. Поездки и причинные типы Word не установлены.',fontsize=9)
    fig.subplots_adjust(left=.065,right=.98,bottom=.245,top=.885)
    fig.savefig(output/'centre_rural_demography_2002_2021.png',dpi=160);plt.close(fig)
    fig, ax = plt.subplots(figsize=(12, 6), facecolor='#fafbf9');ax.set_facecolor('#fafbf9')
    labels=[]
    for i,row in enumerate(values['comparison']):
        ax.barh(i,row['complete'],color='#357b6c',height=.6)
        ax.barh(i,row['unknown'],left=row['complete'],color='#d9dddf',height=.6)
        labels.append(f'{row["start"]}–2021 · '+('только первичные наблюдения' if row['mode']=='strict_direct_observed' else 'все принятые числа'))
        ax.text(row['complete']+350,i,f'{row["complete"]:,} определено'.replace(',',' '),va='center',fontsize=10,
                color='#24343a',bbox={'facecolor':'#fafbf9','alpha':.85,'edgecolor':'none','pad':2})
    ax.set_yticks(range(4),labels);ax.invert_yaxis();ax.set_xlim(0,31000)
    ax.set_xticks([0,10000,20000,28512],['0','10 000','20 000','28 512'])
    ax.set_xlabel('Число центров с определённой совместной динамикой')
    ax.spines[['top','right','left']].set_visible(False);ax.grid(axis='x',color='#e1e6e5');ax.set_axisbelow(True)
    fig.suptitle(f'Строгий вывод о 2010–2021 годах возможен только для {values["comparison"][2]["complete"]:,} центров'.replace(',', ' '),x=.04,y=.96,ha='left',fontsize=16,weight='bold')
    fig.text(.04,.875,'Серый — совместная динамика неизвестна. Полный знаменатель каждого варианта: 28 512 центров.',fontsize=10)
    fig.text(.04,.065,'«Все принятые числа» включают защищённые вторичные значения 2010 года; это не дополнительная выборка первичных наблюдений.',fontsize=9)
    fig.text(.04,.025,'Источник: одна база переписей и одинаковые составы 2021 года. Неполные суммы не названы населением всего окружения.',fontsize=9)
    fig.subplots_adjust(left=.36,right=.97,bottom=.23,top=.81)
    fig.savefig(output/'centre_rural_demography_comparability.png',dpi=160);plt.close(fig)
    (output/'figure_values.json').write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'figures':str(output),'values':values},ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readout',type=Path,required=True);parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();run(a.readout,a.registry,a.output)
