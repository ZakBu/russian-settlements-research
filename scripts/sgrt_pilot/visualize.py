#!/usr/bin/env python3
"""Export geographic maps of dated, incomplete functional pilot scenarios.

Coordinates use a spherical Lambert azimuthal equal-area projection centred on
regional settlement points. No invented polygon boundaries or travel-time
contours are drawn. Colours describe known objects and conditional scenarios,
not observed flows or demonstrated SGRT membership.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

REGION_NAMES={"удмуртская":"Удмуртия","ленинградская":"Ленинградская область","челябинская":"Челябинская область","вологодская":"Вологодская область"}
BLUE="#27648C"; GOLD="#CF9A30"; ORANGE="#CC7040"; GREY="#B8BDC3"; INK="#273441"
PALETTE=[BLUE,GOLD,ORANGE,"#6C816A","#AA6C91"]


def project(lon,lat,lon0,lat0):
    """Spherical LAEA, kilometres, true geographic inputs in degrees."""
    lam,phi,lam0,phi0=map(np.deg2rad,[np.asarray(lon,dtype=float),np.asarray(lat,dtype=float),lon0,lat0])
    cosine=np.sin(phi0)*np.sin(phi)+np.cos(phi0)*np.cos(phi)*np.cos(lam-lam0)
    denominator=1+cosine
    k=np.sqrt(2/np.where(denominator>0,denominator,np.nan))
    return 6371.0088*k*np.cos(phi)*np.sin(lam-lam0),6371.0088*k*(np.cos(phi0)*np.sin(phi)-np.sin(phi0)*np.cos(phi)*np.cos(lam-lam0))


def read(path):
    return pd.read_parquet(path) if path.suffix==".parquet" else pd.read_csv(path)


def reference(df):
    d=df.copy()
    if "model" in d:d=d[d.model.eq("functional")]
    if "decay_family" in d:d=d[d.decay_family.eq("exponential")]
    if "half_life_minutes" in d:d=d[np.isclose(d.half_life_minutes,30)]
    if "kernel_floor" in d:d=d[np.isclose(d.kernel_floor,.05)]
    return d


def decorate(ax,title):
    ax.set_title(title,loc="left",fontsize=11,pad=11)
    ax.set_aspect("equal",adjustable="box")
    ax.set_xlabel("км к востоку от центра проекции",fontsize=8)
    ax.set_ylabel("км к северу от центра проекции",fontsize=8)
    ax.tick_params(labelsize=8)
    ax.grid(True,color="#E4E7EA",linewidth=.5)
    ax.spines[["top","right"]].set_visible(False)


def draw_region(s,outcomes,links,outdir,region,function,service_order,source_label,all_settlements=None):
    s=s.copy();lon0=float(s.lon.median());lat0=float(s.lat.median())
    s["x"],s["y"]=project(s.lon,s.lat,lon0,lat0)
    sourcekey="source_record_id"
    d=outcomes[(outcomes.function==function)&(outcomes.service_order==service_order)&outcomes[sourcekey].isin(s[sourcekey])].copy()
    if d.empty:return None
    r=reference(d)
    if r.empty:return None
    # Multiple dated source scenarios must be drawn separately by caller.
    if r.duplicated(sourcekey).any():raise ValueError("Reference map contains multiple outcomes per accepted origin")
    r=r.merge(s[[sourcekey,"x","y"]],on=sourcekey,how="left",validate="one_to_one")
    sizes=np.clip(3+np.log1p(s.population.fillna(0))*1.5,3,27)
    fig,axes=plt.subplots(2,2,figsize=(13,12))
    for ax in axes.flat:ax.scatter(s.x,s.y,s=sizes,c="#E0E3E7",linewidths=0,zorder=1,rasterized=True)
    ax=axes[0,0]
    known=r.local_supply_status.isin(["present","observed","proxy","mapped_present"]) if "local_supply_status" in r else r.primary_is_local.fillna(False)
    ax.scatter(r.loc[known,"x"],r.loc[known,"y"],s=19,c=BLUE,marker="s",linewidths=.3,edgecolors="white",zorder=2)
    ax.legend(handles=[Line2D([],[],marker="s",linestyle="",color=BLUE,label="Учтён объект; мощность неизвестна"),Line2D([],[],marker="o",linestyle="",color="#C1C6CD",label="Наличие функции неизвестно")],loc="best",fontsize=8,frameon=True)
    decorate(ax,"А. Известное предложение и пропуски")
    # Label the three largest settlements using names from the accepted base.
    for label_i,(_,row) in enumerate(s.nlargest(3,"population").iterrows()):
        ax.annotate(str(row.get("name",row[sourcekey])),(row.x,row.y),xytext=(5,5+label_i*9),textcoords="offset points",fontsize=8,color=INK)
    ax=axes[0,1]
    has=r.primary_candidate_id.notna()&r.primary_cost_minutes.notna()
    scale_max=max(60,float(r.loc[has,"primary_cost_minutes"].quantile(.95))) if has.any() else 60
    points=ax.scatter(r.loc[has,"x"],r.loc[has,"y"],c=r.loc[has,"primary_cost_minutes"],s=12,cmap="cividis",vmin=0,vmax=scale_max,linewidths=0,zorder=2,rasterized=True)
    fig.colorbar(points,ax=ax,shrink=.75,label="минуты: выбранный условный кандидат",extend="max" if has.any() and r.loc[has,"primary_cost_minutes"].max()>scale_max else "neither")
    if (~has).any():ax.scatter(r.loc[~has,"x"],r.loc[~has,"y"],s=13,c=GREY,marker="x",zorder=3)
    decorate(ax,"Б. Автомобильные затраты до кандидата")
    ax=axes[1,0]
    choices=r.primary_candidate_id.value_counts()
    top=choices.head(5).index.tolist()
    mapping={str(v):PALETTE[i] for i,v in enumerate(top)}
    for dest,count in choices.items():
        subset=r[r.primary_candidate_id.eq(dest)]
        ax.scatter(subset.x,subset.y,s=12,c=mapping.get(str(dest),GREY),linewidths=0,zorder=2,rasterized=True)
    pool=s if all_settlements is None else all_settlements
    candidate_points=pool[pool[sourcekey].isin(top)].copy()
    candidate_points["x"],candidate_points["y"]=project(candidate_points.lon,candidate_points.lat,lon0,lat0)
    ax.scatter(candidate_points.x,candidate_points.y,c=[mapping[str(v)] for v in candidate_points[sourcekey]],marker="*",s=100,edgecolors=INK,linewidths=.4,zorder=3)
    for _,row in candidate_points.iterrows():ax.annotate(str(row.get("name",row[sourcekey]))+(" (внешний)" if row.get("region",region)!=region else ""),(row.x,row.y),xytext=(4,4),textcoords="offset points",fontsize=8)
    decorate(ax,"В. Условные зоны: цвет по главному кандидату")
    ax.text(.01,.01,"Пять крупнейших зон — цветом; прочие — серым.\nТочки НП, сплошные границы не реконструированы.",transform=ax.transAxes,fontsize=8,va="bottom",bbox=dict(facecolor="white",alpha=.9,edgecolor="none"))
    ax=axes[1,1]
    functional=d[d.model.eq("functional")] if "model" in d else d
    def choice_count(values):return values.fillna("__NO_CANDIDATE__").nunique()
    switches=functional.groupby(sourcekey).primary_candidate_id.agg(choice_count)
    stability=r[sourcekey].map(switches).fillna(0)
    stable=stability.eq(1);variable=stability.gt(1)
    ax.scatter(r.loc[stable,"x"],r.loc[stable,"y"],s=12,c=BLUE,linewidths=0,zorder=2,rasterized=True)
    ax.scatter(r.loc[variable,"x"],r.loc[variable,"y"],s=17,c=ORANGE,marker="^",linewidths=0,zorder=3,rasterized=True)
    ax.legend(handles=[Line2D([],[],marker="o",linestyle="",color=BLUE,label=f"Одинаковый кандидат: {int(stable.sum())} НП"),Line2D([],[],marker="^",linestyle="",color=ORANGE,label=f"Изменение / отсев: {int(variable.sum())} НП")],loc="best",fontsize=8)
    variants=functional[["decay_family","half_life_minutes","kernel_floor"]].drop_duplicates() if set(["decay_family","half_life_minutes","kernel_floor"]).issubset(functional) else pd.DataFrame()
    if len(variants)<=1:
        ax.clear();ax.scatter(s.x,s.y,s=8,c=GREY,linewidths=0,rasterized=True)
        decorate(ax,"Г. Чувствительность здесь не рассчитана")
        ax.text(.5,.5,"Для этой территории сохранён только\nопорный вариант параметров.\nОдинаковость одного варианта\nне означает устойчивости.",transform=ax.transAxes,ha="center",va="center",fontsize=10,color=INK,bbox=dict(facecolor="white",alpha=.94,edgecolor="none"))
    else:decorate(ax,"Г. Чувствительность к затуханию и отсечению")
    rname=REGION_NAMES.get(region,region)
    function_label={"healthcare":"медицина","education":"образование","commerce":"торговля"}.get(function,function)
    order_label={"broad_recorded_function_not_service_order":"все отмеченные объекты без разделения порядка услуг","school":"школы","primary_fap":"ФАП и фельдшерские пункты"}.get(service_order,service_order)
    fig.suptitle(f"{rname}: {function_label}\n{order_label}; сценарий по неполным данным, не наблюдённые поездки",fontsize=14,color=INK,y=.98)
    transform=str(r.supply_transform.iloc[0]) if "supply_transform" in r else "as_provided"
    weight_note="Все известные центры имеют равный вес: порядок кандидатов определяется близостью." if transform=="binary" else "Вес — число отмеченных объектов, а не измеренная мощность обслуживания."
    fig.text(.07,.018,f"Источник предложения: {source_label}. Население и дорога: 2021.\nОпорный сценарий: экспонента, полураспад 30 мин, отсечение веса 0,05; параметры не калиброваны.\nПроекция: азимутальная Ламберта, центр {lon0:.3f}° в.д., {lat0:.3f}° с.ш.; сфера R=6371,009 км.\nНеотмеченные объекты — неизвестное состояние. Цвет зоны означает выбор среди известных кандидатов.\n{weight_note} Стабильность сценария не доказывает реальную связь.\nНулевые затраты внутри одного НП — приближение; существование и мощность объекта не проверены по поездкам.",fontsize=8,color=INK)
    fig.subplots_adjust(left=.07,right=.94,bottom=.13,top=.90,hspace=.27,wspace=.28)
    extra="_".join(str(r[c].iloc[0]) for c in ["source_scenario","supply_transform"] if c in r)
    safe="_".join(str(v).replace("/","-").replace(" ","_") for v in [region,function,service_order,extra])
    png=outdir/(safe+".png");pdf=outdir/(safe+".pdf")
    fig.savefig(png,dpi=170,facecolor="white");fig.savefig(pdf,facecolor="white");plt.close(fig)
    return {"region":region,"function":function,"service_order":service_order,"source_scenario":str(r.source_scenario.iloc[0]) if "source_scenario" in r else None,"supply_transform":transform,"settlements":len(r),"known_local_supply":int(known.sum()),"reference_candidate":int(has.sum()),"varying_choice":int(variable.sum()) if len(variants)>1 else None,"tested_parameter_variants":len(variants),"projection_center_lon":lon0,"projection_center_lat":lat0,"png":png.name,"pdf":pdf.name}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--settlements",required=True,type=Path)
    p.add_argument("--outcomes",type=Path)
    p.add_argument("--context-settlements",type=Path,help="Explicit external nonadditive context centres")
    p.add_argument("--links",type=Path)
    p.add_argument("--types",type=Path,help="Descriptive fixed-zone typology")
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--source-label",default="OSM, снимок 2021; неполное наличие объектов")
    p.add_argument("--attachments",type=Path,help="Separate normative attachment map")
    p.add_argument("--quarantine",type=Path,help="Documented context contradictions excluded from normative map")
    p.add_argument("--supply",type=Path,help="OSM supply table for selected official-plan comparison")
    p.add_argument("--official",type=Path,help="Selected official Udmurt planning list; not full network")
    p.add_argument("--functions",default="healthcare",help="Comma-separated functions to map")
    p.add_argument("--orders",default="",help="Comma-separated service orders; empty=all")
    a=p.parse_args();s=read(a.settlements);d=read(a.outcomes) if a.outcomes else pd.DataFrame();links=read(a.links) if a.links else pd.DataFrame();types=read(a.types) if a.types else None
    if a.context_settlements:
        context=read(a.context_settlements).copy()
        if "source_record_id" not in context:context["source_record_id"]=context.center_id
        else:context["source_record_id"]=context.source_record_id.fillna(context.center_id)
        s=pd.concat([s,context],ignore_index=True).drop_duplicates("source_record_id",keep="first")
    for source,target in [("longitude","lon"),("latitude","lat"),("settlement_name","name"),("region_norm","region")]:
        if target not in s and source in s:s[target]=s[source]
    if not d.empty and "observation_year" in d and d.observation_year.nunique(dropna=False)>1:
        p.error("Process each observation year in a separate dated case")
    a.out.mkdir(parents=True,exist_ok=True);manifest=[]
    for region in sorted(s.region.dropna().unique()):
        region_s=s[s.region.eq(region)&s.lon.notna()&s.lat.notna()]
        if d.empty:continue
        subset=d[d.source_record_id.isin(region_s.source_record_id)&d.function.isin(a.functions.split(","))]
        if a.orders:subset=subset[subset.service_order.isin(a.orders.split(","))]
        groups=[c for c in ["source_scenario","supply_transform","function","service_order"] if c in subset]
        for key,g in subset.groupby(groups,dropna=False,sort=True):
            source_label=a.source_label
            if "source_scenario" in g and str(g.source_scenario.iloc[0]).startswith("official_"):
                source_label="План подключения ФАП/ФП: каталог 2025, план 2026; работа объектов не подтверждена"
            if "observation_year" in g:
                year=g.observation_year.iloc[0]
                source_label+=f"; год наблюдения {int(year)}" if pd.notna(year) else ""
            if "source_scenario" in g:
                scenario_name={"spatial_proxy":"пространственная привязка объектов","strict_address":"строгая адресная привязка","official_selected_planning_list_2025":"выборочный план подключения ФАП"}.get(str(g.source_scenario.iloc[0]),str(g.source_scenario.iloc[0]))
                if not str(g.source_scenario.iloc[0]).startswith("official_"):source_label+=f"; {scenario_name}"
            result=draw_region(region_s,g,links,a.out,region,g.function.iloc[0],g.service_order.iloc[0],source_label,all_settlements=s)
            if result:manifest.append(result)
            if types is not None:draw_type_map(region_s,g,types,a.out,region,g.function.iloc[0],g.service_order.iloc[0])
    (a.out/"maps_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    if a.attachments:draw_normative_attachments(s,read(a.attachments),a.out,read(a.quarantine) if a.quarantine else None)
    if a.official:
        if not a.supply:p.error("--official requires --supply")
        draw_official_presence(s,read(a.supply),read(a.official),a.out)
    print(json.dumps({"map_pages":len(manifest),"output":str(a.out)},ensure_ascii=False))



def draw_normative_attachments(settlements, attachments, outdir, quarantine=None):
    """Map published normative links, retaining only resolved full-NP scopes.

    These are relations between representative settlement points, not road paths,
    patient flows, capacity estimates, or reconstructed provider addresses.
    """
    s=settlements.copy().set_index("source_record_id",drop=False)
    doc=attachments.copy()
    partial=doc.origin_is_partial_address_scope.fillna(True)
    eligible=doc[doc.origin_id.notna()&doc.destination_id.notna()&~partial].copy()
    quarantined_rows=0
    if quarantine is not None:
        invalid={(str(row.sheet).strip(),int(row.excel_row_1based)) for row in quarantine.itertuples(index=False)}
        bad=eligible.apply(lambda row:(str(row["sheet"]).strip(),int(row["excel_row_1based"])) in invalid,axis=1)
        quarantined_rows=int(bad.sum());eligible=eligible.loc[~bad].copy()
    eligible=eligible[eligible.origin_id.isin(s.index)&eligible.destination_id.isin(s.index)]
    relations=eligible[["origin_id","destination_id"]].drop_duplicates()
    external=relations[relations.origin_id.ne(relations.destination_id)]
    ids=set(relations.origin_id)|set(relations.destination_id)
    points=s[s.index.isin(ids)].copy()
    if points.empty:return None
    lon0=float(points.lon.median());lat0=float(points.lat.median())
    points["x"],points["y"]=project(points.lon,points.lat,lon0,lat0)
    # Background is the full accepted frame of this region, not only matched rows.
    background=s[s.region.eq("ленинградская")].copy()
    background["x"],background["y"]=project(background.lon,background.lat,lon0,lat0)
    fig,axes=plt.subplots(1,2,figsize=(14,8))
    ax=axes[0]
    ax.scatter(background.x,background.y,s=5,c="#DDE1E5",linewidths=0,rasterized=True)
    seg=[]
    for row in external.itertuples(index=False):
        origin=points.loc[row.origin_id];dest=points.loc[row.destination_id]
        seg.append([[origin.x,origin.y],[dest.x,dest.y]])
    ax.add_collection(LineCollection(seg,colors=BLUE,linewidths=.5,alpha=.45,zorder=2,rasterized=True))
    destinations=points.loc[points.index.intersection(external.destination_id)]
    ax.scatter(destinations.x,destinations.y,s=45,marker="*",c=GOLD,edgecolors=INK,linewidths=.3,zorder=4)
    ax.scatter(points.x,points.y,s=6,c=BLUE,linewidths=0,zorder=3,rasterized=True)
    decorate(ax,f"А. {len(external):,} внешних нормативных связей".replace(","," "))
    ax.legend(handles=[Line2D([],[],color=BLUE,linewidth=1,label="Опубликованное прикрепление"),Line2D([],[],marker="*",linestyle="",color=GOLD,label="НП размещения указанного подразделения"),Line2D([],[],marker="o",linestyle="",color="#BCC3CA",label="Все НП принятой базы региона")],fontsize=8,loc="best")
    ax=axes[1]
    ax.scatter(background.x,background.y,s=5,c="#DDE1E5",linewidths=0,rasterized=True)
    choices=external.groupby("destination_id").origin_id.nunique().sort_values(ascending=False)
    top=choices.head(5).index.tolist()
    membership=relations.groupby("origin_id").destination_id.agg(list)
    multi_ids=membership[membership.map(len).gt(1)].index
    for i,dest_id in enumerate(top):
        subset=points[points.index.isin(relations.loc[relations.destination_id.eq(dest_id),"origin_id"])]
        ax.scatter(subset.x,subset.y,s=16,c=PALETTE[i],linewidths=0,zorder=2,rasterized=True)
        dest=points.loc[dest_id]
        ax.scatter([dest.x],[dest.y],c=PALETTE[i],s=100,marker="*",edgecolors=INK,linewidths=.5,zorder=4)
        ax.annotate(str(dest.get("name",dest_id)),(dest.x,dest.y),xytext=(4,4),textcoords="offset points",fontsize=8)
    multiple=points[points.index.isin(multi_ids)]
    ax.scatter(multiple.x,multiple.y,s=25,marker="o",facecolors="none",edgecolors=INK,linewidths=.6,zorder=5)
    decorate(ax,"Б. Пять крупных наборов прикреплений")
    ax.text(.01,.01,f"Разрешённых НП с несколькими подразделениями: {len(multiple)}.\nНаборы могут пересекаться; это не исключающие районы.",transform=ax.transAxes,fontsize=8,va="bottom",bbox=dict(facecolor="white",alpha=.92,edgecolor="none"))
    fig.suptitle("Ленинградская область: обслуживание по документу от 29.11.2023\nНормативные прикрепления из документа, а не наблюдённые поездки пациентов",fontsize=15,color=INK,y=.97)
    fig.text(.06,.04,f"Источник: приложение к документу от 29.11.2023, lofoms.spb.ru; {len(doc)} исходных строк,\n{len(eligible)} строк с разрешёнными обоими концами и без частичного адресного охвата; {len(relations)} уникальных пар.\nЛинии соединяют представительские точки НП 2021 года: геометрия маршрутов не восстановлена.\nПроекция Ламберта, центр {lon0:.3f}° в.д., {lat0:.3f}° с.ш. Неразрешённые записи не считаются отсутствием обслуживания.\nИсключено контекстных противоречий привязки: {quarantined_rows}; исходные записи сохранены.",fontsize=8,color=INK)
    fig.subplots_adjust(left=.06,right=.97,bottom=.17,top=.85,wspace=.22)
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    for ext in ("png","pdf"):fig.savefig(outdir/("leningrad_normative_medical_attachments_2024."+ext),dpi=180,facecolor="white")
    plt.close(fig)
    result={"source_rows":len(doc),"context_quarantined_rows":quarantined_rows,"eligible_rows":len(eligible),"unique_pairs":len(relations),"unique_external_pairs":len(external),"external_origin_settlements":external.origin_id.nunique(),"external_destination_settlements":external.destination_id.nunique(),"origins_multiple_documented_sites":len(multiple),"projection_center_lon":lon0,"projection_center_lat":lat0}
    (outdir/"normative_map_summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    return result



def draw_official_presence(settlements, supply, official, outdir):
    """Compare selected 2025 plan entries with two separate OSM2021 proxies."""
    s=settlements[settlements.region.eq("удмуртская")].copy()
    lon0=float(s.lon.median());lat0=float(s.lat.median())
    s["x"],s["y"]=project(s.lon,s.lat,lon0,lat0)
    official_ids=set(official.source_record_id.dropna())
    official_ids &= set(s.source_record_id)
    fig,axes=plt.subplots(1,2,figsize=(13,8));summary=[]
    for ax,scenario,label in zip(axes,["strict_address","spatial_proxy"],["А. Только строгая адресная привязка OSM","Б. Пространственное приближение OSM"]):
        osm_ids=set(supply.loc[supply.function.eq("healthcare")&supply.scenario.eq(scenario),"source_record_id"])
        both=official_ids & osm_ids
        only_official=official_ids-osm_ids
        ax.scatter(s.x,s.y,s=6,c="#DDE1E5",linewidths=0,zorder=1,rasterized=True)
        for ids,col,marker in [(only_official,ORANGE,"s"),(osm_ids-official_ids,BLUE,"o"),(both,GOLD,"*")]:
            q=s[s.source_record_id.isin(ids)];ax.scatter(q.x,q.y,s=18 if marker!="*" else 55,c=col,marker=marker,linewidths=0,zorder=2,rasterized=True)
        decorate(ax,label)
        for label_i,(_,row) in enumerate(s.nlargest(3,"population").iterrows()):
            ax.annotate(str(row.get("name",row.source_record_id)),(row.x,row.y),xytext=(4,4+label_i*6),textcoords="offset points",fontsize=8,color=INK)
        ax.legend(handles=[Line2D([],[],marker="s",linestyle="",color=ORANGE,label=f"Есть в плане, не найдено в OSM: {len(only_official)}"),Line2D([],[],marker="*",linestyle="",color=GOLD,label=f"В плане и OSM: {len(both)}"),Line2D([],[],marker="o",linestyle="",color=BLUE,label="Другие НП с медициной в OSM"),Line2D([],[],marker="o",linestyle="",color="#BCC3CA",label="Остальные НП: состояние неизвестно")],loc="best",fontsize=8)
        summary.append({"osm_scenario":scenario,"settlements":len(s),"selected_plan_settlements":len(official_ids),"overlap_with_osm":len(both),"plan_without_osm":len(only_official),"scope":"dated_selected_plan_not_full_operating_registry"})
    fig.suptitle("Удмуртия: известные медицинские объекты и пропуски источников\nВыборочный план подключения ФАП к интернету и OSM — разные по дате и охвату источники",fontsize=14,color=INK,y=.97)
    fig.text(.07,.035,f"План: каталог 2025 года, подключение в 2026 году; {len(official_ids)} НП с принятыми представительскими точками.\nОн не доказывает работу ФАП, мощность или полноту медицинской сети. OSM: снимок 2021, любые отмеченные медицинские объекты.\nОтсутствие совпадения может отражать пропуск, разное содержание или разные годы; это не оценка ошибки OSM.\nПроекция Ламберта, центр {lon0:.3f}° в.д., {lat0:.3f}° с.ш.; населённые пункты по принятой базе 2021 года.",fontsize=8,color=INK)
    fig.subplots_adjust(left=.07,right=.97,bottom=.16,top=.85,wspace=.25)
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    for ext in ("png","pdf"):fig.savefig(outdir/("udmurt_selected_fap_plan_vs_osm."+ext),dpi=180,facecolor="white")
    plt.close(fig)
    (outdir/"official_presence_map_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    return summary



def draw_type_map(settlements,outcomes,types,outdir,region,function,service_order):
    reference_outcomes=reference(outcomes)
    if reference_outcomes.empty:return None
    fields=[c for c in ["source_scenario","supply_transform","model","decay_family","half_life_minutes","kernel_floor"] if c in reference_outcomes]
    scenario="|".join(str(reference_outcomes[c].iloc[0]) for c in fields)
    t=types[types.scenario.eq(scenario)&types.function.eq(function)&types.service_order.eq(service_order)]
    r=reference_outcomes.merge(t,left_on="primary_candidate_id",right_on="center_id",how="left",validate="many_to_one",suffixes=("","_unit"))
    s=settlements.copy();lon0=float(s.lon.median());lat0=float(s.lat.median());s["x"],s["y"]=project(s.lon,s.lat,lon0,lat0)
    r=r.merge(s[["source_record_id","x","y"]],on="source_record_id",how="left",validate="one_to_one")
    fig,ax=plt.subplots(figsize=(10,9));ax.scatter(s.x,s.y,s=7,c="#DDE1E5",linewidths=0,rasterized=True)
    colors={"growth":BLUE,"decline":ORANGE,"unchanged":GOLD}
    markers={"growth":"^","decline":"v","unchanged":"o"}
    for center_direction,marker in markers.items():
        for periphery_direction,color in colors.items():
            q=r[r.center_direction_2002_2021.eq(center_direction)&r.surroundings_direction_2002_2021.eq(periphery_direction)&r.unit_status.eq("candidate_functional_zone")]
            ax.scatter(q.x,q.y,s=18,c=color,marker=marker,linewidths=0,zorder=2,rasterized=True)
    unknown=r[r.type_code.isin(["insufficient_comparable_demography","external_context_not_ordinary_settlement"])]
    ax.scatter(unknown.x,unknown.y,s=17,c=INK,marker="x",linewidths=.5,zorder=3,rasterized=True)
    handles=[Line2D([],[],marker="^",linestyle="",color=INK,label="Центр растёт"),Line2D([],[],marker="v",linestyle="",color=INK,label="Центр сокращается"),Line2D([],[],marker="o",linestyle="",color=INK,label="Центр без изменения"),Line2D([],[],marker="s",linestyle="",color=BLUE,label="Окружение растёт"),Line2D([],[],marker="s",linestyle="",color=ORANGE,label="Окружение сокращается"),Line2D([],[],marker="s",linestyle="",color=GOLD,label="Окружение без изменения"),Line2D([],[],marker="x",linestyle="",color=INK,label="Неопределённый тип / внешний контекст"),Line2D([],[],marker="o",linestyle="",color="#BEC4CB",label="Нет кандидата / узел без внешних участников")]
    for label_i,(_,row) in enumerate(s.nlargest(3,"population").iterrows()):
        ax.annotate(str(row.get("name",row.source_record_id)),(row.x,row.y),xytext=(4,4+label_i*7),textcoords="offset points",fontsize=8,color=INK)
    ax.legend(handles=handles,loc="best",fontsize=8,ncol=2)
    decorate(ax,"Форма — динамика центра; цвет — динамика сопоставимой части окружения")
    rname=REGION_NAMES.get(region,region)
    flabel={"healthcare":"медицинские","education":"образовательные","commerce":"торговые"}.get(function,function)
    fig.suptitle(f"{rname}: {flabel} кандидатные зоны\nОписательная демография 2002–2021 в фиксированном составе",fontsize=14,color=INK,y=.97)
    zones=t[t.unit_status.eq("candidate_functional_zone")];missing=int(zones.type_code.eq("insufficient_comparable_demography").sum())
    fig.text(.08,.03,f"Опорный сценарий: экспонента, полураспад 30 мин, отсечение веса 0,05; по неполным функциям.\nДинамика считается только по численно сопоставимым зачтённым рядам; её охват — в таблице единиц.\nПричинные типы Word (аграрные, промышленные и т.д.) не выводятся из одного знака динамики.\nТочки показывают главный условный выбор НП; границы исторических районов и иерархия не установлены.\nПроекция Ламберта, центр {lon0:.3f}° в.д., {lat0:.3f}° с.ш.; предложение и дорожная сеть датированы в таблицах сценария.",fontsize=8,color=INK)
    fig.subplots_adjust(left=.10,right=.96,bottom=.15,top=.87)
    extra="_".join(str(reference_outcomes[c].iloc[0]) for c in ["source_scenario","supply_transform"] if c in reference_outcomes)
    safe="_".join(str(v).replace("/","-").replace(" ","_") for v in [region,function,service_order,extra,"demographic_types"])
    for ext in ("png","pdf"):fig.savefig(Path(outdir)/(safe+"."+ext),dpi=180,facecolor="white")
    plt.close(fig)
    return {"mapped_origins":len(r),"zones_with_external_members":len(zones),"zones_missing_demography":missing}


if __name__=="__main__":main()
