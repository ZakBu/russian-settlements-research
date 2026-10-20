#!/usr/bin/env python3
"""Source-backed point atlas; no synthetic hulls or inferred administrative borders."""
from pathlib import Path
import json,hashlib,argparse,textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from pyproj import Transformer
H=Path(__file__).resolve().parent;R=H.parent
INITIAL_HASHES={}
def watch(paths):
 for p in paths:
  p=Path(p).resolve()
  if p.exists() and str(p) not in INITIAL_HASHES:INITIAL_HASHES[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
watch([R/'axis/full_settlement_axis.parquet',H/'sources/ne_110m_coastline.geojson'])
T=Transformer.from_crs('EPSG:4326','+proj=aea +lat_1=50 +lat_2=70 +lat_0=60 +lon_0=100 +datum=WGS84 +units=m +no_defs',always_xy=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','pdf.fonttype':42,'axes.titlesize':12,'figure.facecolor':'#fbfaf7','axes.facecolor':'#f0f4f4'})
A=pd.read_parquet(R/'axis/full_settlement_axis.parquet');valid=A.lat.notna()&A.lon.notna();A['_x'],A['_y']=T.transform(A.lon.to_numpy(),A.lat.to_numpy())
xy=A.loc[valid,['_x','_y']].to_numpy();bounds=np.nanquantile(xy,[0,1],axis=0);coasts=[]
p=H/'sources/ne_110m_coastline.geojson'
if p.exists():
 try:
  for f in json.loads(p.read_text())['features']:
   g=f['geometry'];segments=[g['coordinates']] if g['type']=='LineString' else g['coordinates']
   for seg in segments:
    z=np.array(seg);x,y=T.transform(z[:,0],z[:,1]);z=np.c_[x,y];z[np.r_[False,np.abs(np.diff(x))>2e6]]=np.nan;coasts.append(z)
 except Exception:pass
RECEIPTS=[]
def base(ax,title):
 if coasts:ax.add_collection(LineCollection(coasts,color='#b9c7c8',linewidth=.45,zorder=0))
 ax.set_xlim(bounds[0,0]-1.5e5,bounds[1,0]+1.5e5);ax.set_ylim(bounds[0,1]-1.5e5,bounds[1,1]+1.5e5);ax.set_aspect('equal');ax.set_anchor('W');ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,loc='left',fontweight='bold',pad=10)
 for spine in ax.spines.values():spine.set_visible(False)
 ax.scatter(A.loc[valid,'_x'],A.loc[valid,'_y'],s=.08,c='#c5cccc',rasterized=True,linewidths=0,alpha=.35)
def points(ax,d,color,size=.6,alpha=.7):
 if len(d):
  x,y=T.transform(d.lon.to_numpy(float),d.lat.to_numpy(float));ax.scatter(x,y,s=size,c=color,alpha=alpha,linewidths=0,rasterized=True)
def export(fig,name,caption,sourcepaths):
 sourcepaths=list(dict.fromkeys(list(sourcepaths)+[R/'axis/full_settlement_axis.parquet']+([H/'sources/ne_110m_coastline.geojson'] if (H/'sources/ne_110m_coastline.geojson').exists() else [])))
 before={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in sourcepaths}
 for key,value in before.items():
  if INITIAL_HASHES.get(key)!=value:raise RuntimeError(f'Input changed before figure export: {key}')
 fig.text(.035,.017,caption,ha='left',va='bottom',fontsize=8,color='#48575a',wrap=True)
 files=[]
 for ext in ['png','svg','pdf']:
  p=H/f'{name}.{ext}';fig.savefig(p,dpi=200,bbox_inches='tight',facecolor=fig.get_facecolor());files.append({'path':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 plt.close(fig)
 after={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in sourcepaths}
 if before!=after:raise RuntimeError(f'Input changed while exporting {name}; rerun from stable model outputs')
 RECEIPTS.append({'figure':name,'outputs':files,'inputs':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sourcepaths},'geometry':'point observations and optional graph relations; no hull boundaries','inputs_stable_before_read_before_export_after_export':True})
def colorbar(fig,p,ax,**kwargs):
 cax=inset_axes(ax,width='2.8%',height='95%',loc='center left',bbox_to_anchor=(1.02,0,1,1),bbox_transform=ax.transAxes,borderpad=0)
 return fig.colorbar(p,cax=cax,extend=kwargs.get('extend','neither'))
def legend(ax,items):
 ax.legend(handles=[Line2D([],[],marker='o',linestyle='',markersize=5,color=c,label=s) for s,c in items],loc='lower left',fontsize=8,framealpha=.9)
def coverage():
 snapfile=R/'transport/settlement_road_snap.parquet';snap=pd.read_parquet(snapfile);d=A.merge(snap[['id','snap_status','snap_km','weak_component']],on='id',how='left',validate='one_to_one')
 fig,axs=plt.subplots(3,1,figsize=(15,19));fig.suptitle('Поселенческая ось и измеримость дорожного тяготения',fontsize=18,x=.035,ha='left',fontweight='bold')
 base(axs[0],f'Перепись 2021: {len(A):,} сущностей; координаты у {int(valid.sum()):,}'.replace(',',' '))
 observed=d.population_2021.notna()&d.is_additive_source_unit;points(axs[0],d[observed&d.lat.notna()],'#126c85',.6,.65);points(axs[0],d[~observed&d.lat.notna()],'#ca8251',.8,.6)
 legend(axs[0],[(f'НП 2021 с населением и аддитивным статусом: {int(observed.sum()):,}','#126c85'),(f'Прочие сущности оси: {int((~observed).sum()):,}','#ca8251')])
 base(axs[1],'Дороги OSM 19.10.2026: привязка к графу, без реконструкции сети 2021')
 for status,color in [('within2km','#218c75'),('2to5km','#d5a33e'),('5to10km','#dc7c45'),('over10km_unaccepted','#cc6653')]:
  mask=d.snap_status.eq(status);points(axs[1],d[mask],color,.6,.65)
 missing=d.snap_status.isna();points(axs[1],d[missing&d.lat.notna()],'#7b728a',.8,.8)
 legend(axs[1],[(f'{s}: {int(d.snap_status.eq(s).sum()):,}',c) for s,c in [('within2km','#218c75'),('2to5km','#d5a33e'),('5to10km','#dc7c45'),('over10km_unaccepted','#cc6653')]]+[(f'Нет записи привязки: {int(missing.sum()):,}','#7b728a')])
 base(axs[2],'Круглогодичная сеть: привязка и раздельные компоненты связности')
 main_component=int(snap.weak_component.value_counts().idxmax());accepted=d.snap_km.le(10);main=accepted&d.weak_component.eq(main_component);other=accepted&~d.weak_component.eq(main_component);far=d.snap_km.gt(10)
 for mask,color in [(main,'#297a95'),(other,'#d69335'),(far,'#c5564b')]:points(axs[2],d[mask],color,.7,.7)
 legend(axs[2],[(f'Крупнейший компонент, ≤10 км: {int(main.sum()):,}','#297a95'),(f'Прочие компоненты, ≤10 км: {int(other.sum()):,}','#d69335'),(f'Привязка >10 км не принята: {int(far.sum()):,}','#c5564b')])
 fig.subplots_adjust(top=.9,bottom=.065,hspace=.2,left=.035,right=.98)
 export(fig,'01_axis_road_coverage','Население — переписи 2002 / 2010 / 2021; дороги — снимок 2026, исключены зимние/сезонные/условные пути. Связность графа не равна фактическим поездкам.\nПроекция Альберса 50° / 70° с.ш.; береговая линия Natural Earth для ориентации. Отсутствие координат отражено в счетчике, на карте такая запись не показывается.',[R/'axis/full_settlement_axis.parquet',snapfile,R/'transport/graph_receipt.json',R/'transport/yearround_profile_receipt.json'])
def themes():
 pf=R/'typology/settlement_features.parquet';f=pd.read_parquet(pf);d=A.merge(f,on='id',validate='one_to_one')
 layers=[('Рекреационные объекты: контекст 1 / 3 км','recreation_facility_evidence','#248e8c'),('Садовые участки OSM: контекст 3 км','dacha_landuse_evidence','#77a144'),('Исторические моногорода 2012','historical_monotown_evidence','#b37b41'),('Добывающие площадки OSM: контекст 5 км','mapped_resource_site_context_evidence','#87649c')]
 fig,axs=plt.subplots(2,2,figsize=(18,10));fig.suptitle('Независимые тематические слои для проверки Word-типов',fontsize=18,x=.035,ha='left',fontweight='bold')
 for ax,(title,col,color) in zip(axs.flat,layers):
  mask=d[col].fillna(False);base(ax,f'{title}\n{int(mask.sum()):,} поселений со свидетельством'.replace(',',' '));points(ax,d[mask],color,3.5 if col=='historical_monotown_evidence' else 1.1,.8)
 fig.subplots_adjust(top=.87,bottom=.1,hspace=.23,wspace=.04)
 export(fig,'02_functional_evidence','Минздрав / OSM 2026 и исторический реестр 2012. Ближайший объект — контекст, принадлежность поселению и поездки не доказаны.\nДобыча не равна переходу на вахту; моногород не равен утрате промышленности; садовые участки не равны дачной миграции.',[R/'axis/full_settlement_axis.parquet',pf])
def demographics():
 fig,axs=plt.subplots(2,1,figsize=(15,12));fig.suptitle('Демографическая ось концепции: динамика поселений',fontsize=18,x=.035,ha='left',fontweight='bold')
 for ax,(y0,y1) in zip(axs,[(2002,2010),(2010,2021)]):
  p0=A[f'population_{y0}'];p1=A[f'population_{y1}'];ok=p0.gt(0)&p1.ge(0)&A.is_additive_source_unit
  rate=(p1/p0)**(1/(y1-y0))-1
  masks=[(ok&rate.lt(-.0025),'#bf615a','Сокращение'),(ok&rate.abs().le(.0025),'#b8ab88','Стабильность'),(ok&rate.gt(.0025),'#288f88','Рост')]
  base(ax,f'{y0}–{y1}: среднегодовая динамика; порог ±0,25%')
  for mask,color,label in masks:points(ax,A[mask],color,.65,.65)
  legend(ax,[(f'{label}: {int(mask.sum()):,}',color) for mask,color,label in masks]+[(f'Без вычислимой пары: {int((~ok).sum()):,}','#c5cccc')])
 fig.subplots_adjust(top=.88,bottom=.08,hspace=.2,left=.035,right=.98)
 export(fig,'05_settlement_demographic_dynamics','Исходная ось: часть 2010 — вторичные protected-значения с неподтвержденным охватом; первичные поправки четырех регионов основной модели здесь не применены.\nАдминистративные изменения не устранены; это не классификация СГРТ. Начальное 0 не получает искусственного темпа роста; финальное 0 означает −100%.',[R/'axis/full_settlement_axis.parquet'])
def ethnicity_context():
 pf=R/'typology/settlement_features.parquet';d=A.merge(pd.read_parquet(pf),on='id',validate='one_to_one');col='share_declared_not_russian_response2021';ok=d[col].notna()&d.lat.notna()&d.lon.notna()
 fig,ax=plt.subplots(figsize=(15,8));fig.suptitle('Этнические ответы переписи 2021: описательный контекст',fontsize=18,x=.035,ha='left',fontweight='bold');base(ax,f'Пригодных долей: {int(d[col].notna().sum()):,}; подавленных записей: {int(d.ethnicity_suppressed2021.sum()):,}'.replace(',',' '))
 x,y=T.transform(d.loc[ok,'lon'].to_numpy(),d.loc[ok,'lat'].to_numpy());p=ax.scatter(x,y,c=d.loc[ok,col],s=.9,cmap='viridis',vmin=0,vmax=1,alpha=.8,linewidths=0,rasterized=True)
 cb=colorbar(fig,p,ax=ax,fraction=.025,pad=.02,panchor=False);cb.set_label('1 − русские ответы / лица, указавшие национальность')
 fig.subplots_adjust(top=.82,bottom=.12,left=.035,right=.98)
 export(fig,'06_ethnic_composition_context','Публичные агрегированные ответы переписи 2021; категории допускают множественный ответ. Подавленные значения −9 не превращены в нули.\nДоля среди заявивших не измеряет язык, причины рождаемости или миграции. Это не доказательство этнокультурного механизма Word 6.',[R/'axis/full_settlement_axis.parquet',pf])
def agro_context():
 cp=R/'context/climate_settlement_features.parquet';sp=R/'context/soil_settlement_features.parquet';mp=R/'context/municipal_settlement_features.parquet'
 d=A.merge(pd.read_parquet(cp),on='id',validate='one_to_one').merge(pd.read_parquet(sp),on='id',validate='one_to_one')
 layers=[('Сумма активных температур >10°C','climate_gaez_sat_above10_cday_1981_2010','YlOrRd',0,6000,'°C · суток'),('Увлажнение апреля–сентября','climate_gaez_summer_precipitation_over_pet_1981_2010','BrBG',0,2,'Осадки / потенциальная эвапотранспирация'),('Почвенная оценка FAO: нижняя граница класса','soil_gaez_low_input_most_limiting_rating_class_rating_lower','YlGn',0,1,'Рейтинг 0…1; кукуруза, низкие вложения')]
 fig,axs=plt.subplots(3,1,figsize=(12,17));fig.suptitle('Аграрные условия: реальные независимые природные слои',fontsize=18,x=.035,ha='left',fontweight='bold')
 for ax,(title,col,cmap,lo,hi,unit) in zip(axs,layers):
  ok=d[col].notna()&d.lat.notna()&d.lon.notna();base(ax,title+f' · {int(d[col].notna().sum()):,} значений'.replace(',',' '));x,y=T.transform(d.loc[ok,'lon'].to_numpy(),d.loc[ok,'lat'].to_numpy());p=ax.scatter(x,y,c=d.loc[ok,col],s=.6,cmap=cmap,vmin=lo,vmax=hi,alpha=.8,linewidths=0,rasterized=True);cb=colorbar(fig,p,ax=ax,fraction=.022,pad=.015,panchor=False,extend='max' if col.endswith('1981_2010') and hi==2 else 'neither');cb.set_label(unit)
 fig.subplots_adjust(top=.91,bottom=.07,left=.035,right=.98,hspace=.2)
 export(fig,'07_agro_climate_soil','FAO GAEZ v4, сетка 5′: климатическая норма 1981–2010; САТ рассчитана источником из суточных температур. P/PET ≥ 2 показано верхним цветом.\nПочвенный рейтинг относится к кукурузе при низких вложениях: это не российский бонитет и не измеренная урожайность. Пропуски — серый фон.',[R/'axis/full_settlement_axis.parquet',cp,sp])
 m=A.merge(pd.read_parquet(mp,columns=['id','context_sown_share_of_farmland_source_harmonized_usable_2008','context_historical_boundary_equivalence_proven']),on='id',validate='one_to_one');col='context_sown_share_of_farmland_source_harmonized_usable_2008';ok=m[col].notna()&m.lat.notna()&m.lon.notna()
 fig,ax=plt.subplots(figsize=(15,8));fig.suptitle('Посевная доля муниципального контекста: доступный срез 2008',fontsize=18,x=.035,ha='left',fontweight='bold');base(ax,f'Посевы / сельхозугодья одного года · {int(m[col].notna().sum()):,} поселений с контекстом'.replace(',',' '));x,y=T.transform(m.loc[ok,'lon'].to_numpy(),m.loc[ok,'lat'].to_numpy());p=ax.scatter(x,y,c=m.loc[ok,col],s=.9,cmap='YlGn',vmin=0,vmax=1,alpha=.8,linewidths=0,rasterized=True);cb=colorbar(fig,p,ax=ax,fraction=.025,pad=.02,panchor=False);cb.set_label('Посевная площадь / площадь сельхозугодий МО')
 fig.subplots_adjust(top=.82,bottom=.13,left=.035,right=.98)
 export(fig,'08_municipal_sown_share_2008','БДМО / «Если быть точным»: показатели 2008 связаны по ретроспективно гармонизированному коду. Эквивалентность границ 2008 → 2021 не доказана.\nОдинаковое значение МО повторено у его поселений; это не собственная посевная доля НП, значения по НП не суммируются. Строгие доли 2010 / 2021 не вычислимы.',[R/'axis/full_settlement_axis.parquet',mp])
def current_mono_map():
 p=R/'typology/settlement_features.parquet';d=A.merge(pd.read_parquet(p),on='id',validate='one_to_one');fig,ax=plt.subplots(figsize=(15,8));fig.suptitle('Действующий перечень моногородов: юридический статус 2026',fontsize=18,x=.035,ha='left',fontweight='bold');base(ax,'121 буквальная уникальная привязка из 264 муниципальных обозначений')
 items=[]
 for k,color,label in [(1,'#bd594f','Наиболее сложное положение'),(2,'#d49b3c','Риски ухудшения'),(3,'#268f86','Стабильное положение')]:
  ok=d.current_monotown_category2026.eq(k).fillna(False);points(ax,d[ok],color,8,.9);items.append((f'{label}: {int(ok.sum())}',color))
 legend(ax,items);fig.subplots_adjust(top=.82,bottom=.13,left=.035,right=.98)
 export(fig,'09_current_monotowns_2026','Распоряжение 11.03.2026 №469-р, редакция 13.04.2026 №822-р; действует с 01.06.2026. 264 МО: 52 / 149 / 63 по категориям; карта — только 121 привязка.\nИсторический перечень 2012 показан отдельно на карте 02. Юридическая сложность МО не доказывает сокращение промышленности 2002–2021. 143 строки не размещены.',[R/'axis/full_settlement_axis.parquet',p,R/'typology/current_monotowns2026.csv'])
def type_inputs(m):
 canonical=R/'typology/canonical'/m.name
 hp=canonical/'word_type_hypotheses.parquet'
 if not hp.exists():return m/'word_type_hypotheses.parquet',[]
 receipt=canonical/'receipt.json';manifest=canonical/'manifest.json'
 if not(receipt.exists() and manifest.exists()):raise RuntimeError('Canonical overlay exists but is not complete')
 watch([hp,receipt,manifest]);meta=json.loads(manifest.read_text())
 assert hashlib.sha256(hp.read_bytes()).hexdigest()==meta['files'][hp.name]['sha256'],'Canonical table checksum mismatch'
 assert hashlib.sha256(receipt.read_bytes()).hexdigest()==meta['receipt_sha256'],'Canonical receipt checksum mismatch'
 assert hashlib.sha256((m/'output_manifest.json').read_bytes()).hexdigest()==meta['model_output_manifest_sha256'],'Canonical model binding mismatch'
 return hp,[receipt,manifest,m/'output_manifest.json']

def modelmaps(m):
 m=m.resolve()
 config_name={'output_word_ci_2021_inclusive':'model_inputs_word_ci_2021_inclusive.json','output_word_ci_2021_baseline':'model_inputs_word_ci_2021.json','output_2021_restricted_baseline':'model_inputs_2021_restricted.json','output_2021_restricted_inclusive':'model_inputs_2021_restricted_inclusive.json'}.get(m.name)
 config=json.loads((m.parent/config_name).read_text()) if config_name else {}
 service_year=config.get('mass_reference_year','см. конфигурацию')
 service_period=f'{service_year} + текущие 2026' if 'inclusive' in m.name else str(service_year)
 config_sources=[m.parent/config_name] if config_name else []
 thematic_dates=f'Сеть услуг: {service_period}; дороги/рекреация/ресурсы: OSM / Минздрав 2026; моногорода 2012 и 2026 отдельно.'
 mp=m/'memberships.parquet';sp=m/'systems.parquet';hp,type_sources=type_inputs(m);watch(type_sources);config_sources+=type_sources
 type_title='Девять Word-типов: полный набор и операционные гипотезы' if type_sources else 'Широкие операционные прототипы: чувствительность intrinsic'
 type_note='Canonical: малый город/пгт ≤50 тыс. для 2/3/5/7/8; для 5 крупный город ≥100 тыс. в 90 мин — сценарий, не буквальный порог Word.' if type_sources else 'Широкие прототипы intrinsic: дополнительные буквальные ограничения canonical overlay здесь не применены.'
 if not all(p.exists() for p in [mp,sp,hp]):return
 d=pd.read_parquet(mp);s=pd.read_parquet(sp);hyp=pd.read_parquet(hp)
 levels=sorted(s.level.unique());fig,axs=plt.subplots(len(levels),1,figsize=(15,6*len(levels)),squeeze=False);fig.suptitle('Дорожные СГРТ: уровни расчетного потенциала тяготения',fontsize=17,x=.035,ha='left',fontweight='bold')
 for ax,lev in zip(axs.flat,levels):
  col=f'center_id_l{lev}';base(ax,f'Уровень {lev} · {len(s[s.level.eq(lev)]):,} центров'.replace(',',' '))
  if col not in d:continue
  good=d[col].notna();centerlabels=sorted(d.loc[good,col].unique());codes={c:i for i,c in enumerate(centerlabels)};x,y=T.transform(d.loc[good,'lon'].to_numpy(float),d.loc[good,'lat'].to_numpy(float));colors=[codes[c]%20 for c in d.loc[good,col]]
  ax.scatter(x,y,c=colors,cmap='tab20',s=.7,alpha=.7,linewidths=0,rasterized=True)
  ss=s[s.level.eq(lev)];points(ax,ss,'#1d282d',3,.9);points(ax,d[~good],'#cf563e',.65,.65)
  legend(ax,[(f'Точки с назначением: {int(good.sum()):,}; цвет повторяется для разных центров','#467b96'),(f'Центры: {len(ss):,}','#1d282d'),(f'Без назначения: {int((~good).sum()):,}; с координатами: {int((~good & d.lat.notna() & d.lon.notna()).sum()):,}','#cf563e'),(f'Без координат, не нанесены: {int((d.lat.isna() | d.lon.isna()).sum()):,}','#9d9d9d')])
 fig.subplots_adjust(top=.89,bottom=.07,hspace=.2,left=.035,right=.98);export(fig,'03_road_hierarchy_'+m.name,'Модельная принадлежность по дорожному времени; это предварительная гипотеза функциональных районов.\nНаселение 2021; дорожная сеть 2026. Цвета точек повторяются и не задают полигоны границ. Входная конфигурация: '+m.name,[mp,sp]+config_sources)
 # Both long and wide formats are supported; per-type evidence status remains separate.
 rows=[]
 for _,r in hyp.iterrows():
  for k in range(1,10):
   v=r.get(f'word_type{k}',None)
   if v is not None:rows.append({'level':r['level'],'center_id':r['center_id'],'type':k,'status':str(v)})
 if not rows and {'word_type','rule_status'}.issubset(hyp.columns):rows=hyp.rename(columns={'word_type':'type','rule_status':'status'}).to_dict('records')
 if not rows:return
 z=pd.DataFrame(rows).merge(s[['level','center_id','lat','lon']],on=['level','center_id'],validate='many_to_one');lowest=min(levels)
 all_type_rows=z.copy()
 for selected_level in [None]+levels:
  z=all_type_rows if selected_level is None else all_type_rows[all_type_rows.level.eq(selected_level)]
  suffix='' if selected_level is None else f'_level{selected_level}'
  level_label=f'Все {len(levels)} уровня' if selected_level is None else f'Уровень {selected_level}'
  fig,axs=plt.subplots(3,3,figsize=(21,17));fig.suptitle(type_title+'\n'+level_label,fontsize=18,x=.035,ha='left',fontweight='bold')
  for k,ax in enumerate(axs.flat,1):
   q=z[z.type.eq(k)];title=q.word_type_name.iloc[0] if len(q) and 'word_type_name' in q else f'Word-тип {k} (название отсутствует в источнике)';base(ax,textwrap.fill(f'{k}. {title}',width=43,break_long_words=False,break_on_hyphens=False));ax.set_title(textwrap.fill(f'{k}. {title}',width=43,break_long_words=False,break_on_hyphens=False),fontsize=10,loc='left',fontweight='bold');yes=q.status.str.startswith('satisfied')|q.status.isin(['True','true']);unk=q.status.str.startswith('unknown');partial=q.get('operational_hypothesis',q.get('descriptive_partial_candidate_not_proven_type',pd.Series(False,index=q.index))).fillna(False).astype(bool)&~yes;points(ax,q[~yes&~partial],'#747b78',.55,.45);points(ax,q[partial],'#ce851b',12,.95);points(ax,q[yes],'#168b86',16,.95)
   uncertain_count=int(q.get('dynamics_uses_secondary_protected_values',pd.Series(False,index=q.index)).fillna(False).sum())
   ax.text(.02,.02,f'Все условия: {int(yes.sum())} · гипотезы: {int(partial.sum())}\nНеизвестно: {int(unk.sum())} · систем×уровней: {len(q)}\nНеподтв. рамка населения: {uncertain_count}',transform=ax.transAxes,fontsize=8)
  fig.legend(handles=[Line2D([],[],marker='o',linestyle='',color=c,label=t) for c,t in [('#168b86','Полный Word-набор'),('#d89a36','HYPOTHESIS: операционное ядро'),('#747b78','Другие недоказанные центры')]],loc='lower center',bbox_to_anchor=(.5,.055),ncol=3,frameon=False,fontsize=10)
  fig.subplots_adjust(top=.89,bottom=.1,hspace=.55,wspace=.08);export(fig,'04_nine_word_types_'+m.name+suffix,'Зеленый — полный Word-набор; оранжевый — операционное ядро HYPOTHESIS, полный набор не выполнен/не установлен; серый — прочие недоказанные.\n'+level_label+'. Случай = центр×уровень; уровни вложены. Маркеры — центры, фон — НП. '+thematic_dates+' Этносостав 2021; гипотезы не равны полным типам.\n'+type_note+' '+m.name,[sp,hp]+config_sources)

def broad_prototype_comparison(m):
 m=m.resolve();hp,extra=type_inputs(m);p=hp.parent/'broad_prototypes.parquet';sp=m/'systems.parquet'
 if not p.exists():return
 watch([p,sp]+extra);b=pd.read_parquet(p);canonical=pd.read_parquet(hp);systems=pd.read_parquet(sp);b=b.merge(systems[['level','center_id','lat','lon']],on=['level','center_id'],validate='many_to_one');accepted=set(map(tuple,canonical.loc[canonical.operational_hypothesis.fillna(False),['level','center_id','word_type']].to_numpy()));b['_canonical']=[tuple(x) in accepted for x in b[['level','center_id','word_type']].to_numpy()]
 fig,axs=plt.subplots(3,3,figsize=(21,17));fig.suptitle('Широкие прототипы и буквальные операционные ограничения Word\nСравнение на неизменной физической сетке; не доказанные типы',fontsize=18,x=.035,ha='left',fontweight='bold')
 for k,ax in enumerate(axs.flat,1):
  q=b[b.word_type.eq(k)];title=canonical.loc[canonical.word_type.eq(k),'word_type_name'].iloc[0];base(ax,textwrap.fill(f'{k}. {title}',43,break_long_words=False,break_on_hyphens=False));ax.set_title(textwrap.fill(f'{k}. {title}',43,break_long_words=False,break_on_hyphens=False),fontsize=10,loc='left',fontweight='bold');points(ax,q[~q._canonical],'#508aab',9,.9);points(ax,q[q._canonical],'#ce851b',12,.95);ax.text(.02,.02,f'Широких прототипов: {len(q)}\nПосле буквальных ограничений: {int(q._canonical.sum())}',transform=ax.transAxes,fontsize=8)
 fig.legend(handles=[Line2D([],[],marker='o',linestyle='',color=c,label=t) for c,t in [('#508aab','BROAD: не проходит буквальные ограничения'),('#ce851b','CANONICAL: операционная гипотеза')]],loc='lower center',bbox_to_anchor=(.5,.055),ncol=2,frameon=False,fontsize=10);fig.subplots_adjust(top=.89,bottom=.1,hspace=.55,wspace=.08)
 export(fig,'04b_broad_prototypes_'+m.name,'Широкие прототипы сохранены для диагностики; классификация Word использует canonical overlay. Доказанных полных типов нет. Случай = центр×уровень, уровни вложены.\nДополнительные ограничения: малый город/пгт ≤50 тыс.; для типа 5 крупный город ≥100 тыс. в 90 мин (сценарий); география типа 7 без свидетельства UNKNOWN. '+m.name,[p,hp,sp]+extra)

def demographic_matrix(m):
 m=m.resolve();hp=m/'word_type_hypotheses.parquet'
 if not hp.exists():return
 q=pd.read_parquet(hp).drop_duplicates(['level','center_id']);good=q.population_pair_complete.fillna(False)&q.center_annual_rate.notna()&q.rural_annual_rate.notna();d=q[good]
 fig,ax=plt.subplots(figsize=(11,9));fig.suptitle('Центр и сельское окружение: фактическая динамическая матрица',fontsize=16,x=.05,ha='left',fontweight='bold')
 for lev,g in d.groupby('level'):
  exact=g.get('population_pair_exact_primary_supported',pd.Series(False,index=g.index)).fillna(False)
  for mask,marker,scope in [(exact,'o','первичные подтвержденные значения'),(~exact,'x','рамка не подтверждена')]:
   gg=g[mask]
   if len(gg):ax.scatter(100*gg.center_annual_rate,100*gg.rural_annual_rate,s=9,alpha=.45,marker=marker,label=f'Уровень {lev}, {scope}: {len(gg)}',linewidths=.5,rasterized=True)
 for v in [-.25,.25]:ax.axvline(v,color='#9eaaa9',lw=.7,ls='--');ax.axhline(v,color='#9eaaa9',lw=.7,ls='--')
 ax.axvline(0,color='#61716f',lw=.8);ax.axhline(0,color='#61716f',lw=.8);ax.set_xscale('symlog',linthresh=.5);ax.set_yscale('symlog',linthresh=.5);ax.set_xlabel('Среднегодовая динамика населения центра, %');ax.set_ylabel('Среднегодовая динамика сельского окружения, %');ax.grid(alpha=.15);ax.legend(loc='best');ax.set_title(f'Только полные пары 2010–2021: {len(d)}; неполные/невычислимые исключены: {int((~good).sum())}',loc='left',fontsize=11)
 fig.subplots_adjust(top=.88,bottom=.16,left=.1,right=.97)
 export(fig,'10_center_rural_dynamics_'+m.name,'Одна точка — система; уровни вложены. Крестики: есть вторичные protected-значения без подтвержденной сопоставимости охвата, динамика предварительная.\nПунктир: пороги ±0,25% в год. Симметричная логарифмическая шкала; границы НП во времени не проверены, административные изменения не устранены. Квадрант не равен Word-типу. '+m.name,[hp])
def regional_maps(m):
 m=m.resolve();mp=m/'memberships.parquet';sp=m/'systems.parquet'
 if not(mp.exists() and sp.exists()):return
 d=pd.read_parquet(mp);s=pd.read_parquet(sp);lev=min(s.level);col=f'center_id_l{lev}'
 if col not in d:col='assigned_center_id'
 centers=sorted(d[col].dropna().unique());codes={x:i for i,x in enumerate(centers)}
 windows=[('Северо-Запад',27,36,58,62),('Кубань',36,43,43,47),('Башкортостан',53,60,51,57)]
 fig,axs=plt.subplots(1,3,figsize=(21,8));fig.suptitle('Региональные окна: нижний уровень дорожных СГРТ',fontsize=19,x=.035,ha='left',fontweight='bold')
 for ax,(name,x0,x1,y0,y1) in zip(axs,windows):
  base(ax,f'{name} · {x0}–{x1}° в.д. / {y0}–{y1}° с.ш.')
  bx=np.r_[np.linspace(x0,x1,30),np.linspace(x0,x1,30),np.full(30,x0),np.full(30,x1)];by=np.r_[np.full(30,y0),np.full(30,y1),np.linspace(y0,y1,30),np.linspace(y0,y1,30)];xx,yy=T.transform(bx,by);ax.set_xlim(min(xx),max(xx));ax.set_ylim(min(yy),max(yy))
  q=d[d.lon.between(x0,x1)&d.lat.between(y0,y1)];ok=q[col].notna();x,y=T.transform(q.loc[ok,'lon'].to_numpy(float),q.loc[ok,'lat'].to_numpy(float));ax.scatter(x,y,c=[codes[x]%20 for x in q.loc[ok,col]],cmap='tab20',vmin=0,vmax=19,s=5,alpha=.75,linewidths=0,rasterized=True);points(ax,q[~ok],'#ce5445',5,.9)
  ss=s[s.level.eq(lev)&s.lon.between(x0,x1)&s.lat.between(y0,y1)];points(ax,ss,'#182b30',12,.9)
  pop='system_population_known_sum_2021';labels=ss.sort_values(pop,ascending=False).head(5) if pop in ss else ss.sort_values('name').head(5)
  anchors=q[q.id.isin(['ctx:RU-FED-MOW','ctx:RU-FED-SPB'])];points(ax,anchors,'#182b30',22,.95);labels=pd.concat([labels,anchors],ignore_index=True).drop_duplicates('id' if 'id' in labels else 'name')
  for _,r in labels.iterrows():
   x,y=T.transform(r.lon,r.lat);ax.annotate(r['name'],(x,y),xytext=(3,4),textcoords='offset points',fontsize=8,bbox={'facecolor':'white','alpha':.7,'edgecolor':'none','pad':1})
  xlo,xhi=ax.get_xlim();ylo,yhi=ax.get_ylim();barx=xlo+.05*(xhi-xlo);bary=ylo+.06*(yhi-ylo);ax.plot([barx,barx+100000],[bary,bary],c='#213838',lw=2);ax.text(barx,bary+.015*(yhi-ylo),'100 км в проекции',fontsize=8)
  ax.text(.02,.015,f'Назначено: {int(ok.sum())}; без центра L1: {int((~ok).sum())}',transform=ax.transAxes,fontsize=8,bbox={'facecolor':'white','alpha':.8,'edgecolor':'none'})
 fig.subplots_adjust(top=.87,bottom=.13,left=.035,right=.98,wspace=.08)
 export(fig,'11_regional_sgrt_'+m.name,'Окна зафиксированы до оценки точности. Цвет — ID системы нижнего уровня (цвета повторяются); черные точки — центры, красные — без центра нижнего уровня (могут присоединиться выше).\nПодписаны 5 крупнейших известных систем и федеральные внешние центры в окне. Масштаб в проекции Альберса; точки не означают доказанные полигоны границ. '+m.name,[mp,sp])
 (H/'regional_windows.json').write_text(json.dumps({'windows':[dict(name=n,lon_min=a,lon_max=b,lat_min=c,lat_max=d) for n,a,b,c,d in windows],'selection':'predeclared_by_root_before_results; notconditionedonaccuracy','labels':'five largest known2021system populations plus exact external federal anchors within window; readability only'},ensure_ascii=False,indent=2))
def experimental_bonitet():
 p=R/'soil_bonitet_recovery/experimental_bonitet_settlement_intervals.parquet'
 if not p.exists():return
 d=A.merge(pd.read_parquet(p),on='id',validate='one_to_one');lo='soil_bonitet_atlas_experimental_interval_lower';hi='soil_bonitet_atlas_experimental_interval_upper';ok=d[lo].notna()&d[hi].notna()&d.lat.notna()&d.lon.notna()
 from matplotlib.colors import BoundaryNorm
 fig,ax=plt.subplots(figsize=(15,8));fig.suptitle('Бонитет из почвенного атласа: экспериментальные интервалы',fontsize=18,x=.035,ha='left',fontweight='bold');base(ax,f'{int(ok.sum()):,} устойчивых интервалов; значения не приняты в основную модель'.replace(',',' '));x,y=T.transform(d.loc[ok,'lon'].to_numpy(),d.loc[ok,'lat'].to_numpy());classes=(d.loc[ok,lo]/10).to_numpy();cm=plt.get_cmap('YlGn',13);pnt=ax.scatter(x,y,c=classes,s=1.2,cmap=cm,norm=BoundaryNorm(np.arange(-.5,13.5,1),13),linewidths=0,alpha=.9,rasterized=True);cb=colorbar(fig,pnt,ax=ax);cb.set_ticks(range(13));cb.set_ticklabels([f'{i*10}–{(i+1)*10}' if i<12 else '120–125' for i in range(13)]);cb.set_label('Интервал атласа; не точечный балл поселения')
 fig.subplots_adjust(top=.82,bottom=.14,left=.035,right=.98)
 export(fig,'12_experimental_bonitet_intervals','Национальный атлас почв, 2011, с.240–241, масштаб 1:30 млн; исходная CRS и дата состояния неизвестны. Геопривязка: 45 контролей, техпроверка 12 опор: RMSE 19,26 км (не слепая).\nКласс устойчив ≥95% в окрестности ≈50 км; вне контрольной оболочки значения удержаны. Интервал почвенного округа, не измерение НП и не российская оценка 2021.',[R/'axis/full_settlement_axis.parquet',p,R/'soil_bonitet_recovery/recovery_receipt.json'])
def source_recovery_impact(m):
 m=m.resolve();p=m/'demographic_source_recovery_sensitivity.parquet';sp=m/'systems.parquet';primary=R/'demography2010_recovery/root_reviewed_primary2010_four_regions_v1.parquet'
 if not(p.exists() and sp.exists()):return
 watch([primary]);reviewed=pd.read_parquet(primary);accepted=reviewed.reviewed_primary2010_override_allowed.fillna(False);naccepted=int(accepted.sum());nchanged=int((accepted & reviewed.reviewed_primary2010_population.ne(reviewed.baseline_original_secondary_population)).sum());accepted_label=f'{naccepted:,}'.replace(',',' ');changed_label=f'{nchanged:,}'.replace(',',' ')
 q=pd.read_parquet(p);systems=pd.read_parquet(sp);q=q.merge(systems[['level','center_id','lat','lon']+[c for c in ['system_population_complete_2010','system_population_complete_2021'] if c in systems]],on=['level','center_id'],validate='one_to_one');q=q[q.level.eq(q.level.min())].copy();changed=q.n_population_values_changed_in_system.gt(0);q['population_initial_delta']=q.system_population_known_sum_2010-q.original_system_population_known_sum_initial
 fig,axs=plt.subplots(1,2,figsize=(18,8));fig.suptitle('Влияние первичной поправки населения 2010 на неизменной сетке СГРТ',fontsize=18,x=.035,ha='left',fontweight='bold');base(axs[0],f'Нижний уровень: {int(changed.sum())} систем с замененными исходными значениями')
 for mask,color,label in [(changed&q.population_initial_delta.lt(0),'#bd6257','Сумма 2010 уменьшилась'),(changed&q.population_initial_delta.gt(0),'#288e90','Сумма 2010 увеличилась')]:points(axs[0],q[mask],color,12,.85)
 legend(axs[0],[('Сумма 2010 уменьшилась','#bd6257'),('Сумма 2010 увеличилась','#288e90')])
 complete=q.original_system_population_complete_initial.fillna(False)
 for c in ['system_population_complete_2010','system_population_complete_2021']:complete=complete&q.get(c,pd.Series(False,index=q.index)).fillna(False)
 rateok=complete&q.system_annual_rate_original_source.notna()&q.system_annual_rate_reviewed_source.notna();ax=axs[1]
 for mask,color,label in [(rateok&~changed,'#bcc3c1','Без замены источника'),(rateok&changed,'#ce8c2f','Есть замена 2010')]:ax.scatter(100*q.loc[mask,'system_annual_rate_original_source'],100*q.loc[mask,'system_annual_rate_reviewed_source'],c=color,s=12,alpha=.65,label=f'{label}: {int(mask.sum())}',linewidths=0,rasterized=True)
 allrates=np.r_[100*q.loc[rateok,'system_annual_rate_original_source'],100*q.loc[rateok,'system_annual_rate_reviewed_source']]
 if len(allrates):lo=float(np.nanmin(allrates));hi=float(np.nanmax(allrates));ax.plot([lo,hi],[lo,hi],c='#6b7876',lw=.8,ls='--')
 ax.set_xscale('symlog',linthresh=.5);ax.set_yscale('symlog',linthresh=.5);ax.set_xlabel('Среднегодовой темп 2010–2021 до замены, %');ax.set_ylabel('После замены, %');ax.set_title('Пересчитанные темпы только для полных пар',loc='left',fontsize=12,fontweight='bold');ax.grid(alpha=.15);ax.legend(fontsize=8)
 oldphase=np.where(q.system_annual_rate_original_source<-.0025,-1,np.where(q.system_annual_rate_original_source>.0025,1,0));newphase=np.where(q.system_annual_rate_reviewed_source<-.0025,-1,np.where(q.system_annual_rate_reviewed_source>.0025,1,0));flips=int((oldphase[rateok&changed]!=newphase[rateok&changed]).sum());ax.text(.02,.02,f'Изменился класс рост/стабильность/сжатие: {flips}',transform=ax.transAxes,fontsize=9)
 fig.subplots_adjust(top=.83,bottom=.15,left=.035,right=.98,wspace=.2)
 export(fig,'13_demographic_source_recovery_'+m.name,f'Башкортостан, Вологодская, Новгородская и Тверская области: {accepted_label} первичных привязок, {changed_label} замененных чисел. Одинаковая сетка, чувствительность к источнику.\nПолнота чисел не доказывает сопоставимость остальных исторических рядов. Карта 05 — исходная ось; здесь первичная поправка 2010. '+m.name,[p,sp,primary])
def regional_land_2021():
 rp=R/'land2021_recovery/regional_sown_share_farmland2021.parquet';ap=R/'land2021_recovery/regional_axis_aliases.parquet';mp=R/'context/municipal_settlement_features.parquet'
 if not(rp.exists() and ap.exists()):return
 watch([rp,ap,mp]);ratio=pd.read_parquet(rp);aliases=pd.read_parquet(ap);joined=ratio.merge(aliases[['subject_code_in_Rosreestr_source','axis_region']],on='subject_code_in_Rosreestr_source',validate='one_to_one');assert joined.axis_region.is_unique and len(joined)==85
 col='sown_share_of_actual_farmland_2021_usable';d=A.merge(joined[['axis_region',col]],left_on='region',right_on='axis_region',how='left',validate='many_to_one');oldcol='context_sown_share_of_farmland_source_harmonized_usable_2008';old=A.merge(pd.read_parquet(mp,columns=['id',oldcol]),on='id',validate='one_to_one')
 fig,axs=plt.subplots(2,1,figsize=(15,13));fig.suptitle('Посевная доля: разные пространственные уровни источников',fontsize=18,x=.035,ha='left',fontweight='bold')
 for ax,frame,c,title in [(axs[0],old,oldcol,'2008: муниципальный контекст; эквивалентность исторических границ не доказана'),(axs[1],d,col,f'2021: только субъекты РФ; {int(joined[col].notna().sum())} из 85 региональных значений')]:
  base(ax,title);ok=frame[c].notna()&frame.lat.notna()&frame.lon.notna();x,y=T.transform(frame.loc[ok,'lon'].to_numpy(),frame.loc[ok,'lat'].to_numpy());pnt=ax.scatter(x,y,c=frame.loc[ok,c],cmap='YlGn',vmin=0,vmax=1,s=.65,alpha=.8,linewidths=0,rasterized=True);cb=colorbar(fig,pnt,ax=ax);cb.set_label('Посевная площадь / фактические сельхозугодья')
 fig.subplots_adjust(top=.87,bottom=.12,left=.035,right=.98,hspace=.25)
 export(fig,'14_municipal2008_vs_regional2021_land','Разные источники, годы и зерна: это НЕ временная динамика. 2021: все категории хозяйств Росстата / сельхозугодья всех категорий земель Росреестра на 01.01.2022.\nРегиональные значения повторены у НП для показа, не распределены по муниципалитетам. Низкая доля не означает заброшенность: знаменатель включает пастбища, сенокосы, многолетние насаждения.',[R/'axis/full_settlement_axis.parquet',mp,rp,ap])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path);args=p.parse_args()
 watch([R/x for x in ['transport/settlement_road_snap.parquet','transport/graph_receipt.json','transport/yearround_profile_receipt.json','typology/settlement_features.parquet','typology/current_monotowns2026.csv','context/climate_settlement_features.parquet','context/soil_settlement_features.parquet','context/municipal_settlement_features.parquet','soil_bonitet_recovery/experimental_bonitet_settlement_intervals.parquet','soil_bonitet_recovery/recovery_receipt.json']])
 if args.model_dir:watch([args.model_dir/x for x in ['memberships.parquet','systems.parquet','word_type_hypotheses.parquet','demographic_source_recovery_sensitivity.parquet']]+list(args.model_dir.parent.glob('model_inputs*.json')))
 coverage();themes();demographics();ethnicity_context();agro_context();current_mono_map();experimental_bonitet();regional_land_2021()
 if args.model_dir:modelmaps(args.model_dir);broad_prototype_comparison(args.model_dir);demographic_matrix(args.model_dir);regional_maps(args.model_dir);source_recovery_impact(args.model_dir)
 old=json.loads((H/'map_manifest.json').read_text()) if (H/'map_manifest.json').exists() else [];by={r['figure']:r for r in old};by.update({r['figure']:r for r in RECEIPTS});(H/'map_manifest.json').write_text(json.dumps(list(by.values()),ensure_ascii=False,indent=2));print(json.dumps({'figures':[r['figure'] for r in RECEIPTS]},ensure_ascii=False))
