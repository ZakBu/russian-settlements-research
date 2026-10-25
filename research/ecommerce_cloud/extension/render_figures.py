"""Publication figures from the reviewed tables; never infer causal effects."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024'
OUT=ROOT/'work/ecommerce_cloud_extension/figures';OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10.5,'axes.spines.top':False,
    'axes.spines.right':False,'axes.axisbelow':True,'savefig.facecolor':'white'})
blue='#2166a7';orange='#b96332';grey='#aeb6bf'

sizes=pd.read_csv(BASE/'execution_20261024/geography/by_size.csv')
h=sizes[sizes.size2021.isin(['01_1_100','02_101_500','03_501_1000','04_1001_3000','05_3001_10000','06_10001_50000'])]
assert len(h)==6
fig,ax=plt.subplots(figsize=(10.6,5.5))
bars=ax.barh(range(6),100*h.either_positive_np_share,color=blue,height=.65)
ax.set_yticks(range(6),['1–100','101–500','501–1 000','1 001–3 000','3 001–10 000','10 001–50 000'])
for b,(_,r) in zip(bars,h.iterrows()):
    ax.text(min(b.get_width()+1.3,90),b.get_y()+b.get_height()/2,f'{100*r.either_positive_np_share:.2f}%',va='center',fontsize=9)
ax.invert_yaxis();ax.set_xlim(0,110);ax.set_xticks([0,20,40,60,80,100]);ax.grid(axis='x',alpha=.18)
ax.set_ylabel('Собственное население поселения в 2021 году, человек')
ax.set_xlabel('Поселения с положительной записью хотя бы одной сети, %')
ax.set_title('Собственное присутствие резко связано с размером поселения',loc='left',fontsize=13)
fig.subplots_adjust(left=.19,bottom=.23,right=.96,top=.88)
fig.text(.03,.035,'144 151 поселение принятой основы; WB 21.10.2026 и сторонний Ozon 06.08.2026.\nРазные даты и полнота; отсутствие принятой записи не означает отсутствия услуги. Это конфигурация, не эффект.',fontsize=8.7)
fig.savefig(OUT/'size_gradient.png',dpi=170);plt.close(fig)

recent=pd.read_csv(HERE/'outcomes/recent_population_panels.csv')
recent=recent[recent.medium_primary2002]
assert len(recent)==170
fig,ax=plt.subplots(figsize=(10.6,5.2))
fields=['own_growth_pct','other_growth_pct']
assert all(x in recent.columns for x in fields),recent.columns.tolist()
ax.boxplot([recent[fields[0]],recent[fields[1]]],tick_labels=['Территория центра','Остальная часть района'],
    orientation='horizontal',showfliers=False,patch_artist=True,boxprops={'facecolor':'#dbe8f3'},medianprops={'color':blue,'linewidth':2})
ax.axvline(0,color=grey,lw=1);ax.grid(axis='x',alpha=.2)
ax.set_xlabel('Изменение населения на 1 января 2023–2025 годов, %')
ax.set_title('В выбранной панели окружение обычно сокращается быстрее центра',loc='left',fontsize=12)
fig.subplots_adjust(left=.25,right=.96,bottom=.26,top=.86)
fig.text(.03,.035,'170 средних центров, 34 региона. Ящик: межквартильный интервал, линия: медиана; крайние точки не показаны.\nБДПМО Y48112027. Условные муниципальные территории; составы 2023/2024 не подтверждены. Не эффект платформ.',fontsize=8.5)
fig.savefig(OUT/'recent_population.png',dpi=170);plt.close(fig)

sens=pd.read_csv(HERE/'outcomes/area_sensitivity.csv')
g=sens[sens.sensitivity.eq('exclude_oryol_and_factor2')]
assert len(g)==2
fig,ax=plt.subplots(figsize=(10.6,5.4))
left=np.zeros(2)
for field,label,color in [('area_decline_n','Площадь сократилась',orange),('area_stable_n','Не изменилась',grey),('area_growth_n','Выросла',blue)]:
    val=100*g[field].to_numpy()/g.medium_centres_n.to_numpy()
    ax.barh([0,1],val,left=left,label=label,color=color,height=.5)
    for j,(v,n) in enumerate(zip(val,g[field])):
        if v>7:ax.text(left[j]+v/2,j,str(n),ha='center',va='center',color='white',fontsize=11)
    left+=val
ax.set_yticks([0,1],['Обычные магазины\n158 центров','Специализированные\nнепродовольственные\n136 центров'])
ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('Доля центров соответствующей панели, %')
ax.set_title('Площадь торговли меняется неодинаково по категориям',loc='left',fontsize=13)
ax.legend(loc='upper left',bbox_to_anchor=(0,-.22),ncol=3,frameon=False,fontsize=9)
fig.subplots_adjust(left=.23,right=.96,bottom=.34,top=.87)
fig.text(.03,.035,'IV кварталы 2022–2024; условные муниципальные территории центра. Числа внутри полос — центры.\nДиагностическая чувствительность: исключены Орловская область и межгодовые разрывы вне [0,5; 2].\nЭто не удостоверенная очистка всех ошибок и не оценка вытеснения платформами.',fontsize=8.5)
fig.savefig(OUT/'area_changes.png',dpi=170);plt.close(fig)

x=pd.read_csv(HERE/'outcomes/combined_population_trade.csv')
x=x[x.category.eq('Магазины')]
assert len(x)==115
fig,ax=plt.subplots(figsize=(9.5,6.4))
ax.scatter(x.share_change_pp,x.centre_share_change2022_2024_pp,s=27,color=blue,alpha=.7,edgecolors='white',linewidths=.3)
ax.axhline(0,color=grey,lw=1);ax.axvline(0,color=grey,lw=1)
ax.axhline(1,color=grey,lw=.8,ls=':');ax.axhline(-1,color=grey,lw=.8,ls=':')
ax.axvline(.5,color=grey,lw=.8,ls=':');ax.axvline(-.5,color=grey,lw=.8,ls=':')
ax.set_xlabel('Изменение демографической доли, п.п.\n1 января 2023–2025')
ax.set_ylabel('Изменение доли числа магазинов, п.п.\nIV кварталы 2022–2024')
ax.set_title('Торговая и демографическая доли — разные исходы',loc='left',fontsize=13)
ax.grid(alpha=.15)
fig.subplots_adjust(left=.15,right=.95,bottom=.24,top=.88)
fig.text(.03,.035,'115 средних центров с общей панелью. Показаны все наблюдения; регрессионный эффект не оценивался.\nПунктир — описательные пороги 0,5 п.п. для населения и 1 п.п. для магазинов.\nСоседние, но разные периоды; условная муниципальная сопоставимость. Это не причинная связь.',fontsize=8.5)
fig.savefig(OUT/'different_roles.png',dpi=170);plt.close(fig)
print('Created four publication figures from reviewed CSV tables.')
