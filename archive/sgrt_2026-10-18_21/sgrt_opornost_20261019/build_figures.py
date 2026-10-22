"""Plot the documented service graph; no geometrical catchment polygons."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    ap.add_argument('--graph',type=Path,required=True)
    ap.add_argument('--axis',type=Path,required=True)
    a=ap.parse_args();r=a.root;out=r/'figures';out.mkdir(exist_ok=True)
    e=pd.read_csv(a.graph/'service_edges_calculated.csv');c=pd.read_csv(a.graph/'documented_functional_centers.csv')
    axis=pd.read_parquet(a.axis).set_index('id');print(json.dumps({'edge_columns':list(e.columns),'center_columns':list(c.columns)}))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    sources=['SV2025','TV2021','NV2026','BA_MED']
    names={'SV2025':'Нижнетуринский округ · акт 2025','TV2021':'Конаковский район · акт 2021','NV2026':'Невьянский округ · акт 2026','BA_MED':'Учалинский район\nДата страницы неизвестна'}
    fig,axs=plt.subplots(2,2,figsize=(16,12),layout='constrained')
    for ax,sid in zip(axs.flat,sources):
        d=e[e.source_id.eq(sid)].copy();seen=set();xy=[]
        for row in d.itertuples(index=False):
            ou=getattr(row,'origin_uid',None);du=getattr(row,'destination_uid',None)
            if ou not in axis.index or du not in axis.index:continue
            p=axis.loc[ou];q=axis.loc[du]
            eligible=np.isfinite(getattr(row,'distance_km',np.nan))
            if not eligible:continue
            ax.plot([p.lon,q.lon],[p.lat,q.lat],color='#3783aa',lw=1,alpha=.65,zorder=1)
            ax.scatter(p.lon,p.lat,s=14,color='#90a6b2',edgecolor='white',linewidth=.25,zorder=2)
            xy.extend([(p.lon,p.lat),(q.lon,q.lat)])
            if du not in seen:
                ax.scatter(q.lon,q.lat,s=90,marker='s',color='#125379',edgecolor='white',linewidth=.7,zorder=3)
                ax.annotate(str(q['name']),(q.lon,q.lat),xytext=(5,5),textcoords='offset points',fontsize=9,color='#15374b',zorder=4)
                seen.add(du)
        ax.set_title(names[sid],loc='left',fontweight='bold',fontsize=11,color='#15374b')
        ax.set_xlabel('Долгота, °');ax.set_ylabel('Широта, °');ax.grid(alpha=.15)
        if xy:
            ar=np.asarray(xy);span=np.ptp(ar,axis=0);pad=np.maximum(span*.15,[.015,.01]);ax.set_xlim(ar[:,0].min()-pad[0],ar[:,0].max()+pad[0]);ax.set_ylim(ar[:,1].min()-pad[1],ar[:,1].max()+pad[1]);ax.set_aspect(1/np.cos(np.deg2rad(ar[:,1].mean())))
        ax.text(.01,.01,'Линия — документированное обслуживание; не маршрут поездки',transform=ax.transAxes,fontsize=8,color='#526575')
    fig.suptitle('Опорные сервисные связи: внешнее окружение из первичных документов',fontsize=17,fontweight='bold',color='#15374b')
    fig.savefig(out/'01_documented_service_networks.png',dpi=200)
    fig.savefig(out/'01_documented_service_networks.svg')
    fig.savefig(out/'01_documented_service_networks.pdf')
    plt.close(fig)
    d=c.sort_values('external_census_population_2021')
    fig,ax=plt.subplots(figsize=(12,8))
    fig.subplots_adjust(left=.20,right=.94,bottom=.14,top=.9)
    y=np.arange(len(d));ax.barh(y,d.external_census_population_2021,color='#286f97',height=.65)
    ax.set_yticks(y,d.destination_name);ax.set_xlabel('Население перечисленных внешних НП по переписи 2021, человек')
    ax.set_title('Разный внешний охват документированных сервисных узлов',loc='left',fontsize=16,color='#15374b',fontweight='bold')
    ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    for yy,n in zip(y,d.external_census_population_2021):ax.annotate(str(int(n)),(n,yy),xytext=(4,0),textcoords='offset points',va='center',fontsize=9)
    fig.text(.01,.003,'Покрытие документов и связки частичное. Все жители НП ≠ число школьников, пациентов или пользователей. Даты актов различаются.',fontsize=8,color='#526575')
    for ext in ['png','svg','pdf']:fig.savefig(out/f'02_external_population.{ext}',dpi=200)
    plt.close(fig)
    files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.suffix in {'.png','.svg','.pdf'}}
    (out/'manifest.json').write_text(json.dumps({'graph':str(a.graph),'axis_sha256':hashlib.sha256(a.axis.read_bytes()).hexdigest(),'files':files},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
