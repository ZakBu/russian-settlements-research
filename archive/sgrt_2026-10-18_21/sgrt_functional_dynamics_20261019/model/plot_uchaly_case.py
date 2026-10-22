#!/usr/bin/env python3
"""Two genuine geographic scales for one documented multilevel service fragment."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pyproj import CRS,Transformer,Geod

R=Path(__file__).resolve().parent.parent;O=R/'model/figures';O.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
p=pd.read_parquet(R.parent/'anchor_research_20261019/data/point_axis.parquet')
p=p[p.municipality_upper_2021.eq('Учалинский муниципальный район')&p.name.isin(['Калуево','Амангильдино','Малоказаккулово','Уральск'])].set_index('name')
assert len(p)==4
t=Transformer.from_crs(4326,CRS.from_proj4('+proj=aeqd +lat_0=54.055609 +lon_0=58.945018 +datum=WGS84 +units=m'),always_xy=True)
xy={n:np.array(t.transform(r.lon,r.lat))/1000 for n,r in p.iterrows()}
fig=plt.figure(figsize=(13,7.6));gs=fig.add_gridspec(2,2,height_ratios=[1,.38],left=.065,right=.97,top=.81,bottom=.065,wspace=.23,hspace=.09)
left=fig.add_subplot(gs[0,0]);right=fig.add_subplot(gs[0,1]);note=fig.add_subplot(gs[1,:]);note.axis('off')
fig.suptitle('Малоказаккулово: две внешние функции и включение в старший школьный уровень',x=.065,y=.97,ha='left',fontsize=15,fontweight='bold',color='#17395c')
fig.text(.065,.915,'Учалинский район, Башкортостан. Документированный фрагмент обслуживания; общая граница СГРТ не навязывается.',fontsize=10.5)
blue='#1767a6';green='#25847b';purple='#815ba7'

def arrow(ax,a,b,c,rad=0,dash=False):
    ax.annotate('',xy=xy[b],xytext=xy[a],arrowprops=dict(arrowstyle='-|>',color=c,lw=2.3,connectionstyle=f'arc3,rad={rad}',linestyle='--' if dash else '-',shrinkA=8,shrinkB=11),zorder=2)
def node(ax,n,offset=(0,12),color='#17395c',big=False):
    co=xy[n];ax.scatter(*co,s=135 if big else 75,c=color,edgecolors='white',linewidths=1.1,zorder=4)
    count=f'{int(p.loc[n,"population_2021"]):,}'.replace(',',' ')
    ax.annotate(n+'\n'+count+' жителей (2021)',co,xytext=offset,textcoords='offset points',ha='center',va='bottom' if offset[1]>0 else 'top',fontsize=10.2,fontweight='bold' if big else 'normal',zorder=5)

arrow(left,'Калуево','Малоказаккулово',blue,.17)
arrow(left,'Калуево','Малоказаккулово',green,-.17)
arrow(left,'Амангильдино','Малоказаккулово',blue,0)
for n in ['Калуево','Амангильдино','Малоказаккулово']:node(left,n,(0,-19) if n=='Малоказаккулово' else (0,14),blue if n=='Малоказаккулово' else '#17395c',n=='Малоказаккулово')
left.set(xlim=(-5.6,2.8),ylim=(-1.6,3.5),xlabel='Километры к востоку от Малоказаккулова',ylabel='Километры к северу')
left.set_title('Местный уровень: школа 1–9 и ФАП',loc='left',fontsize=11,fontweight='bold',pad=14)
left.legend(handles=[Line2D([0],[0],color=blue,lw=2.3,label='Школьное прикрепление: 12.03.2025'),Line2D([0],[0],color=green,lw=2.3,label='Обслуживание ФАП: публикация 09.01.2025')],loc='upper left',frameon=False,fontsize=8.7)
for a,rad in [('Амангильдино',.12),('Калуево',-.13),('Малоказаккулово',.04)]:arrow(right,a,'Уральск',purple,rad,True)
for n in ['Калуево','Амангильдино','Малоказаккулово','Уральск']:
    offset={'Калуево':(12,28),'Амангильдино':(22,10),'Малоказаккулово':(12,-16),'Уральск':(0,13)}[n]
    node(right,n,offset,purple if n=='Уральск' else '#17395c',n=='Уральск')
right.set(xlim=(-6.2,15),ylim=(-2.3,11),xlabel='Километры к востоку от Малоказаккулова',ylabel='Километры к северу')
right.set_title('Старший уровень: школа 10–11 в Уральске',loc='left',fontsize=11,fontweight='bold',pad=14)
right.legend(handles=[Line2D([0],[0],color=purple,lw=2.3,ls='--',label='Школьное прикрепление: 12.03.2025')],loc='upper left',frameon=False,fontsize=8.7)
for ax in [left,right]:ax.grid(color='#e7edf2',lw=.7);ax.set_aspect('equal',adjustable='box')
note.text(0,.91,'Установлено: документы 2025 года связывают Калуево с Малоказаккуловом по школе и ФАП.',fontsize=10.5,fontweight='bold',color='#17395c')
note.text(0,.67,'Нижний школьный уровень сохраняется: Амангильдино и Калуево → Малоказаккулово (1–9 классы).\nСтарший уровень включает те же деревни и само Малоказаккулово → Уральск (10–11 классы).',fontsize=10.2,linespacing=1.5)
note.text(0,.35,'Линии показывают документированные отношения, а не маршруты или измеренные поездки. Масштабы карт различаются.\nНаселение всех возрастов приведено для контекста и не равно числу учеников или пациентов.',fontsize=9.4,color='#485867',linespacing=1.5)
note.text(0,.08,'Источники: подписанный акт № 03-224 УД от 12.03.2025, PDF с.13 (печатная с.11); Учалинская ЦРБ, «Было–стало», 09.01.2025.\nКоординаты: неизменная поселенческая ось; транспортная доступность и иные функции этим фрагментом не измерены.',fontsize=9,color='#485867',linespacing=1.45)
for ext in ['png','svg','pdf']:fig.savefig(O/f'02_uchaly_multifunction_nesting.{ext}',dpi=240,facecolor='white')
plt.close(fig)
geod=Geod(ellps='WGS84');dist={}
for a,b in [('Калуево','Малоказаккулово'),('Амангильдино','Малоказаккулово'),('Малоказаккулово','Уральск')]:
    dist[a+'→'+b]=geod.inv(p.loc[a,'lon'],p.loc[a,'lat'],p.loc[b,'lon'],p.loc[b,'lat'])[2]/1000
(O/'UCHALY_MAP_AUDIT.json').write_text(json.dumps({'point_ids':p.id.to_dict(),'coordinates':p[['lat','lon']].to_dict('index'),'direct_distances_km':dist,'maps_different_scales':True,'transport_routes_asserted':False,'multifunction_fragment':True,'whole_sgrt_all_functions_asserted':False,'visual_qa':'PNG inspected, adjacent right-panel labels separated; dates legends and population caveat legible'},ensure_ascii=False,indent=2))
