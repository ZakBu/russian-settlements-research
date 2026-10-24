#!/usr/bin/env python3
"""Standalone source-backed research atlas; settlement points, no invented zones."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D

INK='#24333E'; BLUE='#236A95'; ORANGE='#C57737'; TEAL='#438879'; GOLD='#B69A4E'; GREY='#B3BDC1'; LIGHT='#E8ECEC'; PAPER='#FAFBF9'
LABELS={'school_lower_secondary':'1–9 классы','school_upper':'10–11 классы','school_grade_unspecified':'ступень не уточнена','medical_primary_fap':'первичная помощь ФАП'}
COLORS={'school_lower_secondary':BLUE,'school_upper':ORANGE,'school_grade_unspecified':GREY,'medical_primary_fap':TEAL}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':INK,'axes.labelcolor':INK,'axes.edgecolor':GREY,'xtick.color':INK,'ytick.color':INK,'axes.titleweight':'bold','pdf.fonttype':42,'savefig.facecolor':PAPER})


def projection(lon,lat,lon0,lat0):
    lam,phi,lam0,phi0=map(np.deg2rad,[np.asarray(lon,float),np.asarray(lat,float),lon0,lat0])
    k=np.sqrt(2/(1+np.sin(phi0)*np.sin(phi)+np.cos(phi0)*np.cos(phi)*np.cos(lam-lam0)))
    return 6371.0088*k*np.cos(phi)*np.sin(lam-lam0),6371.0088*k*(np.cos(phi0)*np.sin(phi)-np.sin(phi0)*np.cos(phi)*np.cos(lam-lam0))


def page(title,subtitle,number):
    fig=plt.figure(figsize=(11.69,8.27),facecolor=PAPER)
    fig.text(.065,.95,'СЕЛЬСКО-ГОРОДСКИЕ СИСТЕМЫ  /  УЧАЛИНСКИЙ РАЙОН',fontsize=9,color=TEAL,weight='bold')
    fig.text(.065,.895,title,fontsize=22,weight='bold')
    fig.text(.065,.845,subtitle,fontsize=10,color='#596A73')
    fig.add_artist(Line2D([.065,.935],[.81,.81],transform=fig.transFigure,color=LIGHT,lw=1))
    fig.text(.065,.045,'Исследовательский проход • 24 октября 2026 • Источники и данные в комплекте',fontsize=8,color='#657780')
    fig.text(.935,.045,f'{number:02d}',ha='right',fontsize=10,color=TEAL)
    return fig


def paragraph(fig,x,y,text,width=49,size=11,color=INK):
    for p in text.split('\n'):
        lines=textwrap.wrap(p,width=width) if p else ['']
        fig.text(x,y,'\n'.join(lines),fontsize=size,color=color,va='top',linespacing=1.5)
        y-=len(lines)*.026*(size/11)+.022
    return y


def draw_map(ax,nodes,links,context=None,names=None,main=False):
    selected=nodes if names is None else nodes[nodes.name.isin(names)]
    lon0=float(selected.lon.mean());lat0=float(selected.lat.mean())
    points=nodes.copy();points['x'],points['y']=projection(points.lon,points.lat,lon0,lat0)
    chosen=points[points.source_record_id.isin(selected.source_record_id)]
    xmin,xmax=chosen.x.min(),chosen.x.max();ymin,ymax=chosen.y.min(),chosen.y.max()
    margin=max((xmax-xmin)*.18,(ymax-ymin)*.18,1.4)
    if context is not None:
        x,y=projection(context.accepted_longitude_2021,context.accepted_latitude_2021,lon0,lat0)
        ax.scatter(x,y,s=10,color=LIGHT,zorder=1)
    ax.set_facecolor(PAPER)
    lookup=points.set_index('source_record_id')
    for r in links.itertuples():
        if r.origin_id==r.destination_id or r.origin_id not in set(chosen.source_record_id) or r.destination_id not in set(chosen.source_record_id):continue
        a,b=lookup.loc[r.origin_id],lookup.loc[r.destination_id]
        color=COLORS.get(r.service_code,TEAL)
        rad=.09 if r.service_code=='school_upper' else -.1 if r.service_code=='medical_primary_fap' else 0
        ax.annotate('',xy=(b.x,b.y),xytext=(a.x,a.y),arrowprops=dict(arrowstyle='-|>',color=color,lw=1.4,linestyle='--',connectionstyle=f'arc3,rad={rad}',shrinkA=5,shrinkB=7),zorder=2)
    centers=set(links.destination_id)
    annotations=[]
    for r in chosen.itertuples():
        iscenter=r.source_record_id in centers
        ax.scatter(r.x,r.y,s=80 if iscenter else 33,marker='s' if iscenter else 'o',color=INK if iscenter else BLUE,edgecolors=PAPER,linewidths=.9,zorder=4)
        offset={'Малоказаккулово':(6,-17),'Калуево':(6,9),'Амангильдино':(-4,9),'Уральск':(6,7),'Курама':(6,-18),'Каримово':(6,8),'Комсомольск':(6,-18)}.get(r.name,(6,6))
        label=r.name+(f'\n{int(r.population_2021):,} чел.'.replace(',',' ') if main else '')
        annotation=ax.annotate(label,(r.x,r.y),xytext=offset,textcoords='offset points',fontsize=9 if main else 8,color=INK,zorder=5,
                    bbox=dict(facecolor=PAPER,alpha=.88,edgecolor='none',pad=1.5))
        annotations.append(annotation)
    ax.set_xlim(xmin-margin,xmax+margin);ax.set_ylim(ymin-margin,ymax+margin)
    ax.set_aspect('equal',adjustable='box');ax.grid(color=LIGHT,lw=.7,zorder=0)
    for spine in ['top','right']:ax.spines[spine].set_visible(False)
    ax.tick_params(labelsize=8);ax.set_xlabel('км к востоку',fontsize=9);ax.set_ylabel('км к северу',fontsize=9)
    ax.text(.98,.98,'С ↑',transform=ax.transAxes,ha='right',va='top',fontsize=9,color=TEAL)
    ax.text(0,-.17,'Проекция Ламберта; точки НП. Пунктир — связь, не дорога.',transform=ax.transAxes,fontsize=8,color='#657780')
    # Greedy label positioning on the rendered map, retaining readable type.
    ax.figure.canvas.draw();renderer=ax.figure.canvas.get_renderer();placed=[]
    for annotation in annotations:
        original=annotation.get_position();accepted=False
        for dx,dy in [original,(6,14),(6,-18),(-6,14),(-6,-18),(6,26),(-6,26),(6,-30),(-6,-30),(18,4),(-18,4)]:
            annotation.set_position((dx,dy));annotation.set_ha('right' if dx<0 else 'left')
            box=annotation.get_window_extent(renderer).expanded(1.04,1.1)
            if not any(box.overlaps(other) for other in placed):accepted=True;break
        placed.append(box)
    return points


def build(root):
    root=Path(root);out=root/'figures';out.mkdir(exist_ok=True)
    for p in out.iterdir():
        if p.is_file() and (p.name[:2].isdigit() or p.name=='local_systems_atlas.pdf'):p.unlink()
    nodes=pd.read_parquet(root/'services/nodes.parquet')
    links=pd.read_parquet(root/'analysis/documented_relations_with_costs.parquet')
    units=pd.read_parquet(root/'analysis/documented_unit_demography.parquet')
    context=pd.read_parquet(root/'roads/road_endpoints.parquet')
    summary=json.loads((root/'analysis/summary.json').read_text())
    core=['Малоказаккулово','Калуево','Амангильдино','Уральск']
    pages=[]
    fig=page('Малое село тоже может быть центром','Документированные услуги разных порядков вместо единого поля городских масс',1)
    ax=fig.add_axes([.07,.22,.51,.53]);draw_map(ax,nodes,links[links.function.eq('education')],context,names=core,main=True)
    fig.text(.63,.745,'299',fontsize=42,color=BLUE,weight='bold');fig.text(.63,.695,'жителей в Малоказаккулове, перепись 2021',fontsize=10)
    paragraph(fig,.63,.635,'Местная школа объединяет три деревни для 1–9 классов.\nДля 10–11 классов те же деревни закреплены за школой Уральска.\nОдна связь не отменяет другую: Уральск не поглощает нижнюю систему.',width=35,size=12)
    fig.legend(handles=[Line2D([0],[0],color=BLUE,ls='--',label='1–9 классы'),Line2D([0],[0],color=ORANGE,ls='--',label='10–11 классы')],loc='lower left',bbox_to_anchor=(.06,.09),frameon=False,ncol=2)
    pages.append(('01_local_system',fig))

    fig=page('Две независимые ветви обслуживания','Школьное закрепление: постановление от 12.03.2025 № 03-224УД; выбранные строки акта',2)
    ax=fig.add_axes([.07,.25,.4,.49]);draw_map(ax,nodes,links[links.service_code.isin(['school_lower_secondary','school_upper'])],context,names=core)
    ax.set_title('Малоказаккулово → Уральск',loc='left',fontsize=12,pad=12)
    ax=fig.add_axes([.56,.25,.37,.49]);draw_map(ax,nodes,links[links.service_code.isin(['school_lower_secondary','school_upper'])],context,names=['Курама','Каримово','Комсомольск'])
    ax.set_title('Курама → Комсомольск',loc='left',fontsize=12,pad=12)
    fig.text(.07,.115,'Масштабы панелей различаются. Между ветвями около 70 км: объединяющая их связь не установлена.',fontsize=10)
    fig.legend(handles=[Line2D([0],[0],color=BLUE,ls='--',label='1–9 классы'),Line2D([0],[0],color=ORANGE,ls='--',label='10–11 классы')],loc='lower left',bbox_to_anchor=(.06,.15),frameon=False,ncol=2)
    pages.append(('02_two_branches',fig))

    fig=page('Полные школьные территории шире ядра','Все 24 отношения из четырёх выбранных строк; самоприкрепления сохранены в таблицах',3)
    for pos,centers,title in [([.07,.25,.42,.49],['Уральск','Малоказаккулово'],'Уральск: 12 НП; Малоказаккулово: 3 НП'),([.56,.25,.37,.49],['Комсомольск','Курама'],'Комсомольск: 7 НП; Курама: 2 НП')]:
        subset=links[links.destination_name.isin(centers)&links.function.eq('education')]
        names=nodes[nodes.source_record_id.isin(set(subset.origin_id)|set(subset.destination_id))].name.tolist()
        ax=fig.add_axes(pos);draw_map(ax,nodes,subset,None,names);ax.set_title(title,loc='left',fontsize=11,pad=12)
    fig.text(.07,.12,'Серые связи: ступень в строке акта не уточнена. Эти 14 отношений не превращены в назначение по классам.',fontsize=9)
    pages.append(('03_full_territories',fig))

    fig=page('Первичная помощь остаётся местной','Сообщение Учалинской ЦРБ: ФАП обслуживает Малоказаккулово и Калуево; дата численности неизвестна',4)
    ax=fig.add_axes([.07,.25,.46,.49]);draw_map(ax,nodes,links[links.function.eq('healthcare')],context,names=core,main=True)
    paragraph(fig,.59,.74,'2,3 минуты\nКалуево → Малоказаккулово по статической автомобильной сети 2021 года.\n330 жителей и 52 ребёнка указаны в сообщении ФАП без даты численности. Перепись 2021 даёт этим двум НП 411 жителей. Это разные основания.\nУральская участковая больница указана в структуре ЦРБ: 10 коек, год не указан. Маршрут пациентов туда источником не установлен.',width=40,size=11)
    fig.text(.07,.115,'Койки стационара не равны мощности ФАП. Наличие больницы не создаёт автоматически её внешнюю зону.',fontsize=10)
    pages.append(('04_primary_healthcare',fig))

    fig=page('Местные связи занимают минуты','21 внешнее документированное отношение; автомобильная модель 2021, а не школьный автобус',5)
    external=links[links.external].copy()
    selected=external[external.service_code.ne('school_grade_unspecified')].sort_values(['service_code','cost_minutes'])
    ax=fig.add_axes([.31,.22,.6,.54]);labels=[f'{r.origin_name} → {r.destination_name}' for r in selected.itertuples()]
    y=np.arange(len(selected));ax.barh(y,selected.cost_minutes,color=[COLORS[x] for x in selected.service_code],height=.65)
    ax.set_yticks(y,labels,fontsize=9);ax.invert_yaxis();ax.set_xlim(0,max(selected.cost_minutes)*1.2);ax.set_xlabel('минуты, статическая автомобильная модель')
    for yy,v in zip(y,selected.cost_minutes):ax.text(v+.25,yy,f'{v:.1f}',va='center',fontsize=9)
    for sp in ['top','right','left']:ax.spines[sp].set_visible(False)
    ax.grid(axis='x',color=LIGHT);ax.set_axisbelow(True)
    fig.text(.07,.12,f'Все внешние отношения выбранных строк: {external.cost_minutes.min():.1f}–{external.cost_minutes.max():.1f} мин. Это не предельный радиус.',fontsize=10)
    pages.append(('05_directed_times',fig))

    fig=page('Ближайшая подходящая услуга','Сравнение на уже прочитанных документах; неполная сеть поставщиков, не независимая проверка точности',6)
    strict=pd.read_parquet(root/'analysis/service_comparison.parquet');strict=strict[strict.scenario.eq('known_service_only')]
    old=pd.read_parquet(root/'analysis/population_weight_counterexample.parquet')
    proxy=pd.read_parquet(root/'analysis/service_comparison.parquet');proxy=proxy[proxy.scenario.eq('school_type_proxy_sensitivity')]
    ax=fig.add_axes([.30,.43,.21,.29]);values=[int(proxy.matches_documented_destination.sum()),int(old.matches_documented_destination.sum())]
    ax.barh([1,0],values,color=[BLUE,ORANGE],height=.55);ax.set_yticks([1,0],['Ближайшая подходящая','Вес населения × затухание'],fontsize=10);ax.set_xlim(0,len(strict)+1)
    for yy,v in zip([1,0],values):ax.text(v+.15,yy,f'{v} из {len(strict)}',va='center',fontsize=12,weight='bold')
    ax.set_xlabel('совпадений с документным направлением');ax.spines[['top','right']].set_visible(False)
    paragraph(fig,.59,.74,'Сравниваются отношения с явно указанной ступенью или видом помощи. Остальные НП не получают обязательного внешнего центра.\nВ обоих столбцах одинаковый набор поставщиков: дополнительно разрешены две нижние ступени, выведенные из типа школы. Это диагностическое предположение, не факт акта.\nНи один вариант не измеряет реальные поездки или свободные места.',width=40,size=11)
    fig.text(.07,.18,'Базовая модель не умножает притяжение на число одинаковых городских учреждений.',fontsize=11,weight='bold')
    fig.text(.07,.12,'Обнаруженное совпадение показывает согласованность малого примера; оно не доказывает переносимость на Россию.',fontsize=10)
    pages.append(('06_model_diagnostic',fig))

    fig=page('Население можно сравнить внутри контура','Переписи 2002 и 2021; школьное закрепление 2025. Не доказана неизменность исторических связей.',7)
    ax=fig.add_axes([.20,.27,.31,.47]);small=nodes[nodes.name.isin(core)].copy()
    y=np.arange(len(small));ax.barh(y+.17,small.effective_population_2002,height=.30,color=GREY,label='2002');ax.barh(y-.17,small.effective_population_2021,height=.30,color=BLUE,label='2021')
    ax.set_yticks(y,small.name,fontsize=10);ax.invert_yaxis();ax.set_xlabel('жителей');ax.legend(frameon=False,loc='lower right');ax.spines[['top','right']].set_visible(False)
    for yy,v in zip(y-.17,small.effective_population_2021):ax.text(v+15,yy,str(int(v)),va='center',fontsize=9)
    paragraph(fig,.59,.74,'Малоказаккулово и две деревни:\n578 → 559 жителей (2002–2021). Центр 310 → 299, окружение 268 → 260.\nПолная школьная территория Уральска — 12 НП: 4 127 → 3 401 житель. Четыре НП ядра — только часть этой территории.\nУ Курамы нет принятого значения 2002 года. Динамический тип её полной системы остаётся с недостаточными данными.',width=40,size=11)
    fig.text(.07,.12,'Типы описывают знак изменения центра и окружения. Они не доказывают причинную устойчивость или перехват функций.',fontsize=9)
    pages.append(('07_population',fig))

    fig=page('Аграрная база есть за пределами юрлиц','Хозяйства населения, два сельсовета, 2008–2009. Это муниципальный контекст, не значения отдельных деревень.',8)
    profiles=pd.read_parquet(root/'economy/outputs/municipal_profiles.parquet')
    groups=[('Амангильдинский сельсовет',BLUE),('Уральский сельсовет',TEAL)]
    ax=fig.add_axes([.09,.34,.4,.39]);ticks=[]
    for i,(name,color) in enumerate(groups):
        for j,year in enumerate([2008,2009]):
            row=profiles[(profiles.municipality.eq(name))&profiles.year.eq(year)].iloc[0]
            xx=i*3+j;pot=row.household_potato_ha;veg=row.household_vegetable_ha
            ax.bar(xx,pot,color=color,width=.65);ax.bar(xx,veg,bottom=pot,color=GOLD,width=.65)
            ax.text(xx,pot+veg+2,f'{pot+veg:g}',ha='center',fontsize=10)
            ticks.append((xx,str(year)))
    ax.set_xticks([x for x,_ in ticks],[t for _,t in ticks]);ax.set_ylabel('га посевов хозяйств населения');ax.set_ylim(0,140);ax.spines[['top','right']].set_visible(False)
    ax.text(.19,-.19,'Амангильдинский',transform=ax.transAxes,ha='center',fontsize=9);ax.text(.80,-.19,'Уральский',transform=ax.transAxes,ha='center',fontsize=9)
    fig.legend(handles=[Line2D([0],[0],color=BLUE,lw=7,label='картофель (цвет сельсовета)'),Line2D([0],[0],color=GOLD,lw=7,label='овощи')],loc='lower left',bbox_to_anchor=(.075,.19),frameon=False,fontsize=9)
    paragraph(fig,.59,.74,'Данные пересчитаны из первичного муниципального Parquet: 31 строка по двум сельсоветам.\nВ 2008 году: 1 561 и 2 988 голов КРС в хозяйствах населения. Коровы входят в КРС и отдельно к нему не прибавляются.\nНоль зарегистрированных аграрных юрлиц в маленькой деревне не означает отсутствия сельского хозяйства.\nРайонные гектары не распределяются между деревнями пропорционально населению.',width=40,size=11)
    fig.text(.07,.105,'2007–2009 — ранний наблюдаемый срез. Его нельзя выдавать за аграрную структуру 2021 или 2026 года.',fontsize=10)
    pages.append(('08_agriculture',fig))

    fig=page('Современный аграрный контекст района','Учалинский муниципальный район; хозяйства всех категорий. Показатели не распределены между деревнями.',9)
    district=pd.read_parquet(root/'economy/outputs/recent_district_agriculture.parquet')
    for position,metric,title,color in [([.09,.30,.35,.40],'grain_sown_ha','Зерновые и зернобобовые, га',BLUE),([.57,.30,.35,.40],'cattle_heads','Крупный рогатый скот, голов',TEAL)]:
        z=district[district.metric.eq(metric)&district.category.eq('Хозяйства всех категорий')].sort_values('year')
        ax=fig.add_axes(position);xx=np.arange(len(z));ax.bar(xx,z.value,color=[GREY,color,color],width=.55)
        ax.set_xticks(xx,z.year.astype(int));ax.set_ylim(0,z.value.max()*1.23);ax.set_title(title,loc='left',fontsize=12,pad=12)
        for x,value in zip(xx,z.value):ax.text(x,value+z.value.max()*.03,f'{int(value):,}'.replace(',',' '),ha='center',fontsize=11)
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color=LIGHT);ax.set_axisbelow(True)
    fig.text(.09,.18,'2010–2021: зерновая площадь −51%; поголовье КРС −35%. Это изменения районных показателей.',fontsize=11)
    fig.text(.09,.12,'Общий итог посевов 2010 года отсутствует. Сопоставимость исторических границ отдельно не доказана.',fontsize=10)
    pages.append(('09_district_agriculture',fig))

    fig=page('Работодатель — отдельный функциональный узел','Агрофирма «Байрамгул»: официальный сайт, регистрационные свидетельства и сведения ФНС',10)
    ax=fig.add_axes([.07,.26,.44,.48]);draw_map(ax,nodes,links.iloc[:0],context,names=core,main=True)
    employer=pd.read_parquet(root/'economy/outputs/employer_evidence.parquet').iloc[0]
    office=nodes[nodes.name.eq('Уральск')].iloc[0]
    ax.annotate('Контактный адрес агрофирмы',(float(projection([office.lon],[office.lat],nodes[nodes.name.isin(core)].lon.mean(),nodes[nodes.name.isin(core)].lat.mean())[0][0]),float(projection([office.lon],[office.lat],nodes[nodes.name.isin(core)].lon.mean(),nodes[nodes.name.isin(core)].lat.mean())[1][0])),xytext=(-20,26),textcoords='offset points',ha='right',color=ORANGE,fontsize=9)
    jobs_path=root/'economy/outputs/organisation_headcount.csv'
    headcount=None
    if jobs_path.exists():
        jobs=pd.read_csv(jobs_path,dtype=str)
        for col in ['headcount','workers','organisation_headcount','employee_count','КолРаб']:
            if col in jobs and len(jobs):
                matching=jobs[jobs.astype(str).apply(lambda x:x.str.contains('0270015537').any(),axis=1)]
                if len(matching):headcount=matching.iloc[0][col]
    headline=f'{headcount} работников юрлица' if headcount is not None else 'Численность не установлена'
    fig.text(.59,.74,headline,fontsize=18,color=ORANGE,weight='bold')
    paragraph(fig,.59,.665,'ФНС: среднесписочная численность за 2025 год; опубликовано 25.09.2026.\nКонтактный адрес и карта офиса — Уральск, Советская, 6. На сайте перечислены профессии: тракторист, агроном, ветеринар и другие. Число профессий не является числом вакансий.\nРаботники юридического лица не размещаются автоматически по адресу офиса. География ферм и места проживания работников не установлены.\nТрудовые стрелки на карте пока не рисуются.',width=40,size=11)
    fig.text(.07,.12,'Школа, ФАП и агрофирма описывают разные функции одного поселения; общей суммой их не заменяем.',fontsize=10)
    pages.append(('10_employer',fig))

    fig=page('Что установлено и что ещё предстоит','Малые функциональные системы восстановлены по документам; полная система СГРТ пока не выделена',11)
    paragraph(fig,.08,.75,'ЕСТЬ\nЧетыре выбранные школьные территории: 12, 7, 3 и 2 НП; две пары ступеней обслуживания.\nМестный ФАП с названными двумя деревнями.\nДорожные стоимости с отдельными датой и предпосылками.\nПереписная динамика, аграрный контекст и подтверждённый работодатель.',width=44,size=12)
    paragraph(fig,.56,.75,'НУЖНО ДОБАВИТЬ\nДети по ступеням, учащиеся и места; фактические маршруты подвоза.\nПолные медицинские услуги, мощности и прикрепления.\nАдреса рабочих площадок, работники по площадкам и направления поездок.\nСовременная локальная аграрная структура.\nЗатем — проверяемое объединение функций и уровней, с сохранением вторичных центров.',width=43,size=12)
    fig.text(.08,.135,'Файлы содержат исходные документы, источники, даты, контрольные суммы и код повторения.',fontsize=11,weight='bold')
    pages.append(('11_next_evidence',fig))
    with PdfPages(out/'local_systems_atlas.pdf') as pdf:
        pdf.infodict().update(Title='Локальные системы обслуживания Учалинского района',Author='russian-settlements-research',Subject='Документы, доступность, демография и аграрная база')
        for name,fig in pages:
            fig.savefig(out/(name+'.png'),dpi=170)
            fig.savefig(out/(name+'.pdf'))
            pdf.savefig(fig);plt.close(fig)
    return {'pages':len(pages),'atlas':'figures/local_systems_atlas.pdf'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    print(json.dumps(build(p.parse_args().root),ensure_ascii=False))
