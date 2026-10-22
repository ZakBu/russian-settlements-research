"""Current provider-published pickup locations; never an SGRT boundary map."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from pyproj import Transformer


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    ap.add_argument('--world',type=Path,required=True)
    a=ap.parse_args(); r=a.root; out=r/'figures';out.mkdir(exist_ok=True)
    source=r/'marketplaces/wb_delivery_locations_ru_20261019.parquet'
    d=pd.read_parquet(source)
    world=json.loads(a.world.read_text())['features']
    tr=Transformer.from_crs('EPSG:4326','+proj=aea +lat_1=50 +lat_2=70 +lat_0=56 +lon_0=100 +datum=WGS84 +units=m +no_defs',always_xy=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig=plt.figure(figsize=(20,13),facecolor='white')
    main=fig.add_axes([.025,.35,.95,.52])
    bg='#f2f5f7'; ink='#163e59';blue='#176493'
    def poly_parts(f):
        g=f['geometry'];return [g['coordinates']] if g['type']=='Polygon' else g['coordinates'] if g['type']=='MultiPolygon' else []
    def draw(ax,project=False,bbox=None):
        ax.set_facecolor('#edf4f8')
        for f in world:
            if f['properties']['CONTINENT'] not in ['Europe','Asia']:continue
            for poly in poly_parts(f):
                ring=np.asarray(poly[0]);lo,la=ring[:,0],ring[:,1]
                if project:
                    x,y=tr.transform(lo,la);xy=np.c_[x,y]
                else:xy=ring
                if np.isfinite(xy).all():ax.add_patch(Polygon(xy,facecolor=bg,edgecolor='#b4c4ce',lw=.4,zorder=0))
        if project:
            x,y=tr.transform(d.longitude.to_numpy(),d.latitude.to_numpy())
            ax.scatter(x,y,s=1.5,alpha=.55,color=blue,linewidths=0,rasterized=True,zorder=3)
            pts=[]
            for f in world:
                if f['properties']['ADM0_A3']=='RUS':
                    for poly in poly_parts(f):
                        q=np.asarray(poly[0]);xx,yy=tr.transform(q[:,0],q[:,1]);pts.extend(zip(xx,yy))
            p=np.asarray(pts);pad=np.ptp(p,axis=0)*.03
            ax.set_xlim(p[:,0].min()-pad[0],p[:,0].max()+pad[0]);ax.set_ylim(p[:,1].min()-pad[1],p[:,1].max()+pad[1]);ax.set_aspect('equal');ax.set_axis_off()
        else:
            ax.scatter(d.longitude,d.latitude,s=2.2,alpha=.5,color=blue,linewidths=0,rasterized=True,zorder=3)
            ax.set_xlim(bbox[0],bbox[1]);ax.set_ylim(bbox[2],bbox[3]);ax.set_aspect(1/np.cos(np.deg2rad((bbox[2]+bbox[3])/2)))
            ax.grid(alpha=.2,lw=.4);ax.tick_params(labelsize=8);ax.xaxis.set_major_locator(MaxNLocator(5));ax.yaxis.set_major_locator(MaxNLocator(5));ax.set_xlabel('Долгота, °',fontsize=8);ax.set_ylabel('Широта, °',fontsize=8)
    draw(main,True)
    for pos,title,bbox in [([.035,.09,.28,.24],'Европейская часть',(26,52,48,62)),([.355,.09,.28,.24],'Урал и юг Сибири',(52,105,49,62)),([.675,.09,.28,.24],'Юг Дальнего Востока',(125,145,42,57))]:
        ax=fig.add_axes(pos);draw(ax,bbox=bbox);ax.set_title(title,loc='left',fontweight='bold',fontsize=12,color=ink,pad=8)
    fig.text(.035,.965,'Опубликованные места доставки Wildberries',fontsize=23,fontweight='bold',color=ink)
    fig.text(.035,.931,'Снимок 19 октября 2026 · физические местоположения, а не районы тяготения',fontsize=14,color='#536b7b')
    fig.text(.035,.906,f'{len(d):,} записей всех типов в источниковом разделе ru; подтипы сохранены отдельно'.replace(',',' '),fontsize=12,color=ink)
    fig.text(.035,.045,'Точка — опубликованное место доставки, включая подтипы с неустановленной публичностью. Не все точки доказаны как общедоступные ПВЗ.',fontsize=10,color='#405b6b')
    fig.text(.035,.025,'Источник: публичный CDN Wildberries. Раздел ru включает Баренцбург на Шпицбергене; исходная запись сохранена. Подложка: Natural Earth.',fontsize=9,color='#536b7b')
    fig.text(.035,.009,'Полнота сети и актуальная работа каждого объекта не подтверждены независимым обходом. Привязка к НП для нанесения этих точек не используется.',fontsize=9,color='#536b7b')
    for ext in ['png','svg','pdf']:fig.savefig(out/f'01_wb_published_network_20261019.{ext}',dpi=300)
    plt.close(fig)
    audit={'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'world_sha256':hashlib.sha256(a.world.read_bytes()).hexdigest(),'plotted_rows':len(d),'source_ru_is_not_legal_RF_boundary':True,'barentsburg_source_id':50080949,'geocoded_axis_used_for_plot':False,'catchment_polygons':0,'projection':'Albers 50/70 N, central meridian 100 E','files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.glob('01_wb_published_network_20261019.*')}}
    (out/'national_map_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'rows':len(d),'files':list(audit['files'])}))


if __name__=='__main__':main()
