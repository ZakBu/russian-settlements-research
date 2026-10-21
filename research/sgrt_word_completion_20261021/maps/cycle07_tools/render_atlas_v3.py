#!/usr/bin/env python3
"""Cycle07 exact membership point atlas; no inferred territorial polygon boundaries."""
from pathlib import Path
import argparse,hashlib,json,textwrap,math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[2]
CRS='+proj=aea +lat_1=50 +lat_2=70 +lat_0=60 +lon_0=100 +datum=WGS84 +units=m +no_defs'
T=Transformer.from_crs('EPSG:4326',CRS,always_xy=True)
GEOMETRY_NOTE='Точки — точная принадлежность НП. Границы между НП неизвестны; линии к ядру схематические, не дороги и не потоки.'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def path(s):
 p=Path(s);return p if p.is_absolute() else ROOT/p
def read_table(spec):
 p=path(spec['path']);d=pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p)
 return d.rename(columns={v:k for k,v in spec.get('columns',{}).items()})
def need(d,cols,label):
 missing=set(cols)-set(d)
 if missing:raise ValueError(f'{label}: missing columns {sorted(missing)}')
def load(config,require_admission=False):
 if config.get('family')!='cycle07_bottomup':raise ValueError('Only new cycle07_bottomup family admitted')
 if not config.get('component_integration_status') or not config.get('population_frame_scope'):raise ValueError('Explicit component integration and source/partition scopes required')
 watches={}
 for name,spec in config['sources'].items():
  p=path(spec['path']);actual=sha(p)
  if actual!=spec['sha256']:raise ValueError(f'Changed/unbound source: {name}')
  watches[str(p)]=actual
 if require_admission:
  if len(config.get('independent_admissions',[]))<2:raise ValueError('Require hierarchy and complete-typology independent admissions')
  for s in config['independent_admissions']:
   p=path(s['path']);assert sha(p)==s['sha256'];r=json.loads(p.read_text())
   for k in s['status_pointer']:r=r[k]
   if r!=s['expected_status'] or 'ACCEPT' not in str(r).upper():raise ValueError('Independent admission not accepted')
   watches[str(p)]=s['sha256']
 n=read_table(config['sources']['nodes']);u=read_table(config['sources']['units']);m=read_table(config['sources']['memberships']);ty=read_table(config['sources']['types'])
 need(n,['id','name','lat','lon','population_2021','formal_city2021','source_record_id_2021'],'nodes');need(u,['unit_id','level','core_id','kind'],'units');need(m,['unit_id','id'],'memberships');need(ty,['unit_id','primary_type_id','primary_type_name','structural_class','unit_role'],'types')
 for d,key,label in [(n,'id','nodes'),(u,'unit_id','units'),(ty,'unit_id','types')]:
  if d[key].isna().any() or d[key].duplicated().any():raise ValueError(f'{label}: invalid unique key')
 if m.duplicated(['unit_id','id']).any():raise ValueError('Duplicate membership')
 if not set(m.unit_id)<=set(u.unit_id) or not set(m.id)<=set(n.id):raise ValueError('Orphan membership')
 if set(u.unit_id)!=set(ty.unit_id):raise ValueError('All output units must have exact complete typology coverage')
 if ty[['primary_type_id','primary_type_name','structural_class','unit_role']].isna().any().any() or (ty.primary_type_id.astype(str).str.strip()=='').any():raise ValueError('Incomplete measured types')
 # Typology carries roles; hierarchy carries its actual levels. Never recreate old ranks.
 extra=[c for c in ty if c not in u or c=='unit_id'];u=u.merge(ty[extra],on='unit_id',validate='one_to_one')
 need(u,['primary2010_population_share','protected_secondary2010_population_share','population2010_known_denominator','2010_missing_population_count','population_quality_share_denominator_scope'],'unit population quality')
 for c in ['primary2010_population_share','protected_secondary2010_population_share']:
  v=pd.to_numeric(u[c],errors='coerce');den=pd.to_numeric(u.population2010_known_denominator,errors='coerce')
  if ((v.notna()&~v.between(0,1)).any() or (v.notna()&(den<=0)).any()):raise ValueError('Invalid source2010 share or zero-denominator imputation')
 if 'is_overlay_membership' not in m:m['is_overlay_membership']=False
 if m.is_overlay_membership.isna().any() or not pd.api.types.is_bool_dtype(m.is_overlay_membership):raise ValueError('Unknown/nonboolean overlay membership status')
 z=m.merge(u,on='unit_id',validate='many_to_one').merge(n,on='id',validate='many_to_one',suffixes=('','_node'))
 primary=z[~z.is_overlay_membership.astype(bool)]
 if primary.duplicated(['level','id']).any():raise ValueError('Double primary membership within resolution')
 u['level']=u.level.fillna(config.get('atomic_level_label','atomic')).astype(str)
 expected=config['retained_resolutions'];actual=u.level.unique().tolist()
 if set(expected)!=set(actual):raise ValueError('Retained resolutions must be explicitly exhaustive')
 u['level']=u.level.astype(str);z['level']=z.level.astype(str)
 valid=np.isfinite(z.lat)&np.isfinite(z.lon)&z.lat.between(-90,90)&z.lon.between(-180,180)
 z['_coordinate_valid']=valid;z['_x']=np.nan;z['_y']=np.nan
 z.loc[valid,'_x'],z.loc[valid,'_y']=T.transform(z.loc[valid,'lon'].to_numpy(),z.loc[valid,'lat'].to_numpy())
 nvalid=np.isfinite(n.lat)&np.isfinite(n.lon)&n.lat.between(-90,90)&n.lon.between(-180,180)
 n['_x']=np.nan;n['_y']=np.nan;n.loc[nvalid,'_x'],n.loc[nvalid,'_y']=T.transform(n.loc[nvalid,'lon'].to_numpy(),n.loc[nvalid,'lat'].to_numpy())
 # Missingness is counted separately, never imputed to a measured zero/type.
 return n,u,z,watches
class Atlas:
 def __init__(self,out,n,u,z,cfg,watches):
  self.out=out;self.n=n;self.u=u;self.z=z;self.cfg=cfg;self.watch=watches;self.pages=[];self.coasts=[];self.pdf=PdfPages(out/'atlas_cycle07.pdf')
  plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'axes.titlesize':12,'figure.facecolor':'#fafaf7','axes.facecolor':'#f0f4f4'})
  cats=sorted(u.structural_class.astype(str).unique())
  if len(cats)>20:raise ValueError('Morethan20structuralclasses requires new explicit facet protocol, never silently Other')
  cm=plt.get_cmap('tab20');self.colors={k:cm(i%20) for i,k in enumerate(cats)}
  coast=cfg['sources'].get('coastline')
  if coast:
   for f in json.loads(path(coast['path']).read_text())['features']:
    g=f['geometry'];segs=[g['coordinates']] if g['type']=='LineString' else g['coordinates']
    for a in segs:
     a=np.asarray(a);x,y=T.transform(a[:,0],a[:,1]);v=np.c_[x,y];v[np.r_[False,np.abs(np.diff(x))>2e6]]=np.nan;self.coasts.append(v)
 def finish(self,fig,title,caption,kind,metadata=None):
  i=len(self.pages)+1;fig.suptitle(title,x=.045,ha='left',fontsize=16,fontweight='bold');fig.text(.045,.035,textwrap.fill(caption,150),fontsize=8,va='bottom',color='#37464b');fig.text(.955,.015,str(i),ha='right',fontsize=8)
  fig.subplots_adjust(left=.055,right=.95,top=.89,bottom=.15,hspace=.42,wspace=.28)
  p=self.out/f'{i:02}_{kind}.png';fig.savefig(p,dpi=self.cfg.get('dpi',150),facecolor=fig.get_facecolor());self.pdf.savefig(fig);plt.close(fig)
  self.pages.append({'page':i,'kind':kind,'title':title,'png':p.name,'sha256':sha(p),'caption':caption,**(metadata or {})})
 def textpage(self,title,paras,kind):
  fig,ax=plt.subplots(figsize=(14,10));ax.axis('off');ax.text(0,1,'\n\n'.join(textwrap.fill(x,115) for x in paras),va='top',fontsize=11,linespacing=1.5,transform=ax.transAxes);self.finish(fig,title,GEOMETRY_NOTE,kind)
 def base(self,ax,d,title):
  if self.coasts:ax.add_collection(LineCollection(self.coasts,color='#aebdc0',lw=.4,zorder=0))
  v=d[d._coordinate_valid] if '_coordinate_valid' in d else d.dropna(subset=['_x','_y'])
  if len(v):
   lo=v[['_x','_y']].min().to_numpy();hi=v[['_x','_y']].max().to_numpy();pad=np.maximum((hi-lo)*.06,15000);ax.set_xlim(lo[0]-pad[0],hi[0]+pad[0]);ax.set_ylim(lo[1]-pad[1],hi[1]+pad[1])
  ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,loc='left');[s.set_visible(False) for s in ax.spines.values()]
  return v
 def scatter(self,ax,d,mode='structure',size=.8):
  v=d[d._coordinate_valid]
  if mode=='structure':colors=v.structural_class.map(self.colors).tolist()
  else:
   ids=v.unit_id.astype(str);colors=[plt.get_cmap('hsv')(int(hashlib.sha256(s.encode()).hexdigest()[:8],16)/2**32) for s in ids]
  ax.scatter(v._x,v._y,c=colors,s=size,linewidths=0,alpha=.8,rasterized=True)
 def legend(self,ax,d):
  counts=d.groupby('structural_class').unit_id.nunique()
  handles=[Line2D([],[],marker='o',ls='',color=self.colors[k],label=f'{self.cfg.get("structural_display_aliases",{}).get(str(k),str(k))}: {int(v):,} ед.'.replace(',',' '),markersize=5) for k,v in counts.items()]
  ax.legend(handles=handles,fontsize=7,loc='lower left',ncol=min(3,max(1,math.ceil(len(handles)/6))),framealpha=.93)
 def national(self,level):
  d=self.z[self.z.level==level];fig,axs=plt.subplots(2,1,figsize=(14,12))
  self.base(axs[0],d,'Принадлежность НП: цвет иллюстрирует группу; идентификатор — в CSV');self.scatter(axs[0],d,'membership',.45)
  coreids=self.u.loc[(self.u.level==level)&self.u.kind.isin(['functional_union','external_context_anchor']),'core_id'].dropna().unique();cores=self.n[self.n.id.isin(coreids)].dropna(subset=['_x','_y']);axs[0].scatter(cores._x,cores._y,marker='^',s=5,c='#202020',alpha=.65,linewidths=0,rasterized=True,label=f'Ядра с координатами: {len(cores)}');axs[0].legend(loc='lower left',fontsize=7)
  self.base(axs[1],d,'Все измеренные типы сохранены; цвет — только структурная компонента');self.scatter(axs[1],d,'structure',.45);self.legend(axs[1],d)
  self.finish(fig,f'{self.cfg.get("view_metadata",{}).get(level,{}).get("label",level)}: национальная картина',GEOMETRY_NOTE+' Цвета групп могут повторяться; это не уникальный справочник единиц. Полные типы: type_counts.csv; роли считаются отдельно.',f'national_{len(self.pages)}',{'resolution':level,'n_membership_rows':len(d),'missing_coordinates':int((~d._coordinate_valid).sum())})
 def zooms(self):
  # All source-known million cities, plus two source-specified contexts; never inject territorial population.
  million=self.n[(self.n.population_2021>=1_000_000)&self.n.id.astype(str).str.startswith('np3:')&self.n['formal_city2021'].eq(True)&self.n.source_record_id_2021.notna()].sort_values(['population_2021','id'],ascending=[False,True])
  ids=list(dict.fromkeys(self.cfg.get('external_context_anchor_ids',[])+million.id.tolist()));selection=[];level=self.cfg['zoom_resolution']
  for ident in ids:
   node=self.n[self.n.id==ident]
   if node.empty:raise ValueError(f'Missing requested zoom anchor {ident}')
   d=self.z[(self.z.level==level)&(self.z.id==ident)&~self.z.is_overlay_membership.astype(bool)]
   if len(d)!=1:raise ValueError(f'Zoom anchor requires one actual primary membership: {ident}')
   uid=d.iloc[0].unit_id;members=self.z[(self.z.level==level)&(self.z.unit_id==uid)];selection.append({'anchor_id':ident,'anchor_name':node.iloc[0]['name'],'unit_id':uid,'resolution':level,'n_members':len(members)})
  for j in range(0,len(selection),2):
   fig,axs=plt.subplots(1,2,figsize=(14,10));axs=np.atleast_1d(axs)
   for ax,s in zip(axs,selection[j:j+2]):
    d=self.z[(self.z.level==level)&(self.z.unit_id==s['unit_id'])];self.base(ax,d,f"{s['anchor_name']}: {len(d):,} НП; без координат {int((~d._coordinate_valid).sum())}".replace(',',' '));self.scatter(ax,d,'structure',9)
    unit=self.u[self.u.unit_id==s['unit_id']].iloc[0];core=self.n[self.n.id==unit.core_id]
    if len(core) and np.isfinite(core.iloc[0]._x):
     c=core.iloc[0];ax.scatter([c._x],[c._y],marker='*',s=150,c='#111111',edgecolors='white',zorder=5);ax.annotate(str(c['name']),[c._x,c._y],xytext=(5,6),textcoords='offset points',fontsize=9)
     # Only exact member-core endpoints. No inference of road geometry; all nonzero segments retained.
     v=d[d._coordinate_valid];segments=np.stack([v[['_x','_y']].to_numpy(),np.tile([c._x,c._y],(len(v),1))],axis=1);ax.add_collection(LineCollection(segments,color='#657b82',lw=.35,alpha=.17,zorder=1))
    self.legend(ax,d)
   if len(selection[j:j+2])==1:axs[-1].axis('off')
   self.finish(fig,f'Крупные города: действительное полное членство, разрешение {level}',GEOMETRY_NOTE+' Охват панели включает всех членов; дальние участники не обрезаны. Звезда — фактическое ядро единицы, оно может отличаться от города в заголовке.','city_zoom_'+str(j//2+1),{'selections':selection[j:j+2]})
  pd.DataFrame(selection).to_csv(self.out/'city_zoom_selection.csv',index=False)
 def diagnostics(self):
  u=self.u;z=self.z
  self.textpage('Cycle07: модельные районы и наблюдаемые источники',[
   'Версия входов: '+json.dumps(self.cfg['component_integration_status'],ensure_ascii=False),
   'Знаменатели: '+json.dumps(self.cfg['population_frame_scope'],ensure_ascii=False),
   'Новая bottom-up иерархия: только принятые выходы cycle07. Число уровней не задаётся заранее; старые четыре ранга не подставляются.',
   'Все построенные единицы имеют полный измеренный тип. На картах цвет показывает только структурную компоненту; это картографическая сводка, а не новая классификация. Каждый полный код и его частота сохранены в таблицах.',
   'Принадлежность НП установлена моделью на зафиксированных данных. Пространство между точками не обследовано как функциональная граница. Береговая линия служит только ориентиром.',
   'Контекстные якоря Москвы и Петербурга не превращены в аддитивное население собственного города. Изоляты, переносимые атомы и настоящие наложения отделены. Территориальный район с внешним якорем сохраняет обычных сельских членов; неизвестное собственное население якоря не удаляет его сельский район с карты.'
  ],'scope')
  fig,axs=plt.subplots(1,2,figsize=(14,10));a=z.groupby('level').agg(rows=('id','size'),coordinate_known=('_coordinate_valid','sum'));a.plot.bar(ax=axs[0]);axs[0].set_title('Членство и координаты (строки по разрешению)');u.groupby(['level','unit_role']).size().unstack(fill_value=0).plot.bar(stacked=True,ax=axs[1]);axs[1].set_title('Роли единиц: отдельные знаменатели');self.finish(fig,'Покрытие и знаменатели',GEOMETRY_NOTE+' Отсутствующие координаты посчитаны; их НП не удалены из таблицы членства.','coverage')
  freq_u=u
  if 'all_units' in self.cfg['sources'] and 'all_types' in self.cfg['sources']:
   au=read_table(self.cfg['sources']['all_units']);at=read_table(self.cfg['sources']['all_types']);assert au.unit_id.is_unique and at.unit_id.is_unique and set(au.unit_id)==set(at.unit_id)
   ac=[x for x in at if x not in au or x=='unit_id'];freq_u=au.merge(at[ac],on='unit_id',validate='one_to_one');freq_u['level']=freq_u.operational_view_id.astype(str)
   kc=[x for x in ['unit_id','operational_view_id','unit_role','center_scope','core_id','unit_name','primary_type_id','primary_type_name','complete_profile_id','classification_confidence','source_quality_flags'] if x in freq_u];freq_u[kc].to_csv(self.out/'all_actual_unit_type_registry.csv.gz',index=False,compression='gzip')
  counts=freq_u.groupby(['level','unit_role','primary_type_id','primary_type_name','structural_class'],dropna=False).size().reset_index(name='n_units');counts.to_csv(self.out/'type_counts.csv',index=False)
  fig,ax=plt.subplots(figsize=(14,10))
  for lev,d in counts.groupby('level'):
   d=d.groupby('primary_type_id').n_units.sum().sort_values(ascending=False);ax.plot(np.arange(1,len(d)+1),d.to_numpy(),'.-',ms=3,label=f'{lev}: {len(d)} кодов')
  ax.set_yscale('log');ax.set_xlabel('Порядок полного кода по частоте (каждый код — отдельная точка)');ax.set_ylabel('Количество единиц, логарифмическая ось');ax.legend();self.finish(fig,'Частоты всех полных измеренных типов','Ни один код не объединён в «прочее». Коды/названия/роли и точные частоты — type_counts.csv. Оси ранжирования не означают качество типа.','all_type_frequencies')
  fig,ax=plt.subplots(figsize=(14,10));u.groupby(['level','unit_role','structural_class']).size().unstack(fill_value=0).plot.bar(stacked=True,ax=ax,color=self.colors);ax.set_ylabel('Единицы, не население');self.finish(fig,'Структурная компонента типа','Цветовая сводка карты не заменяет полный тип. Контекстные/переносимые роли показаны отдельно.','structural_counts')
  fig,axs=plt.subplots(1,2,figsize=(14,10))
  if 'n_children' in u:
   for lev,d in u.groupby('level'):axs[0].hist(d.n_children.dropna(),bins=20,histtype='step',label=lev)
   axs[0].legend();axs[0].set_title('Число целых дочерних единиц')
  if 'parent_unit_id' in u:u.assign(has_parent=u.parent_unit_id.notna()).groupby(['level','has_parent']).size().unstack(fill_value=0).plot.bar(ax=axs[1]);axs[1].set_title('Наличие принятого родителя')
  self.finish(fig,'Связь родитель — дети','Вложенность берётся из фактических идентификаторов и проверяется отдельно производителем; отсутствующий родитель не придуман.','parent_child')
  merge=read_table(self.cfg['sources']['merge_diagnostics']);need(merge,['candidate_cap','merge_index','Q'],'merge diagnostics');fig,ax=plt.subplots(figsize=(14,10))
  for cap,d in merge.groupby('candidate_cap'):ax.plot(d.merge_index,d.Q,label=str(cap))
  ax.set_xlabel('Число принятых слияний');ax.set_ylabel('Фактический Q');ax.legend(title='Кандидатный охват, мин');self.finish(fig,'Действительный путь целевой функции','Взвешенная модульность условного потенциала: наша инженерная адаптация. Охваты не переименованы в географические уровни.','merge_objective')
  knee=read_table(self.cfg['sources']['knee_diagnostics']);need(knee,['candidate_cap','knee_status','retained'],'knee diagnostics');knee.to_csv(self.out/'knee_decisions.csv',index=False);fig,ax=plt.subplots(figsize=(14,10));ax.axis('off');cols=[c for c in ['candidate_cap','knee_status','retained','median_ari','p10_ari','knee_fraction_iqr'] if c in knee];table=ax.table(cellText=[[textwrap.fill(str(v),20) for v in row] for row in knee[cols].fillna('NA').values],colLabels=[textwrap.fill(c,18) for c in cols],loc='center',cellLoc='left');table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,2.2)
  self.finish(fig,'Решение о перегибе и устойчивость','Показаны все испытанные охваты, включая no-knee/неустойчивые исходы. Это не метод, приписанный Райсиху или OECD.','knee_stability')
  fig,axs=plt.subplots(1,2,figsize=(14,10))
  for col,ax in zip(['max_member_direct_minutes','max_member_geodesic_km'],axs):
   if col in u:
    for lev,d in u.groupby('level'):ax.hist(pd.to_numeric(d[col],errors='coerce').dropna(),bins=35,histtype='step',label=lev)
    ax.legend();ax.set_title(col)
   else:ax.text(.1,.5,'Измерение не предоставлено',transform=ax.transAxes)
  self.finish(fig,'Прямой охват всех членов','Гистограммы исходных измерений. Дорожные минуты и геодезические километры не смешиваются; неизвестные не равны нулю.','direct_extent')
  fig,axs=plt.subplots(1,2,figsize=(14,10));ax=axs[0];cols=[c for c in ['extent_complete','n_native2021_geometry_unknown','n_native2021_direct_route_unknown','primary2010_population_share','protected_secondary2010_population_share','2010_missing_population_count'] if c in u]
  if cols:
   vals=[]
   for c in cols:vals.append((textwrap.fill(c,22),int(u[c].isna().sum()),int(pd.to_numeric(u[c],errors='coerce').fillna(0).gt(0).sum())))
   ax.axis('off');table=ax.table(cellText=vals,colLabels=['Поле','NA','Положительное / True'],loc='center',cellLoc='left',colWidths=[.6,.15,.25]);table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,2.3)
  else:ax.text(.1,.5,'Поля полноты не предоставлены',transform=ax.transAxes)
  for lev,d in u.groupby('level'):
   axs[1].hist(d.protected_secondary2010_population_share.dropna(),bins=np.linspace(0,1,21),histtype='step',label=str(lev))
  axs[1].set_title('Доля вторичногоP2010 в известном аддитивномP2010');axs[1].set_xlabel('Доля; нулевой знаменатель остаётсяNA');axs[1].legend()
  self.finish(fig,'Географическая и источниковая полнота','Знаменатель долей2010 — известное неотрицательное аддитивное население членов, не оценка всего города. Контекстные неизвестные слоты отдельно. Флаги не доказывают границы или механизм.','source_quality')
  fig,axs=plt.subplots(1,2,figsize=(14,10));nd=self.n.copy();nd['_coordinate_valid']=np.isfinite(nd._x)&np.isfinite(nd._y);v=self.base(axs[0],nd,'Датированный исходный кадр: все координаты');native=nd.source_record_id_2021.notna()&nd.population_2021.notna()
  for mask,color,label in [(native,'#007b80','Собственное наблюдение2021'),(~native,'#b8b3ae','Прочие исходные записи')]:
   d=nd[mask&nd._coordinate_valid];axs[0].scatter(d._x,d._y,c=color,s=.4,alpha=.65,label=label,rasterized=True)
  axs[0].legend(fontsize=7);counts=pd.DataFrame({'С координатами':[int((native&nd._coordinate_valid).sum()),int((~native&nd._coordinate_valid).sum())],'Без координат':[int((native&~nd._coordinate_valid).sum()),int((~native&~nd._coordinate_valid).sum())]},index=['Наблюдение2021','Прочие записи']);counts.plot.bar(stacked=True,ax=axs[1]);self.finish(fig,'Национальный исходный кадр и неизвестные местоположения',GEOMETRY_NOTE+' Кадр измерений отделён от допустимости центра. Неизвестные координаты видны в счётчике.','native_source_frame')
  boot=read_table(self.cfg['sources']['bootstrap_diagnostics']);need(boot,['candidate_cap','replicate_id','status','assessable'],'bootstrap diagnostics')
  if boot.duplicated(['candidate_cap','replicate_id']).any():raise ValueError('Duplicate bootstrap replicate')
  if set(boot.candidate_cap)!=set(knee.candidate_cap) or boot.status.isna().any():raise ValueError('Missing candidatecap or bootstrapstatus; failed outcomes maynotbe hidden')
  if not boot.groupby('candidate_cap').size().eq(50).all():raise ValueError('All50 prospective bootstrap outcomes mustbe retained')
  boot.to_csv(self.out/'all_bootstrap_outcomes.csv',index=False);fig,axs=plt.subplots(1,2,figsize=(14,10));boot.groupby(['candidate_cap','status']).size().unstack(fill_value=0).plot.bar(stacked=True,ax=axs[0]);axs[0].set_title('Все50исходов на кандидатный охват');axs[0].set_ylabel('Повторы')
  for cap,d in boot.groupby('candidate_cap'):
   if 'ari' in d:axs[1].scatter(np.repeat(str(cap),d.ari.notna().sum()),d.ari.dropna(),s=10,label=str(cap))
  axs[1].set_title('ДоступныеARI, пропуски не стали нулём');axs[1].set_ylabel('Условная устойчивостьARI');self.finish(fig,'Bootstrap: доступность и все неудачные исходы','Показаны все50повторов для каждого охвата. НедоступныеARI остаютсяNA; допуск по числу пригодных повторов задаёт исходный протокол, а не картограф.','bootstrap_outcomes')
  provenance=[f'{k}: {s["path"]}; SHA256 {s["sha256"][:16]}…' for k,s in self.cfg['sources'].items()]
  self.textpage('Источники и воспроизводимость',provenance+['Полные SHA и параметры: input_binding.json / render_receipt.json. Проекция Альберса50°/70°, центральный меридиан100°. Береговая линия — ориентир, не граница функциональной территории.'],'provenance')
 def close(self):self.pdf.close()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--output',required=True);ap.add_argument('--stage',choices=['preregister','render'],default='preregister');args=ap.parse_args();cfg=json.loads(Path(args.config).read_text());out=Path(args.output)
 if out.exists() and any(out.iterdir()):raise ValueError('Output must be new/empty; frozen outputs never overwritten')
 n,u,z,watches=load(cfg,require_admission=args.stage=='render');out.mkdir(parents=True,exist_ok=True)
 binding={'config_sha256':sha(args.config),'code_sha256':sha(__file__),'sources':watches,'retained_resolutions':cfg['retained_resolutions'],'counts':{'nodes':len(n),'units':len(u),'membership_rows':len(z)},'geometry':'exact sourceNPmembershippoints; geographic boundaries unknown; optional schematiccorelines only','classification':'full codes retained; structural-class color is visualsummary only','stage':args.stage}
 (out/'input_binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n')
 if args.stage=='preregister':print(json.dumps(binding,ensure_ascii=False));return
 pd.DataFrame([{'structural_class':k,'display_alias':v} for k,v in cfg.get('structural_display_aliases',{}).items()]).to_csv(out/'structural_display_dictionary.csv',index=False)
 atlas=Atlas(out,n,u,z,cfg,watches)
 try:
  atlas.diagnostics()
  for lev in cfg['retained_resolutions']:atlas.national(str(lev))
  atlas.zooms()
 finally:atlas.close()
 kc=[x for x in ['unit_id','level','unit_role','center_scope','core_id','primary_type_id','primary_type_name','complete_profile_id','classification_confidence','source_quality_flags','primary2010_population_share','protected_secondary2010_population_share','population2010_known_denominator','2010_missing_population_count'] if x in u];u[kc].to_csv(out/'unit_type_registry.csv.gz',index=False,compression='gzip');z[['unit_id','id','level','is_overlay_membership','_coordinate_valid']].to_csv(out/'exact_memberships.csv.gz',index=False,compression='gzip')
 if {p:sha(p) for p in watches}!=watches or sha(__file__)!=binding['code_sha256'] or sha(args.config)!=binding['config_sha256']:raise ValueError('Inputs/code/config changed during rendering')
 receipt={'status':'COMPUTED_AUTHOR_VISUAL_QA_PENDING','binding':binding,'pages':atlas.pages,'page_count':len(atlas.pages),'page_budget_target':[20,30],'page_budget_met':20<=len(atlas.pages)<=30,'no_inferred_polygons':True,'classification_unchanged':True,'files':[{'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()]}
 (out/'render_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'pages':len(atlas.pages),'output':str(out)}))
if __name__=='__main__':main()
