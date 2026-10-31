"""Fresh regional directed car-access scenario; no commuting inference.

Run: python scripts/krasnodar_access/compute.py --pbf PATH --population PATH --out DIR
OSM streets, model speeds, directionality and connectors are explicit. Times
represent inbound access to a settlement reference point, not door-to-door peak
journeys, public transport accessibility, or measured labour-market membership.
"""
from __future__ import annotations
import argparse, hashlib, json, re, time
from pathlib import Path
import osmium
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from pyproj import Transformer
import shapely
from shapely.geometry import LineString, mapping
from shapely.ops import transform

BBOX=(37.,43.8,41.,46.7)
SPEEDS={'motorway':100,'motorway_link':45,'trunk':80,'trunk_link':40,'primary':60,'primary_link':35,'secondary':50,'secondary_link':30,'tertiary':40,'tertiary_link':25,'unclassified':35,'residential':25,'living_street':10,'service':15,'road':25}
FORWARD=Transformer.from_crs(4326,32637,always_xy=True)
BACK=Transformer.from_crs(32637,4326,always_xy=True)

def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def haversine(a,b):
 a=np.radians(a);b=np.radians(b);d=b-a
 return 6371008.8*2*np.arcsin(np.minimum(1,np.sqrt(np.sin(d[1]/2)**2+np.cos(a[1])*np.cos(b[1])*np.sin(d[0]/2)**2)))

class Roads(osmium.SimpleHandler):
 def __init__(self):
  super().__init__();self.coords={};self.arcs={};self.ways=0;self.denied=0
 def way(self,w):
  t=w.tags;road=t.get('highway');access=t.get('motor_vehicle',t.get('vehicle',t.get('access','yes')))
  if road not in SPEEDS or t.get('route')=='ferry':return
  if access in {'no','private','agricultural','forestry'} or t.get('area')=='yes':self.denied+=1;return
  speed=SPEEDS[road];ms=t.get('maxspeed','');match=re.fullmatch(r'(\d+(?:\.\d+)?)(?:\s*(mph|km/h))?',ms)
  if match:
   limit=float(match[1])*(1.609344 if match[2]=='mph' else 1);speed=min(speed,limit)
  if speed<=0:return
  oneway=t.get('oneway','yes' if road=='motorway' or t.get('junction')=='roundabout' else 'no')
  nodes=list(w.nodes)
  for a,b in zip(nodes,nodes[1:]):
   if not(a.location.valid() and b.location.valid()):continue
   ca=(a.lon,a.lat);cb=(b.lon,b.lat)
   if not all(BBOX[0]<=c[0]<=BBOX[2] and BBOX[1]<=c[1]<=BBOX[3] for c in [ca,cb]):continue
   self.coords[a.ref]=ca;self.coords[b.ref]=cb;cost=haversine(ca,cb)/1000/speed*60
   if cost<=0:continue
   edges=[(a.ref,b.ref)] if oneway in {'yes','1','true'} else [(b.ref,a.ref)] if oneway=='-1' else [(a.ref,b.ref),(b.ref,a.ref)]
   for e in edges:
    if e not in self.arcs or cost<self.arcs[e]:self.arcs[e]=cost
  self.ways+=1

def geojson(path,features):path.write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,separators=(',',':')))
def feature(g,p):return {'type':'Feature','geometry':mapping(g),'properties':p}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pbf',type=Path,required=True);ap.add_argument('--population',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--core',type=Path,required=True);ap.add_argument('--routes-only',action='store_true');ap.add_argument('--destinations',choices=['both','point','core'],default='both');args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
 start=time.time();p=pd.read_parquet(args.population);print('population columns',list(p),flush=True)
 (out/'population_schema.json').write_text(json.dumps({'columns':list(p),'rows':len(p)},ensure_ascii=False))
 h=Roads();h.apply_file(str(args.pbf),locations=True,idx='flex_mem');print('roads',len(h.coords),len(h.arcs),time.time()-start,flush=True)
 ids=np.array(list(h.coords),dtype='int64');xy=np.array(list(h.coords.values()));index={int(n):i for i,n in enumerate(ids)}
 u=np.array([index[e[0]] for e in h.arcs],dtype='int32');v=np.array([index[e[1]] for e in h.arcs],dtype='int32');w=np.array(list(h.arcs.values()))
 graph=coo_matrix((w,(u,v)),shape=(len(ids),len(ids))).tocsr();x,y=FORWARD.transform(xy[:,0],xy[:,1]);proj=np.column_stack([x,y]);tree=cKDTree(proj)
 # Population input schema is validated explicitly below; no fabricated points.
 if {'accepted_latitude','accepted_longitude'}.issubset(p):
  p=p[p.accepted_point_present.eq(True)&p.is_additive_settlement_record.eq(True)&p.working_credit_present.eq(True)].copy()
  p['lat']=p.accepted_latitude;p['lon']=p.accepted_longitude
 if {'census_year','lat','lon','source_record_id'}.issubset(p):p=p[p.census_year.eq(2021)].copy()
 elif {'year','lat','lon','source_record_id'}.issubset(p):p=p[p.year.eq(2021)].copy()
 else:raise ValueError('Need accepted long census table with year, lat/lon and source_record_id')
 p=p[p.lon.between(BBOX[0],BBOX[2])&p.lat.between(BBOX[1],BBOX[3])].copy()
 names=[c for c in ['name','settlement_name','name_raw','source_name'] if c in p]
 if not names:raise ValueError('No name field')
 namecol=names[0];centres=p[p[namecol].astype(str).str.fullmatch(r'(?:г\.?\s*)?Краснодар',case=False)]
 if len(centres)!=1:print(centres.to_string(),flush=True);raise ValueError('Need unique accepted Krasnodar point')
 centre=centres.iloc[0];cp=FORWARD.transform(float(centre.lon),float(centre.lat));cd,ci=tree.query(cp)
 if cd>2000:raise ValueError('Centre snap exceeds2km')
 arrival=dijkstra(graph.T.tocsr(),directed=True,indices=int(ci),limit=150)+cd/1000/15*60
 px,py=FORWARD.transform(p.lon.to_numpy(),p.lat.to_numpy());snap,nearest=tree.query(np.column_stack([px,py]));p['snap_m']=snap;p['road_node_osm_id']=ids[nearest];p['time_minutes_base']=arrival[nearest]+snap/1000/15*60
 p.loc[snap>2000,'time_minutes_base']=np.nan
 p['time_minutes_slow']=p.time_minutes_base*1.3
 core_file=args.core;core=json.loads(core_file.read_text());core_shape=shapely.geometry.shape(core['geometry']);seeds=np.flatnonzero(shapely.contains_xy(core_shape,xy[:,0],xy[:,1]));
 if len(seeds)==0:raise ValueError('No road nodes inside accepted core')
 arrival_core=dijkstra(graph.T.tocsr(),directed=True,indices=seeds,min_only=True,limit=150)
 p['time_minutes_to_core']=arrival_core[nearest]+snap/1000/15*60
 p.loc[snap>2000,'time_minutes_to_core']=np.nan
 p['time_minutes_to_core_slow']=p.time_minutes_to_core*1.3
 p['functional_commuting_status']='not_computable_no_OD';p['access_class']='outside_90_or_unreachable'
 p.loc[p.time_minutes_base.le(90),'access_class']='extended_60_to_90'
 p.loc[p.time_minutes_base.le(60),'access_class']='within_60_sensitive_to_slowdown'
 p.loc[p.time_minutes_slow.le(60),'access_class']='within_60_both_speed_scenarios'
 p.loc[p.snap_m.gt(2000),'access_class']='unknown_snap_over_2km'
 p['included_candidate_60']=p.time_minutes_to_core.le(60);p['included_candidate_90']=p.time_minutes_to_core.le(90)
 p['core_access_class']='outside_90_or_no_route_within_150'
 p.loc[p.time_minutes_to_core.le(90),'core_access_class']='extended_60_to_90'
 p.loc[p.time_minutes_to_core.le(60),'core_access_class']='within_60_sensitive_to_slowdown'
 p.loc[p.time_minutes_to_core_slow.le(60),'core_access_class']='within_60_both_speed_scenarios'
 p.loc[p.snap_m.gt(2000),'core_access_class']='unknown_snap_over_2km'
 p.to_csv(out/'settlement_access.csv',index=False);p.to_parquet(out/'settlement_access.parquet',index=False)
 from sample_routes import check_routes
 check_routes(graph,xy,p,nearest,int(ci),(float(centre.lon),float(centre.lat)),cd/1000/15*60,out)
 if args.routes_only:return
 # Display generalized reachable-road zones; membership is ONLY the point-time
 # table. Buffer/closing is cartography, never a travel-time interpolation.
 features=[];reachable_roads=[]
 destinations={'point':arrival,'core':arrival_core} if args.destinations=='both' else {args.destinations:arrival if args.destinations=='point' else arrival_core}
 for destination,arr in destinations.items():
  previous={1.:shapely.Polygon(),1.3:shapely.Polygon()};previous_wgs={1.:shapely.Polygon(),1.3:shapely.Polygon()};destination_features=[]
  for factor in [1.,1.3]:
   for budget in [30,60,90]:
    residual=budget/factor-arr[v];fraction=np.clip(residual/w,0,1);keep=fraction>0
    aa=proj[v[keep]];bb=aa+(proj[u[keep]]-aa)*fraction[keep,None];segments=shapely.linestrings(np.stack([aa,bb],axis=1))
    lines=shapely.line_merge(shapely.union_all(segments)).simplify(30,preserve_topology=False)
    poly=shapely.union_all(shapely.buffer(shapely.get_parts(lines),500,quad_segs=2))
    poly=poly.buffer(1000,quad_segs=2).buffer(-1000,quad_segs=2).simplify(120,preserve_topology=True)
    poly=shapely.union(poly,previous[factor]);previous[factor]=poly
    wg=shapely.union(transform(BACK.transform,poly),previous_wgs[factor]);previous_wgs[factor]=wg;props={'minutes':budget,'speed_time_factor':factor,'destination':destination,'centre':'Краснодар','evidence':'road_network_model','geometry_role':'generalized_reachable_road_corridor','buffer_m':500,'closing_m':1000,'simplify_m':120,'not_functional_boundary':True}
    f=feature(wg,props);features.append(f);destination_features.append(f);geojson(out/f'{destination}_isochrone_{budget}_{factor:g}.geojson',[f])
    if destination=='point' and factor==1. and budget==90:
     reachable_roads=[feature(transform(BACK.transform,lines.simplify(70)),{'minutes':90,'evidence':'road_network_model'})]
    print('polygon',destination,factor,budget,shapely.get_num_coordinates(poly),flush=True)
  geojson(out/f'{destination}_isochrones.geojson',destination_features)
 geojson(out/'isochrones_all_destinations.geojson',features)
 if reachable_roads:geojson(out/'reachable_roads_90.geojson',reachable_roads)
 # Detect truncated search geometry: no reachable90 road vertex may approach
 # the extraction edge within0.03 degrees.
 edge=np.minimum.reduce([xy[:,0]-BBOX[0],BBOX[2]-xy[:,0],xy[:,1]-BBOX[1],BBOX[3]-xy[:,1]])<.03
 boundary_min=float(np.min(arrival[edge])) if edge.any() else None
 core_boundary_min=float(np.min(arrival_core[edge])) if edge.any() else None
 stats={'source_pbf':str(args.pbf.name),'pbf_sha256':sha(args.pbf),'pbf_bytes':args.pbf.stat().st_size,'population_sha256':sha(args.population),'bbox':BBOX,'osm_ways_considered':h.ways,'nodes':len(ids),'directed_arcs':len(w),'centre':{k:str(centre[k]) for k in ['source_record_id',namecol,'lat','lon']},'centre_snap_m':float(cd),'core_road_seed_nodes':len(seeds),'core_polygon_properties':core['properties'],'core_candidate_30':int(p.time_minutes_to_core.le(30).sum()),'core_candidate_60':int(p.time_minutes_to_core.le(60).sum()),'core_candidate_90':int(p.time_minutes_to_core.le(90).sum()),'settlement_rows':len(p),'access_class_counts':p.access_class.value_counts().to_dict(),'candidate_30':int(p.time_minutes_base.le(30).sum()),'candidate_60':int(p.time_minutes_base.le(60).sum()),'candidate_90':int(p.time_minutes_base.le(90).sum()),'min_minutes_at_bbox_edge':boundary_min if boundary_min is not None and np.isfinite(boundary_min) else None,'min_core_minutes_at_bbox_edge':core_boundary_min if core_boundary_min is not None and np.isfinite(core_boundary_min) else None,'bbox_not_truncated_90':(boundary_min is None or boundary_min>90) and (core_boundary_min is None or core_boundary_min>90),'speed_defaults_kmh':SPEEDS,'connector_kmh':15,'snap_limit_m':2000,'slow_time_factor':1.3,'elapsed_s':time.time()-start,'limits':['No observed commuting OD: no15% classification','No congestion, signals, turn costs, turn restrictions or live closures','OSM motor_vehicle/vehicle/access and one-way tags parsed; private roads excluded; motorcar-specific and conditional access not evaluated','Reference-point snap is geometric: crossings/barriers require local verification','Generalized polygons include unmapped/interstitial land: use point-time table for membership','Population2021 and road snapshot2026 are different dates','No public transport or door-to-door measurement']}
 (out/'summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2));print(json.dumps(stats,ensure_ascii=False),flush=True)
 if not stats['bbox_not_truncated_90']:raise ValueError('Need expanded bbox before publishing90')
if __name__=='__main__':main()
