"""National source-backed evidence maps; no catchment polygons or centre claims."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from pyproj import Transformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Polygon,Patch

R=Path(__file__).resolve().parent
B=R.parent
WORLD=B/'restored/extracted/inputs/recovery_inputs/enrichment/world.geojson'
PROFILE=R/'screening/support_point_profiles.parquet'
TRANS=Transformer.from_crs('EPSG:4326','+proj=laea +lat_0=65 +lon_0=100 +datum=WGS84 +units=m +no_defs',always_xy=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def project(lon,lat):
 x,y=TRANS.transform(np.asarray(lon),np.asarray(lat));return np.asarray(x)/1000,np.asarray(y)/1000
def main():
 out=R/'figures';out.mkdir(exist_ok=True)
 d=pd.read_parquet(PROFILE,columns=['id','name','lat','lon','population_2021','population_size_bin','baseline_function_diversity','legal_native_function_diversity','physical_baseline_function_diversity','wb_strict_function_diversity']);assert len(d)==142570 and d.id.is_unique
 audit=json.loads((R/'screening/SCREENING_AUDIT.json').read_text());assert audit['places_loaded'] and audit['pass']
 g=json.loads(WORLD.read_text());rus=[];others=[]
 for f in g['features']:
  p=f['properties'];isru=p.get('name')=='Russia' or p.get('ADMIN')=='Russia' or p.get('iso_a3')=='RUS'
  geo=f['geometry']; polys=geo['coordinates'] if geo['type']=='MultiPolygon' else [geo['coordinates']]
  for poly in polys:
   a=np.asarray(poly[0]);x,y=project(a[:,0],a[:,1]);v=np.column_stack([x,y]);(rus if isru else others).append(v)
 assert rus, 'Russia polygon missing'
 x,y=project(d.lon,d.lat);xy=np.column_stack([x,y]);np.save(out/'projected_coordinates.npy',xy)
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
 land=np.vstack(rus);xmin,ymin=np.nanmin(land,axis=0);xmax,ymax=np.nanmax(land,axis=0)
 def backdrop(ax):
  for v in others:ax.add_patch(Polygon(v,facecolor='#fafbfc',edgecolor='#d9dfe3',linewidth=.3,zorder=0))
  for v in rus:ax.add_patch(Polygon(v,facecolor='#f3f6f7',edgecolor='#9baab4',linewidth=.45,zorder=1))
  ax.set_aspect('equal');ax.set_xlim(xmin-90,xmax+90);ax.set_ylim(ymin-90,ymax+90);ax.axis('off')
 def base(title,sub):
  fig=plt.figure(figsize=(17,11));ax=fig.add_axes([.035,.34,.93,.54]);backdrop(ax)
  fig.text(.045,.955,title,fontsize=21,fontweight='bold',color='#163b54')
  fig.text(.045,.915,sub,fontsize=11,color='#435c6e')
  fig.text(.045,.055,'Ось: 142 570 НП; население — перепись 2021. RFSD 2025; WB 19.10.2026; Overture 23.09.2026.',fontsize=9,color='#435c6e')
  fig.text(.045,.035,'Показаны свидетельства источников, а не границы СГРТ, поездки или доказанная внешняя опорность. Проекция LAEA 65°N, 100°E.',fontsize=9,color='#435c6e')
  for name,lon,lat in [('Москва',37.6176,55.7558),('Санкт-Петербург',30.3351,59.9343)]:
   fx,fy=project(lon,lat);ax.scatter(fx,fy,s=45,marker='*',facecolor='white',edgecolor='#173d56',linewidth=.8,zorder=30);ax.annotate(name+'†',(fx,fy),xytext=(-5,8),textcoords='offset points',fontsize=7,color='#173d56',zorder=31)
  fig.text(.045,.076,'† Москва и Санкт-Петербург — отдельные территориальные агрегаты; в знаменатель 142 570 НП не входят.',fontsize=9,color='#435c6e')
  return fig,ax
 def inset(fig,rect,bounds,values,colors,labels=None):
  ax=fig.add_axes(rect);backdrop(ax);lo,hi,la,lb=bounds;mask=d.lon.between(lo,hi)&d.lat.between(la,lb)
  corners=np.array([[lo,la],[hi,la],[lo,lb],[hi,lb]]);xx,yy=project(corners[:,0],corners[:,1]);ax.set_xlim(xx.min(),xx.max());ax.set_ylim(yy.min(),yy.max())
  ax.set_facecolor('white');ax.axis('on');ax.set_xticks([]);ax.set_yticks([])
  for i,c in enumerate(colors):
   m=mask&(values==i);ax.scatter(x[m],y[m],s=3 if i else 1.3,c=c,edgecolors='none',zorder=2+i)
  for s in ax.spines.values():s.set_visible(True);s.set_color('#ccd6dd')
  return ax
 def save(fig,stem):
  for ext in ['png','svg','pdf']:fig.savefig(out/f'{stem}.{ext}',dpi=260,facecolor='white')
  plt.close(fig)
 vals=np.select([d.baseline_function_diversity==0,d.baseline_function_diversity==1,d.baseline_function_diversity.between(2,3),d.baseline_function_diversity.between(4,6)],[0,1,2,3],default=4)
 colors=['#d8dfe4','#82b6cf','#448db4','#1d628f','#103d63'];labels=['Нет принятого свидетельства','1 группа','2–3 группы','4–6 групп','7–11 групп']
 fig,ax=base('Наблюдаемые функции поселений','Объединение разных источников: одна функция учитывается один раз; категории источников сохранены отдельно.')
 for i,c in enumerate(colors):
  m=vals==i;ax.scatter(x[m],y[m],s=.55 if i==0 else 2.4+i*.35,c=c,edgecolors='none',zorder=i+2)
 for rect,box,label in [([.06,.10,.25,.22],(31,43,52,61),'Центральная Россия'),([.34,.10,.25,.22],(52,66,51,61),'Урал')]:
  ia=inset(fig,rect,box,vals,colors);ia.set_title(label,fontsize=10,loc='left')
 handles=[Patch(color=c,label=f'{lab}: {int((vals==i).sum()):,}'.replace(',',' '))for i,(c,lab)in enumerate(zip(colors,labels))]
 fig.legend(handles=handles,loc='lower right',bbox_to_anchor=(.965,.11),frameon=False,fontsize=10)
 save(fig,'01_function_profiles')
 legal=d.legal_native_function_diversity.gt(0);physical=d.physical_baseline_function_diversity.gt(0)|d.wb_strict_function_diversity.gt(0)
 cat=np.select([legal&physical,~legal&physical,legal&~physical],[3,2,1],default=0)
 cols=['#d8dfe4','#d8a756','#4191ba','#155176'];labs=['Нет принятых свидетельств','Только юридические записи','Только объекты / WB','Есть оба вида свидетельств']
 fig,ax=base('Разные источники видят разные части сети','Наличие юридической записи и опубликованного объекта сопоставлено по UID; их расхождение не означает ошибку или закрытие.')
 for i,c in enumerate(cols):
  m=cat==i;ax.scatter(x[m],y[m],s=.55 if i==0 else 3,c=c,edgecolors='none',zorder=i+2)
 for rect,box,label in [([.06,.10,.25,.22],(31,43,52,61),'Центральная Россия'),([.34,.10,.25,.22],(120,138,42,57),'Юг Дальнего Востока')]:
  ia=inset(fig,rect,box,cat,cols);ia.set_title(label,fontsize=10,loc='left')
 fig.legend(handles=[Patch(color=c,label=f'{lab}: {int((cat==i).sum()):,}'.replace(',',' ')) for i,(c,lab)in enumerate(zip(cols,labs))],loc='lower right',bbox_to_anchor=(.965,.11),frameon=False,fontsize=10)
 save(fig,'02_source_agreement')
 # Present missing evidence using settlement-size strata; never call absence of source absence of a service.
 sizes=['zero','1_99','100_499','500_999','1000_2999','3000_9999','10000_49999','50000_99999','100000_plus','unknown'];titles=['0','1–99','100–499','500–999','1–2,9 тыс.','3–9,9 тыс.','10–49,9 тыс.','50–99,9 тыс.','100 тыс.+','Неизвестно']
 rows=[]
 for s,title in zip(sizes,titles):
  m=d.population_size_bin.eq(s);n=int(m.sum());rows.append({'size_bin':s,'label':title,'settlements':n,'positive_evidence':int((m&(vals>0)).sum()),'no_accepted_evidence':int((m&(vals==0)).sum()),'legal':int((m&legal).sum()),'physical_or_wb':int((m&physical).sum())})
 st=pd.DataFrame(rows);st.to_csv(out/'size_coverage.csv',index=False);st=st[st.settlements>0]
 fig,axs=plt.subplots(1,2,figsize=(17,9),gridspec_kw={'width_ratios':[1.1,1]});fig.subplots_adjust(left=.09,right=.97,bottom=.16,top=.83,wspace=.32)
 yy=np.arange(len(st));share=st.positive_evidence/st.settlements*100
 axs[0].barh(yy,100,color='#e0e6ea');axs[0].barh(yy,share,color='#2c7ca6');axs[0].set_yticks(yy,st.label);axs[0].invert_yaxis();axs[0].set_xlim(0,108);axs[0].set_xlabel('Доля НП с принятым свидетельством, %');axs[0].set_title('Покрытие зависит от размера поселения',loc='left',fontweight='bold')
 for j,(v,n)in enumerate(zip(share,st.settlements)):axs[0].text(min(v+1.5,100.5),j,f'{v:.1f}%',va='center',fontsize=9)
 counts=pd.Series({'Только юридические':int((cat==1).sum()),'Только объекты / WB':int((cat==2).sum()),'Оба вида':int((cat==3).sum()),'Нет принятого свидетельства':int((cat==0).sum())})
 axs[1].barh(np.arange(4),counts.to_numpy(),color=[cols[1],cols[2],cols[3],cols[0]]);axs[1].set_yticks(np.arange(4),counts.index);axs[1].invert_yaxis();axs[1].set_xlabel('Число поселений');axs[1].set_title('Связки дополнены, исходные НП сохранены',loc='left',fontweight='bold');axs[1].ticklabel_format(axis='x',style='plain')
 for j,v in enumerate(counts):axs[1].text(v+1000,j,f'{v:,}'.replace(',',' '),va='center',fontsize=9)
 axs[1].set_xlim(0,max(counts)*1.19)
 for ax in axs:ax.grid(axis='x',alpha=.13);ax.set_axisbelow(True)
 fig.text(.055,.94,'Где данные ещё не дают ответа',fontsize=22,color='#163b54',fontweight='bold');fig.text(.055,.895,'Нет принятого свидетельства ≠ нет услуги. Пробелы сохранены и доступны для следующего массового уточнения.',fontsize=12,color='#435c6e')
 fig.text(.055,.06,'Общий знаменатель: 142 570 НП. Положительное свидетельство: RFSD 2025, физический POI или WB по основной связке.',fontsize=10,color='#435c6e')
 save(fig,'03_evidence_gaps')
 (out/'source_agreement.csv').write_text(pd.DataFrame({'category':labs,'settlements':[int((cat==i).sum())for i in range(4)]}).to_csv(index=False))
 manifest={'profile_sha256':sha(PROFILE),'world_sha256':sha(WORLD),'projection':'LAEA lat0=65 lon0=100 WGS84 km','scope':'reference142570; no catchment or political boundary claim','actual_command':'python national_integration_20261019/build_figures.py','files':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)}for p in sorted(out.iterdir())if p.suffix in {'.png','.svg','.pdf','.csv'}}}
 (out/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':'PASS','figures':3,'national_maps':2,'diagnostic_charts':1,'formats':3,'rows':len(d),'inputs':manifest['profile_sha256']}))
if __name__=='__main__':main()
