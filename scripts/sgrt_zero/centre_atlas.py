#!/usr/bin/env python3
"""Export inspectable maps of direct service stars and documentary fragments."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_mass.figures import project

PAPER='#FAFBF9'; INK='#253640'; BLUE='#236A95'; TEAL='#3D8179'; GREY='#B4BDC2'; GOLD='#B39942'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':INK,'axes.labelcolor':INK,'pdf.fonttype':42})


def page(title, subtitle, number):
    fig=plt.figure(figsize=(11.69,8.27),facecolor=PAPER)
    fig.text(.065,.947,title,fontsize=20,weight='bold')
    fig.text(.065,.891,subtitle,fontsize=10,va='top',linespacing=1.5)
    fig.text(.065,.033,'Население: переписи 2002/2010/2021 • учреждения: даты источников • автомобильные дороги OSM 2021',fontsize=7,color='#586970')
    fig.text(.945,.033,f'{number:02}',ha='right',fontsize=10)
    return fig


def map_axis(ax):
    ax.set_aspect('equal',adjustable='box');ax.set_facecolor(PAPER)
    ax.set_xlabel('км к востоку от центра проекции');ax.set_ylabel('км к северу')
    ax.grid(color='#E1E7E6',lw=.5)
    for side in ['top','right']:ax.spines[side].set_visible(False)


def run(root, reference_path, output):
    output.mkdir(parents=True,exist_ok=True)
    main=root/'scenarios/daily_20_school30_wb'
    stars=pd.read_parquet(main/'strict_three_core_stars.parquet')
    members=pd.read_parquet(main/'strict_three_core_memberships.parquet')
    ref=pd.read_parquet(reference_path).dropna(subset=['source_record_id']).set_index('source_record_id')
    allref=ref[ref.analysis_origin.fillna(False)]
    docs=pd.read_parquet(root/'documents/documented_memberships.parquet')
    summaries=json.loads((root/'scenarios/combined_summary.json').read_text())['scenarios']
    data={'strict_star_count':len(stars),'strict_external_records':int(members.member_role.eq('direct_surroundings').sum()),'pages':[]}
    with PdfPages(output/'centre_atlas.pdf') as pdf:
        def save(fig,stem):
            fig.savefig(output/(stem+'.png'),dpi=145,facecolor=PAPER)
            pdf.savefig(fig,facecolor=PAPER);plt.close(fig);data['pages'].append(stem)
        fig=page('Где совпадают три базовых направления',
            f'{len(stars)} модельных групп: центр и жилые поселения, выбирающие в нём школу, базовую помощь и продукты.\n'
            'Это строгий поднабор; несовпадение функций в других местах не доказывает отсутствия локальной системы.',1)
        ax=fig.add_axes([.08,.19,.85,.61]);x,y=project(allref.lon,allref.lat)
        ax.scatter(x,y,c=GREY,s=.4,alpha=.4,rasterized=True,label='Остальные исходные точки: статус систем не установлен')
        focus=members.drop_duplicates('origin_id');x,y=project(focus.lon,focus.lat)
        ax.scatter(x,y,c=TEAL,s=7,linewidths=.2,edgecolors=INK,rasterized=True,label='Центры и участники строгого поднабора')
        map_axis(ax);ax.legend(loc='lower left',fontsize=8,frameon=True)
        fig.text(.065,.105,'Показаны реальные точки НП в равновеликой проекции Ламберта. Сплошные границы не восстанавливались.\nСерый цвет не означает отсутствие услуг или связей. Наблюдённые поездки не использованы.',fontsize=9)
        save(fig,'01_country')
        fig=page('Размеры посчитаны по составу каждой группы',
            'Только центр и участники с совпадением всех трёх основных направлений; более слабые связи не прибавлены.',2)
        ax=fig.add_axes([.10,.26,.38,.50]);d=stars.strict_geodesic_diameter_km.dropna()
        if len(d):ax.hist(d,bins='fd',color=TEAL,edgecolor=PAPER)
        else:ax.text(.5,.5,'Групп в этом поднаборе нет',ha='center',transform=ax.transAxes)
        ax.set_xlabel('Диаметр по точкам НП, км');ax.set_ylabel('Число групп');ax.grid(axis='y',alpha=.2)
        bx=fig.add_axes([.59,.26,.33,.50]);counts=stars.strict_external_member_count.value_counts().sort_index()
        bx.bar(counts.index,counts.values,color=BLUE);bx.set_xlabel('Внешних жилых поселений');bx.set_ylabel('Число групп');bx.grid(axis='y',alpha=.2)
        fig.text(.065,.14,f'Диаметр: медиана {d.median():.2f} км; 95-й процентиль {d.quantile(.95):.2f} км; максимум {d.max():.2f} км.\n'
            'Диаметр — расстояние между крайними точками, а не радиус и не время поездки.\n'
            'Школьные ступени, свободные мощности и фактические поездки этим совпадением не подтверждаются.',fontsize=10)
        data['diameter_km']={'median':float(d.median()),'p95':float(d.quantile(.95)),'max':float(d.max())}
        save(fig,'02_sizes')
        fig=page('Один и тот же расчёт при разных условиях близости',
            'Число групп строгого поднабора. Пределы времени заданы до просмотра результата; это сценарии, не наблюдения.',3)
        rows=[]
        labels={'daily_20_school30_wb':'Основной: магазины 20, школа 30 мин','daily_10_school15_wb':'Более близкие: магазины 10, школа 15 мин','daily_30_school30_wb':'Более широкие: магазины 30, школа 30 мин','core3_20_school30':'Три функции, без ПВЗ','daily_20_school30_yandex':'Другой оператор ПВЗ'}
        for sid,s in summaries.items():rows.append((labels[sid],s['strict_three_core_model_screened_stars']))
        ax=fig.add_axes([.40,.29,.48,.48]);positions=np.arange(len(rows))
        ax.barh(positions,[r[1] for r in rows],color=TEAL);ax.set_yticks(positions,[r[0] for r in rows],fontsize=9);ax.invert_yaxis();ax.set_xlabel('Число модельных групп');ax.set_xlim(0,max(1,max(r[1] for r in rows))*1.18)
        for y,(_,v) in zip(positions,rows):ax.text(v+1,y,str(v),va='center')
        fig.text(.065,.13,'Изменение временных пределов — сценарная чувствительность, а не доверительный интервал.\nБазовая помощь — 30 минут во всех вариантах. ПВЗ не участвует в строгом правиле трёх функций.',fontsize=10)
        save(fig,'03_sensitivity')
        fig=page('Документы подтверждают разные местные зоны',
            'Учалинский район: прикрепление к школе 1–9 классов (постановление 12.03.2025) и сообщение ФАПа.\nЭто три функциональных фрагмента с пересечениями, а не три независимых СГРТ.',4)
        for slot,centre in enumerate(['Малоказаккулово','Курама']):
            ax=fig.add_axes([.09+.46*slot,.25,.38,.50]);part=docs[docs.centre_name.eq(centre)]
            anchor=part[part.is_centre].iloc[0];lon0=float(anchor.lon);lat0=float(anchor.lat)
            local=allref[(allref.lat-lat0).abs().lt(.14)&(allref.lon-lon0).abs().lt(.20)]
            x,y=project(local.lon,local.lat,lon0,lat0);ax.scatter(x,y,c=GREY,s=12,alpha=.5)
            for code,color,style,label in [('school_lower_secondary',BLUE,'-','Школа, 1–9 классы'),('medical_primary_fap',GOLD,'--','Заявленная территория ФАПа')]:
                part2=part[part.service_code.eq(code)]
                if part2.empty:continue
                x,y=project(part2.lon,part2.lat,lon0,lat0)
                for px,py in zip(x,y):ax.plot([0,px],[0,py],style,color=color,lw=1.4)
                ax.scatter(x,y,c=color,s=35,label=label)
            unique=part.drop_duplicates('origin_id');x,y=project(unique.lon,unique.lat,lon0,lat0)
            for px,py,name in zip(x,y,unique.name):
                offset=(6,-16) if name==centre else (4,12)
                ax.annotate(name,(px,py),xytext=offset,textcoords='offset points',fontsize=8)
            ax.scatter([0],[0],marker='*',s=160,color=TEAL,edgecolor=INK,zorder=5);map_axis(ax);ax.set_title(centre,fontsize=12)
            # Extent follows the documented members, not the wider background
            # inventory. Otherwise a three-village system becomes unreadable.
            ax.set_xlim(min(x)-2.5,max(x)+5.);ax.set_ylim(min(y)-3.,max(y)+3.)
            ax.legend(loc='lower left',fontsize=7)
        fig.text(.065,.12,'В Кураме и Каримове известны собственные ФАПы: школьное прикрепление не отменяет местную медицину.\nШкольные точки национальной карты близки к документированным центрам, но их НП и ступени автоматически не установлены.',fontsize=9)
        save(fig,'04_documents')
        fig=page('Конкретный состав строгих модельных групп',
            'Линия означает три выбранных базовых направления к одному НП; это не измеренный поток жителей.\nШкола, медицина и продукты проверены как разные функции. Показаны точки НП, а не сплошная граница.',5)
        for slot,(name,region) in enumerate([('Старый Мутабаш','башкортостан'),('Новосиль','орловская')]):
            chosen=stars[stars.centre_name.eq(name)&stars.centre_region.eq(region)]
            ax=fig.add_axes([.09+.46*slot,.24,.38,.51])
            if chosen.empty:
                ax.text(.5,.5,'Не входит в строгий вариант',ha='center',transform=ax.transAxes);continue
            selected=chosen.iloc[0];part=members[members.star_id.eq(selected.star_id)]
            anchor=part[part.member_role.eq('centre')].iloc[0]
            x,y=project(part.lon,part.lat,float(anchor.lon),float(anchor.lat))
            for px,py in zip(x,y):ax.plot([0,px],[0,py],color=TEAL,lw=.8,alpha=.65)
            ax.scatter(x,y,s=35,color=TEAL,edgecolor=INK,lw=.4)
            ax.scatter([0],[0],marker='*',s=170,color=GOLD,edgecolor=INK,zorder=5)
            offsets={'Новосиль':(6,12,'left'),'Заречье':(-10,-15,'right'),
                     'Пенькозавод':(-8,-21,'right'),'Тюково':(8,-10,'left'),
                     'Сорочий Мост':(5,11,'left'),'Ямская Слобода':(-5,-15,'right'),
                     'Шейский Мост':(5,11,'left'),'Лужки':(8,12,'left')}
            for i,(px,py,label) in enumerate(zip(x,y,part.name)):
                dx,dy,ha=offsets.get(label,(4,7 if i%2==0 else -12,'left'))
                ax.annotate(label,(px,py),xytext=(dx,dy),textcoords='offset points',ha=ha,fontsize=7.5,
                            bbox={'facecolor':PAPER,'alpha':.72,'edgecolor':'none','pad':.1})
            map_axis(ax);ax.margins(.28)
            ax.set_title(f'{name}: {int(selected.strict_external_member_count)} внешних НП\nДиаметр {selected.strict_geodesic_diameter_km:.2f} км',fontsize=11)
        fig.text(.065,.12,'Строгое совпадение не подтверждает школьную ступень, свободные мощности или действующую работу всех объектов.\nДругие однофункциональные территории вокруг этих центров могут быть шире и сохраняются отдельно.',fontsize=9)
        save(fig,'05_named_groups')
        context_stars=pd.read_parquet(main/'centre_stars.parquet')
        context_members=pd.read_parquet(main/'centre_memberships.parquet')
        daily=context_stars[context_stars.one_or_more_core_external_positive_whole.gt(0)
            & context_stars.centre_unmarked_whole_record & context_stars.centre_positive_population_known
            & context_stars.centre_ordinary_credited_or_nonadditive_context]
        near=context_members[context_members.star_id.isin(daily.star_id)
            & (context_members.member_role.eq('centre') | (context_members.core_family_count.ge(1)&context_members.positive_credited_whole))]
        near=near.drop_duplicates('origin_id')
        fig=page('За строгим поднабором сохраняется более широкая сеть',
            f'{len(daily):,} известных центров с внешними жилыми участниками хотя бы по одной основной функции.\n'
            'Здесь функции могут вести в разные места. Это пересекающиеся зоны обслуживания, а не готовое общее районирование.'.replace(',',' '),6)
        ax=fig.add_axes([.08,.19,.85,.61]);x,y=project(allref.lon,allref.lat)
        ax.scatter(x,y,c=GREY,s=.4,alpha=.4,rasterized=True,label='Другие точки: единый статус системы не назначен')
        x,y=project(near.lon,near.lat)
        ax.scatter(x,y,c=TEAL,s=.8,alpha=.75,rasterized=True,label='Есть прямая базовая связь с известным НП-центром')
        map_axis(ax);ax.legend(loc='lower left',fontsize=8,frameon=True)
        fig.text(.065,.105,'Узел сохраняет местную функцию, даже если его жители обращаются в другое место за иной услугой.\nСерый цвет не доказывает отсутствие связи; площадки с неизвестным НП-владельцем сохранены в таблицах.',fontsize=9)
        data['known_daily_centres_with_positive_whole_external_core_members']=len(daily)
        data['wider_network_unique_origin_records']=len(near)
        save(fig,'06_wider_service_network')
    (output/'figure_values.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.root,a.reference,a.output)
