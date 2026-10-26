#!/usr/bin/env python3
"""Six-page static atlas of direct level-zero centres and source limitations.

Every displayed count is read from the supplied registry or route tables.
The atlas draws settlement points and model relations, never inferred borders.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, FuncFormatter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_mass.figures import project

PAPER = '#FAFBF9'; INK = '#253640'; MUTED = '#596A73'; GREY = '#BAC3C6'
COLORS = {3: '#3D8179', 2: '#236A95', 1: '#B39942', 0: '#8A959C'}
FUNCTIONS = {'medical_basic': 'Базовая медицина', 'school': 'Школа', 'grocery': 'Продукты'}
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'text.color': INK,
                     'axes.labelcolor': INK, 'axes.edgecolor': GREY, 'pdf.fonttype': 42})


def num(value):
    return f'{int(value):,}'.replace(',', ' ')


def wrap(value, width=120):
    return '\n'.join(textwrap.wrap(str(value), width=width))


def page(title, subtitle, number):
    fig = plt.figure(figsize=(11.69, 8.27), facecolor=PAPER)
    fig.text(.06, .95, 'ЦЕНТРЫ ПОВСЕДНЕВНОГО ОБСЛУЖИВАНИЯ  /  РОССИЯ', fontsize=8.5, color=MUTED)
    fig.text(.06, .89, title, fontsize=20, weight='bold')
    fig.text(.06, .843, wrap(subtitle, 136), fontsize=9.4, color=MUTED, va='top', linespacing=1.4)
    fig.text(.06, .060, 'Неизвестное не означает отсутствие • местное время 0 — наличие услуги в НП • линии — модельные связи, не трассы', fontsize=7.1, color=MUTED)
    fig.text(.06, .035, 'НП и население: переписи • учреждения: даты источников • дороги OSM 2021 • геометрия не является юридической границей', fontsize=7, color=MUTED)
    fig.text(.94, .035, f'{number:02}', ha='right', fontsize=10, color=MUTED)
    return fig


def style(ax, xlabel=None, ylabel=None, map_plot=False):
    ax.set_facecolor(PAPER)
    for side in ['top', 'right']: ax.spines[side].set_visible(False)
    ax.tick_params(labelsize=8.5)
    ax.grid(color='#E0E6E5', lw=.55, axis='both' if map_plot else 'y', zorder=0)
    if xlabel: ax.set_xlabel(xlabel, fontsize=9)
    if ylabel: ax.set_ylabel(ylabel, fontsize=9)
    if map_plot: ax.set_aspect('equal', adjustable='box')


def local_map(ax, selected, members, background, *, max_labels=7):
    part = members[members.star_id.eq(selected.star_id)].copy()
    anchor = part[part.member_role.eq('centre')]
    if len(anchor) != 1: raise ValueError('Local map needs exactly one centre anchor')
    lon0, lat0 = float(anchor.lon.iloc[0]), float(anchor.lat.iloc[0])
    part = part[np.isfinite(part.lat) & np.isfinite(part.lon)]
    x, y = project(part.lon, part.lat, lon0, lat0)
    span = max(float(np.ptp(x)), float(np.ptp(y)), 3.)
    pad = max(1.2, span * .12)
    xmin, xmax, ymin, ymax = min(x)-pad, max(x)+pad, min(y)-pad, max(y)+pad
    near = background[(background.lat-lat0).abs().lt(max(.1, span/70))
                      & (background.lon-lon0).abs().lt(max(.1, span/35))]
    bx, by = project(near.lon, near.lat, lon0, lat0)
    ax.scatter(bx, by, s=5, c=GREY, alpha=.45, linewidths=0, rasterized=True, zorder=1)
    for px, py, count, role in zip(x, y, part.core_family_count, part.member_role):
        if role == 'centre': continue
        ax.plot([0, px], [0, py], color=COLORS.get(int(count), GREY), lw=.7, alpha=.6, zorder=2)
    external = part.member_role.ne('centre').to_numpy()
    ax.scatter(x[external], y[external], s=20, c=[COLORS.get(int(v), GREY) for v in part.loc[external, 'core_family_count']],
               linewidths=.25, edgecolors=INK, rasterized=True, zorder=3)
    ax.scatter([0], [0], marker='*', s=125, c=INK, zorder=5)
    ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
    style(ax, 'км к востоку', 'км к северу', map_plot=True)
    # Labels sample spatially separated points; every member remains drawn.
    coords=np.column_stack([x,y]); labelled=[int(np.argmin(x*x+y*y))]
    while len(labelled)<min(max_labels,len(part)):
        distance=np.min(((coords[:,None,:]-coords[labelled][None,:,:])**2).sum(axis=2),axis=1)
        distance[labelled]=-1
        labelled.append(int(np.argmax(distance)))
    annotations=[]
    for position in labelled:
        row=part.iloc[position]
        annotations.append(ax.annotate(str(row['name']),(x[position],y[position]),xytext=(4,7),
            textcoords='offset points',fontsize=6.9,
            bbox=dict(facecolor=PAPER,alpha=.88,edgecolor='none',pad=.5),zorder=6))
    ax.figure.canvas.draw();renderer=ax.figure.canvas.get_renderer();placed=[]
    for annotation in annotations:
        for dx,dy in [(5,8),(5,-14),(-5,8),(-5,-14),(5,22),(-5,22),(12,-25),(-12,-25),(20,4),(-20,4)]:
            annotation.set_position((dx,dy));annotation.set_ha('right' if dx<0 else 'left')
            bbox=annotation.get_window_extent(renderer).expanded(1.04,1.07)
            if not any(bbox.overlaps(previous) for previous in placed):break
        placed.append(bbox)
    return part


def chosen_case(centres, name, region):
    rows = centres[centres.centre_name.eq(name) & centres.centre_region.eq(region)]
    return None if rows.empty else rows.sort_values('centre_settlement_id').iloc[0]


def run(registry, scenario, reference_path, output, before_summary=None):
    output.mkdir(parents=True, exist_ok=True)
    centre_path = registry / 'level0_centres.parquet'
    member_path = registry / 'level0_memberships.parquet'
    edge_path = scenario / 'daily_edges.parquet'
    centres = pd.read_parquet(centre_path)
    members = pd.read_parquet(member_path)
    edges = pd.read_parquet(edge_path)
    core = edges[edges.service_family.isin(FUNCTIONS)].copy()
    ref = pd.read_parquet(reference_path).dropna(subset=['source_record_id'])
    ref = ref[ref.analysis_origin.fillna(False) & ref.lat.notna() & ref.lon.notna()]
    anchors = members[members.member_role.eq('centre')].set_index('star_id')
    if anchors.index.duplicated().any(): raise ValueError('Repeated centre anchor')
    if centres.star_id.duplicated().any(): raise ValueError('Repeated registered centre')
    for column in ['lat', 'lon']:
        centres[column] = centres.star_id.map(anchors[column])
    counts = centres.own_known_basic_function_count.value_counts().sort_index().to_dict()
    before = json.loads(before_summary.read_text()) if before_summary else None
    audit = {'registered_centres': len(centres), 'by_own_functions': {str(k): int(v) for k,v in counts.items()},
             'pages': [], 'actual_trips_observed': False, 'exclusive_partition': False,
             'source_inputs_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in [centre_path, member_path, edge_path, reference_path]}}
    pdf_path = output / 'identity_repair_atlas.pdf'
    with PdfPages(pdf_path) as pdf:
        def save(fig, stem):
            fig.savefig(output / (stem+'.png'), dpi=150, facecolor=PAPER)
            pdf.savefig(fig, facecolor=PAPER); plt.close(fig); audit['pages'].append(stem)

        # 1. All direct centres, never the strict common-three subset alone.
        fig = page('Центры нулевого уровня',
                   'Модель сохраняет центры с внешними жилыми НП хотя бы по одной базовой функции. Собственный набор центра показан отдельно.', 1)
        for x, value, label in [(.06, len(centres), 'центров с внешним окружением'),
                                (.39, counts.get(3, 0), 'записаны три выбранные функции'),
                                (.72, int(centres.external_participant_count.sum()), 'пар «центр — внешний НП»')]:
            fig.text(x, .746, num(value), fontsize=25, weight='bold', color=INK)
            fig.text(x, .711, wrap(label, 35), fontsize=8.7, color=MUTED, va='top')
        ax = fig.add_axes([.08, .22, .85, .45])
        x,y = project(ref.lon, ref.lat); ax.scatter(x,y,s=.3,c=GREY,alpha=.35,linewidths=0,rasterized=True)
        handles = []
        for count in sorted(counts):
            group = centres[centres.own_known_basic_function_count.eq(count)]
            x,y = project(group.lon, group.lat)
            ax.scatter(x,y,s=2.2 if count==3 else 1.,c=COLORS[count],alpha=.8,linewidths=0,rasterized=True,zorder=count+2)
            handles.append(Line2D([],[],marker='o',ls='',color=COLORS[count],markersize=5,
                                  label=f'{count} '+('известная функция' if count==1 else 'известные функции')+f'; центров: {num(len(group))}'))
        style(ax, 'Равновеликая проекция Ламберта; км к востоку', 'км к северу', map_plot=True)
        ax.legend(handles=handles,loc='lower left',fontsize=8,framealpha=.95)
        fig.text(.06,.12,'Три функции: школа, базовая медицина, продукты. Серый фон — остальные точки НП.\nЧисло пар не является числом разных поселений: прямые окружения пересекаются.',fontsize=8.7)
        save(fig, '01_level0_country')

        # 2. Sizes in equal units with the complete tail retained.
        fig = page('Размеры прямого окружения',
                   'Диаметр — расстояние между крайними точками состава. Это не радиус и не автомобильное время.', 2)
        ax = fig.add_axes([.10,.26,.37,.48]); bx = fig.add_axes([.58,.26,.34,.48])
        for count in [1,2,3]:
            group = centres[centres.own_known_basic_function_count.eq(count)]
            d = group.core_diameter_km.dropna().sort_values().to_numpy()
            if len(d): ax.step(d,np.arange(1,len(d)+1)/len(d),where='post',color=COLORS[count],lw=1.6,label=f'{count} '+('функция' if count==1 else 'функции')+f'; центров: {num(len(d))}')
            n = group.external_participant_count.dropna().sort_values().to_numpy()
            if len(n): bx.step(n,np.arange(1,len(n)+1)/len(n),where='post',color=COLORS[count],lw=1.6)
        style(ax,'Диаметр, км','Доля центров не больше указанного размера'); ax.set_ylim(0,1.03); ax.legend(fontsize=8,loc='lower right')
        style(bx,'Внешних жилых НП','Доля центров'); bx.set_ylim(0,1.03)
        diam = centres.core_diameter_km.dropna()
        fig.text(.06,.15, f'Все центры: медиана {diam.median():.2f} км; 95-й процентиль {diam.quantile(.95):.2f} км; максимум {diam.max():.2f} км.\n'
                 f'Диаметр отсутствует у {num(centres.core_diameter_km.isna().sum())} из {num(len(centres))} центров. Хвост распределения не отрезан.',fontsize=9.5)
        audit['diameter_km']={'median':float(diam.median()),'p95':float(diam.quantile(.95)),'max':float(diam.max())}
        save(fig,'02_direct_sizes')

        # 3. Three concrete places, no fabricated replacement if absent.
        fig = page('Как выглядит центр и его соседи',
                   'Точки — населённые пункты. Цвет внешней точки показывает число базовых направлений к этому центру, а не его собственную полноту.',3)
        cases = [('Новоузенск','саратовская'),('Питерка','саратовская'),('Симферополь','крым')]
        for slot,(name,region) in enumerate(cases):
            ax = fig.add_axes([.07+slot*.313,.27,.255,.46]); selected = chosen_case(centres,name,region)
            if selected is None:
                ax.text(.5,.5,'Не вошёл в этот\nрасчётный вариант',ha='center',va='center',transform=ax.transAxes)
                ax.set_title(name,fontsize=11);ax.set_axis_off();continue
            local_map(ax,selected,members,ref,max_labels=5)
            ax.set_title(f'{name}\nСвоих функций: {int(selected.own_known_basic_function_count)}; внешних НП: {int(selected.external_participant_count)}',fontsize=9.5)
            audit.setdefault('named_examples',[]).append({'name':name,'region':region,'star_id':selected.star_id,
                 'own_functions':int(selected.own_known_basic_function_count),'external_members':int(selected.external_participant_count),
                 'diameter_km':float(selected.core_diameter_km)})
        handles=[Line2D([],[],marker='o',ls='',color=COLORS[c],label=f'{c} '+('направление' if c==1 else 'направления')) for c in [1,2,3]]
        fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.17),ncol=3,fontsize=9,frameon=False)
        fig.text(.06,.115,'У одного соседа могут совпасть три направления, у другого — только школа. Оба сохраняются в прямом окружении.',fontsize=9)
        save(fig,'03_named_centres')

        # 4. Version comparison is not population change or a causal estimate.
        fig = page('Что меняется после исправления привязок',
                   'Собственные функции центра и принадлежность площадки НП — разные показатели. Данные разных версий не являются временным рядом.',4)
        ax=fig.add_axes([.29,.31,.24,.42]); labels=['Три функции','Две функции','Одна функция']; ys=np.arange(3)
        current=[int(counts.get(i,0)) for i in [3,2,1]]
        if before and 'by_recorded_own_basic_function_count' in before:
            old=before['by_recorded_own_basic_function_count']; old_values=[int(old.get(str(i),old.get(i,0))) for i in [3,2,1]]
            ax.barh(ys-.17,old_values,height=.29,color=GREY,label='Сохранённый контроль')
            ax.barh(ys+.17,current,height=.29,color=COLORS[3],label='Текущий расчёт')
            ax.legend(fontsize=7,loc='upper left',bbox_to_anchor=(-.85,-.12),frameon=False)
            audit['version_comparison']={'before_own_function_counts':old_values,'after_own_function_counts':current,
                                         'not_a_temporal_change_or_isolated_causal_effect':True}
        else:ax.barh(ys,current,color=COLORS[3])
        ax.set_yticks(ys,labels);ax.invert_yaxis();style(ax,'Центров')
        for y,v in zip(ys,current): ax.text(v+max(current)*.025,y+.17 if before else y,num(v),fontsize=8,va='center')
        ax.set_xlim(0,max(current+[1])*1.32)
        bx=fig.add_axes([.64,.31,.28,.42]); coverage=[]
        for family in FUNCTIONS:
            rows=core[core.service_family.eq(family)]; admitted=rows[rows.l0_admitted]
            known=int(admitted.provider_settlement_id.notna().sum()); unknown=len(admitted)-known
            coverage.append({'service_family':family,'all_origins':len(rows),'admitted':len(admitted),'known_provider_np':known,'unknown_provider_np':unknown})
        for i,row in enumerate(coverage):
            bx.barh(i,row['known_provider_np'],color=COLORS[3]);bx.barh(i,row['unknown_provider_np'],left=row['known_provider_np'],color=GREY)
        bx.set_yticks(range(3),[FUNCTIONS[r['service_family']] for r in coverage]);bx.invert_yaxis();style(bx,'Допущенных направлений, тыс.')
        bx.xaxis.set_major_locator(MaxNLocator(4));bx.xaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value/1000:g}'))
        fig.text(.59,.23,'Зелёный: НП площадки установлен в модели.\nСерый: площадка есть, её НП не установлен.',fontsize=8.7)
        fig.text(.06,.13,'При сравнении версий одновременно менялись привязки учреждений и пространственный учёт НП.\n'
                 f'В каждой сфере — {num(coverage[0]["all_origins"])} исходных точек; это не наблюдения поездок и не временная динамика услуг.',fontsize=9)
        audit['provider_np_coverage']=coverage;save(fig,'04_source_correction')

        # 5. Identity support and population-budget limitations are inspectable.
        fig = page('На каких данных держатся связи',
                   'Картографическое попадание — отдельное основание. Оно не становится явным адресом, юридической границей или наблюдением поездки.',5)
        ax=fig.add_axes([.22,.31,.34,.43]); rows=[]
        for family in FUNCTIONS:
            group=core[core.service_family.eq(family)&core.l0_admitted]
            tier=group.get('provider_identity_evidence_tier',pd.Series(None,index=group.index))
            carto=int((group.provider_settlement_id.notna()&tier.eq('dated_cartographic_locality_containment')).sum())
            unknown=int(group.provider_settlement_id.isna().sum());retained=len(group)-carto-unknown
            rows.append([retained,carto,unknown])
        left=np.zeros(3)
        for j,(label,color) in enumerate([('Унаследованные адресные / реестровые',COLORS[2]),('Датированная картография',COLORS[3]),('НП не установлен',GREY)]):
            vals=np.array(rows)[:,j];ax.barh(range(3),vals,left=left,color=color,label=label);left+=vals
        ax.set_yticks(range(3),list(FUNCTIONS.values()));ax.invert_yaxis();style(ax,'Допущенных направлений, тыс.')
        ax.xaxis.set_major_locator(MaxNLocator(4));ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value/1000:g}'))
        ax.legend(fontsize=7.5,loc='lower center',bbox_to_anchor=(.46,-.36),frameon=False)
        flags=[]
        for field,label in [('road_access_component_review_needed','Дорожная привязка / компонента'),
                            ('coincident_coordinate_requires_review','Совпавшие исходные координаты'),
                            ('school_stage_unknown','Школьная ступень не установлена')]:
            if field in members:
                n=int(members[members[field].fillna(True)].star_id.nunique());flags.append((label,n))
        if 'population_budget_partial' in centres:flags.append(('Неполный зачтённый бюджет населения',int(centres.population_budget_partial.sum())))
        bx=fig.add_axes([.63,.31,.31,.43]);bx.set_axis_off()
        if flags:
            table=bx.table(cellText=[[wrap(label,27),num(value)] for label,value in flags],
                           colLabels=['Признак проверки','Центров'],cellLoc='left',colWidths=[.78,.22],bbox=[0,0,1,1])
            table.auto_set_font_size(False);table.set_fontsize(8.7)
            for (i,j),cell in table.get_celld().items():
                cell.set_edgecolor('#DCE3E2');cell.set_linewidth(.5);cell.set_facecolor('#EAF0EE' if i==0 else PAPER)
        fig.text(.06,.13,'Признаки справа могут пересекаться: их нельзя складывать. Бюджет учитывает правила недублирования населения.\nИсходную численность центра и неполную зачтённую сумму нельзя выдавать за полное население системы.',fontsize=9)
        audit['identity_support_by_function']={f:dict(zip(['retained','cartographic','unknown_np'],r)) for f,r in zip(FUNCTIONS,rows)}
        audit['centre_review_flags']=dict(flags);save(fig,'05_identity_and_quality')

        # 6. Show the full extreme, not only convenient small examples.
        fig = page('Самые широкие окружения требуют отдельного разбора',
                   'Ранжирование по диаметру прямого состава; данные не обрезаны под желаемое число районов или размер города.',6)
        largest=centres.dropna(subset=['core_diameter_km']).sort_values(['core_diameter_km','centre_settlement_id'],ascending=[False,True]).head(8)
        if len(largest):
            ax=fig.add_axes([.08,.30,.36,.43]);selected=largest.iloc[0];local_map(ax,selected,members,ref,max_labels=7)
            ax.set_title(f'{selected.centre_name}: диаметр {selected.core_diameter_km:.2f} км',fontsize=10)
            cols=['Центр / регион','Свои\nфункции','Внешних\nНП','Диаметр,\nкм']
            cells=[[wrap(f'{r.centre_name}, {r.centre_region}',24),str(int(r.own_known_basic_function_count)),num(r.external_participant_count),f'{r.core_diameter_km:.2f}'] for r in largest.itertuples()]
            table_ax=fig.add_axes([.50,.27,.44,.47]);table_ax.set_axis_off()
            table=table_ax.table(cellText=cells,colLabels=cols,cellLoc='left',colWidths=[.54,.14,.15,.17],bbox=[0,0,1,1])
            table.auto_set_font_size(False);table.set_fontsize(8)
            for (i,j),cell in table.get_celld().items():
                cell.set_edgecolor('#DCE3E2');cell.set_linewidth(.5);cell.set_facecolor('#EAF0EE' if i==0 else PAPER)
            audit['largest_centres']=largest[['centre_settlement_id','centre_name','centre_region','own_known_basic_function_count','external_participant_count','core_diameter_km']].to_dict('records')
        fig.text(.06,.14,'Большой диаметр может отражать разные площадки внутри крупного НП, неполные местные альтернативы или ошибку данных.\nНужно проверять конкретные связи, пригодность услуг и дороги. Сам диаметр не доказывает единую территорию обслуживания.',fontsize=9)
        save(fig,'06_extent_tail')
    (output/'figure_values.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pages':len(audit['pages']),'pdf':str(pdf_path),'registered_centres':len(centres)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['registry','scenario','reference','output']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--before-summary',type=Path)
    a=parser.parse_args();run(a.registry,a.scenario,a.reference,a.output,a.before_summary)
