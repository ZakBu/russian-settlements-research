"""Five directed counterchecks and model routes, never observed journeys."""
import json
from pathlib import Path
import numpy as np
from scipy.sparse.csgraph import dijkstra

SAMPLES=['Яблоновский','Энем','Динская','Горячий Ключ','Марьянская']
def check_routes(graph,xy,frame,nearest,centre_index,centre_lonlat,centre_connector_minutes,out):
 reverse,pred=dijkstra(graph.T.tocsr(),directed=True,indices=int(centre_index),limit=150,return_predecessors=True)
 comparisons=[];features=[]
 for name in SAMPLES:
  positions=np.flatnonzero(frame.settlement_name.eq(name).to_numpy())
  if len(positions)!=1:raise ValueError(f'Need unique named sample: {name}, got{len(positions)}')
  position=int(positions[0]);r=frame.iloc[position];origin=int(nearest[position])
  forward=dijkstra(graph,directed=True,indices=origin,limit=150)
  f=float(forward[centre_index]);b=float(reverse[origin])
  if not np.isfinite(f) or not np.isfinite(b):raise ValueError('Expected finite sample path: '+name)
  if not np.isclose(f,b,atol=1e-8,rtol=1e-11):raise ValueError('Forward/reverse direction mismatch: '+name)
  connector=float(r.snap_m)/1000/15*60;total=f+connector+centre_connector_minutes
  if not np.isclose(total,r.time_minutes_base,atol=1e-8,rtol=1e-11):raise ValueError('Published time differs from connectors and route: '+name)
  route=[origin];seen={origin};current=origin
  while current!=centre_index:
   nxt=int(pred[current])
   if nxt<0 or nxt in seen:raise ValueError('Incomplete/cyclic predecessor path: '+name)
   if graph[current,nxt]<=0:raise ValueError('Reversed original one-way edge: '+name)
   route.append(nxt);seen.add(nxt);current=nxt
  edge_sum=sum(float(graph[a,b]) for a,b in zip(route,route[1:]))
  if not np.isclose(edge_sum,f,atol=1e-8,rtol=1e-11):raise ValueError('Route edge sum differs from shortest path: '+name)
  props={'name':name,'source_record_id':str(r.source_record_id),'destination':'accepted_census_point_of_Krasnodar','direction':'inbound','evidence':'model_route_not_observed_trip','road_minutes_forward':f,'road_minutes_reverse_search':b,'origin_connector_minutes':connector,'destination_connector_minutes':centre_connector_minutes,'total_minutes':total,'road_arcs':len(route)-1,'road_edge_sum_minutes':edge_sum,'max_forward_reverse_difference_minutes':abs(f-b)}
  comparisons.append(props);features.append({'type':'Feature','geometry':{'type':'LineString','coordinates':xy[route].tolist()},'properties':{**props,'kind':'road_route'}})
  for label,coords in [('origin_connector',[[float(r.lon),float(r.lat)],xy[origin].tolist()]),('destination_connector',[xy[centre_index].tolist(),list(centre_lonlat)])]:
   features.append({'type':'Feature','geometry':{'type':'LineString','coordinates':coords},'properties':{'name':name,'kind':label,'evidence':'straight_model_connector_not_verified_path'}})
 result={'samples':comparisons,'check':'forward_original_graph_equals_reverse_destination_search_with_connectors','note':'Shortlisted model car paths for checking direction and bridge alignment; no observed journey or turn-restriction validation claimed.'}
 Path(out,'sample_routes.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));Path(out,'sample_routes.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,separators=(',',':')))
 print(json.dumps(result,ensure_ascii=False),flush=True)
 return result
