"""Standalone scientific exports. Never reads holdout outcomes outside evaluated outputs.
Run from workspace root: python research_staging/figures/build_figures.py
"""
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parents[2]; S=ROOT/'research_staging'; O=S/'figures'; A=ROOT/'repo/research_staging/data_audit'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':15,'axes.labelsize':11,'figure.facecolor':'white','axes.facecolor':'white','svg.fonttype':'none','savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9aabb6','text.color':'#1d2f40','axes.labelcolor':'#1d2f40','xtick.color':'#1d2f40','ytick.color':'#1d2f40'})
BLUE='#2469A0'; LIGHT='#92B8D6'; GRAY='#b3bdc7'; DARK='#334e68'
captions=[]; sources=[]
def readj(p): return json.loads(Path(p).read_text())
def save(fig,stem,data,caption,source):
 fig.tight_layout(pad=1.5);fig.savefig(O/(stem+'.png'),dpi=300,bbox_inches='tight');fig.savefig(O/(stem+'.jpg'),dpi=300,bbox_inches='tight',pil_kwargs={'quality':95});fig.savefig(O/(stem+'.svg'),bbox_inches='tight');plt.close(fig)
 data.to_csv(O/(stem+'.csv'),index=False);captions.append('## '+stem+'\n\n'+caption+'\n\nИсточник: '+source+'\n');sources.append({'figure':stem,'source':source,'rows':len(data)})
def fmt(x,pos=None): return f'{x:,.0f}'.replace(',',' ')
a=readj(A/'evidence/data_contract.json')
d=pd.DataFrame({'выборка':['Вся панель stage71','Положительное население 2010','Разработка: риск 2010','Отложенные блоки: риск 2010'],'n':[a['shape'][0],a['risk_sets']['risk_zero_2021'],101593,19731]})
f,ax=plt.subplots(figsize=(9,4.8));ax.barh(d['выборка'][::-1],d.n[::-1],color=[LIGHT,BLUE,BLUE,GRAY]);ax.set_xlim(0,165000);ax.xaxis.set_major_formatter(FuncFormatter(fmt));ax.set_xlabel('Число записей / населённых пунктов');ax.set_title('1. Панель и совокупность риска')
for i,n in enumerate(d.n[::-1]):ax.text(n+1800,i,fmt(n),va='center')
save(f,'01_panel_risk',d,'Панель принятых обычных НП со значениями трёх переписей; 2010>0 определяет риск перехода к нулю к 2021. Всего 142 570 уникальных UID. Разработка и holdout — разделение текущего запуска, а не доказанная историческая неизвестность данных. Состав всех выборок сохранён в split_manifest. Не является всей совокупностью переписных НП России.','data_audit/evidence/data_contract.json; e1/development/split_manifest.csv.gz')
d=pd.read_csv(A/'evidence/zero_three_way_patterns.csv');g=d.groupby(['positive2002','positive2010','positive2021'],dropna=False).n.sum().reset_index();g['траектория']=g.apply(lambda r:' → '.join('>0' if r[c] else '0' for c in ['positive2002','positive2010','positive2021']),axis=1)
f,axs=plt.subplots(1,2,figsize=(12,5),gridspec_kw={'width_ratios':[1,1.5]});q=pd.read_csv(A/'evidence/population_value_quality_2010.csv');p=q.loc[q.value.str.startswith('secondary',na=False),'n'].sum();z=pd.DataFrame({'статус':['Вторичный защищённый','Остальные статусы'],'n':[p,a['shape'][0]-p]});axs[0].bar(z['статус'],z.n,color=[BLUE,GRAY]);axs[0].tick_params(axis='x',rotation=15);axs[0].yaxis.set_major_formatter(FuncFormatter(fmt));axs[0].set_ylabel('Записи');axs[0].set_title('Качество выбранного 2010')
non=g[g.траектория!='>0 → >0 → >0'];axs[1].barh(non.траектория,non.n,color=BLUE);axs[1].xaxis.set_major_formatter(FuncFormatter(fmt));axs[1].set_xlabel('Число записей');axs[1].set_title('Траектории с хотя бы одним нулём')
for i,n in enumerate(non.n):axs[1].text(n+80,i,fmt(n),va='center',fontsize=9)
axs[1].set_xlim(0,non.n.max()*1.2)
save(f,'02_quality_zero',g,'Качество 2010 показано укрупнённо; полные исходные категории в data_audit. Справа полный набор семи траекторий с нулём, годы слева направо 2002/2010/2021; положительная во все годы траектория исключена только из правого изображения и остаётся в CSV. Это числовые статусы переписных записей, не исчезновение места. Преобладание защищённых вторичных значений ограничивает демографическую интерпретацию малых значений и нулей.','data_audit/evidence/zero_three_way_patterns.csv; population_value_quality_2010.csv')
z.to_csv(O/'02_quality_status.csv',index=False)
ftr=pd.read_csv(S/'geo/features.csv.gz',usecols=['entity_uid','latitude_2010','longitude_2010','population_2010']);sp=pd.read_csv(S/'e1/development/split_manifest.csv.gz');m=ftr.merge(sp,on='entity_uid',validate='one_to_one');m['x_m']=m.longitude_2010;m['y_m']=m.latitude_2010
from pyproj import Transformer
tr=Transformer.from_crs('EPSG:4326','EPSG:3576',always_xy=True);m.x_m,m.y_m=tr.transform(m.longitude_2010.to_numpy(),m.latitude_2010.to_numpy());b=m.groupby(['block_id','holdout'])[['x_m','y_m']].mean().reset_index();f,ax=plt.subplots(figsize=(9,6.5))
for h,col,lbl in [(False,GRAY,'Разработка'),(True,BLUE,'Отложенные блоки')]:
 t=m[m.holdout==h];ax.scatter(t.x_m/1000,t.y_m/1000,s=.12,color=col,alpha=.55,rasterized=True,label=lbl)
ax.set_aspect('equal');ax.set_xlabel('x, км');ax.set_ylabel('y, км');ax.set_title('3. География разделения наблюдений');ax.legend(markerscale=12,frameon=False,loc='lower left')
xl=ax.get_xlim();yl=ax.get_ylim();sx=xl[1]-.13*(xl[1]-xl[0])-500;sy=yl[0]+.11*(yl[1]-yl[0]);tick=.012*(yl[1]-yl[0]);ax.plot([sx,sx+500],[sy,sy],color=DARK,lw=2);ax.vlines([sx,sx+500],sy-tick,sy+tick,color=DARK,lw=1.2);ax.text(sx+250,sy+2*tick,'500 км в проекции',ha='center',va='bottom',fontsize=9)
save(f,'03_spatial_split',b,'Реальные репрезентативные координаты записей 2010, перепроецированные в EPSG:3576 (Lambert Azimuthal Equal Area, центр 90° в.д.). Это карта размещения записей без административной подложки; белые участки не означают отсутствие поселений вне панели. Синий показывает целиком отложенные блоки; точки регионов, не вошедшие в панель, не изображены. Координаты не доказаны как измерения на дату переписи. Масштабная линейка показывает 500 км в координатах проекции, не универсальное наземное расстояние. CSV содержит центры тяжести точек блоков в метрах, а не границы блоков.','geo/features.csv.gz; e1/development/split_manifest.csv.gz')
rows=[]
for name,lab in [('e1','E1: история соседей'),('e2','E2: иерархия'),('e3','E3: морфология')]:
 j=readj(S/name/'development/result.json');met='brier' if name=='e1' else 'mae';base=j['baseline'][met];ci=j['paired_interval'];rows.append(dict(direction=name,label=lab,split='development',gain=100*ci['delta']/base,lo=100*ci['ci95'][0]/base,hi=100*ci['ci95'][1]/base,n=ci['n_rows'],blocks=ci['n_blocks']))
final=S/'final/evaluation.json'
if final.exists():
 j=readj(final)
 for v in j['results']:
  if v['primary']:
   met='brier' if v['task']=='zero' else 'mae';base=v['baseline'][met];ci=v['interval'];rows.append(dict(direction=v['id'][:2].lower(),label={'E1_primary':'E1: история соседей','E2_primary':'E2: иерархия'}[v['id']],split='holdout',gain=100*v['relative_gain'],lo=100*ci['ci95'][0]/base,hi=100*ci['ci95'][1]/base,n=ci['n_rows'],blocks=ci['n_blocks']))
d=pd.DataFrame(rows);f,ax=plt.subplots(figsize=(9,5));labels=[]
for i,r in d.iterrows():
 ax.errorbar(r.gain,i,xerr=[[r.gain-r.lo],[r.hi-r.gain]],fmt='o' if r.split=='holdout' else 's',color=BLUE if r.split=='holdout' else DARK,capsize=4);labels.append(r.label+(' · holdout' if r.split=='holdout' else ' · разработка'))
ax.set_yticks(range(len(d)),labels);ax.axvline(0,color=GRAY);ax.axvline(2,color=LIGHT,linestyle='--',label='Порог пользы 2%');ax.set_xlabel('Относительное снижение ошибки, % (плюс = улучшение)');ax.set_title('4. Добавочная прогностическая информация');ax.legend(frameon=False)
save(f,'04_loss_gains',d,'Показан парный block-bootstrap 95% интервал условно на обученных прогнозах: 1999 выборок блоков, seed 20261018. E1: Brier перехода к нулю; E2/E3: MAE симметричного изменения населения. На этапе разработки n=101593, 382 блока; CV с 60-км буфером. Отложенные результаты добавляются только при наличии final/evaluation.json. Порог 2% — рабочее соглашение текущего протокола, не общая норма науки. Разработка — разведка, а интервалы не калиброваны симуляцией.','e1/e2/e3 development/result.json; final/evaluation.json, если существует')
if final.exists():
 j=readj(final);rows=[]
 for v in j['results']:
  met='brier' if v['task']=='zero' else 'mae';base=v['baseline'][met];ci=v['interval'];rows.append(dict(id=v['id'],direction=v['id'][:2],gain=100*v['relative_gain'],lo=100*ci['ci95'][0]/base,hi=100*ci['ci95'][1]/base))
 d=pd.DataFrame(rows);f,axs=plt.subplots(1,2,figsize=(12,7));f.suptitle('5. Заранее фиксированные проверки устойчивости')
 for ax,direction in zip(axs,['E1','E2']):
  t=d[d.direction==direction].reset_index(drop=True)
  for i,r in t.iterrows():ax.errorbar(r.gain,i,xerr=[[r.gain-r.lo],[r.hi-r.gain]],fmt='o',color=BLUE,capsize=3)
  names={'primary':'Основная','r10':'Радиус 10 км','r60':'Радиус 60 км','nn':'Контроль близости','buffer100':'Буфер 100 км','linear':'Линейная модель','raw_control':'Контроль массы 2002','permuted':'Перестановка','original':'Исходные значения 2010','drift':'Исключение дрейфа'};ax.set_yticks(range(len(t)),[names.get(z[3:],z) for z in t.id]);ax.axvline(0,color=GRAY);ax.axvline(2,color=LIGHT,ls='--');ax.set_title(direction);ax.set_xlabel('Снижение ошибки, %')
 save(f,'05_locked_sensitivities',d,'Все заранее зафиксированные конфигурации отложенной проверки; повторные использования одного holdout не являются независимыми повторениями. r10/r60: радиус; nn: контроль нормированной близости; buffer100: буфер 100 км; linear: линейное семейство; raw_control: исходная масса 2002; permuted: перестановка добавленных признаков внутри блоков; original/drift: чувствительность к значению 2010 и координатному дрейфу. Интервалы условные, не скорректированы за множественность; это диагностика, не меню выбора успешной модели.','final/evaluation.json')
pairs=pd.read_csv(S/'e2/illustrative_pairs_preoutcome.csv');r=pairs.iloc[0];d=pd.DataFrame({'место':[r.name2010_a,r.name2010_b],'population2010':[r.p2010_a,r.p2010_b],'mass30':[r.mass30_a,r.mass30_b],'count30':[r.count30_a,r.count30_b],'maxshare30':[r.maxshare30_a,r.maxshare30_b],'effective_n30':[r.effective_n30_a,r.effective_n30_b]});f,axs=plt.subplots(1,2,figsize=(9,4.5));axs[0].bar(d['место'],d.maxshare30*100,color=[BLUE,LIGHT]);axs[0].set_ylabel('Доля крупнейшего соседа, %');axs[0].set_ylim(0,100);axs[1].bar(d['место'],d.effective_n30,color=[BLUE,LIGHT]);axs[1].set_ylabel('Эффективное число соседей');f.suptitle('6. Одинаковая масса — разная концентрация')
save(f,'06_Xonly_concentration_pair',d,f'Пример отобран без чтения исходов 2021, по лексикографическому UID. Иркутская область; собственное население {r.p2010_a:.0f}/{r.p2010_b:.0f}, масса окружения 30 км {r.mass30_a:.0f}/{r.mass30_b:.0f}, число соседей {r.count30_a:.0f}/{r.count30_b:.0f}. Эффективное число = 1/сумма квадратов долей масс. Это иллюстрация различимости признаков при близкой массе, не оценка воздействия и не национальное доказательство перекрытия.','e2/illustrative_pairs_preoutcome.csv; development_X_support.json')
c=pd.read_csv(S/'e3/regional_curves.csv');c=c[(c.grid=='absolute_km')&(c.radius_km==10)&c.region.isin(['ивановская','карелия','кировская'])];d=c[['region','initial_n','zero2021_n','initial_lcc_fixed','surviving_lcc_fixed','surviving_lcc_active']].copy();f,axs=plt.subplots(1,3,figsize=(12,4.5),sharey=False)
for ax,(_,r) in zip(axs,d.iterrows()):
 vals=[r.initial_lcc_fixed,r.surviving_lcc_fixed,r.surviving_lcc_active];ax.plot([0,1],np.array(vals[:2])*100,'o-',color=BLUE,label='Фиксированный знаменатель');ax.plot([0,1],np.array([vals[0],vals[2]])*100,'s--',color=DARK,label='Только активные');ax.set_xticks([0,1],['2010','2021']);ax.set_title(r.region.capitalize());ax.set_ylabel('Доля крупнейшей компоненты, %')
axs[0].legend(frameon=False,fontsize=8,loc='lower left');f.suptitle('7. Знаменатель меняет вывод о связности')
save(f,'07_denominator_counterexample',d,'Разведочные development-регионы; геометрический граф 10 км. Удалены только узлы с положительным населением 2010 и нулём 2021; возвращения из нуля не включены. Фиксированный знаменатель равен числу начальных узлов; активный знаменатель — числу оставшихся. Во всех трёх примерах доля с активным знаменателем растёт при снижении доли с фиксированным. Это математическая чувствительность метрики, не доказательство улучшения связности и не результат пространственной нулевой модели. Шкалы y у панелей различаются.','e3/regional_curves.csv; descriptive_summary.json')
cal=S/'statistics/calibration/run_v1/results.json'
if cal.exists():
 j=readj(cal);d=pd.DataFrame(j['results']);f,ax=plt.subplots(figsize=(9,4.8));x=np.arange(len(d));y=100*d.coverage.to_numpy();lo=np.array([z[0] for z in d.coverage_mc_wilson95])*100;hi=np.array([z[1] for z in d.coverage_mc_wilson95])*100
 ax.errorbar(x,y,yerr=[y-lo,hi-y],fmt='o',capsize=5,color=BLUE,markersize=7);ax.axhline(95,color=DARK,ls='--',label='Номинальные 95%');ax.set_xticks(x,['Независимые блоки','Зависимость 100 км','Зависимость 300 км']);ax.set_ylim(65,100);ax.set_ylabel('Покрытие известного нуля, %');ax.set_title('8. Неопределённость зависит от дальности связи');ax.legend(frameon=False)
 save(f,'08_synthetic_coverage',d,'Синтетическая диагностика bootstrap на реальной геометрии 89 отложенных блоков (19731 запись риска): 300 генераций гауссовых разностей потерь с известным нулевым средним, 499 bootstrap-повторов. Вертикальные интервалы — Wilson 95% неопределённость доли покрытия в Monte Carlo, не интервалы исследовательского эффекта. Зависимость 100/300 км задана генератором, не оценена из реальных остатков. Это не калибровка learner, отбора, прогностического эффекта или p-value. При дальней зависимости номинальный 95% интервал может недопокрывать; реальная дальность не установлена.','statistics/calibration/run_v1/results.json')
(O/'captions.md').write_text('# Подписи к научным рисункам\n\n'+'\n'.join(captions))
files=sorted(O.glob('[0-9][0-9]_*.png')); thumbs=[]
for p in files:
 im=Image.open(p).convert('RGB');im.thumbnail((800,450));tile=Image.new('RGB',(820,490),'white');tile.paste(im,((820-im.width)//2,25));ImageDraw.Draw(tile).text((15,465),p.stem,fill='black');thumbs.append(tile)
sheet=Image.new('RGB',(1640,490*((len(thumbs)+1)//2)), '#e4e8eb')
for i,im in enumerate(thumbs):sheet.paste(im,((i%2)*820,(i//2)*490))
sheet.save(O/'contact_sheet.jpg',quality=88)
(O/'manifest.json').write_text(json.dumps({'figures':sources,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'final_available':final.exists(),'status':'rendered; visual_review_pending'},ensure_ascii=False,indent=2))
print('rendered',len(files),'figures')
