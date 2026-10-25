#!/usr/bin/env python3
"""Read-only public-route access diagnostic; no observed driveway or barrier-free connector claim."""
from pathlib import Path
import sys,json,numpy as np,pandas as pd
from scipy.sparse.csgraph import dijkstra
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/sgrt_mass'));from routes import load_graph,haversine_km
import argparse
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--prepared-root',type=Path);parser.add_argument('--roads',type=Path);parser.add_argument('--graph-dir',type=Path);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)

root=args.bundle;w=args.output;m=args.prepared_root;graph=load_graph(args.graph_dir);roads=pd.read_parquet(args.roads,columns=['node_index','osm_id','lat','lon'])
frames=[]
for folder in ['routes_complete_scope_corrected','routes_education_commerce_corrected','routes_commerce_components_corrected','routes_wb','routes_yandex']:
 f=pd.read_parquet(m/folder/'provider_road_seeds.parquet',columns=['provider_id','service_code','site_lat','site_lon','road_node_index','snap_km']);frames.append(f)
pool=pd.concat(frames).drop_duplicates(['provider_id','service_code','site_lat','site_lon']);candidates=pd.read_parquet(w/'selected_counterexample_candidates.parquet');rows=[]
for svc in ['daily_grocery','school_general','medical_basic_primary','parcel_pickup_wildberries_current']:
 c=candidates[candidates.service_code.eq(svc)&candidates.diagnostic_kind.eq('external_implied_speed')].nlargest(1,'_speed');rows.extend(c.to_dict('records'))
for svc,name in [('higher_education','Тутаев'),('higher_education','Тобольск'),('school_general','Тасута')]:
 d=pd.read_parquet(root/'routes/nearest'/f'{svc}.parquet');rows.extend(d[d.name.eq(name)].to_dict('records'))
reports=[]
for r in rows:
 pid=r['unconstrained_nearest_provider_id'];p=pool[pool.provider_id.eq(pid)&pool.service_code.eq(r['service_code'])].drop_duplicates();assert len(p)==1,(pid,len(p));p=p.iloc[0];u=int(r['road_node_index']);v=int(p.road_node_index);dist,pred=dijkstra(graph,directed=True,indices=u,limit=240,return_predecessors=True);dc=dijkstra(graph,directed=True,indices=v,limit=240);network=float(dist[v]);connector=4*(r['snap_km']+p.snap_km);forward=network+connector;back=float(dc[u])+connector if np.isfinite(dc[u]) else None;path=[v]
 while path[-1]!=u:
  prev=int(pred[path[-1]]);assert prev>=0,'disconnected selected path';path.append(prev);assert len(path)<=100000
 path.reverse();maxspeed=0.;asym=0;edgecases=[]
 for x,y in zip(path,path[1:]):
  a,b=graph.indptr[x:x+2];at=int(np.searchsorted(graph.indices[a:b],y))+int(a);assert at<b and graph.indices[at]==y;cost=float(graph.data[at]);km=float(haversine_km(roads.lat.iloc[x],roads.lon.iloc[x],roads.lat.iloc[y],roads.lon.iloc[y]));speed=km/cost*60 if cost>0 else None
  if speed is not None:maxspeed=max(maxspeed,speed)
  c,d=graph.indptr[y:y+2];rev=int(np.searchsorted(graph.indices[c:d],x))+int(c);rv=float(graph.data[rev]) if rev<d and graph.indices[rev]==x else None
  if rv is None or abs(rv-cost)>1e-8:asym+=1
 report={'name':r['name'],'region':r['region'],'service':r['service_code'],'origin_id':r['origin_id'],'raw_selected_provider_id':pid,'published_raw_minutes':r['unconstrained_nearest_cost_minutes'],'independent_origin_to_selected_minutes':forward,'independent_selected_to_origin_minutes':back,'origin_to_selected_error_minutes':forward-r['unconstrained_nearest_cost_minutes'],'path_edges':len(path)-1,'path_edges_with_asymmetric_reverse_arc':asym,'maximum_per_arc_straight_speed_kmh':maxspeed,'turn_restrictions_and_observed_driveways_validated':False};reports.append(report);print(json.dumps(report,ensure_ascii=False),flush=True)
(w/'actual_direction_and_arc_speed_cases.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
