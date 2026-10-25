#!/usr/bin/env python3
"""Standalone research atlas from the actual zero-level/higher calculation.

Counts are read from frozen tables. Single demand records, uncertainty and
external 2015 reference boundaries are never presented as discovered SGRT.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import textwrap
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.colors import Normalize
from matplotlib.patches import Polygon

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_mass.figures import project

PAPER='#FAFBF9';INK='#253640';GRID='#E1E7E6';BLUE='#236A95';TEAL='#3D8179';GOLD='#B39942';ORANGE='#C97636';PINK='#A05E80';GREY='#B4BDC2';DARK='#5A6267'
STATUS={
 'multi':('В группе с несколькими населёнными НП',TEAL,'o'),
 'own':('Есть услуга в своём НП',GOLD,'s'),
 'near_single':('Близкий вариант есть; общая группа не выделена',PINK,'d'),
 'far':('В источниках найден только дальний вариант',ORANGE,'^'),
 'no_road':('Автомобильный путь не восстановлен',DARK,'x'),
 'unknown':('Близкое и дальнее направление не установлено',GREY,'o'),
}
TYPES={'monocentric_service_profile':'Один известный НП-поставщик','polycentric_service_profile':'Несколько известных НП-поставщиков','supplier_settlement_identity_partial_or_unknown':'НП части поставщиков не установлен','no_supported_daily_link':'Близкая связь не установлена','guarded_multichild_functional_candidate':'Условное объединение нижних групп','retained_subsystem':'Нижняя группа сохранена'}
FAMILIES={'medical_basic_primary':'Базовая медицинская помощь','basic_health':'Базовая медицинская помощь','medical_basic':'Базовая медицинская помощь','health_basic':'Базовая медицинская помощь','healthcare':'Базовая медицинская помощь','school_general':'Школа','school':'Школа','education':'Образование','preschool':'Детский сад','daily_retail':'Повседневные магазины','retail':'Повседневные магазины','grocery':'Продуктовые магазины','daily_shopping':'Повседневные магазины','daily_grocery':'Продуктовые магазины','pickup':'Пункты выдачи','parcel_pickup':'Пункты выдачи','ecommerce':'Пункты выдачи','medical_physician_primary':'Врачебная помощь','medical_hightech_licensed':'Высокотехнологичная помощь','vocational_education':'Колледжи и техникумы','higher_education':'Высшее образование','comparison_retail':'Более редкие покупки','medical_specialized':'Специализированная помощь'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':INK,'axes.labelcolor':INK,'axes.edgecolor':GREY,'xtick.color':INK,'ytick.color':INK,'pdf.fonttype':42,'savefig.facecolor':PAPER})


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for b in iter(lambda:stream.read(1<<20),b''):h.update(b)
 return h.hexdigest()


def num(x):return f'{int(x):,}'.replace(',',' ')
def words(s,width=110):return '\n'.join(textwrap.wrap(str(s),width=width))
def family_name(key):
 key=str(key)
 if key in FAMILIES:return FAMILIES[key]
 low=key.lower()
 if 'pickup' in low or 'parcel' in low or 'ecom' in low:return 'Пункты выдачи'
 if 'school' in low:return 'Школа'
 if 'preschool' in low:return 'Детский сад'
 if 'retail' in low or 'grocery' in low or 'shop' in low:return 'Магазины'
 if 'health' in low or 'medical' in low:return 'Медицинская помощь'
 return 'Дополнительная услуга'


def layout(title,subtitle,page):
 fig=plt.figure(figsize=(11.69,8.27),facecolor=PAPER)
 fig.text(.06,.955,'МЕСТНОЕ ОБСЛУЖИВАНИЕ  /  РОССИЯ',fontsize=9,color=TEAL,weight='bold')
 fig.text(.06,.90,title,fontsize=19,weight='bold')
 fig.text(.06,.855,words(subtitle,132),fontsize=9.5,va='top',color='#586970',linespacing=1.35)
 fig.text(.06,.026,'Переписи 2002/2010/2021 • услуги датированы источниками • направления не являются наблюдёнными поездками',fontsize=7.2,color='#64767D')
 fig.text(.94,.026,f'{page:02d}',ha='right',fontsize=9,color=TEAL)
 return fig


def note(fig,text,y=.09,width=136,size=9):fig.text(.06,y,words(text,width),va='top',fontsize=size,linespacing=1.35,color='#586970')
def style(ax,x=None,y=None):
 ax.set_facecolor(PAPER)
 for side in ['top','right']:ax.spines[side].set_visible(False)
 ax.grid(axis='y',color=GRID,lw=.6,zorder=0)
 if x:ax.set_xlabel(x)
 if y:ax.set_ylabel(y)
 ax.tick_params(labelsize=8.5)


def dots(ax,frame,color=GREY,s=.55,marker='o',alpha=.65,lon0=100.,lat0=60.,zorder=2):
 d=frame[frame.lat.notna()&frame.lon.notna()]
 x,y=project(d.lon,d.lat,lon0,lat0)
 ax.scatter(x,y,c=color,s=s,marker=marker,linewidths=.35 if marker=='x' else 0,alpha=alpha,rasterized=True,zorder=zorder)
 return d.assign(x=x,y=y)


def map_style(ax,extent=None):
 ax.set_aspect('equal',adjustable='box');style(ax,'км к востоку от центра проекции','км к северу')
 ax.grid(color=GRID,lw=.5)
 if extent:ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:])


def labels(ax,frame,column='name',maximum=5):
 rows=frame.dropna(subset=[column]).drop_duplicates(column).head(maximum)
 placed=[]
 for i,row in enumerate(rows.itertuples()):
  literal=str(getattr(row,column));label=words(literal[:44]+('…' if len(literal)>44 else ''),24)
  annotation=ax.annotate(label,(row.x,row.y),xytext=(5,7),textcoords='offset points',fontsize=8,bbox=dict(facecolor=PAPER,alpha=.9,edgecolor='none',pad=1.1),zorder=9)
  ax.figure.canvas.draw();renderer=ax.figure.canvas.get_renderer();bounds=ax.get_window_extent(renderer)
  okay=False
  for dx,dy in [(5,7),(5,-17),(-5,7),(-5,-21),(5,22),(-5,22)]:
   annotation.set_position((dx,dy));annotation.set_ha('right' if dx<0 else 'left');box=annotation.get_window_extent(renderer)
   inside=box.x0>=bounds.x0 and box.x1<=bounds.x1 and box.y0>=bounds.y0 and box.y1<=bounds.y1
   if inside and not any(box.overlaps(old) for old in placed):okay=True;placed.append(box);break
  if not okay:annotation.set_visible(False)


def metric(fig,x,value,label):
 fig.text(x,.775,value,fontsize=24,color=TEAL,weight='bold')
 fig.text(x,.735,words(label,34),fontsize=9,va='top',linespacing=1.3)


def yes(frame,column):
 return frame[column].fillna(False).eq(True) if column in frame else pd.Series(False,index=frame.index)


def classified_origins(reference,members,units,edges):
 origins=reference[reference.analysis_origin.fillna(False) if 'analysis_origin' in reference else reference.ordinary_spatial_2021.fillna(False)].copy()
 joined=members[['origin_id','unit_id']].merge(units[['unit_id','inhabited_multi_np_service_area']],on='unit_id',validate='many_to_one')
 origins=origins.merge(joined,left_on='source_record_id',right_on='origin_id',how='left',validate='one_to_one')
 def ids(mask):return set(edges.loc[mask,'origin_id'])
 admitted=yes(edges,'l0_admitted');own=admitted&edges.provider_settlement_id.eq(edges.origin_id)
 if 'known_local_supply' in edges:own|=admitted&yes(edges,'known_local_supply')
 if 'local_service_present' in edges:own|=admitted&yes(edges,'local_service_present')
 finite=pd.to_numeric(edges.cost_minutes,errors='coerce').notna()
 status=edges.get('route_status',pd.Series('',index=edges.index)).fillna('').astype(str)
 reason=edges.get('unknown_reason',pd.Series('',index=edges.index)).fillna('').astype(str)
 service_status=edges.get('service_status',edges.get('status',pd.Series('',index=edges.index))).fillna('').astype(str)
 no_road=status.str.contains('origin_road_endpoint_unavailable|no_accepted_road|no_directed_route',regex=True)|reason.str.contains('origin_road_endpoint_unavailable|no_directed_route',regex=True)
 if 'origin_road_endpoint_accepted' in edges:no_road|=edges.origin_road_endpoint_accepted.eq(False).fillna(False)
 limits=pd.to_numeric(edges.get('admission_limit_minutes',pd.Series(np.nan,index=edges.index)),errors='coerce')
 far=service_status.eq('far_known_candidate')|(finite&limits.notna()&pd.to_numeric(edges.cost_minutes,errors='coerce').gt(limits))
 admitted_ids=ids(admitted);own_ids=ids(own);far_ids=ids(far&~admitted);road_ids=ids(no_road)
 origins['display_status']='unknown'
 origins.loc[origins.source_record_id.isin(road_ids),'display_status']='no_road'
 origins.loc[origins.source_record_id.isin(far_ids),'display_status']='far'
 origins.loc[origins.source_record_id.isin(admitted_ids),'display_status']='near_single'
 origins.loc[origins.source_record_id.isin(own_ids),'display_status']='own'
 origins.loc[yes(origins,'inhabited_multi_np_service_area'),'display_status']='multi'
 return origins


class Inputs:
 def __init__(self,root,hierarchy,scenario,higher=None):
  self.root=Path(root);self.hierarchy=Path(hierarchy) if hierarchy else self.root/'hierarchy';self.sources={};self.before={}
  self.ref=self.table('context/analysis_reference.parquet')
  self.units=self.at(self.hierarchy/'level0_units.parquet');self.members=self.at(self.hierarchy/'level0_memberships.parquet');self.edges=self.at(self.hierarchy/'daily_edge_evidence.parquet')
  values=sorted(self.units.scenario_id.unique())
  if scenario is None:
   if len(values)!=1:raise ValueError('Choose --scenario explicitly: '+repr(values))
   scenario=values[0]
  if scenario not in values:raise ValueError('Unknown scenario: '+str(scenario))
  self.scenario=scenario
  self.units=self.units[self.units.scenario_id.eq(scenario)].copy();self.members=self.members[self.members.scenario_id.eq(scenario)].copy()
  if 'scenario_id' in self.edges:self.edges=self.edges[self.edges.scenario_id.eq(scenario)].copy()
  if self.members.origin_id.duplicated().any():raise ValueError('A plotted source scenario must have one group per origin')
  self.origins=classified_origins(self.ref,self.members,self.units,self.edges)
  expected=self.ref.loc[self.ref.analysis_origin.fillna(False) if 'analysis_origin' in self.ref else self.ref.ordinary_spatial_2021.fillna(False),'source_record_id'].dropna()
  if set(self.members.origin_id)!=set(expected):raise ValueError('National atlas cannot present a regional subset as full-country unknowns')
  self.multi=self.units[yes(self.units,'inhabited_multi_np_service_area')]
  self.anchor=self.at(self.hierarchy/'level0_provider_anchors.parquet',optional=True)
  if len(self.anchor) and 'scenario_id' in self.anchor:self.anchor=self.anchor[self.anchor.scenario_id.eq(scenario)]
  # Every population lookup retains nonadditive federal context separately.
  self.refidx=self.ref[self.ref.source_record_id.notna()].set_index('source_record_id')
  admitted=self.edges[yes(self.edges,'l0_admitted')]
  positive=set(self.origins.loc[self.origins.population_role.eq('ordinary_settlement_record')&yes(self.origins,'credit_2021')&self.origins.population_2021.gt(0),'source_record_id'])
  ext=admitted[admitted.origin_id.isin(positive)&admitted.provider_settlement_id.notna()&~admitted.provider_settlement_id.eq(admitted.origin_id)]
  self.centres=self.ref[self.ref.source_record_id.isin(ext.provider_settlement_id)].copy()
  self.higher=[]
  higher_root=Path(higher) if higher else self.root/'upward'/str(scenario)
  higher_paths=list(self.hierarchy.rglob('higher_units.parquet'))
  if higher_root.exists():higher_paths+=list(higher_root.rglob('units.parquet'))
  for path in sorted(set(higher_paths)):
   mempath=path.with_name('higher_memberships.parquet' if path.name=='higher_units.parquet' else 'memberships.parquet')
   if not mempath.exists():continue
   u=self.at(path);m=self.at(mempath)
   if 'scenario_id' in u:u=u[u.scenario_id.eq(scenario)].copy()
   if 'scenario_id' in m:m=m[m.scenario_id.eq(scenario)].copy()
   if len(u):self.higher.append((int(u.level.max()),u,m,path.parent))
  self.higher.sort(key=lambda x:x[0])
 def at(self,path,optional=False):
  path=Path(path)
  if not path.exists():
   if optional:return pd.DataFrame()
   raise FileNotFoundError(path)
  key=str(path.relative_to(self.root)) if path.is_relative_to(self.root) else str(path)
  self.sources[key]={'sha256':sha(path),'bytes':path.stat().st_size};self.before[path]=self.sources[key]['sha256']
  frame=pd.read_parquet(path);self.sources[key]['rows']=len(frame);return frame
 def table(self,path,optional=False):return self.at(self.root/path,optional)
 def geojson(self,path,optional=False):
  path=Path(path)
  if not path.exists():
   if optional:return None
   raise FileNotFoundError(path)
  key=str(path.relative_to(self.root)) if path.is_relative_to(self.root) else str(path)
  self.sources[key]={'sha256':sha(path),'bytes':path.stat().st_size};self.before[path]=self.sources[key]['sha256']
  return json.loads(path.read_text())


def plot_status(ax,points,*,lon0=100,lat0=60,extent=None,centres=None):
 for code,(label,color,marker) in STATUS.items():
  d=points[points.display_status.eq(code)]
  dots(ax,d,color=color,s=(5.0 if marker!='o' else 3.0) if extent is not None else (.75 if marker!='o' else .55),marker=marker,alpha=.72,lon0=lon0,lat0=lat0)
 if centres is not None and len(centres):
  dots(ax,centres,color=BLUE,s=12.0 if extent is not None else .6,marker='*',alpha=.8 if extent is not None else .45,lon0=lon0,lat0=lat0,zorder=5)
 map_style(ax,extent)


def city(reference,name,region=None):
 rows=reference[reference.name.eq(name)&reference.source_record_id.notna()&reference.lat.notna()&reference.lon.notna()]
 if region is not None:rows=rows[rows.region.eq(region)]
 if not len(rows):return None
 return rows.sort_values('population_2021',ascending=False).iloc[0]


def around(points,centre,radius_km):
 x,y=project(points.lon,points.lat,centre.lon,centre.lat)
 return points[(np.abs(x)<=radius_km)&(np.abs(y)<=radius_km)].copy()


def service_region(ax,data,centre,radius,service,all_origins):
 pts=around(all_origins,centre,radius);dots(ax,pts,color=GREY,s=4,alpha=.5,lon0=centre.lon,lat0=centre.lat)
 map_style(ax,[-radius,radius,-radius,radius])
 e=data[data.origin_id.isin(pts.source_record_id)&data.service_family.eq(service)&yes(data,'l0_admitted')].copy()
 if len(e):
  ids=e.provider_settlement_id.dropna().value_counts().head(3).index.tolist()
  unknown=e.provider_settlement_id.isna()
  assignments=dict(zip(ids,[BLUE,ORANGE,TEAL]));colors=[]
  for _,r in e.iterrows():colors.append(assignments.get(r.provider_settlement_id,PINK if pd.isna(r.provider_settlement_id) else GOLD))
  r=pts.set_index('source_record_id').loc[e.origin_id]
  x,y=project(r.lon,r.lat,centre.lon,centre.lat);ax.scatter(x,y,s=9,c=colors,linewidths=0,rasterized=True,zorder=3)
  for i,(_,r0) in enumerate(e.iterrows()):
   if pd.isna(r0.get('provider_lat')) or pd.isna(r0.get('provider_lon')):continue
   origin=pts.loc[pts.source_record_id.eq(r0.origin_id)].iloc[0]
   x,y=project([origin.lon,r0.provider_lon],[origin.lat,r0.provider_lat],centre.lon,centre.lat)
   ax.plot(x,y,color=colors[i],lw=.45,alpha=.35,ls='--',zorder=1)
  providers=e[e.provider_lat.notna()&e.provider_lon.notna()].drop_duplicates(['provider_settlement_id','provider_site_id']).copy()
  providers=providers.rename(columns={'provider_lat':'lat','provider_lon':'lon','provider_name':'name'})
  names=all_origins.set_index('source_record_id')['name']
  providers['name']=providers.provider_settlement_id.map(names).fillna(providers['name'])
  d=dots(ax,providers,color=INK,s=20,marker='*',alpha=.85,lon0=centre.lon,lat0=centre.lat,zorder=5)
  if len(d):labels(ax,d.sort_values('name'),maximum=3)
 map_style(ax,[-radius,radius,-radius,radius]);ax.set_title(family_name(service),fontsize=11)
 return {'origins_in_frame':len(pts),'origins_with_admitted_candidate':len(e),'provider_np_unknown':int(e.provider_settlement_id.isna().sum())}


def external_outline(ax,geo,efua_id,lon0,lat0):
 matches=[f for f in geo['features'] if int(f['properties']['eFUA_ID'])==int(efua_id)] if geo else []
 for f in matches:
  g=f['geometry'];polygons=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
  for rings in polygons:
   for i,ring in enumerate(rings):
    a=np.asarray(ring,float);x,y=project(a[:,0],a[:,1],lon0,lat0)
    ax.plot(x,y,color=DARK,lw=.9,ls='--',alpha=.85,zorder=4)
 return len(matches)


def build(root,hierarchy=None,output=None,scenario=None,higher=None,comparison_hierarchy=None,comparison_kind="inventory",comparison_upward=None,health_supply=None):
 data=Inputs(root,hierarchy,scenario,higher);data.geojson(Path(root)/'context/context_sources.json',True);out=Path(output) if output else Path(root)/'figures';out.mkdir(parents=True,exist_ok=True)
 health_has_saratov2021=False;health_has_federal_current=False
 pages=[];counts=data.origins.display_status.value_counts().to_dict();pdf_path=out/'zero_level_atlas.pdf'
 def save(fig,name,details):
  number=len(pages)+1;stem=f'{number:02d}_{name}'
  fig.canvas.draw();w,h=fig.canvas.get_width_height();renderer=fig.canvas.get_renderer();clipped=[]
  for text in fig.texts:
   box=text.get_window_extent(renderer)
   if box.x0<-.5 or box.x1>w+.5 or box.y0<-.5 or box.y1>h+.5:clipped.append(text.get_text())
  if clipped:raise ValueError('Clipped figure text: '+repr(clipped))
  fig.savefig(out/(stem+'.png'),dpi=170,facecolor=PAPER);pdf.savefig(fig,facecolor=PAPER);plt.close(fig)
  pages.append({'page':number,'file':stem+'.png','detail':details})
 with PdfPages(pdf_path) as pdf:
  #1: every origin has a meaning; centres are an overlay, not the only colour.
  fig=layout('Нулевой уровень: ближайшее обслуживание','Группы построены по известной части услуг. Цвет показывает состояние НП; звёзды — поставщиков с внешними участниками.',1)
  metric(fig,.06,num(len(data.multi)),'групп минимум с двумя населёнными НП')
  metric(fig,.37,num(int((data.multi.all_core_daily_families_have_candidate).sum())),'из этих групп имеют известных поставщиков всех 3 основных услуг')
  metric(fig,.69,num(len(data.origins)),'точек НП и городских контекстов в расчёте')
  ax=fig.add_axes([.06,.23,.88,.43]);plot_status(ax,data.origins,centres=data.centres)
  handles=[Line2D([],[],marker=marker,ls='',color=color,label=f'{label}: {num(counts.get(code,0))}',markersize=5) for code,(label,color,marker) in STATUS.items()]
  handles.append(Line2D([],[],marker='*',ls='',color=BLUE,label=f'НП-поставщик: {num(data.centres.source_record_id.nunique())}; возможны собственные внешние связи',markersize=8))
  fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.055,.075),ncol=2,frameon=False,fontsize=8.2,columnspacing=1.4)
  save(fig,'national_statuses',{'display_status_counts':counts,'multi_np_groups':len(data.multi),'known_external_centres':int(data.centres.source_record_id.nunique()),'centres_and_members_are_not_disjoint_sets':True})

  #2: source presence at the same NP grain; all85 reference regions remain rows.
  fig=layout('Где сведения привязаны к конкретным НП','Доля расчётных НП с адресно известной услугой. Светлая клетка означает нехватку сведений, а не отсутствие учреждения.',2)
  den=data.origins.groupby('region').source_record_id.nunique();regions=sorted(data.ref.region.dropna().unique());matrix=pd.DataFrame(index=regions)
  health_offer='health/public_scope_corrected/np_supply.parquet' if (Path(root)/'health/public_scope_corrected/np_supply.parquet').exists() else 'health/np_supply.parquet'
  if (Path(root)/'health/public_scope_child_corrected/np_supply.parquet').exists():health_offer='health/public_scope_child_corrected/np_supply.parquet'
  if health_supply is not None:health_offer=str(health_supply)
  education_root='education_general_scope_corrected' if (Path(root)/'education_general_scope_corrected/np_supply.parquet').is_file() else 'education'
  commerce_root='commerce_address_components_corrected' if (Path(root)/'commerce_address_components_corrected/supply.parquet').is_file() else 'commerce_identity_corrected' if (Path(root)/'commerce_identity_corrected/supply.parquet').is_file() else 'commerce'
  files=[(health_offer,'Медицина',['medical_basic_primary']),(education_root+'/np_supply.parquet','Образование',['school_general','preschool','preschool_official']),(commerce_root+'/supply.parquet','Магазины / ПВЗ',None)]
  details={}
  for relative,label,codes in files:
   effective=relative
   if label=='Магазины / ПВЗ' and commerce_root=='commerce' and (Path(root)/'commerce/federal_context/supply.parquet').exists():effective='commerce/federal_context/supply.parquet'
   d=data.table(effective)
   if label=='Медицина':
    health_has_saratov2021=bool(yes(d,'saratov_historical_2021_evidence_present').any());health_has_federal_current=bool(yes(d,'federal_current_2026_evidence_present').any())
   if label=='Магазины / ПВЗ':
    wb_path=commerce_root+'/supply_wb_current.parquet' if (Path(root)/(commerce_root+'/supply_wb_current.parquet')).exists() else 'commerce/federal_context/supply_wb_current.parquet'
    wb=data.table(wb_path,True)
    d=d[d.service_code.eq('daily_grocery')]
    if len(wb):d=pd.concat([d,wb[wb.service_code.eq('parcel_pickup_wildberries_current')]],ignore_index=True)
    host=data.table(commerce_root+'/fivepost/supply_grocery_current_host_proxy.parquet',True)
    if len(host):d=pd.concat([d,host[host.service_code.eq('daily_grocery_current_retail_host')]],ignore_index=True)
   valid=d.source_record_id.notna()&d.supply_status.isin(['observed','proxy'])
   if codes is not None:valid&=d.service_code.isin(codes)
   else:valid&=d.service_code.isin(['daily_grocery','daily_grocery_current_retail_host','parcel_pickup_wildberries_current'])
   d=d.loc[valid,['source_record_id']].drop_duplicates('source_record_id').merge(data.origins[['source_record_id','region']],on='source_record_id',how='inner',validate='one_to_one')
   n=d.groupby('region').source_record_id.nunique().reindex(regions).fillna(0);matrix[label]=(n/den.reindex(regions)*100).fillna(0);details[label]={'known_np':int(n.sum()),'denominator':int(den.sum())}
  chunks=np.array_split(np.asarray(regions,dtype=object),3);norm=Normalize(0,100)
  for i,chunk in enumerate(chunks):
   ax=fig.add_axes([.18+i*.31,.17,.14,.60]);a=matrix.loc[list(chunk)]
   image=ax.imshow(a.to_numpy(),cmap='Blues',norm=norm,aspect='auto',interpolation='nearest')
   ax.set_yticks(np.arange(len(a)),[str(x).capitalize() for x in a.index],fontsize=7.8);ax.set_xticks(range(3),['Мед.','Образ.','Торг.'],fontsize=8);ax.xaxis.tick_top();ax.tick_params(length=0)
  cax=fig.add_axes([.33,.13,.35,.018]);cb=fig.colorbar(image,cax=cax,orientation='horizontal');cb.set_label('Доля НП с известным адресным свидетельством, %',fontsize=8);cb.ax.tick_params(labelsize=8)
  note(fig,'Картографические объекты без подтверждённого НП в эту долю не входят. Три федеральных города — отдельные контексты; доля НП не равна доле обслуженных жителей.',y=.07,size=8)
  save(fig,'regional_source_coverage',{'region_count':len(regions),'matrix_percent':matrix.reset_index(names='region').to_dict('records'),'grain':'NP_with_source_identity_not_users_or_complete_institution_network'})

  #3: direction certainty and functional completeness are different axes.
  fig=layout('Состояние связи и полнота сведений различаются','Найденный дальний врач не означает, что рядом известны школа и магазин. Нулевой остаток неизвестных направлений не доказывает полноту сети.',3)
  ax=fig.add_axes([.34,.24,.29,.49]);keys=list(STATUS);values=[counts.get(k,0) for k in keys]
  ax.barh(range(len(keys)),values,color=[STATUS[k][1] for k in keys],height=.65,zorder=3)
  ax.set_yticks(range(len(keys)),[words(STATUS[k][0],34) for k in keys],fontsize=8.5);ax.invert_yaxis();style(ax,'Точек НП / городских контекстов')
  for i,v in enumerate(values):ax.text(v+max(values)*.012,i,num(v),va='center',fontsize=8)
  ax.set_xlim(0,max(values)*1.23 if max(values) else 1)
  complete=data.members[['origin_id','unit_id']].merge(data.units[['unit_id','known_core_daily_families']],on='unit_id',validate='many_to_one').known_core_daily_families.value_counts().reindex([3,2,1,0],fill_value=0)
  ax=fig.add_axes([.76,.24,.18,.49]);ax.bar(range(4),complete.values,color=[TEAL,GOLD,ORANGE,GREY],zorder=3);ax.set_xticks(range(4),['3 из 3','2 из 3','1 из 3','0 из 3'],fontsize=8,rotation=30);style(ax,'Известны близкие основные услуги','Точек НП');ax.set_title('Медицина, школа, магазин',fontsize=9)
  note(fig,'Справа — известные близкие варианты медицины, школы и магазина; ПВЗ учитывается дополнительно. Собственная услуга устанавливается по НП, а не по пути из каждого дома. Это не проверка фактического удовлетворения потребности.',y=.13)
  save(fig,'meaning_of_statuses',{'counts':dict(zip(keys,values)),'origin_total':len(data.origins),'known_core_service_counts':{str(k):int(v) for k,v in complete.items()}})

  #4: do not sell single records as a great number of multi-settlement areas.
  fig=layout('Размер групп: одиночные НП показаны отдельно','Состав нижних групп определяется одинаковым набором выбранных поставщиков. Группа из одной точки не доказывает наличие окружающих деревень.',4)
  ax=fig.add_axes([.08,.23,.40,.50]);u=data.units
  bins=[0,1,2,5,10,20,np.inf];labels0=['0','1','2–4','5–9','10–19','20 и больше']
  sizes=u.positive_credited_member_records
  category=pd.cut(sizes,bins=[-1,0,1,4,9,19,np.inf],labels=labels0)
  hist=category.value_counts(sort=False);ax.bar(labels0,hist,color=TEAL,zorder=3);style(ax,'НП с зачтённым положительным населением 2021','Групп');ax.tick_params(axis='x',rotation=20)
  ax=fig.add_axes([.60,.23,.32,.50]);q=data.multi[data.multi.member_geodesic_diameter_km.notna()]
  ax.hist(q.member_geodesic_diameter_km,bins=np.arange(0,max(10,float(q.member_geodesic_diameter_km.max())+5) if len(q) else 11,5),color=BLUE,edgecolor=PAPER,zorder=3);style(ax,'Максимальное расстояние между точками, км','Многопоселенческих групп')
  note(fig,'Размер рассчитан между точками НП, не по дороге. В колонке 0 нет участника с зачтённым положительным населением: возможны неизвестность или городской контекст, а не только отсутствие жителей.',y=.12)
  save(fig,'sizes',{'inhabited_member_histogram':{str(k):int(v) for k,v in hist.items()},'multi_np_group_diameter_median_km':float(q.member_geodesic_diameter_km.median()) if len(q) else None})

  #5: functional/demographic descriptions without claiming causal Word types.
  fig=layout('Типы нижних групп и изменение населения','Типы описывают найденные варианты обслуживания. Динамика относится к принятому составу НП, а не к доказанным историческим границам.',5)
  ax=fig.add_axes([.34,.27,.27,.48]);types=u.type_code.value_counts();names=[TYPES.get(x,'Дополнительный описательный тип') for x in types.index]
  ax.barh(range(len(types)),types.values,color=TEAL,zorder=3);ax.set_yticks(range(len(types)),[words(x,32) for x in names],fontsize=9);ax.invert_yaxis();style(ax,'Групп')
  ax=fig.add_axes([.72,.27,.20,.48]);complete=data.multi[data.multi.complete_member_demography_2002_2021.fillna(False)] if 'complete_member_demography_2002_2021' in data.multi else data.multi.iloc[0:0]
  counts_dem=complete.member_direction_2002_2021.value_counts().reindex(['decline','growth','unchanged'],fill_value=0)
  ax.bar(['Сокращение','Рост','Без изменения'],counts_dem.values,color=[BLUE,ORANGE,GREY],zorder=3);ax.tick_params(axis='x',rotation=30);style(ax,'2002–2021','Групп с полными сопоставимыми рядами')
  note(fig,'Динамика рассчитана по обычным учтённым НП с сопоставимыми значениями обоих лет. Москва, Петербург и Севастополь — отдельные справочные центры; их население не добавлено к этим суммам. Пропуски не заменены нулём.',y=.12)
  save(fig,'types_and_demography',{'descriptive_type_counts':types.to_dict(),'complete_multi_np_demography_groups':len(complete),'demography':counts_dem.to_dict()})

  #6: equal functional order is not an equal population-size requirement.
  fig=layout('Саратовская область: проверка четырёх местных центров','Четыре центра показаны на участках с разным увеличением. Правила одинаковы для города и села; преимущество по населению не задаётся.',6)
  centres=[('Саратов и Энгельс','Саратов',35),('Новоузенск','Новоузенск',24),('Питерка','Питерка',24)];cases=[]
  for i,(label,name,radius) in enumerate(centres):
   c=city(data.ref,name,'саратовская');ax=fig.add_axes([.06+i*.305,.23,.27,.48])
   if c is None:ax.text(.5,.5,'Точка центра не найдена',ha='center',transform=ax.transAxes);ax.axis('off');continue
   pts=around(data.origins,c,radius);cs=around(data.centres,c,radius);plot_status(ax,pts,lon0=c.lon,lat0=c.lat,extent=[-radius,radius,-radius,radius],centres=cs)
   names=['Саратов','Энгельс'] if name=='Саратов' else [name]
   marks=data.ref[data.ref.name.isin(names)&data.ref.region.eq('саратовская')&data.ref.lat.notna()&data.ref.lon.notna()].sort_values('population_2021',ascending=False).drop_duplicates('name')
   marks=dots(ax,marks,color=INK,s=38,marker='*',alpha=1,lon0=c.lon,lat0=c.lat,zorder=8);labels(ax,marks,maximum=2);ax.set_title(label,fontsize=11)
   if i:ax.set_ylabel('')
   cases.append({'name':label,'frame_halfwidth_km':radius,'np_points':len(pts),'display_status_counts':pts.display_status.value_counts().to_dict()})
  note(fig,'Окна — увеличение карты, а не радиус расчёта. Медицина: федеральные адреса 2026 года и отдельные исторические сведения. Точка НП — приближение, не координаты здания.' if health_has_federal_current else 'Окна — увеличение карты, а не радиус расчёта. Медицина области дополнена официальными адресами 2021 года; их работа в 2026 году и реальные поездки не подтверждены.' if health_has_saratov2021 else 'Окна — увеличение карты, а не радиус расчёта. Официального реестра области в этом варианте нет; дальний кандидат не доказывает поездку.',y=.14,size=8)
  save(fig,'saratov_zero_local_windows',{'cases':cases})

  #7: four separate service footprints in the same Saratov/Engels window.
  fig=layout('Саратов и Энгельс: услуги показаны раздельно','Цвет различает поставщиков внутри панели. Пунктир — направление к зданию или точке НП, не трасса дороги.',7)
  c=city(data.ref,'Саратов','саратовская');families=sorted(data.edges.service_family.unique());service_details=[]
  for i,family in enumerate(families[:4]):
   ax=fig.add_axes([.07+(i%2)*.47,.20+(1-i//2)*.32,.39,.24])
   if c is not None:service_details.append({'service':str(family),**service_region(ax,data.edges,c,30,family,data.origins)})
   else:ax.text(.5,.5,'Точка Саратова не найдена',transform=ax.transAxes,ha='center');ax.axis('off')
   if i<2:ax.set_xlabel('')
  note(fig,'Серые точки: в этом виде услуг близкий вариант не принят. Цвет и пунктир показывают выбранного поставщика; розовый — объект без установленного НП. Названия НП и положение здания сохраняются раздельно.',y=.115)
  save(fig,'saratov_service_layers',{'family_count':len(families),'shown':service_details})

  #8: the actual upward calculation, not level numbers manufactured by a loop.
  fig=layout('Как нижние группы объединяются выше','Новый шаг учитывается только при появлении дополнительных функций и допустимого пространственного объединения.',8)
  ax=fig.add_axes([.10,.25,.80,.48]);higher_counts=[]
  for level,hu,hm,path in data.higher:
   new=hu[yes(hu,'new_territorial_merger')]
   higher_counts.append({'level':level,'new_mergers':len(new),'retained_units':len(hu)-len(new),'total_units':len(hu),'source':str(path),'maximum_effective_merge_depth':int(hu.effective_merge_depth.max()) if 'effective_merge_depth' in hu else None})
  if higher_counts:
   positions=np.arange(len(higher_counts));values=[r['new_mergers'] for r in higher_counts]
   ax.bar(positions,values,color=BLUE,zorder=3);ax.set_xticks(positions,[f'Шаг {r["level"]}' for r in higher_counts]);style(ax,'Дополнительный функциональный шаг','Новых объединений нижних групп')
   for x,v in zip(positions,values):ax.text(x,v+max(values+[1])*.025,num(v),ha='center',fontsize=10)
   ax.set_ylim(0,max(values+[1])*1.17)
  else:
   ax.axis('off');ax.text(.03,.74,'Данные законченного укрупнения пока не получены.',fontsize=16,transform=ax.transAxes)
   ax.text(.03,.56,words('Существование дальнего врача или вуза сохраняет связь, но само по себе не превращает пол-области в единую местную систему.',90),fontsize=12,transform=ax.transAxes,va='top')
  note(fig,'Необъединённые группы сохраняются; шаг не равен доказанному порядку. Редкая помощь учитывается по отдельным заявленным профилям: подходящая больница для каждого жителя не установлена. Пределы 90/120 минут — авторские варианты, не оценки наблюдённых поездок.',y=.13)
  save(fig,'upward_progress',{'layers':higher_counts,'zero_multi_np_groups':len(data.multi)})

  #9: Saratov and Engels above the daily level, with boundaries external only.
  fig=layout('Саратов и Энгельс: проверка более широких связей','Медицинские функции области дополнены федеральным реестром 2026 года. Пространственные объединения остаются расчётными кандидатами.' if health_has_federal_current else 'Область дополнена реестром медицинских подразделений 2021 года; проверяется влияние датированного источника, а не наблюдённых поездок.' if health_has_saratov2021 else 'Результат ограничен полнотой источников: официальные медицинские подразделения Саратовской области в основе отсутствуют.',9)
  c=city(data.ref,'Саратов','саратовская');ax=fig.add_axes([.08,.20,.55,.55]);details={}
  if c is not None:
   pts=around(data.origins,c,210);dots(ax,pts,color=GREY,s=1.5,alpha=.55,lon0=c.lon,lat0=c.lat)
   ids=set()
   if data.higher:
    level,hu,hm,path=data.higher[-1]
    key='np:'+c.source_record_id
    keys=hu.get('all_provider_keys_json',hu.get('real_provider_keys_json',pd.Series('',index=hu.index))).astype(str)
    supported=hu.effective_merge_depth.gt(0) if 'effective_merge_depth' in hu else yes(hu,'new_territorial_merger')
    selected=hu[keys.str.contains(key,regex=False)&supported]
    ids=set(hm.loc[hm.unit_id.isin(selected.unit_id),'origin_id']);dots(ax,pts[pts.source_record_id.isin(ids)],color=BLUE,s=6,alpha=.8,lon0=c.lon,lat0=c.lat)
    details={'level':level,'groups_with_saratov_provider':len(selected),'associated_origins_in_window':len(set(pts.source_record_id)&ids)}
   marks=data.ref[data.ref.name.isin(['Саратов','Энгельс','Новоузенск','Питерка'])&data.ref.region.eq('саратовская')&data.ref.lat.notna()&data.ref.lon.notna()].sort_values('population_2021',ascending=False).drop_duplicates('name')
   marks=dots(ax,marks,color=INK,s=38,marker='*',alpha=1,lon0=c.lon,lat0=c.lat,zorder=8);labels(ax,marks,maximum=4);map_style(ax,[-170,200,-200,160])
  else:ax.axis('off')
  fig.text(.68,.68,words('Цветные точки — НП в полученных группах, где Саратов указан одним из поставщиков.',32),fontsize=11,va='top',linespacing=1.4)
  fig.text(.68,.46,words('Серые точки — остальные НП, включая собственные местные группы. Больничный профиль не означает подходящую помощь для любой потребности; реальные потоки не наблюдались.' if health_has_federal_current else 'Серые точки — остальные НП, включая самостоятельные местные группы. Реестр 2021 года не подтверждает нынешнюю работу всех подразделений и фактические потоки.' if health_has_saratov2021 else 'Серые точки — остальные НП. Отсутствие более высокой группы здесь нельзя считать реальной самостоятельностью: в медицинском реестре отсутствует вся область.',32),fontsize=11,va='top',linespacing=1.4)
  note(fig,'Показан последний фактически полученный шаг. При отсутствии допустимых объединений карта сохраняет справочные НП без вымышленной зоны города.',y=.12)
  save(fig,'saratov_higher',details)

  #10: public2015 shapes provide an explicit external comparison, not truth.
  fig=layout('Москва и Петербург: сравнение с внешней оценкой 2015 года','Пунктир — границы eFUA исследовательского продукта GHSL/JRC. Это другая модель и другой год, а не проверенные границы наших систем.',10)
  geo=data.geojson(Path(root)/'literature/external_fua_russia/analysis_frame_efua_2015.geojson',True)
  cases=data.table('literature/external_fua_russia/external_fua_named_cases.parquet',True);detail=[]
  for i,(name,region,radius) in enumerate([('Москва','москва',110),('Санкт-Петербург','санкт петербург',80)]):
   ax=fig.add_axes([.07+i*.47,.22,.40,.51]);c=city(data.ref,name,region)
   if c is None:ax.axis('off');continue
   pts=around(data.origins,c,radius);dots(ax,pts,color=GREY,s=1.7,alpha=.55,lon0=c.lon,lat0=c.lat)
   case=cases[cases.name_ru.eq(name)] if len(cases) else pd.DataFrame();efua=int(case.eFUA_ID.iloc[0]) if len(case) else None
   shown=set();level=None
   if data.higher:
    level,hu,hm,path=data.higher[-1]
    # An inherited supplier name does not make every referring group part of
    # this city's own group. Select its actual membership, with exact IDs.
    city_unit_ids=set(hm.loc[hm.origin_id.eq(c.source_record_id),'unit_id'])
    selection=hu.unit_id.isin(city_unit_ids)
    supported=hu.effective_merge_depth.gt(0) if 'effective_merge_depth' in hu else yes(hu,'new_territorial_merger')
    selected=hu[selection&supported];shown=set(hm.loc[hm.unit_id.isin(selected.unit_id),'origin_id'])
    dots(ax,pts[pts.source_record_id.isin(shown)],color=BLUE,s=7,alpha=.8,lon0=c.lon,lat0=c.lat)
   if efua is not None:external_outline(ax,geo,efua,c.lon,c.lat)
   dots(ax,pd.DataFrame([c]),color=INK,s=55,marker='*',alpha=1,lon0=c.lon,lat0=c.lat,zorder=9);map_style(ax,[-radius,radius,-radius,radius]);ax.set_title(name,fontsize=12)
   detail.append({'name':name,'external_efua_id':efua,'last_computed_level':level,'associated_model_points_in_window':len(shown&set(pts.source_record_id)),'selection_rule':'actual_unit_containing_city_context_not_any_inherited_supplier_or_reference'})
  note(fig,'Цветные точки — итоговая группа, в которую входит данный городской контекст; серые — остальные НП. Внешний контур 2015 года не доказывает поездки. Население федеральных городов не прибавляется к суммам обычных НП.',y=.13)
  save(fig,'moscow_petersburg_external_comparison',{'cases':detail,'external_boundaries_are_not_ground_truth':True})

  #11: same reference sample, service-specific travel instead of one radius.
  fig=layout('Доступность различается по видам услуг','Сравнение относится к точкам НП и модельной автомобильной стоимости. Это не число поездок жителей.',11)
  ax=fig.add_axes([.26,.22,.66,.53]);distributions=[];labels1=[];detail=[]
  for family,g in data.edges.groupby('service_family',sort=True):
   finite=pd.to_numeric(g.cost_minutes,errors='coerce').dropna();admitted=g[yes(g,'l0_admitted')].cost_minutes.dropna()
   distributions.append(finite.to_numpy(float));labels1.append(family_name(family));detail.append({'service':family,'finite':len(finite),'admitted':len(admitted),'median_all_finite_minutes':float(finite.median()) if len(finite) else None,'p90_all_finite_minutes':float(finite.quantile(.9)) if len(finite) else None,'over180':int(finite.gt(180).sum())})
  if distributions:
   bp=ax.boxplot(distributions,vert=False,tick_labels=labels1,showfliers=False,patch_artist=True)
   for patch in bp['boxes']:patch.set(facecolor=BLUE,alpha=.65)
  style(ax,'Модельные минуты')
  note(fig,'Прямоугольник — 25–75-й процентили, линия — медиана; усы — до 1,5 межквартильного размаха. Выбросы скрыты только на рисунке. Отсутствующие пути сохранены отдельно; дальние варианты остаются в исходных данных.',y=.12)
  save(fig,'service_accessibility',{'service_distributions':detail,'axis_display_cap_minutes':None,'outliers_hidden_in_boxplot_only':True,'is_a_new_admission_limit':False})

  #12: preserve agriculture/workforce as context, not fictitious settlement jobs.
  fig=layout('Сельское хозяйство и сведения о работниках','Районные сельхозпоказатели не распределены по деревням. Численность работников охватывает только часть организаций.',12)
  agro_path=Path(root)/'context/settlement_agriculture_context.parquet';work_path=Path(root)/'context/settlement_partial_workforce.parquet'
  detail={}
  ax=fig.add_axes([.06,.25,.43,.48]);style(ax)
  if agro_path.exists():
   a=data.at(agro_path);col='agri_sown_area_ha_2021_municipal_context';groups=['grain','feed','technical'];fields=[col]+[f'agri_{key}_sown_ha_2021_municipal_context' for key in groups]
   p=data.origins.merge(a[a.source_record_id.notna()][['source_record_id']+fields],on='source_record_id',how='left',validate='one_to_one')
   total=pd.to_numeric(p[col],errors='coerce');v=p[fields[1:]].apply(pd.to_numeric,errors='coerce');v.columns=groups
   valid=total.gt(0)&v.notna().all(axis=1)&v.ge(0).all(axis=1)&v.sum(axis=1).le(total*1.02)
   p['crop_profile']='unknown';p.loc[valid,'crop_profile']='mixed';dominant=v.ge(total*.5,axis=0)&valid.to_numpy()[:,None]
   for key in groups:p.loc[dominant[key]&dominant.sum(axis=1).eq(1),'crop_profile']=key
   p.loc[total.eq(0),'crop_profile']='reported_zero'
   crop_colors={'unknown':GRID,'reported_zero':GREY,'mixed':DARK,'grain':GOLD,'feed':TEAL,'technical':ORANGE}
   for key,color in crop_colors.items():dots(ax,p[p.crop_profile.eq(key)],color=color,s=.5 if key=='unknown' else .85,alpha=.65)
   detail['municipal_crop_profile_np_counts']=p.crop_profile.value_counts().to_dict();map_style(ax)
   fig.legend(handles=[Line2D([],[],marker='o',ls='',color=crop_colors[k],label=n) for k,n in [('grain','Зерновые'),('feed','Кормовые'),('technical','Технические'),('mixed','Нет преобладания'),('reported_zero','Опубликован нулевой посев'),('unknown','Недостаточно сведений')]],loc='lower left',bbox_to_anchor=(.055,.175),ncol=3,frameon=False,fontsize=7.8)
  else:ax.text(.5,.5,'Сельхозтаблица не передана',ha='center',transform=ax.transAxes)
  ax.set_title('Районный профиль посевов, 2021',fontsize=10)
  ax=fig.add_axes([.55,.25,.40,.48]);style(ax)
  if work_path.exists():
   w=data.at(work_path);col='partial_organisation_workforce_2025';p=data.origins.merge(w[w.source_record_id.notna()][['source_record_id',col]],on='source_record_id',how='left',validate='one_to_one');dots(ax,p,color=GRID,s=.35,alpha=.55);known=p[p[col].notna()];dots(ax,known,color=BLUE,s=1.3,alpha=.75);detail['np_with_partial_workforce']=len(known);map_style(ax)
  else:ax.text(.5,.5,'Таблица работников не передана',ha='center',transform=ax.transAxes)
  ax.set_title('Есть частичная численность работников, 2025',fontsize=10)
  note(fig,'Цвет означает наличие записи. Посевы характеризуют муниципальную территорию; работники относятся к ограниченному кругу организаций. Эти показатели не заменяют данные о рабочих местах и поездках на работу.',y=.14)
  save(fig,'agriculture_and_workforce',detail)
  if comparison_hierarchy is not None:
   compare_path=Path(comparison_hierarchy)
   cu=data.at(compare_path/'level0_units.parquet');cm=data.at(compare_path/'level0_memberships.parquet')
   if cm.origin_id.duplicated().any() or set(cm.origin_id)!=set(data.members.origin_id):raise ValueError('Comparison must cover the identical national origin set once')
   c_multi=cu[yes(cu,'inhabited_multi_np_service_area')]
   fig=layout('Насколько результат зависит от исходных сведений','Основной вариант дополнен датированным медицинским реестром; контроль использует прежние сведения. Это проверка источников, не наблюдение поездок.' if comparison_kind=='inventory' else 'Оба варианта используют одни источники. Более широкий предел — проверка чувствительности, не доказательство реальных поездок.',13)
   categories=['Группы с двумя и более\nнаселёнными НП','Группы с известными\nтремя основными услугами']
   values=np.asarray([[len(data.multi),int(data.multi.all_core_daily_families_have_candidate.sum())],[len(c_multi),int(c_multi.all_core_daily_families_have_candidate.sum())]])
   ax=fig.add_axes([.12,.27,.77,.43]);x=np.arange(2)
   for j,(name,color) in enumerate([('Основной вариант с дополнением' if comparison_kind=='inventory' else 'Основной вариант',BLUE),('Контроль без дополнения' if comparison_kind=='inventory' else 'Расширенный вариант',ORANGE)]):
    bars=ax.bar(x+(j-.5)*.30,values[j],.28,color=color,label=name)
    ax.bar_label(bars,labels=[num(v) for v in values[j]],padding=5,fontsize=10)
   ax.set_xticks(x,categories,fontsize=10);ax.set_ylim(0,float(values.max())*1.18);ax.set_ylabel('Число групп');ax.legend(frameon=False);ax.spines[['top','right']].set_visible(False)
   note(fig,'Группа с одним НП и группа без допустимой близкой связи не считаются многопоселенческой местной системой. Количество модельных групп не равно количеству подтверждённых СГРТ.',y=.14,size=9)
   save(fig,'strict_extended_counts',{'main_scenario':data.scenario,'comparison_scenarios':sorted(cu.scenario_id.unique()),'counts':values.tolist()})
   fig=layout('Где различаются два варианта местных групп','Серые точки имеют тот же признак принадлежности группе с другими населёнными НП. Это не обязательно одинаковые состав и поставщики.',14)
   mainids=set(data.members.loc[data.members.unit_id.isin(data.multi.unit_id),'origin_id']);otherids=set(cm.loc[cm.unit_id.isin(c_multi.unit_id),'origin_id'])
   p=data.origins.copy();p['comparison_state']='same';p.loc[p.source_record_id.isin(otherids-mainids),'comparison_state']='gained';p.loc[p.source_record_id.isin(mainids-otherids),'comparison_state']='lost'
   ax=fig.add_axes([.06,.24,.88,.48]);delta_counts=p.comparison_state.value_counts().to_dict()
   for key,color,label in [('same',GREY,'Признак не изменился'),('gained',TEAL,'Только в сравнительном варианте входит в группу'),('lost',ORANGE,'Только в основном варианте входит в группу')]:
    dots(ax,p[p.comparison_state.eq(key)],color=color,s=.5 if key=='same' else 2,alpha=.6)
   map_style(ax)
   fig.legend(handles=[Line2D([],[],marker='o',ls='',color=c,label=f'{label}: {num(delta_counts.get(k,0))}') for k,c,label in [('same',GREY,'Тот же признак'),('gained',TEAL,'Группа с другими НП только в сравнительном варианте'),('lost',ORANGE,'Группа с другими НП только в основном варианте')]],loc='lower left',bbox_to_anchor=(.055,.14),frameon=False,ncol=1,fontsize=9)
   save(fig,'strict_extended_geography',{'counts':delta_counts,'same_means_same_multi_np_membership_status_not_identical_boundaries':True})
  if comparison_upward is not None:
   if comparison_hierarchy is not None:raise ValueError('Choose either L0 source comparison or higher territorial comparison, not both')
   comparison_root=Path(comparison_upward);variants={}
   for name in ['all_declared','partial_positive_two_domains']:
    layers=[]
    for path in sorted((comparison_root/name).glob('*/units.parquet')):
     u=data.at(path);m=data.at(path.with_name('memberships.parquet'))
     if m.origin_id.duplicated().any() or set(m.origin_id)!=set(data.members.origin_id):raise ValueError('Higher comparison does not retain all national origins')
     layers.append((path.parent.name,u,m))
    if not layers:raise ValueError('No frozen higher comparison found: '+str(comparison_root/name))
    variants[name]=layers
   fig=layout('Как меняются условия более крупных объединений','Источники и пределы прямой доступности одинаковы. Меняются территориальное правило и требование нескольких независимых сфер.',13)
   ax=fig.add_axes([.11,.29,.80,.42]);stage_names=[x[0] for x in variants['all_declared']];x=np.arange(len(stage_names));comparison_counts={}
   strict={p.name:u for _,u,m,p in data.higher}
   for j,(key,label,color) in enumerate([('strict','Основной: участники внутри контура 2015',BLUE),('all_declared','Сравнение: все требуемые сферы',TEAL),('partial_positive_two_domains','Диагностика: две известные сферы',ORANGE)]):
    lookup=strict if key=='strict' else {stage:u for stage,u,m in variants[key]}
    values=[int(yes(lookup[stage],'new_territorial_merger').sum()) if stage in lookup else 0 for stage in stage_names];comparison_counts[key]=values
    bars=ax.bar(x+(j-1)*.24,values,.23,color=color,label=label);ax.bar_label(bars,labels=[num(v) for v in values],padding=3,fontsize=8)
   ax.set_xticks(x,['Больницы и колледжи','Редкие услуги и вузы','Высокотехнологичная помощь'][:len(stage_names)],fontsize=9);ax.set_ylabel('Новые объединения на шаге');ax.spines[['top','right']].set_visible(False);ax.legend(frameon=False,fontsize=8,loc='upper right');ax.margins(y=.18)
   diagnostic_note='Вариант с двумя известными сферами — диагностика, не принятые границы агломераций.'
   _,pu,pm=variants['partial_positive_two_domains'][-1]
   astrakhan=city(data.ref,'Астрахань','астраханская')
   if astrakhan is not None:
    ids=pm.loc[pm.origin_id.eq(astrakhan.source_record_id),'unit_id']
    if len(ids):
     diameter=pu.set_index('unit_id').loc[ids.iloc[0],'member_geodesic_diameter_km']
     diagnostic_note=f'В диагностическом варианте двух сфер группа Астрахани растянулась примерно на {num(round(diameter))} км в диаметре; это не принятые границы агломерации.'
   note(fig,'Основной вариант — строгий; расширенный полный вариант используется для сравнения и требует все заявленные сферы. '+diagnostic_note+' Односферный последний шаг не является новым общим порядком.',y=.14,size=8)
   save(fig,'strict_extended_higher_counts',{'counts':comparison_counts,'stages':stage_names,'same_sources_different_territorial_rules':True,'minimum_independent_domains_rule_also_differs':True,'not_a_pure_effect_of_external_boundary':True})
   fig=layout('Как условия объединения меняют размер групп','Сравнивается число населённых участников: основной строгий вариант и расширенный полный вариант для сравнения.',14)
   if not data.higher:raise ValueError('Strict higher outputs required for comparison')
   _,su,sm,_=data.higher[-1];_,eu,em=variants['all_declared'][-1]
   field='positive_credited_member_records';ss=sm.merge(su[['unit_id',field]],on='unit_id',validate='many_to_one').set_index('origin_id')[field];es=em.merge(eu[['unit_id',field]],on='unit_id',validate='many_to_one').set_index('origin_id')[field]
   p=data.origins.copy();p['difference']=p.source_record_id.map(es)-p.source_record_id.map(ss);p['comparison_state']='same';p.loc[p.difference.gt(0),'comparison_state']='larger';p.loc[p.difference.lt(0),'comparison_state']='smaller'
   ax=fig.add_axes([.06,.31,.88,.43]);cnt=p.comparison_state.value_counts().to_dict()
   for key,color,size in [('same',GREY,.5),('larger',TEAL,2),('smaller',ORANGE,2)]:dots(ax,p[p.comparison_state.eq(key)],color=color,s=size,alpha=.65)
   map_style(ax)
   handles=[Line2D([],[],marker='o',ls='',color=c,label=f'{label}: {num(cnt.get(k,0))}') for k,c,label in [('same',GREY,'То же число участников; состав может отличаться'),('larger',TEAL,'В расширенном варианте группа больше'),('smaller',ORANGE,'В расширенном варианте группа меньше')]]
   fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.055,.13),frameon=False,fontsize=8.8)
   save(fig,'strict_extended_higher_geography',{'counts':cnt,'metric':field,'same_size_does_not_prove_identical_membership':True})
 changed=[str(p) for p,v in data.before.items() if sha(p)!=v]
 if changed:raise RuntimeError('Scientific input changed during rendering: '+repr(changed))
 manifest={'pages':pages,'page_count':len(pages),'scenario_id':data.scenario,'input_files':data.sources,'inputs_changed_during_render':changed,
  'generated_moscow':datetime.now(ZoneInfo('Europe/Moscow')).isoformat(),'code_sha256':sha(Path(__file__)),
  'run_hash':hashlib.sha256(json.dumps({'inputs':data.sources,'scenario':data.scenario,'code':sha(Path(__file__))},sort_keys=True).encode()).hexdigest(),
  'multi_np_groups_are_not_all_profile_rows':True,'external2015_boundaries_are_not_ground_truth':True,'observed_flows_claimed':False}
 (out/'atlas_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'pdf':str(pdf_path),'pages':len(pages),'scenario':data.scenario,'inputs_changed':changed}));return manifest


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--hierarchy',type=Path);p.add_argument('--output',type=Path);p.add_argument('--scenario');p.add_argument('--higher',type=Path);p.add_argument('--comparison-hierarchy',type=Path);p.add_argument('--comparison-kind',choices=['inventory','distance'],default='inventory');p.add_argument('--comparison-upward',type=Path);p.add_argument('--health-supply',type=Path);a=p.parse_args()
 build(a.root,a.hierarchy,a.output,a.scenario,a.higher,a.comparison_hierarchy,a.comparison_kind,a.comparison_upward,a.health_supply)


if __name__=='__main__':main()
