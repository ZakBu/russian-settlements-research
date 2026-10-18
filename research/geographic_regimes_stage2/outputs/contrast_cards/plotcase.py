"""Supplementary pair maps: truthful fixed 2002 projected points; no inferred borders."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe
B=Path(__file__).parent;O=B/'maps';O.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#475569','text.color':'#172b46'})
titles={'contrast_concentration':('Красноярский край','Самарская область'),'contrast_neighborhood':('Волгоградская область','Саратовская область'),'low_contrast':('Кемеровская область','Свердловская область')}
size=lambda p:np.maximum(2,np.asarray(p)/2500)
receipts=[]
for stem,names in titles.items():
 fig,axes=plt.subplots(2,2,figsize=(13,12.8));fig.subplots_adjust(left=.085,right=.965,bottom=.205,top=.88,wspace=.22,hspace=.36)
 fig.suptitle(f'{names[0]} и {names[1]}\nНаселённые пункты панели: 2002 и 2021 годы',fontsize=17,fontweight='bold',y=.975)
 fig.text(.5,.917,'Дополнительная иллюстрация к карточке пары · исходный состав UID и геометрия 2002 года',ha='center',fontsize=10)
 for i,side in enumerate(['a','b']):
  path=B/f'{stem}_{side}_roster.csv';d=pd.read_csv(path);x=d.x6933_m/1000;y=d.y6933_m/1000
  xr=x.max()-x.min();yr=y.max()-y.min();pad=max(xr,yr)*.07
  # Limits exactly equal between years within each territory. Different regions have independent geographic extents.
  bounds=(x.min()-pad,x.max()+pad,y.min()-pad,y.max()+pad)
  top=d.sort_values(['population_2002','entity_uid'],ascending=[False,True]).head(3)
  for j,year in enumerate([2002,2021]):
   ax=axes[i,j];p=d[f'population_{year}'];initial=d.population_2002;pos=p>0
   old=pos&(initial>0);new=pos&(initial==0);zero=~pos&(initial>0);initialzero=~pos&(initial==0)
   ax.set_facecolor('#fbfcfe');ax.grid(color='#e5eaf0',lw=.6,zorder=0)
   ax.scatter(x[initialzero],y[initialzero],s=10,marker='s',facecolors='none',edgecolors='#a4acb6',linewidths=.6,zorder=1)
   ax.scatter(x[zero],y[zero],s=12,marker='x',c='#777f89',linewidths=.8,zorder=2)
   order=np.argsort(p[old].to_numpy());idx=d.index[old][order]
   ax.scatter(x.loc[idx],y.loc[idx],s=size(p.loc[idx]),c='#255e96',alpha=.68,edgecolors='white',linewidths=.35,zorder=3)
   ax.scatter(x[new],y[new],s=size(p[new]),c='#bf831c',alpha=.9,edgecolors='white',linewidths=.35,zorder=4)
   for k,(_,r) in enumerate(top.iterrows()):
    label=str(r.settlement_name_2002);dx,dy=7,8
    # Keep Krasnoyarsk/Achinsk and Volgograd/Volzhsky labels separated.
    if label in ['Ачинск','Волгоград','Самара','Кемерово']:dx,dy=-8,-13
    if label=='Волжский':dx,dy=9,15
    ax.annotate(label,(r.x6933_m/1000,r.y6933_m/1000),xytext=(dx,dy),textcoords='offset points',ha='right' if dx<0 else 'left',fontsize=9,fontweight='medium',path_effects=[pe.withStroke(linewidth=3,foreground='white')],zorder=5)
   ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect('equal',adjustable='box');ax.ticklabel_format(axis='both',style='plain',useOffset=False);ax.locator_params(axis='both',nbins=4)
   ax.set_title(f'{names[i]} · {year}\nНП: {len(d):,}; положительных: {int(pos.sum()):,}; населения: {int(p.sum()):,}'.replace(',',' '),fontsize=11,loc='left',pad=12)
   ax.set_xlabel('X, км · EPSG:6933');ax.set_ylabel('Y, км · EPSG:6933')
  receipts.append({'case':stem,'side':side,'n_rows':len(d),'bounds_km':bounds,'input_file':path.name,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 handles=[Line2D([],[],marker='o',ls='',color='#255e96',label='Положительное население; исходно > 0',markersize=6),Line2D([],[],marker='o',ls='',color='#bf831c',label='Положительное население; исходно 0',markersize=6),Line2D([],[],marker='x',ls='',color='#777f89',label='Нулевое население; исходно > 0',markersize=6),Line2D([],[],marker='s',ls='',markerfacecolor='none',markeredgecolor='#a4acb6',label='Нулевое население; исходно 0',markersize=6)]
 fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.136),ncol=2,frameon=False,fontsize=9)
 sh=[plt.scatter([],[],s=size([v])[0],color='#255e96',alpha=.68,edgecolors='white',linewidths=.35,label=f'{v:,}'.replace(',',' ')) for v in [1000,100000,1000000]]
 fig.legend(handles=sh,loc='lower center',bbox_to_anchor=(.5,.088),ncol=3,frameon=False,title='Людность НП, человек · единый масштаб маркеров',fontsize=9,title_fontsize=9,labelspacing=.8,handletextpad=1.2,columnspacing=2.5)
 foot='Ordinary-панель stage71; полнота территориального охвата не установлена. Границы не показаны.\nПределы карты одинаковы между годами каждой территории; между территориями масштаб различается.\nПлощадь маркера = население / 2500, минимум 2 pt². Нули не означают юридическое или физическое исчезновение.'
 if stem=='contrast_concentration':foot+='\nНорильск: изменение состава учётной единицы; сопоставимая городская масса не восстановлена.'
 elif stem=='contrast_neighborhood':foot+='\nВолгоград: включения 2010; Саратов: учётный состав присоединений 2021 требует проверки.'
 foot+=f'\nИсточник CSV: {stem}_a_roster.csv и {stem}_b_roster.csv (UID).'
 fig.text(.07,.018,foot,fontsize=8.5,va='bottom',linespacing=1.5)
 for ext in ['png','svg']:fig.savefig(O/f'{stem}.{ext}',dpi=190,facecolor='white')
 plt.close(fig)
(O/'map_receipt.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'projection':'EPSG:6933','geometry':'2002 fixed UID coordinates','marker_area_rule':'max(2,population/2500) pt²','inputs':receipts,'output_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in O.iterdir() if p.suffix in ['.png','.svg']}},ensure_ascii=False,indent=2))
