from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

R=Path(__file__).resolve().parent
f=pd.read_csv(R/'wb_pilot_all_delivery_locations.csv');axis=pd.read_parquet(R.parent.parent/'anchor_research_20261019/data/point_axis.parquet')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,2,figsize=(13,10),layout='constrained')
for ax,pilot in zip(axes.flat,['Невьянский','Нижнетуринский','Конаковский','Учалинский']):
    s=f[f.pilot.eq(pilot)]
    for scope,color,marker,label in [(True,'#0875b9','o','Поднабор типов 8/34'),(False,'#df8d24','^','Прочие типы: смысл не подтверждён')]:
        g=s[s.focus_scope.eq(scope)]
        ax.scatter(g.longitude,g.latitude,s=29,c=color,marker=marker,label=label,edgecolors='white',linewidths=.4,zorder=3)
    for uid,g in s.groupby('settlement_uid'):
        a=axis[axis.id.eq(uid)].iloc[0]
        offset={'Цементный':(-35,-14),'Невьянск':(9,1),'Ребристый':(4,-10),
                'Шурала':(4,-11),'Юрьево-Девичье':(-20,-28),'Кунакбаево':(-38,10),
                'Ильчино':(6,-12),'Сафарово':(6,7),'Учалы':(-20,-20) if a.type=='город' else(8,8)}.get(a['name'],(4,6))
        name=('с. Учалы' if a['name']=='Учалы' and a.type=='село' else a['name'])
        ax.annotate(f'{name} ({len(g)})',(g.longitude.median(),g.latitude.median()),xytext=offset,textcoords='offset points',fontsize=8)
    ax.set_title(f'{pilot}: {len(s)} мест доставки в {s.settlement_uid.nunique()} НП',loc='left',fontweight='bold',color='#123c61')
    ax.set_xlabel('Долгота, ° в. д.');ax.set_ylabel('Широта, ° с. ш.');ax.grid(color='#e3e8ed',linewidth=.7)
    ax.margins(.22)
axes[0,0].legend(loc='upper left',fontsize=7,framealpha=.95)
fig.suptitle('Опубликованные места доставки Wildberries в четырёх пилотах',fontsize=16,fontweight='bold',color='#123c61')
fig.supxlabel('Официальный CDN, скачано 19.10.2026; все типы. Только однозначное согласование имени и координат с осью НП.\nЧисло в скобках — записи источника, а не пользователи. Не все подтипы доказаны общедоступными ПВЗ; границы СГРТ не установлены.',fontsize=10)
fig.savefig(R/'wb_pilot_locations.png',dpi=240,bbox_inches='tight',pad_inches=.15)
fig.savefig(R/'wb_pilot_locations.svg',bbox_inches='tight',pad_inches=.15);plt.close(fig)
