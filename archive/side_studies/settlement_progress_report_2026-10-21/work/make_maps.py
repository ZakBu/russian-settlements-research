from pathlib import Path
import json,numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon,Patch
from matplotlib.colors import BoundaryNorm,ListedColormap,TwoSlopeNorm,LogNorm
from pyproj import Transformer
ROOT=Path('work/sources/research/sgrt_word_completion_20261021'); OLD=Path('data'); OUT=Path('work/figures');OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.titlesize':14,'axes.titleweight':'bold','figure.facecolor':'white'})
T=Transformer.from_crs(4326,'+proj=aea +lat_1=50 +lat_2=70 +lat_0=0 +lon_0=100 +datum=WGS84',always_xy=True)
W=pd.read_parquet(OLD/'localities.parquet');A=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet'); coast=json.load(open('data/world.geojson'))
polys=[]
for f in coast['features']:

 if f['properties'].get('CONTINENT') not in ['Europe','Asia']:continue
 g=f['geometry']; ps=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
 for p in ps:
  v=np.array(p[0]);x,y=T.transform(v[:,0],v[:,1]);polys.append((np.c_[x,y],f['properties'].get('ADM0_A3')=='RUS'))
x,y=T.transform(W.lon.to_numpy(),W.lat.to_numpy());LIMIT=[min(x)-180000,max(x)+180000,min(y)-180000,max(y)+180000];stats={};registry=[]
def base(ax,title):
 ax.set_facecolor('#f1f5f7')
 for xy,ru in sorted(polys,key=lambda item:item[1]):ax.add_patch(Polygon(xy,facecolor='#f9faf8' if ru else '#eef0ed',edgecolor='#c4ccd1',lw=.35,zorder=0))
 ax.set_xlim(LIMIT[:2]);ax.set_ylim(LIMIT[2:]);ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
 for s in ax.spines.values():s.set_visible(False)
 ax.set_title(title,loc='left',pad=8)
def point(ax,d,c,**kw):
 f=d.dropna(subset=['lon','lat']);c=np.asarray(c)[d.index.get_indexer(f.index)] if not isinstance(c,str) else c
 x,y=T.transform(f.lon.to_numpy(),f.lat.to_numpy());return ax.scatter(x,y,c=c,s=kw.pop('s',1.5),lw=0,rasterized=True,**kw)
def continuous(ax,d,col,title,cmap='viridis',vmin=None,vmax=None,log=False,div=False,unit=''):
 base(ax,title);f=d[d[col].notna()].copy();f=f[np.isfinite(f[col])];
 norm=LogNorm(max(vmin or 1,.001),vmax or f[col].max()) if log else TwoSlopeNorm(vmin=vmin,vcenter=0,vmax=vmax) if div else matplotlib.colors.Normalize(vmin=vmin if vmin is not None else f[col].min(),vmax=vmax if vmax is not None else f[col].max())
 sc=point(ax,f,f[col],cmap=cmap,norm=norm,s=22 if len(f)<1000 else 2); cb=plt.colorbar(sc,ax=ax,orientation='horizontal',pad=.015,fraction=.05,shrink=.65,extend='both');cb.ax.tick_params(labelsize=10);cb.set_label(unit,fontsize=10,labelpad=1)
 ax.text(.01,.02,f'n = {len(f):,}'.replace(',',' '),transform=ax.transAxes,fontsize=10,bbox=dict(fc='white',ec='none',alpha=.85))
 registry.append({'title':title,'n':len(f),'field':col});return len(f)
def save(fig,name):fig.savefig(OUT/(name+'.png'),dpi=220,bbox_inches='tight',facecolor='white');plt.close(fig)
def panel(n,cols=2):return plt.subplots((n+cols-1)//cols,cols,figsize=(12,((n+cols-1)//cols)*3.65),squeeze=False,layout='constrained')
# Three periods on common bins
fig=plt.figure(figsize=(12,10.5),layout='constrained');gs=fig.add_gridspec(2,2);axs=np.array([fig.add_subplot(gs[0,:]),fig.add_subplot(gs[1,0]),fig.add_subplot(gs[1,1])])
bins=[-101,-75,-50,-25,-10,0,10,25,50,100,np.inf];colors=['#8e1230','#b73249','#d85d63','#ee9891','#f8c8bd','#cadfed','#9fc5df','#679fca','#3375b0','#123e7b']
for ax,c,title in zip(axs.flat,['pct_2002_2021','pct_2002_2010','pct_2010_2021'],['2002–2021 годы','2002–2010 годы','2010–2021 годы']):
 base(ax,title);d=W[W[c].notna()];point(ax,d,np.digitize(d[c],bins[1:-1]),cmap=ListedColormap(colors),norm=BoundaryNorm(np.arange(11)-.5,10));ax.text(.01,.03,f'{len(d):,} поселений'.replace(',',' '),transform=ax.transAxes,fontsize=12)
fig.legend(handles=[Patch(color=c,label=l) for c,l in zip(colors,['−100…−75','−75…−50','−50…−25','−25…−10','−10…0','0…+10','+10…+25','+25…+50','+50…+100','>+100'])],loc='lower center',ncol=5,fontsize=11,bbox_to_anchor=(.5,-.065),title='Изменение населения, %');save(fig,'dynamics')
fig,axs=panel(4)
W['p2021_map']=W.p2021.clip(lower=1)
continuous(axs[0,0],W,'p2021_map','Численность населения 2021',log=True,vmin=1,vmax=1e6,unit='человек; логарифмическая шкала')
continuous(axs[0,1],W,'abs_2002_2021','Абсолютное изменение 2002–2021',cmap='RdBu',div=True,vmin=-10000,vmax=10000,unit='человек; крайние цвета за пределами ±10 тыс.')
ax=axs[1,0];base(ax,'Переходы к нулю и от нуля');labs=['Было >0, стало 0','Было 0, стало >0','0 в оба года'];cols=['#b52d42','#2263a6','#8b9194']
for k,col in enumerate(cols,1):d=W[W.zero_category.eq(k)];point(ax,d,col,s=5)
ax.legend(handles=[Patch(color=c,label=l) for c,l in zip(cols,labs)],loc='lower left',fontsize=9)
ax=axs[1,1];base(ax,'Траектории двух периодов');labs=['Убыль → убыль','Рост → рост','Убыль → рост','Рост → убыль'];cols=['#b52d42','#2263a6','#c49c39','#8070a6']
for k,col in enumerate(cols,1):d=W[W.trajectory.eq(k)];point(ax,d,col,s=2)
ax.legend(handles=[Patch(color=c,label=l) for c,l in zip(cols,labs)],loc='lower left',fontsize=9);save(fig,'structure')
# Source-linked service inventories: baseline vs additional approximate links
service_stats=[]
def services(family,spec,name):
 d=pd.read_parquet(ROOT/f'model_inputs_cycle05/relinked_v4/{family}/settlement_features_full_axis.parquet');fig,axs=panel(len(spec))
 for ax,(label,strict,extra) in zip(axs.flat,spec):
  base(ax,label);b=d[strict].sum(axis=1);e=d[extra].sum(axis=1);geo=d[['lat','lon']].notna().all(axis=1);q=d[geo & b.eq(0)&e.gt(0)];r=d[geo & b.gt(0)];point(ax,q,'#dfa148',s=5);point(ax,r,'#1d6589',s=5)
  bs=int((geo&b.gt(0)).sum());ex=int((geo&b.eq(0)&e.gt(0)).sum());ax.text(.01,.01,f'Адрес: {bs:,} НП   ·   Только география: {ex:,}'.replace(',',' '),transform=ax.transAxes,fontsize=10,bbox=dict(fc='white',ec='none',alpha=.85));service_stats.append([label,bs,ex,int(b.sum()),int(e.sum())])
 for ax in list(axs.flat)[len(spec):]:ax.axis('off')
 fig.legend(handles=[Patch(color='#1d6589',label='Есть адресная привязка'),Patch(color='#dfa148',label='Только дополнительная географическая привязка')],loc='lower center',ncol=2,fontsize=11,bbox_to_anchor=(.5,-.025));save(fig,name)
ed=[]
for label,k in [('Школы','school'),('Детские сады','preschool'),('Колледжи','college'),('Вузы','university'),('Специализированные школы','specialized_non_general_school')]:ed.append((label,[f'education_osm2021_{k}_baseline_count'],[f'education_osm2021_{k}_candidate_additional_count']))
services('education',ed,'education')
med=[]
for label,k in [('ФАПы по явному названию','fap_name_assertion_count'),('Амбулатории по названию','ambulatory_name_assertion_count'),('Поликлиники по названию','polyclinic_name_assertion_count'),('Больницы по тегу hospital','explicit_hospital_sites_count'),('Клинические объекты общего профиля','healthcare_sites_count'),('Аптеки','pharmacy_source_tag_count')]:
 med.append((label,[f'medical_osm_baseline_{k}'],[f'medical_osm_conditional_additional_{k}',f'medical_osm_coordinate_candidate_{k}']))
services('medical',med,'medical')
comm=[]
for label,ks in [('Крупная торговля',['large_retail']),('Прочие магазины',['other_retail']),('Рынки',['market']),('Банки и банкоматы',['bank','atm']),('Почта',['post_office']),('Административные объекты',['administration'])]:comm.append((label,[f'services_osm2021_{k}_baseline_count' for k in ks],[f'services_osm2021_{k}_candidate_additional_count' for k in ks]))
services('commerce',comm,'commerce')
pd.DataFrame(service_stats,columns=['category','NP_strict','NP_geographic_only','strict_objects','additional_objects']).to_csv('work/service_counts.csv',index=False)
# Municipal context: one actual municipal unit per point, representative coordinate only
M=pd.read_parquet(ROOT/'context/municipal_settlement_features.parquet');M=M.merge(A[['id','lat','lon']],on='id',validate='one_to_one');spec=[('Естественный прирост','context_natural_increase_per1000_2021','RdBu',-25,25,True,'человек на 1000 жителей'),('Миграционный прирост','context_migration_increase_per1000_2021','RdBu',-25,25,True,'человек на 1000 жителей'),('Ввод жилья','context_housing_completed_residential_m2_per_capita_2021','YlGnBu',0,1.5,False,'м² на жителя'),('Посевная площадь','context_sown_area_ha_2021','YlGn',1,500000,False,'га; логарифмическая шкала'),('Урожайность зерновых','context_grain_yield_centner_per_ha_2021','YlGn',0,60,False,'ц/га убранной площади'),('Индекс сельхозпроизводства','context_agricultural_production_index_real_previousyear_percent_2021','RdBu',50,150,False,'% к предыдущему году')]
fig,axs=panel(6)
for ax,(title,c,cmap,mi,ma,div,unit) in zip(axs.flat,spec):
 g=M.groupby('municipality_code').agg(lat=('lat','median'),lon=('lon','median'),val=(c,'first'),nunique=(c,'nunique'));assert g['nunique'].le(1).all();g=g.rename(columns={'val':c});continuous(ax,g,c,title,cmap,mi,ma,log=title=='Посевная площадь',div=div,unit=unit)
save(fig,'municipal')
# Natural data
C=A[['id','lat','lon']].merge(pd.read_parquet(ROOT/'context/climate_settlement_features.parquet'),on='id',validate='one_to_one');S=A[['id','lat','lon']].merge(pd.read_parquet(ROOT/'context/soil_settlement_features.parquet'),on='id',validate='one_to_one')
fig,axs=panel(4)
continuous(axs[0,0],C,'climate_gaez_sat_above10_cday_1981_2010','Тепло за вегетационный период','YlOrRd',0,6000,unit='Сумма температур >10 °C, °C·сутки; 1981–2010')
continuous(axs[0,1],C,'climate_gaez_summer_precipitation_over_pet_1981_2010','Увлажнение апреля–сентября','BrBG',0,2,unit='осадки / потенциальная испаряемость; 1981–2010')
continuous(axs[1,0],C,'climate_annual_precipitation_mm','Годовая сумма осадков','YlGnBu',0,1500,unit='мм; климатическая норма 1970–2000')
continuous(axs[1,1],S,'soil_gaez_low_input_most_limiting_rating_class_rating_lower','Почвенная оценка FAO','YlGn',0,1,unit='нижняя граница класса 0–1; кукуруза, низкие вложения');save(fig,'nature')
# supplementary demographic sources
fig,axs=panel(4)
for ax,filename,col,title,unit,cmap,mi,ma,div in [
(axs[0,0],'sex2002_map.csv','female_share','Доля женщин 2002','%', 'PuOr_r',35,65,False),
(axs[0,1],'historical_coverage.csv','nyears','История до 2002 года','Число доступных лет; вторичный источник','cividis',1,15,False),
(axs[1,0],'official_history_1979_1989.csv','pct','Официальные городские ряды 1979–1989','Изменение наличного населения, %','RdBu',-50,50,True),
(axs[1,1],'annual_2022_2024.csv','pct','Оценки городского населения 2022–2024','Изменение, %','RdBu',-10,10,True)]:
 d=pd.read_csv(OLD/filename);continuous(ax,d,col,title,cmap,mi,ma,div=div,unit=unit)
save(fig,'extra_demography')
E=pd.read_parquet(ROOT/'economy_source_recheck/own_code_legal_entities2021_recheck.parquet');E=A[['id','lat','lon']].merge(E,on='id',validate='one_to_one');E=E[E.recomputed_legal_entities2021.gt(0)];fig,axs=panel(1,1);continuous(axs[0,0],E,'recomputed_legal_entities2021','Юридические лица по собственному коду НП','YlGnBu',1,10000,log=True,unit='число регистрационных записей 2021; не занятость');save(fig,'economy')
Path('work/map_registry.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2));print('Figures:',len(list(OUT.glob('*.png'))));print(pd.read_csv('work/service_counts.csv').to_string(index=False))
