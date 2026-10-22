#!/usr/bin/env python3
"""Geographically located documentary change; arrows are statutory, not trips."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pyproj import CRS,Transformer,Geod

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'model/figures';OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
p=pd.read_parquet(ROOT.parent/'anchor_research_20261019/data/point_axis.parquet')
p=p[(p.region=='свердловская')&p.name.isin(['Нижняя Тура','Новая Тура','Платина'])].set_index('name')
t=Transformer.from_crs(4326,CRS.from_proj4('+proj=aeqd +lat_0=58.64 +lon_0=60.02 +datum=WGS84 +units=m'),always_xy=True)
xy={n:np.array(t.transform(r.lon,r.lat))/1000 for n,r in p.iterrows()}
fig=plt.figure(figsize=(12,7.1));gs=fig.add_gridspec(2,2,height_ratios=[1,0.33],width_ratios=[1.75,1],left=.065,right=.98,top=.84,bottom=.08,wspace=.29,hspace=.17)
ax=fig.add_subplot(gs[0,0]);bar=fig.add_subplot(gs[0,1]);note=fig.add_subplot(gs[1,:]);note.axis('off')
fig.suptitle('Новая Тура: школьное закрепление перешло к меньшему центру',x=.065,y=.97,ha='left',fontsize=16,fontweight='bold',color='#17395c')
fig.text(.065,.91,'Сопоставлены приказы 03.03.2023 и 05.03.2025; закрепление сохранено в приказе 10.03.2026.',fontsize=10.5)
origin=xy['Новая Тура'];old=xy['Нижняя Тура'];new=xy['Платина']
for dest,col,rad in [(old,'#8e9ca9',.12),(new,'#1767a6',-.16)]:
    ax.annotate('',xy=dest,xytext=origin,arrowprops=dict(arrowstyle='-|>',lw=2.5,color=col,connectionstyle=f'arc3,rad={rad}',shrinkA=9,shrinkB=12))
for n,co in xy.items():
    ax.scatter(*co,s=120,c='#1767a6' if n!='Новая Тура' else '#17395c',edgecolors='white',linewidths=1.2,zorder=4)
    ax.scatter(co[0],co[1]-.52,marker='+',s=100,c='#25847b',linewidths=2,zorder=5)
    dy=2.4 if n=='Новая Тура' else -1.5
    ha='center'
    own=f'{int(p.loc[n,"population_2021"]):,}'.replace(',',' ')
    ax.annotate(n+'\n'+own+' жителей (2021)',co,xytext=(0,dy*11),textcoords='offset points',ha=ha,va='bottom' if dy>0 else 'top',fontsize=10.5,fontweight='bold')
ax.text(-2.5,3.0,'2023: СОШ № 7\nНижней Туры',color='#677788',ha='center',fontsize=9.5)
ax.text(10.0,3.0,'2025 и 2026:\nПлатинская ООШ',color='#1767a6',ha='center',fontsize=9.5)
ax.set(xlim=(-14,14.4),ylim=(-5.0,6.1),xlabel='Километры к востоку от центра проекции',ylabel='Километры к северу')
ax.set_aspect('equal',adjustable='box');ax.grid(color='#e7edf2',lw=.7)
ax.set_title('Географическое положение; линии не являются маршрутами',fontsize=10.5,loc='left',pad=9)
ax.legend(handles=[Line2D([0],[0],marker='o',color='w',markerfacecolor='#1767a6',markersize=8,label='Школьный пункт назначения'),Line2D([0],[0],marker='+',color='#25847b',lw=0,markersize=9,label='Медицинский объект в перечне')],loc='upper left',frameon=False,fontsize=8.3)
vals=np.array([[228,133],[0,95]])
ys=np.array([1,0]);bar.barh(ys+.16,vals[:,0],height=.28,color='#aab6c2',label='Окружение по акту 2023')
bar.barh(ys-.16,vals[:,1],height=.28,color='#1767a6',label='Окружение по акту 2025')
for j in range(2):
    for k in range(2):bar.text(vals[j,k]+3,ys[j]+(.16 if k==0 else -.16),str(vals[j,k])+'  ('+str([2023,2025][k])+')',va='center',fontsize=9)
bar.set_yticks(ys,['Нижняя Тура','Платина']);bar.set_xlim(0,325);bar.set_ylim(-.55,1.55)
bar.set_title('Меняется прикрепление,\nнаселение фиксировано на 2021',loc='left',fontsize=10.5,pad=12)
bar.set_xlabel('Жителей во внешнем окружении')
bar.grid(axis='x',color='#e7edf2');bar.set_axisbelow(True)
note.text(0,.85,'Что установлено: одна нормативная связь переориентирована от города (18 392 жителя) к посёлку (160 жителей).',fontsize=10.3,fontweight='bold',color='#17395c')
note.text(0,.59,'Для 10 поселений, явно названных в обоих актах, перераспределение составляет −95 и +95 жителей переписи 2021.',fontsize=10)
note.text(0,.34,'Это не число школьников, не демографическое изменение 2023–2025 и не измерение фактических поездок.',fontsize=9.6,color='#485867')
note.text(0,.10,'Медицина: ЦРБ Нижней Туры и ФАП Новой Туры/Платины перечислены на сайте больницы (проверка 19.10.2026);\nэто отдельное свидетельство местоположения функции, без восстановления медицинских связей 2023 года.',fontsize=9.3,color='#485867')
for ext in ['png','svg','pdf']:fig.savefig(OUT/f'01_novaya_tura_documented_change.{ext}',dpi=240,facecolor='white')
plt.close(fig)
g=Geod(ellps='WGS84');dist={}
for dest in ['Нижняя Тура','Платина']:
    _,_,m=g.inv(p.loc['Новая Тура','lon'],p.loc['Новая Тура','lat'],p.loc[dest,'lon'],p.loc[dest,'lat']);dist[dest]=m/1000
(OUT/'MAP_AUDIT.json').write_text(json.dumps({'point_source':'frozen_panel_reference2021','projection':'local azimuthal equidistant','new_tura_direct_distance_km':dist,'source_coordinates_not_independently_resurveyed':True,'arrows_represent':'normative_assignment_not_observed_trip','census_reference':2021,'documents':[2023,2025,2026],'medical_observation':'2026-10-19','visual_qa':'PNG inspected after correction of two annotation overlaps; labels legends dates legible'},ensure_ascii=False,indent=2))
