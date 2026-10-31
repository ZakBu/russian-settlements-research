"""Publication figures from computed GeoJSON and census-backed statistics.

No invented geometry, flows or population. Scientific PNGs belong in Releases.
"""
from __future__ import annotations
import json,math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch,Patch
from matplotlib.path import Path as MplPath
from matplotlib.lines import Line2D
import shapely
from shapely.geometry import shape

PAPER='#faf9f5';INK='#243c43';COLORS={30:'#237f83',60:'#86b8b8',90:'#dce8e4'}

def load(path):return json.loads(Path(path).read_text())
def geometry(ax,g,*,fill=None,edge=None,lw=.5,alpha=1,z=1):
 if g.is_empty:return
 if g.geom_type in {'GeometryCollection','MultiPolygon','MultiLineString','MultiPoint'}:
  for part in g.geoms:geometry(ax,part,fill=fill,edge=edge,lw=lw,alpha=alpha,z=z)
 elif g.geom_type=='Polygon':
  g=shapely.geometry.polygon.orient(g,sign=1.);vertices=[];codes=[]
  for ring in [g.exterior,*g.interiors]:
   xy=list(ring.coords);vertices.extend(xy);codes.extend([MplPath.MOVETO]+[MplPath.LINETO]*(len(xy)-2)+[MplPath.CLOSEPOLY])
  ax.add_patch(PathPatch(MplPath(vertices,codes),facecolor=fill or 'none',edgecolor=edge or 'none',linewidth=lw,alpha=alpha,zorder=z))
 elif g.geom_type in {'LineString','LinearRing'}:
  x,y=g.xy;ax.plot(x,y,color=edge or fill or INK,lw=lw,alpha=alpha,zorder=z)

def configure(ax,bounds):
 xmin,ymin,xmax,ymax=bounds;dx=xmax-xmin;dy=ymax-ymin
 ax.set_xlim(xmin-.035*dx,xmax+.035*dx);ax.set_ylim(ymin-.04*dy,ymax+.04*dy);ax.set_aspect(1/math.cos(math.radians((ymin+ymax)/2)))
 ax.set_facecolor(PAPER);ax.tick_params(colors='#6b7b7d',labelsize=8,width=.4);ax.grid(alpha=.13,color=INK,lw=.4,zorder=0)
 for sp in ax.spines.values():sp.set_color('#d4ddda');sp.set_linewidth(.6)
 ax.set_xlabel('Долгота, ° в. д.',fontsize=8,color='#6b7b7d');ax.set_ylabel('Широта, ° с. ш.',fontsize=8,color='#6b7b7d')

def context(ax,features,core,centre):
 for f in features:
  p=f['properties'];kind=p.get('kind');g=shape(f['geometry'])
  if kind=='road':geometry(ax,g,edge='#90999a',lw=.32,alpha=.43,z=3)
  elif kind=='railway':geometry(ax,g,edge='#777671',lw=.24,alpha=.38,z=3)
  elif kind=='river':geometry(ax,g,edge='#4d91b5',lw=1.05 if p.get('name')=='Кубань' else .55,alpha=.9,z=4)
 geometry(ax,core,fill='#e7e2d2',edge=INK,lw=.7,alpha=.9,z=5)
 ax.scatter([centre[0]],[centre[1]],marker='*',s=68,c=INK,edgecolors='white',linewidths=.5,zorder=8)

def labels(ax,places,names):
 offsets={'Краснодар':(6,-12),'Яблоновский':(-5,-14),'Динская':(6,5),'Горячий Ключ':(6,-12),'Марьянская':(-6,7),'Тимашевск':(5,5),'Усть-Лабинск':(5,5),'Северская':(5,-12)}
 for f in places:
  p=f['properties'];name=p.get('name')
  if name not in names:continue
  x,y=f['geometry']['coordinates'];dx,dy=offsets.get(name,(5,5));ax.scatter([x],[y],s=10,c=INK,edgecolors='white',linewidths=.25,zorder=9)
  ax.annotate(name,(x,y),xytext=(dx,dy),textcoords='offset points',ha='right' if dx<0 else 'left',fontsize=7.2,color=INK,zorder=10,bbox={'boxstyle':'round,pad=.15','fc':PAPER,'ec':'none','alpha':.86})

def fmt(value):return f'{int(value):,}'.replace(',',' ')
def build_figures(access,output):
 access=Path(access);output=Path(output);output.mkdir(parents=True,exist_ok=True)
 plt.rcParams.update({'font.family':'DejaVu Sans','text.color':INK,'axes.titlecolor':INK,'figure.facecolor':PAPER,'savefig.facecolor':PAPER})
 point=load(access/'isochrones_base.geojson')['features'];corezones=load(access/'core_isochrones_base.geojson')['features'];ctx=load(access/'context.geojson')['features'];places=load(access/'places.geojson')['features'];core=shape(load(access/'core.geojson')['features'][0]['geometry']);summary=load(access/'summary.json');stats=load(access/'statistics.json');centre=(float(summary['centre']['lon']),float(summary['centre']['lat']));bounds=shape(next(f for f in corezones if f['properties']['minutes']==90)['geometry']).bounds
 fig,axes=plt.subplots(1,2,figsize=(14,8.5));fig.subplots_adjust(top=.79,bottom=.25,left=.065,right=.965,wspace=.13)
 fig.suptitle('Краснодар: время до центра и до контура города',x=.065,y=.965,ha='left',fontsize=21,fontweight='bold')
 fig.text(.065,.917,'Одна дорожная сеть · въезд в Краснодар · базовый автомобильный сценарий',fontsize=11,color='#667b7d')
 counts=stats['counts']
 for ax,features,dest,title in zip(axes,[point,corezones],['central_point','core_contour'],['До принятой центральной точки','До дорожного узла внутри контура НП']):
  configure(ax,bounds)
  for f in sorted(features,key=lambda f:f['properties']['minutes'],reverse=True):geometry(ax,shape(f['geometry']),fill=COLORS[f['properties']['minutes']],edge='#668f91',lw=.3,z=2)
  context(ax,ctx,core,centre);labels(ax,places,{'Краснодар','Динская','Горячий Ключ','Марьянская'});ax.set_title(title,fontsize=11,loc='left',pad=11,fontweight='bold')
  cc=[next(r for r in counts if r['destination']==dest and r['minutes']==t) for t in [30,60,90]]
  text='\n'.join(f"{r['minutes']} мин  ·  {fmt(r['settlementRecords'])} записей НП  ·  {fmt(r['population2021'])} чел." for r in cc)
  ax.text(0,-.18,text,transform=ax.transAxes,ha='left',va='top',fontsize=9,linespacing=1.65,color=INK)
 fig.legend(handles=[Patch(facecolor=COLORS[t],edgecolor='#668f91',label=f'до {t} минут') for t in [30,60,90]]+[Patch(facecolor='#e7e2d2',edgecolor=INK,label='Контур НП Краснодар')],loc='upper left',bbox_to_anchor=(.06,.89),frameon=False,ncol=4,fontsize=9)
 fig.text(.065,.063,'Источники: OSM / Geofabrik, дороги 29.10.2026; принятая база переписи 2021 года. Население включает Краснодар.',fontsize=8.1,color='#667b7d')
 fig.text(.065,.036,'Зоны обобщают достижимые дороги; автомобильная модель без измеренных пробок. Маска России: Terrae / OSM, 2026.10.',fontsize=8.1,color='#667b7d')
 comparison=output/'access-destinations.png';fig.savefig(comparison,dpi=220);plt.close(fig)
 base=shape(load(access/'candidate_60.geojson')['features'][0]['geometry']);slow=shape(load(access/'candidate_60_slow.geojson')['features'][0]['geometry']);bounds2=base.bounds;interval=stats['core60Range']
 fig,ax=plt.subplots(figsize=(12,9));fig.subplots_adjust(top=.79,bottom=.18,left=.075,right=.94)
 fig.suptitle('Часовой транспортный кандидат: проверка чувствительности',x=.075,y=.965,ha='left',fontsize=18,fontweight='bold')
 fig.text(.075,.918,'Время до контура НП Краснодар · направление поездки — в город',fontsize=11,color='#667b7d');configure(ax,bounds2)
 geometry(ax,base,fill='#e4c9a9',edge='#ad7543',lw=.8,z=2);geometry(ax,slow,fill='#80b2ac',edge='#317b78',lw=.75,z=2.5);context(ax,ctx,core,centre)
 labels(ax,places,{'Краснодар','Яблоновский','Динская','Горячий Ключ','Марьянская','Тимашевск','Усть-Лабинск','Северская'})
 fig.legend(handles=[Patch(facecolor='#e4c9a9',edgecolor='#ad7543',label=f"Базовое время: {fmt(interval['maxSettlements'])} записей НП"),Patch(facecolor='#80b2ac',edgecolor='#317b78',label=f"Время ×1,3: {fmt(interval['minSettlements'])} записей НП")],loc='upper left',bbox_to_anchor=(.07,.89),frameon=False,ncol=2,fontsize=10)
 fig.text(.075,.112,f"Население 2021 года: {fmt(interval['maxPopulation2021'])} → {fmt(interval['minPopulation2021'])} человек; Краснодар включён.",fontsize=10,fontweight='bold')
 fig.text(.075,.075,'Источники: OSM / Geofabrik, 29.10.2026; принятая переписная база 2021 года. Маска России: Terrae / OSM, 2026.10.',fontsize=8.2,color='#667b7d')
 fig.text(.075,.048,'×1,3 — заданный сценарий времени, не наблюдённая пробка и не доверительный интервал. Доля занятых, работающих в ядре, неизвестна.',fontsize=8.2,color='#667b7d')
 candidate=output/'candidate-sensitivity.png';fig.savefig(candidate,dpi=220);plt.close(fig)
 return [comparison.name,candidate.name]
