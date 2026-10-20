#!/usr/bin/env python3
"""Network isochrones: actual reachable road vertices, not invented land polygons."""
from pathlib import Path
from compute_matrix import sha
import json,time
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from pyproj import Transformer
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2]

def run():
 t=time.time();graph=load_npz(ROOT/'routing_graph.npz').transpose().tocsr();nodes=pd.read_parquet(ROOT/'road_nodes.parquet');snap=pd.read_parquet(ROOT/'settlement_road_snap.parquet').set_index('id');master=pd.read_parquet(REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',columns=['id','name','population_2021']);fed=pd.read_csv(REPO/'research/sgrt_national_integration_20261019/core/external_federal_features.csv',usecols=['id','name','population_2021']);master=pd.concat([master,fed]);cities=['Москва','Санкт-Петербург','Казань','Екатеринбург','Новосибирск','Краснодар','Владивосток'];summ=[];colors=['#1c4e69','#3a7f9b','#82b6c2','#d5e3e4'];bounds=[0,30,60,120,180];cmap=ListedColormap(colors);norm=BoundaryNorm(bounds,cmap.N);writer=None
 figdir=ROOT/'isochrones';figdir.mkdir(exist_ok=True)
 for city in cities:
  candidates=master[master.name.eq(city)&master.id.isin(snap.index)].sort_values('population_2021',ascending=False)
  if not len(candidates):continue
  uid=candidates.iloc[0].id;source=snap.loc[uid];dist=dijkstra(graph,indices=int(source.road_node_index),limit=180,directed=True);mask=np.isfinite(dist);z=nodes.loc[mask,['osm_id','lat','lon','node_index']].copy();z['center_id']=uid;z['center_name']=city;z['network_minutes_to_center']=dist[mask].astype('float32');z['connector_minutes_not_added']=True
  if writer is None:writer=pq.ParquetWriter(ROOT/'isochrone_reachable_vertices.parquet',pa.Table.from_pandas(z,preserve_index=False).schema,compression='zstd')
  writer.write_table(pa.Table.from_pandas(z,preserve_index=False));counts={str(b):int((dist<=b).sum()) for b in [30,60,120,180]};summ.append({'center_id':uid,'name':city,'reachable_vertices':len(z),'vertices_within_minutes':counts,'center_snap_km':float(source.snap_km)})
  pr=Transformer.from_crs('EPSG:4326',f'+proj=aeqd +lat_0={source.lat} +lon_0={source.lon} +datum=WGS84',always_xy=True);x,y=pr.transform(z.lon.values,z.lat.values);fig,ax=plt.subplots(figsize=(10,9));order=np.argsort(z.network_minutes_to_center.values)[::-1];ax.scatter(np.asarray(x)[order]/1000,np.asarray(y)[order]/1000,c=z.network_minutes_to_center.values[order],cmap=cmap,norm=norm,s=.25,rasterized=True);ax.scatter([0],[0],marker='*',s=180,c='#222');ax.set_aspect('equal');ax.set_xlabel('Азимутальная эквидистантная проекция, км');ax.set_ylabel('км');ax.set_title(f'{city}: расчётная доступность по дорожной сети',loc='left',fontsize=14);from matplotlib.lines import Line2D;ax.legend(handles=[Line2D([0],[0],marker='o',lw=0,color=c,label=l) for c,l in zip(colors,['0–30 мин','30–60 мин','60–120 мин','120–180 мин'])],loc='best');fig.text(.10,.015,'Показаны реальные достижимые вершины OSM, не сплошная территория и не измеренное время в пробках.\nНаправление: к центру; скорости — сценарий классов/maxspeed; прямой снап-коннектор не добавлен.',fontsize=8);fig.tight_layout(rect=[0,.06,1,1])
  for ext in ['png','svg','pdf']:fig.savefig(figdir/f'{uid.replace(":","_")}.{ext}',dpi=400,bbox_inches='tight')
  plt.close(fig);print(city,len(z),counts,flush=True)
 if writer:writer.close()
 (ROOT/'isochrone_receipt.json').write_text(json.dumps({'status':'COMPUTED_NETWORK_VERTEX_ISOCHRONES','graph_sha256':sha(ROOT/'routing_graph.npz'),'access_repair_receipt_sha256':sha(ROOT/'access_repair_receipt.json'),'yearround_profile_receipt_sha256':sha(ROOT/'yearround_profile_receipt.json'),'sources':summ,'road_source_snapshot':'OSM2026-10-19','time_model':'speed scenario,not observed traffic','interpretation':'Network reachable road vertex sets; no invented terrestrial polygon; no turnrelations/ferry routing','seconds':time.time()-t},ensure_ascii=False,indent=2))
if __name__=='__main__':run()
