#!/usr/bin/env python3
"""National standalone research atlas from frozen mass-model tables.

All maps use spherical Lambert azimuthal equal-area projection of actual
coordinates. No continuous catchment polygons or observed journeys are invented.
"""
from __future__ import annotations
import argparse,hashlib,json,textwrap,sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

INK='#24333E';BLUE='#236A95';TEAL='#3D8179';ORANGE='#C57737';GOLD='#B59A4B';PINK='#9E6590';GREY='#AFB9BD';LIGHT='#E4E9E8';PAPER='#FAFBF9'
SERVICE={'medical_basic_primary':'Базовая первичная помощь','medical_physician_primary':'Врачебная первичная помощь','medical_inpatient':'Стационарные условия','medical_specialized':'Специализированная помощь','medical_day_hospital':'Дневной стационар','school_general':'Общее школьное образование','preschool':'Дошкольное образование','vocational_education':'Среднее профессиональное','higher_education':'Высшее образование'}
AGRI={'grain_dominant_municipal_context':'Зерновое окружение','feed_dominant_municipal_context':'Кормовое окружение','technical_dominant_municipal_context':'Технические культуры','no_dominant_selected_crop_group':'Нет доминирования выбранных групп','insufficient_municipal_data':'Недостаточно сведений','heterogeneous_or_insufficient_municipal_context':'Разнородное окружение / нехватка сведений','reported_zero_sown_area_municipality':'Опубликован нулевой посев','tied_selected_crop_groups':'Равенство долей культур'}
STATE={'known_local_node_with_additional_functional_links':'Местная функция и дополнительные связи','known_local_node_without_external_links':'Известная местная функция','single_sector_external_candidate':'Внешний кандидат по одной сфере','functionally_split_external_candidates':'Разные центры по разным функциям','two_sector_common_centre_candidate':'Общий центр двух сфер','no_supported_external_link_or_unknown':'Связь не установлена / неизвестность','physical_service_candidate_with_unknown_centre_np':'Есть доступный объект; его НП не установлен'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':INK,'axes.labelcolor':INK,'axes.edgecolor':GREY,'xtick.color':INK,'ytick.color':INK,'axes.titleweight':'bold','pdf.fonttype':42,'savefig.facecolor':PAPER})

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def num(v):return f'{int(v):,}'.replace(',',' ')
def wrap(s,width=60):return '\n'.join(textwrap.wrap(str(s),width=width))
def project(lon,lat,lon0=100.,lat0=60.):
 lam,phi,lam0,phi0=map(np.deg2rad,[np.asarray(lon,float),np.asarray(lat,float),lon0,lat0])
 k=np.sqrt(2/np.maximum(1e-12,1+np.sin(phi0)*np.sin(phi)+np.cos(phi0)*np.cos(phi)*np.cos(lam-lam0)))
 return 6371.0088*k*np.cos(phi)*np.sin(lam-lam0),6371.0088*k*(np.cos(phi0)*np.sin(phi)-np.sin(phi0)*np.cos(phi)*np.cos(lam-lam0))
def style(ax,xlabel=None,ylabel=None):
 ax.set_facecolor(PAPER)
 for side in ['top','right']:ax.spines[side].set_visible(False)
 ax.grid(axis='y',color=LIGHT,lw=.7,zorder=0)
 if xlabel:ax.set_xlabel(xlabel)
 if ylabel:ax.set_ylabel(ylabel)
 ax.tick_params(labelsize=9)
def text(fig,x,y,s,width=64,size=11,color=INK):
 fig.text(x,y,wrap(s,width),va='top',fontsize=size,linespacing=1.45,color=color)
def title_page(title,subtitle,page,preview=False):
 fig=plt.figure(figsize=(11.69,8.27),facecolor=PAPER)
 fig.text(.06,.95,'ЛОКАЛЬНЫЕ СИСТЕМЫ РАССЕЛЕНИЯ  /  РОССИЯ',fontsize=9,color=TEAL,weight='bold')
 fig.text(.06,.89,title,fontsize=21,weight='bold')
 fig.text(.06,.845,wrap(subtitle,135),fontsize=10,color='#596A73',va='top')
 fig.add_artist(Line2D([.06,.94],[.79,.79],transform=fig.transFigure,color=LIGHT,lw=1))
 footer='Предварительный рендер • данные пересчитываются' if preview else '24 октября 2026 • население 2002/2010/2021 • учреждения преимущественно 2026 • дороги OSM 2021'
 fig.text(.06,.034,footer,fontsize=7.6,color='#657780')
 fig.text(.94,.034,f'{page:02d}',ha='right',fontsize=10,color=TEAL)
 return fig

def add_map(ax,frame,*,lon0=100,lat0=60,color=GREY,size=.6,alpha=.6,marker='o'):
 d=frame[np.isfinite(pd.to_numeric(frame.lon,errors='coerce'))&np.isfinite(pd.to_numeric(frame.lat,errors='coerce'))]
 x,y=project(d.lon,d.lat,lon0,lat0)
 ax.scatter(x,y,s=size,c=color,alpha=alpha,marker=marker,linewidths=0,rasterized=True,zorder=2)
 return d.assign(x=x,y=y)
def map_style(ax,extent=None):
 ax.set_aspect('equal',adjustable='box');style(ax,'км к востоку от центра проекции','км к северу')
 ax.grid(color=LIGHT,lw=.5);ax.tick_params(labelsize=8)
 if extent is not None:ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:])
def label_points(ax,points,column='name',max_labels=6,color=INK):
 items=points.dropna(subset=[column]).head(max_labels)
 annotations=[]
 for r in items.itertuples():
  an=ax.annotate(str(getattr(r,column)),(r.x,r.y),xytext=(5,6),textcoords='offset points',fontsize=8,color=color,zorder=8,bbox=dict(facecolor=PAPER,alpha=.9,edgecolor='none',pad=1.2))
  annotations.append(an)
 ax.figure.canvas.draw();rend=ax.figure.canvas.get_renderer();placed=[]
 for an in annotations:
  for dx,dy in [(5,7),(5,-16),(-5,7),(-5,-16),(5,20),(-5,20),(15,0),(-15,0)]:
   an.set_position((dx,dy));an.set_ha('right' if dx<0 else 'left');box=an.get_window_extent(rend).expanded(1.03,1.05)
   if not any(box.overlaps(old) for old in placed):break
  placed.append(box)
def national_labels(ax,reference):
 selected=[]
 for name in ['Москва','Санкт-Петербург','Уфа','Новосибирск','Иркутск','Якутск','Владивосток']:
  pool=reference[reference.name.eq(name)&reference.source_record_id.notna()&np.isfinite(reference.lat)&np.isfinite(reference.lon)]
  if len(pool):selected.append(pool.sort_values('population_2021',ascending=False).iloc[0])
 if selected:
  d=pd.DataFrame(selected);d['x'],d['y']=project(d.lon,d.lat)
  ax.scatter(d.x,d.y,s=12,facecolors=PAPER,edgecolors=INK,lw=.55,zorder=5)
  label_points(ax,d,max_labels=len(d))


def count_bars(ax,labels,values,color=BLUE):
 y=np.arange(len(labels));ax.barh(y,values,color=color,height=.63,zorder=3)
 ax.set_yticks(y,labels);ax.invert_yaxis();style(ax)
 maximum=max(values) if len(values) and max(values)>0 else 1
 ax.set_xlim(0,maximum*1.23)
 for i,value in enumerate(values):ax.text(value+maximum*.02,i,num(value),va='center',fontsize=9)

def build(root,output=None,preview=False):
 root=Path(root);out=Path(output) if output else root/'figures';out.mkdir(parents=True,exist_ok=True)
 for old_png in out.glob('[0-9][0-9]_*.png'):old_png.unlink()
 sources={};snapshot={}
 def load(rel,optional=False):
  p=root/rel
  if not p.exists():
   if optional:return pd.DataFrame()
   raise FileNotFoundError(p)
  sources[rel]={'sha256':sha(p),'bytes':p.stat().st_size};snapshot[rel]=sources[rel]['sha256']
  return pd.read_parquet(p)
 ref=load('context/census_reference.parquet');r=ref[ref.ordinary_spatial_2021].copy();r=r[r.source_record_id.notna()]
 r=r[np.isfinite(r.lat)&np.isfinite(r.lon)].copy();ridx=r.set_index('source_record_id')
 units=load('model/units.parquet');members=load('model/memberships.parquet');states=load('model/settlement_functional_states.parquet');comparison=load('model/source_scenario_comparison.parquet');overlap=load('model/basic_physician_overlap_links.parquet',True)
 agro=load('model/settlement_agriculture_profiles.parquet',True);work=load('context/settlement_partial_workforce.parquet',True)
 known=units[units.center_source_record_id.notna()].copy()
 core=known[known.scenario.eq('registry_or_address_np')].copy()
 core_ext=core[core.n_populated_external.gt(0)].copy()
 all_np_ext=units[units.center_source_record_id.notna()&units.center_population_role.eq('ordinary_settlement_record')&units.is_inhabited_external_candidate_cell.fillna(False)].copy()
 school_np_ext=all_np_ext[all_np_ext.service_code.eq('school_general')]
 med=core_ext[core_ext.service_code.eq('medical_basic_primary')].copy()
 phys=core_ext[core_ext.service_code.eq('medical_physician_primary')].copy()
 basic_members=members[members.scenario.eq('registry_or_address_np')&members.service_code.eq('medical_basic_primary')].copy()
 physician_members=members[members.scenario.eq('registry_or_address_np')&members.service_code.eq('medical_physician_primary')].copy()
 pos_external=lambda d:d[d.known_positive_external.fillna(False)] if 'known_positive_external' in d else d[d.is_local.eq(False)]
 basic_ext=pos_external(basic_members);phys_ext=pos_external(physician_members)
 stats={'ordinary_records':len(r),'all_cells':len(units),'known_np_external_cells_core':len(core_ext),'unique_np_centres_with_external_core':all_np_ext.center_source_record_id.nunique(),'all_complementary_main_np_cells_with_external_population':len(all_np_ext),'school_np_centres_with_external_population':school_np_ext.center_source_record_id.nunique(),'basic_cells_with_external_population':len(med),'physician_cells_with_external_population':len(phys),'basic_positive_external_origins':basic_ext.origin_id.nunique(),'all_units_typed':bool(units.type_code.notna().all()),'basic_centres_below1000':int(med.center_population_2021.lt(1000).sum()),'basic_centres_below1000_fraction':float(med.center_population_2021.lt(1000).mean()),'basic_centre_population_median':float(med.center_population_2021.median()),'basic_external_settlements_median':float(med.n_populated_external.median()),'basic_external_population_median':float(med.external_population_2021.median())}
 pages=[]
 pdf=PdfPages(out/'russia_local_systems_atlas.pdf')
 def save(fig,name,detail):
  index=len(pages)+1;stem=f'{index:02d}_{name}';fig.savefig(out/(stem+'.png'),dpi=170,facecolor=PAPER);pdf.savefig(fig,facecolor=PAPER)
  pages.append({'page':index,'file':stem+'.png','title':fig.texts[1].get_text(),'detail':detail});plt.close(fig)

 #1. A concrete result, with a map and explicit unit meaning.
 fig=title_page('Малые центры получили собственное окружение','Массовый расчёт по России: известное местное предложение и разные направления по видам услуг.',1,preview)
 metrics=[(num(stats['unique_np_centres_with_external_core']),'НП-центров с модельными\nвнешними участниками'),(num(len(med)),'центров базовой\nпервичной помощи'),(num(school_np_ext.center_source_record_id.nunique()),'школьных центров\nс установленным НП')]
 for i,(v,label) in enumerate(metrics):fig.text(.065+i*.3,.71,v,fontsize=31,weight='bold',color=TEAL if i==0 else BLUE);fig.text(.065+i*.3,.645,label,fontsize=11,linespacing=1.4)
 ax=fig.add_axes([.06,.12,.56,.42]);add_map(ax,r,color=GREY,size=.27,alpha=.45);q=med.rename(columns={'center_lon':'lon','center_lat':'lat'});add_map(ax,q,color=TEAL,size=2.3,alpha=.8);map_style(ax);ax.set_xlabel('Ламбертова равновеликая проекция; реальные точки НП',fontsize=8)
 text(fig,.67,.55,f"{100*stats['basic_centres_below1000_fraction']:.1f}% базовых ячеек имеют центр меньше 1 тыс. жителей.".replace('.',',',1),width=28,size=12)
 text(fig,.67,.39,f"Медианный центр — {num(stats['basic_centre_population_median'])} житель. Окружение — {num(stats['basic_external_settlements_median'])} жилых НП и {num(stats['basic_external_population_median'])} жителей.",width=29,size=11.5)
 text(fig,.67,.22,'Это модельные кандидаты. Потоки пациентов, вместимость и общая иерархия СГРТ пока не установлены.',width=31,size=9.5,color='#596A73')
 save(fig,'national_result',stats)

 #2. Coverage, expressly not catchments.
 fig=title_page('Где у нас есть сведения, а где — пробелы','Известное предложение базовой помощи показано отдельно от связей. Серый цвет не означает отсутствия учреждения.',2,preview)
 ax=fig.add_axes([.06,.18,.88,.57]);add_map(ax,r,color=GREY,size=.35,alpha=.5);known_basic=core[core.service_code.eq('medical_basic_primary')];add_map(ax,known_basic.rename(columns={'center_lon':'lon','center_lat':'lat'}),color=TEAL,size=2.3,alpha=.85);map_style(ax);national_labels(ax,ref)
 ax.legend(handles=[Line2D([],[],marker='o',ls='',color=TEAL,label=f'Известный поставщик: {num(len(known_basic))} НП'),Line2D([],[],marker='o',ls='',color=GREY,label='Остальные НП: предложение может быть неизвестно')],loc='upper left',frameon=False,fontsize=9)
 text(fig,.065,.13,'Лицензионные реестры преимущественно 2026 года; привязка к населённым пунктам 2021 года. Точки не являются границами ареалов.',width=135,size=9)
 save(fig,'medical_coverage',{'known_basic_settlement_cells':len(known_basic),'denominator':len(r)})

 #3. Candidate membership geography, two service layers.
 fig=title_page('Местное обслуживание и внешняя связь различаются','Одинаковый НП может иметь базовую помощь рядом и отдельного кандидата на врачебную помощь.',3,preview)
 detail={}
 for i,(data,label) in enumerate([(basic_members,'Базовая первичная'),(physician_members,'Врачебная первичная')]):
  ax=fig.add_axes([.055+i*.475,.26,.435,.48]);add_map(ax,r,color=LIGHT,size=.3,alpha=.6)
  ext=pos_external(data);local=data[data.is_local.fillna(False)]
  add_map(ax,r[r.source_record_id.isin(ext.origin_id)],color=ORANGE,size=.8,alpha=.75);add_map(ax,r[r.source_record_id.isin(local.origin_id)],color=TEAL,size=.95,alpha=.9);map_style(ax);ax.set_title(label,fontsize=12)
  text(fig,.06+i*.475,.20,f'Местное: {num(local.origin_id.nunique())} НП\nВнешние кандидаты с известным населением: {num(ext.origin_id.nunique())}',width=56,size=9);detail[label]={'local':local.origin_id.nunique(),'external':ext.origin_id.nunique()}
 fig.legend(handles=[Line2D([],[],marker='o',ls='',color=TEAL,label='Известная местная функция'),Line2D([],[],marker='o',ls='',color=ORANGE,label='Условная внешняя связь')],loc='lower center',bbox_to_anchor=(.5,.105),ncol=2,frameon=False)
 save(fig,'local_and_external',detail)

 #4. Membership sizes.
 fig=title_page('Малые центры получили небольшие окружения','Каждая точка справа — отдельная ячейка базовой помощи с известным НП-центром и внешними жителями.',4,preview)
 ax=fig.add_axes([.075,.22,.4,.5]);bins=[0,2,5,10,20,np.inf];labels=['1–2','3–5','6–10','11–20','21 и больше'];counts=pd.cut(med.n_populated_external,bins=bins,labels=labels).value_counts(sort=False)
 ax.bar(labels,counts,color=TEAL,zorder=3);style(ax,'Внешних НП с известным положительным населением','Ячеек');ax.tick_params(axis='x',rotation=20)
 ax=fig.add_axes([.57,.22,.36,.5]);q=med[(med.center_population_2021>0)&(med.n_populated_external>0)]
 ax.scatter(q.center_population_2021,q.n_populated_external,s=8,alpha=.4,c=BLUE,linewidths=0,rasterized=True);ax.set_xscale('log');ax.set_yscale('log');style(ax,'Население центра, 2021, человек','Внешних населённых пунктов')
 text(fig,.07,.13,'Количество жителей и учреждений не используется для перетягивания соседей. Численность здесь описывает получившийся результат.',width=135,size=10)
 save(fig,'cell_sizes',{'histogram':{str(k):int(v) for k,v in counts.items()},'scatter_rows':len(q)})

 #5. Costs, not measured journeys.
 fig=title_page('Внешние кандидаты ограничены доступностью','Время — по статическому автомобильному графу OSM 2021, с подъездами. Это не наблюдённые поездки.',5,preview)
 ax=fig.add_axes([.08,.24,.4,.47]);detail={}
 for data,label,color in [(basic_ext,'Базовая',TEAL),(phys_ext,'Врачебная',BLUE)]:
  values=pd.to_numeric(data.cost_minutes,errors='coerce').dropna();values=values[values>=0]
  ax.hist(values,bins=np.arange(0,32,2),histtype='step',weights=np.full(len(values),100/max(len(values),1)),density=False,lw=2,color=color,label=label)
  detail[label]={'rows':len(values),'median_minutes':float(values.median()) if len(values) else None,'p95_minutes':float(values.quantile(.95)) if len(values) else None,'max_minutes':float(values.max()) if len(values) else None}
 style(ax,'Минут до кандидата','Направлений в интервале, %');ax.legend(frameon=False)
 ax=fig.add_axes([.57,.24,.35,.47])
 for data,label,color in [(basic_ext,'Базовая',TEAL),(phys_ext,'Врачебная',BLUE)]:
  a=np.sort(pd.to_numeric(data.cost_minutes,errors='coerce').dropna());ax.plot(a,np.arange(1,len(a)+1)/len(a) if len(a) else [],color=color,lw=2,label=label)
 style(ax,'Минут до кандидата','Доля направлений');ax.set_xlim(0,31);ax.set_ylim(0,1);ax.yaxis.set_major_formatter(PercentFormatter(1.))
 text(fig,.075,.15,'30 минут — планировочный ориентир СП 42.13330.2016, таблица 10.1, для сельской первичной помощи; это не оценённый по пациентам закон затухания.',width=133,size=10)
 save(fig,'travel_costs',detail)

 #6. Center population structure, no hard population hierarchy.
 fig=title_page('Локальный центр не обязан быть городом','Группы людности ниже — описание результата, а не заранее заданные уровни СГРТ.',6,preview)
 bands=[-1,0,99,499,999,4999,19999,99999,np.inf];labels=['0','1–99','100–499','500–999','1–5 тыс.','5–20 тыс.','20–100 тыс.','100 тыс.+'];detail={}
 ax=fig.add_axes([.11,.23,.79,.48]);positions=np.arange(len(labels))
 for shift,data,label,color in [(-.18,med,'Базовая',TEAL),(.18,phys,'Врачебная',BLUE)]:
  c=pd.cut(data.center_population_2021,bins=bands,labels=labels).value_counts(sort=False);ax.bar(positions+shift,c,width=.33,color=color,label=label);detail[label]={str(k):int(v) for k,v in c.items()}
 ax.set_xticks(positions,labels,rotation=20);style(ax,'Жители центра по переписи 2021','Ячеек с внешними жителями');ax.legend(frameon=False)
 text(fig,.075,.13,'Сельское наличие функции подтверждается источником. Ни одно поселение не обязано создавать внешний ареал; отдельный известный объект может не иметь выделенного внешнего окружения.',width=133,size=10)
 save(fig,'centre_population',detail)

 # Regional diagrams: full regional coverage plus a reproducible small-centre zoom.
 def region_page(region,title,pageno):
  reg=r[r.region.eq(region)];ur=med[med.center_region.eq(region)].copy()
  candidates=ur[(ur.center_population_2021.between(1,5000))&ur.n_populated_external.between(2,10)].copy()
  if candidates.empty:candidates=ur.copy()
  if candidates.empty:return
  lon0=float(reg.lon.median());lat0=float(reg.lat.median());cx,cy=project(candidates.center_lon,candidates.center_lat,lon0,lat0)
  candidates['select_distance']=np.hypot(cx,cy);anchor=candidates.sort_values(['select_distance','center_source_record_id']).iloc[0]
  zx,zy=project(ur.center_lon,ur.center_lat,float(anchor.center_lon),float(anchor.center_lat));ur['anchor_km']=np.hypot(zx,zy)
  selected=ur[(ur.anchor_km<=27)&ur.n_populated_external.gt(0)].sort_values(['anchor_km','center_source_record_id']).head(3)
  fig=title_page(title+' — местные центры сохраняются','Слева — сведения по региону; справа — выбранное соседство малых центров. Пунктир показывает модельную связь, не дорогу.',pageno,preview)
  ax=fig.add_axes([.055,.19,.39,.55]);add_map(ax,reg,lon0=lon0,lat0=lat0,color=GREY,size=3,alpha=.6)
  kr=core[(core.center_region.eq(region))&core.service_code.eq('medical_basic_primary')];add_map(ax,kr.rename(columns={'center_lon':'lon','center_lat':'lat'}),lon0=lon0,lat0=lat0,color=TEAL,size=9,alpha=.8)
  ax.scatter(*project([anchor.center_lon],[anchor.center_lat],lon0,lat0),s=150,marker='s',facecolors='none',edgecolors=ORANGE,lw=1.8);map_style(ax);ax.set_title('Известное предложение, весь регион',fontsize=11)
  ax=fig.add_axes([.52,.19,.42,.55]);a_lon=float(anchor.center_lon);a_lat=float(anchor.center_lat);points=r.copy();points['x'],points['y']=project(points.lon,points.lat,a_lon,a_lat)
  margin=24.;near=points[(points.x.abs()<=margin)&(points.y.abs()<=margin)];ax.scatter(near.x,near.y,s=12,color=LIGHT,zorder=1)
  legend=[];chosen_names=[];labelsdf=[]
  for (_,center),color in zip(selected.iterrows(),[BLUE,ORANGE,TEAL]):
   g=basic_ext[basic_ext.center_key.eq(center.center_key)];orig=points[points.source_record_id.isin(g.origin_id)];xx,yy=project([center.center_lon],[center.center_lat],a_lon,a_lat);x,y=xx[0],yy[0]
   for item in orig.itertuples():ax.plot([item.x,x],[item.y,y],ls='--',lw=.7,color=color,alpha=.6,zorder=2)
   ax.scatter(orig.x,orig.y,s=22,color=color,edgecolors=PAPER,lw=.3,zorder=4);ax.scatter([x],[y],s=145,marker='*',color=color,edgecolors=INK,lw=.5,zorder=6)
   labelsdf.append(dict(name=center.center_name,x=x,y=y));chosen_names.append(str(center.center_name));legend.append(Line2D([],[],marker='*',color=color,ls='--',label=f'{center.center_name}: {int(center.n_populated_external)} внешних НП'))
  # The second layer starts from residents of the same settlement. It is
  # deliberately not drawn as an observed institutional FAP-to-hospital referral.
  physician_points=set()
  for center in selected.itertuples():
   if pd.isna(center.center_population_2021) or center.center_population_2021<=0:continue
   candidates2=physician_members[physician_members.origin_id.eq(center.center_source_record_id)&~physician_members.is_local.fillna(False)]
   for candidate in candidates2.itertuples():
    dest=getattr(candidate,'provider_settlement_id',None)
    if dest not in ridx.index or dest in physician_points:continue
    gp=ridx.loc[dest];gx,gy=project([gp.lon],[gp.lat],a_lon,a_lat)
    if abs(gx[0])>margin or abs(gy[0])>margin:continue
    sx,sy=project([center.center_lon],[center.center_lat],a_lon,a_lat)
    ax.plot([sx[0],gx[0]],[sy[0],gy[0]],ls='-.',lw=.9,color=PINK,alpha=.8,zorder=3)
    ax.scatter(gx,gy,s=75,marker='D',facecolors='none',edgecolors=PINK,lw=1.3,zorder=7)
    labelsdf.append(dict(name=str(gp['name'])+' (врач)',x=gx[0],y=gy[0]));physician_points.add(dest)
    if len(physician_points)>=2:break
   if len(physician_points)>=2:break
  if physician_points:legend.append(Line2D([],[],marker='D',markerfacecolor='none',color=PINK,ls='-.',label='Врачебный кандидат для жителей того же НП'))
  label_points(ax,pd.DataFrame(labelsdf),max_labels=5);map_style(ax,[-margin,margin,-margin,margin]);ax.set_title('Соседство малых центров',fontsize=11);ax.legend(handles=legend,loc='lower left',fontsize=7.5,frameon=False)
  text(fig,.065,.12,'Выбор примера: центр 1–5 тыс. жителей, 2–10 внешних НП, ближайший к географической середине региона; затем до трёх соседних центров. Это иллюстрация, не критерий расчёта.',width=139,size=8.8)
  save(fig,'region_'+region,{'region':region,'regional_np':len(reg),'centres_with_external':len(ur),'zoom_anchor':str(anchor.center_name),'selected_centres':chosen_names,'additional_physician_centres':sorted(physician_points),'zoom_half_width_km':margin})
 region_page('башкортостан','Башкортостан',7);region_page('удмуртская','Удмуртия',8);region_page('вологодская','Вологодская область',9)

 #10. Non-exclusive higher links and functional states.
 fig=title_page('Следующий уровень не стирает нижний','Связь по врачебной помощи — дополнительный слой. Единственное обязательное дерево подчинения не задавалось.',10,preview)
 ax=fig.add_axes([.075,.28,.31,.43])
 if not overlap.empty:
  counts=overlap.groupby('center_key_basic').candidate_parent_count.max().reindex(med.center_key,fill_value=0);cats=counts.clip(upper=4).value_counts().reindex([0,1,2,3,4],fill_value=0)
  ax.bar(['Нет\nизвестного','1','2','3','4+'],cats,color=TEAL);style(ax,'Врачебных кандидатов\nсреди жителей одной базовой ячейки','Базовых ячеек с внешними жителями')
 else:ax.text(.05,.6,'Таблица перекрытий пока не рассчитана',transform=ax.transAxes);ax.axis('off')
 ax=fig.add_axes([.72,.22,.21,.5]);v=states.functional_state.value_counts();labels=[wrap(STATE.get(k,'Другая описательная категория'),27) for k in v.index];count_bars(ax,labels,v.values,color=BLUE);ax.set_xlabel('Населённых пунктов')
 text(fig,.07,.13,'Несколько направлений — модельная функциональная сложность. Общие пользователи двух уровней не доказывают фактическое направление пациентов между учреждениями.',width=137,size=9)
 save(fig,'functional_layers',{'states':{str(k):int(v) for k,v in v.items()},'overlap_rows':len(overlap)})

 #11. Physical education geometry, deliberately without assigning centre population.
 fig=title_page('Школьные площадки: координаты и принадлежность к НП','Физические объекты OSM 2021 сохраняются отдельно, если их принадлежность населённому пункту не доказана.',11,preview)
 siteunits=units[units.center_source_record_id.isna()&units.service_code.isin(['school_general','preschool'])].copy()
 ax=fig.add_axes([.06,.2,.57,.54]);add_map(ax,r,color=LIGHT,size=.3,alpha=.65)
 if not siteunits.empty:add_map(ax,siteunits.rename(columns={'center_lon':'lon','center_lat':'lat'}),color=PINK,size=1.1,alpha=.8)
 map_style(ax);ax.set_title('Учреждения: собственные координаты',fontsize=12)
 text(fig,.68,.72,f'{num(len(siteunits))} ячеек физических образовательных объектов с неизвестным НП-владельцем.',width=31,size=13)
 text(fig,.68,.52,'Их нельзя автоматически назвать внешними зонами: школа может находиться в том самом селе, откуда начинается расчёт.',width=34,size=11)
 text(fig,.68,.31,'Население ближайшей деревни не приписывается школе. Демография центра и тип «центр–окружение» остаются неизвестными.',width=34,size=11,color='#596A73')
 save(fig,'education_site_identity',{'unknown_centre_site_cells':len(siteunits),'population_not_transferred':True})

 #12. Source-scenario comparison, no summing alternatives.
 fig=title_page('Разные источники: сравнение предложения','OSM 2021 и официальные дошкольные сведения 2025: альтернативные источники показаны раздельно.',12,preview)
 ax=fig.add_axes([.27,.2,.65,.5]);services=[s for s in ['medical_basic_primary','medical_physician_primary','school_general','preschool'] if s in set(comparison.service_code)];y=np.arange(len(services));detail={}
 scenario_specs=[('registry_or_address_np','Известен НП поставщика',BLUE),('physical_sites','Известен физический объект',PINK)]+[(v,'Официальные дошкольные сведения 2025',GOLD) for v in comparison.scenario.unique() if 'official' in str(v)]
 for i,(scenario,label,color) in enumerate(scenario_specs):
  sub=comparison[comparison.scenario.eq(scenario)];vals=[]
  for service in services:
   rows=sub[sub.service_code.eq(service)];vals.append(int(rows.screened_external.sum()) if len(rows) else 0)
  if not any(vals):continue
  ax.barh(y+(i-1)*.22,vals,height=.2,color=color,label=label);detail[scenario]=dict(zip(services,vals))
 ax.set_yticks(y,[wrap(SERVICE[s],28) for s in services]);ax.invert_yaxis();style(ax,'НП с доступным кандидатом по сценарию');ax.legend(frameon=False,loc='lower right',fontsize=8)
 text(fig,.07,.13,'Для физического объекта число направлений означает доступ к площадке, но не доказанное внешнее тяготение между двумя НП. Год, источник и пороги сохраняются раздельно.',width=138,size=9)
 save(fig,'source_scenarios',detail)

 #13. Every unit gets an explicit descriptive state, never a causal Word label.
 fig=title_page('Типы динамики: центр и его окружение','Динамика 2002–2021 относится к фиксированному современному набору НП. Это не восстановленная история границ услуг.',13,preview)
 pairs=med[med.center_direction_02_21.isin(['decline','unchanged','growth'])&med.periphery_direction_02_21.isin(['decline','unchanged','growth'])]
 matrix=pd.crosstab(pairs.center_direction_02_21,pairs.periphery_direction_02_21).reindex(index=['decline','unchanged','growth'],columns=['decline','unchanged','growth'],fill_value=0)
 ax=fig.add_axes([.13,.24,.39,.47]);ax.imshow(matrix.to_numpy(),cmap='Blues',aspect='equal')
 for i in range(3):
  for j in range(3):ax.text(j,i,num(matrix.iloc[i,j]),ha='center',va='center',color='white' if matrix.iloc[i,j]>matrix.to_numpy().max()*.5 else INK,fontsize=13)
 ax.set_xticks(range(3),['Снижение','Без изменения','Рост'],rotation=15);ax.set_yticks(range(3),['Снижение','Без изменения','Рост']);ax.set_xlabel('Окружение');ax.set_ylabel('Центр')
 text(fig,.62,.72,f'Численные направления определены для {num(len(pairs))} ячеек базовой помощи с внешними жителями.',width=34,size=12)
 text(fig,.62,.54,f'Все {num(len(units))} ячеек имеют описательное состояние. Отдельно сохранены отсутствие внешнего окружения, нехватка демографии и неизвестная принадлежность площадки.',width=35,size=11)
 text(fig,.62,.32,'Точный знак изменения не равен существенному росту или спаду. Значения 2010 имеют отдельные флаги качества; причинные типы Word автоматически не присваиваются.',width=35,size=10,color='#596A73')
 save(fig,'demographic_types',{'matrix':matrix.to_dict(),'typed_all_units':stats['all_units_typed'],'scope':'known-centre external cells in main scenario'})

 #14. Agriculture is geographical context, not distributed hectares.
 fig=title_page('Сельское хозяйство добавлено как контекст','Три группы посевов в муниципальном окружении, 2021: без распределения гектаров и выпуска по деревням.',14,preview)
 if not agro.empty:
  ap=agro[agro.source_record_id.notna()].drop_duplicates('source_record_id').merge(r[['source_record_id','lat','lon']],on='source_record_id',how='inner',validate='one_to_one')
  ax=fig.add_axes([.06,.22,.51,.52]);colors={'grain_dominant_municipal_context':GOLD,'feed_dominant_municipal_context':TEAL,'technical_dominant_municipal_context':ORANGE,'no_dominant_selected_crop_group':BLUE,'insufficient_municipal_data':GREY}
  for key,color in colors.items():add_map(ax,ap[ap.agri_context_profile.eq(key)],color=color,size=.7,alpha=.7)
  map_style(ax);ax=fig.add_axes([.78,.25,.15,.43]);v=med.periphery_agricultural_context_type.value_counts() if 'periphery_agricultural_context_type' in med else ap.agri_context_profile.value_counts();count_bars(ax,[wrap(AGRI.get(k,'Другой описательный профиль'),23) for k in v.index],v.values,color=[colors.get(k,GREY) for k in v.index]);ax.set_xlabel('Ячеек базовой помощи' if 'periphery_agricultural_context_type' in med else 'НП в окружении')
 else:text(fig,.1,.6,'Муниципальные аграрные профили пока не присоединены.',size=13)
 text(fig,.07,.13,'Повтор одного муниципального значения у нескольких НП — контекст, а не независимые наблюдения производства. Гектары не увеличивают массу центра.',width=137,size=9)
 save(fig,'agriculture_context',{'records':len(agro),'municipal_values_not_allocated':True})

 #15. Employment: show actual partial observations and missingness.
 fig=title_page('Работники организаций — ещё не все рабочие места','Показываем только опубликованную частичную численность, не заменяя её количеством зарегистрированных фирм.',15,preview)
 if not work.empty:
  w=work[work.source_record_id.notna()].merge(r[['source_record_id','lat','lon']],on='source_record_id',how='inner',validate='one_to_one');col='partial_organisation_workforce_2025';knownw=w[w[col].notna()]
  ax=fig.add_axes([.06,.22,.56,.52]);add_map(ax,r,color=LIGHT,size=.3,alpha=.6)
  if len(knownw):add_map(ax,knownw,color=BLUE,size=1.5,alpha=.8)
  map_style(ax);text(fig,.68,.72,f'{num(len(knownw))} НП с числом работников в опубликованном частичном показателе.',width=33,size=13)
  text(fig,.68,.51,'Не учтены малый бизнес и внешние совместители. Это работники организаций по территории, не занятость всех жителей села.',width=34,size=11)
  text(fig,.68,.29,'Подавленные ячейки и неприсоединённые адреса остаются неизвестными. Отношение к населению нельзя назвать уровнем занятости.',width=34,size=10,color='#596A73')
  detail={'known_partial_workforce_np':len(knownw),'not_total_settlement_jobs':True}
 else:text(fig,.1,.6,'Проверенные частичные сведения пока не присоединены.',size=13);detail={'known_partial_workforce_np':0}
 save(fig,'employment_data',detail)

 #16. Clustering remains a diagnostic, not forced administrative levels.
 clusterfolder=root/'centre_types'
 if not (clusterfolder/'k_diagnostics.parquet').exists():clusterfolder=root/'centre_types_sector_probe'
 diag=load(str((clusterfolder/'k_diagnostics.parquet').relative_to(root)),True)
 fig=title_page('Кластеры центров — диагностика, ещё не уровни','Людность и набор функций можно группировать, но кластер сам по себе не устанавливает вложенность связей.',16,preview)
 if not diag.empty:
  ax=fig.add_axes([.09,.24,.37,.48]);ax2=fig.add_axes([.57,.24,.34,.48])
  variants=list(diag.variant.unique()) if 'variant' in diag else ['single']
  for variant,color in zip(variants,[BLUE,TEAL,ORANGE,GOLD]):
   g=diag[diag.variant.eq(variant)] if 'variant' in diag else diag
   label={'population_only':'По людности','population_and_functions':'Людность и функции','population_functions_and_support':'Людность, функции и окружение'}.get(str(variant),'Дополнительный набор признаков')
   ax.plot(g.k,g.inertia/g.inertia.iloc[0],marker='o',ms=3,color=color,label=label);ax2.plot(g.k,g.silhouette,marker='o',ms=3,color=color,label=label)
  style(ax,'Число кластеров','Остаточная неоднородность, доля');style(ax2,'Число кластеров','Силуэт');ax.legend(frameon=False,fontsize=8)
 else:text(fig,.1,.6,'Диагностика кластеризации ожидает окончательного набора центров.',size=13)
 text(fig,.07,.13,'На одном наборе центров сравниваются варианты признаков. Число кластеров и пороги людности не подгоняются под желаемые уровни.',width=138,size=9)
 save(fig,'centre_clustering',{'source':str(clusterfolder.relative_to(root)),'rows':len(diag),'not_a_hierarchy':True})

 #17. The explicitly undated Chelyabinsk extension is separate evidence.
 proxy=load('medical-chelyabinsk-proxy/argayash_matched_or_held.parquet',True)
 registry=Path(__file__).resolve().parents[2]/'sgrt/mass/registry/argayash_undated_provider_list.csv'
 if proxy.empty and registry.exists():
  sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
  from scripts.sgrt_mass.match import match_addresses
  proxy=match_addresses(pd.read_csv(registry),ref,district_col='district_context')
  proxy['supply_status']='proxy_undated_official_list_not_used_in_2026_registry_routing'
  cache=root/'medical-chelyabinsk-proxy';cache.mkdir(exist_ok=True)
  proxy.to_parquet(cache/'argayash_matched_or_held.parquet',index=False)
  proxy=load('medical-chelyabinsk-proxy/argayash_matched_or_held.parquet')
 if registry.exists():sources['git_registry:argayash_undated_provider_list.csv']={'sha256':sha(registry),'bytes':registry.stat().st_size,'git_path':'sgrt/mass/registry/argayash_undated_provider_list.csv'}
 fig=title_page('Челябинская область: отдельный районный источник','44 записи Аргаяшской ЦРБ — дополнение с неизвестной датой, а не полный областной реестр и не вход основного расчёта.',17,preview)
 if not proxy.empty:
  prox=proxy[proxy.source_record_id.notna()].drop_duplicates('source_record_id').merge(r[['source_record_id','name','lat','lon']],on='source_record_id',how='inner',validate='one_to_one');lon0=float(prox.lon.median());lat0=float(prox.lat.median())
  ax=fig.add_axes([.06,.2,.56,.54]);region=r[r.region.eq('челябинская')];add_map(ax,region,lon0=lon0,lat0=lat0,color=LIGHT,size=5,alpha=.7);pp=add_map(ax,prox,lon0=lon0,lat0=lat0,color=TEAL,size=38,alpha=.9,marker='s');margin=8;map_style(ax,[pp.x.min()-margin,pp.x.max()+margin,pp.y.min()-margin,pp.y.max()+margin]);label_points(ax,pp.sort_values('name'),max_labels=5)
  text(fig,.68,.72,f'{num(len(proxy))} адресных записей → {num(len(prox))} разных НП.',width=32,size=14)
  text(fig,.68,.56,'В официальном перечне есть ФАПы и центры общей врачебной практики. Это полезное подтверждение местного предложения.',width=33,size=11)
  text(fig,.68,.34,'Фраза «временно недоступен» рядом с телефоном не объявлена закрытием учреждения. Пока нет полного HTML и датировки, источник остаётся отдельным.',width=34,size=10,color='#596A73')
 else:text(fig,.1,.6,'Дополнительный районный источник не включён в этот набор входов.',size=13)
 save(fig,'chelyabinsk_additional_source',{'proxy_rows':len(proxy),'not_used_in_main_registry_scenario':True})

 #18. Concrete findings and next test, no formal acceptance receipts.
 fig=title_page('Что теперь можно показать научному руководителю','Получен массовый первый слой локальных систем. Его ограничения видны на тех же картах, что и результат.',18,preview)
 text(fig,.075,.73,f'1. В наборах взаимодополняющих функций найдено {num(stats['unique_np_centres_with_external_core'])} НП-центров с модельными внешними участниками. Слои услуг пересекаются и не образуют единую непересекающуюся сетку.',width=104,size=13)
 text(fig,.075,.56,f'2. Базовая первичная помощь дала {num(len(med))} таких ячеек. Малые сельские узлы сохраняются, потому что городской счётчик учреждений больше не перевешивает расстояние.',width=104,size=13)
 text(fig,.075,.39,'3. Для школ с неизвестной принадлежностью площадки не выдумано население центра. Для сельского хозяйства сохранён муниципальный масштаб; частичная численность работников не объявлена полной занятостью.',width=106,size=12)
 text(fig,.075,.22,'Следующая проверка: независимые территории обслуживания и школьный подвоз, мощности и состав спроса. Общая многоуровневая система СГРТ и причинные типы остаются исследовательской задачей.',width=110,size=11,color='#596A73')
 save(fig,'findings_and_next_step',stats)
 pdf.close()
 changed=[rel for rel,digest in snapshot.items() if sha(root/rel)!=digest]
 manifest={'schema':'sgrt.mass_atlas.v1','preview':preview,'pages':pages,'summary':stats,'inputs':sources,'code_sha256':sha(__file__),'projection':'spherical Lambert azimuthal equal-area; Earth radius6371.0088km; national centre100E60N; regional centres in page metadata','no_catchment_polygons':True,'no_observed_flow_claim':True,'no_population_transfer_to_unidentified_sites':True,'inputs_changed_during_render':changed}
 (out/'atlas_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=lambda v:int(v) if isinstance(v,np.integer) else float(v) if isinstance(v,np.floating) else str(v))+'\n')
 if changed and not preview:raise RuntimeError('Inputs changed during render; regenerate after final model: '+', '.join(changed))
 print(json.dumps({'pages':len(pages),'pdf':str(out/'russia_local_systems_atlas.pdf'),'summary':stats,'changed_inputs':changed},ensure_ascii=False))
 return manifest

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--preview',action='store_true');a=p.parse_args();build(a.root,a.output,a.preview)
