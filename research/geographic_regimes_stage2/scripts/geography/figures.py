"""Six Russian static scientific figures using projected analytic cell geometry."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle,Patch
from matplotlib.colors import Normalize,TwoSlopeNorm
from pyproj import Transformer
B=Path(__file__).parent; O=B/'outputs';F=O/'figures';F.mkdir(exist_ok=True)
m=pd.read_csv(O/'territory_metrics.csv');g=m[m.kind=='grid50'].copy()
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','figure.facecolor':'white'})
R=Path('/workspace/scratch/c21afd18c709/repo/publication/stage71');src=pd.read_csv(R/'ordinary_full3_with_primary_population_sources.csv.gz',usecols=['entity_uid','settlement_name_2002','population_2002','latitude_2002','longitude_2002']);fed=pd.read_csv(R/'accepted_common_federal_territory_axis.csv');fed=fed[(fed.census_year==2002)&fed.territory_key.isin(['RU-FED-MOW','RU-FED-SPB'])];tr=Transformer.from_crs(4326,6933,always_xy=True)
anchors=[]
for name in ['Екатеринбург','Новосибирск','Иркутск','Якутск','Владивосток']:
 r=src[src.settlement_name_2002.eq(name)].sort_values('population_2002',ascending=False).iloc[0];xx,yy=tr.transform(r.longitude_2002,r.latitude_2002);anchors.append({'name':name,'x':xx/1e6,'y':yy/1e6,'federal':False,'uid':r.entity_uid})
for r in fed.itertuples():
 xx,yy=tr.transform(r.longitude,r.latitude);anchors.append({'name':'Москва' if r.territory_key.endswith('MOW') else 'Санкт-Петербург','x':xx/1e6,'y':yy/1e6,'federal':True,'uid':r.territory_key})
pd.DataFrame(anchors).to_csv(F/'anchor_source.csv',index=False)
notes='Панель stage71, фиксированные места 2002 г.; ячейки 50 км, EPSG:6933. Пустое поле не означает отсутствия НП вне панели.\n▲ Москва/Санкт-Петербург — внешние ориентиры; их территориальная масса не распределена по ячейкам. Координаты — репрезентативные точки.'
def save(fig,key):
 for ext in ['png','svg']:fig.savefig(F/f'{key}.{ext}',dpi=220,bbox_inches='tight')
 plt.close(fig)
def mapfig(field,title,label,key,limits,cmap='RdBu',signed=True,note=''):
 fig=plt.figure(figsize=(16,5));ax=fig.add_axes([.055,.32,.92,.53]);cax=fig.add_axes([.29,.19,.49,.025]);inset=fig.add_axes([.055,.035,.14,.12]);norm=TwoSlopeNorm(vmin=limits[0],vcenter=0,vmax=limits[1]) if signed else Normalize(*limits)
 for aa,gg in [(ax,g[g.cell_x>=0]),(inset,g[g.cell_x<0])]:
  rr=[Rectangle((x/1e6-.025,y/1e6-.025),.05,.05) for x,y in zip(gg.cell_x,gg.cell_y)];valid=gg.support20 & gg[field].notna();colors=np.full((len(gg),4),[.80,.82,.84,1.]);colors[valid]=plt.get_cmap(cmap)(norm(gg.loc[valid,field]));aa.add_collection(PatchCollection(rr,facecolors=colors,edgecolors='none'));aa.autoscale_view();aa.set_aspect('equal');aa.tick_params(labelsize=9)
 ax.set(xlabel='x, млн м (EPSG:6933)',ylabel='y, млн м');inset.set_title('За меридианом 180°',fontsize=8);inset.tick_params(labelsize=7);ax.legend(handles=[Patch(facecolor='#ccd1d6',label='Менее 20 положительных НП в 2002 г.')],loc='upper right',frameon=False,fontsize=9)
 for a in anchors:
  ax.scatter(a['x'],a['y'],s=12,c='#242424',marker='^' if a['federal'] else 'o',zorder=4);offset=(-10,-12) if a['name']=='Москва' else (4,5);ax.annotate(a['name'],(a['x'],a['y']),xytext=offset,textcoords='offset points',fontsize=8,color='#202020',bbox={'facecolor':'white','alpha':.8,'edgecolor':'none','pad':.7})
 cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax,orientation='horizontal',extend='both');cb.set_label(label,fontsize=10);fig.text(.055,.94,title,fontsize=16,ha='left');fig.text(.245,.045,notes+('\n'+note if note else ''),fontsize=8.3,color='#444444',va='bottom');save(fig,key)
 g[['unit','cell_x','cell_y','n_rows','n_positive2002','support20',field]].to_csv(F/f'{key}_source.csv',index=False)
g['population_change_pct']=g.relchange_2002_2021*100;g['survival_pct']=g.survival_fraction*100;g['log_density']=np.log10(1+g.density_positive2002_per1000km2)
mapfig('population_change_pct','Изменение численности населения, 2002–2021 гг.','Изменение населения, %','01_population',(-75,75))
mapfig('top10_delta_pp','Изменение доли населения в исходно крупнейших 10% НП','Изменение доли, процентные пункты; состав группы фиксирован по 2002 г.','02_concentration',(-25,25))
mapfig('survival_pct','Сохранение положительной численности в исходно заселённых местах','Доля положительных в 2021 г. среди положительных НП 2002 г., %','03_survival',(0,100),'Blues',False)
mapfig('nn_change_km_p90','Верхняя часть распределения изменений ближайшего соседства','90-й процентиль парных изменений расстояния, км','04_neighbor_change',(-2,2),note='Медиана парного изменения равна 0 в 1356 из 1359 ячеек с достаточной опорой; на карте показан заранее предусмотренный верхний хвост.')
mapfig('log_density','Исходная густота положительных населённых пунктов, 2002 г.','log₁₀(1 + число положительных НП на 1000 км²)','05_baseline_density',(0,2),'Blues',False)
fig,ax=plt.subplots(figsize=(10,6));a=g[g.support20&(g.population2002>0)];ax.scatter(a.population_change_pct,a.top10_delta_pp,s=13,c='#25649c',alpha=.35,edgecolors='none');ax.axhline(0,c='#888888',lw=.8);ax.axvline(0,c='#888888',lw=.8);ax.set(xlabel='Изменение населения в 2002–2021 гг., %',ylabel='Изменение доли исходно крупнейших 10% НП, п. п.',title=f'Численность и концентрация: {len(a):,} ячеек 50 км');ax.set_xlim(-100,150);ax.set_ylim(-60,60);outside=((a.population_change_pct>150)|(a.top10_delta_pp.abs()>60)).sum();fig.text(.12,.02,f'Панель stage71. Не менее 20 положительных НП в 2002 г. на ячейку. За пределами шкал: {outside} ячеек; сохранены в CSV.',fontsize=8.5);fig.tight_layout(rect=(0,.055,1,1));save(fig,'06_population_concentration');a.to_csv(F/'06_population_concentration_source.csv',index=False)
(F/'README.md').write_text('Шесть научных статических рисунков. Карты показывают точную геометрию квадратных аналитических ячеек EPSG6933, без выдуманных границ регионов. Малые ячейки серые; полный состав и исходные CSV сохранены. Основная карта x>=0, отдельная врезка для x<0. Москва/СПб — контекстные якоря, федеральная территориальная масса не размещена в точках. Подписи прочих ориентиров из строк исходной панели. Расстояния WGS84. Медиана парных изменений NN равна0 в1356/1359 supportedcells; показанныйp90 предусмотрен исходным протоколом, не выбран по значимости. Цветовые шкалы ограничены для читабельности, концы со стрелками; исходные значения не обрезаны. Никакой статистической значимости не заявляется.\n')
(F/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in F.iterdir() if p.is_file() and p.name!='sha256.json'},indent=2))
