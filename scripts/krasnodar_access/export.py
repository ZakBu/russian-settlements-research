"""Create lightweight, source-labelled GeoJSON and a frontend manifest."""
import argparse,json,hashlib
from collections import defaultdict
from pathlib import Path
import osmium,pandas as pd,numpy as np,shapely
from shapely.geometry import mapping,LineString,Point
from shapely.ops import transform
from pyproj import Transformer

def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':')))
def fc(features):return {'type':'FeatureCollection','features':features}
def feature(g,p):return {'type':'Feature','geometry':mapping(g),'properties':p}
class Context(osmium.SimpleHandler):
 def __init__(self):super().__init__();self.features=[]
 def way(self,w):
  river=w.tags.get('waterway')=='river';rail=w.tags.get('railway')=='rail';road=w.tags.get('highway') in {'motorway','trunk','primary','secondary'}
  if not(river or road or rail):return
  coords=[(n.lon,n.lat) for n in w.nodes if n.location.valid()]
  if len(coords)<2:return
  g=LineString(coords).intersection(shapely.box(37.5,44.2,40.6,46.1))
  if g.is_empty:return
  self.features.append(feature(g.simplify(.0006),{'kind':'river' if river else 'railway' if rail else 'road','name':w.tags.get('name',''),'osm_way_id':str(w.id),'highway':w.tags.get('highway',''),'source':'OpenStreetMap / Geofabrik2026-10-29'}))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pbf',type=Path,required=True);ap.add_argument('--results',type=Path,required=True);ap.add_argument('--core',type=Path,required=True);ap.add_argument('--skip-context',action='store_true');a=ap.parse_args();out=a.results
 s=json.loads((out/'summary.json').read_text());p=pd.read_csv(out/'settlement_access.csv');roster_fields=['source_record_id','settlement_name','settlement_type','region_norm','district_raw','effective_population','lat','lon','snap_m','time_minutes_base','time_minutes_slow','time_minutes_to_core','time_minutes_to_core_slow','core_access_class','functional_commuting_status','included_candidate_60','included_candidate_90'];p[roster_fields].replace([np.inf,-np.inf],np.nan).to_csv(out/'candidate_roster.csv',index=False);polys=json.loads((out/'point_isochrones.geojson').read_text());base=[f for f in polys['features'] if f['properties']['speed_time_factor']==1];slow=[f for f in polys['features'] if f['properties']['speed_time_factor']==1.3];core_polys=json.loads((out/'core_isochrones.geojson').read_text());core_base=[f for f in core_polys['features'] if f['properties']['speed_time_factor']==1];core_slow=[f for f in core_polys['features'] if f['properties']['speed_time_factor']==1.3]
 write(out/'isochrones_base.geojson',fc(base));write(out/'isochrones_slow.geojson',fc(slow));bands=[];previous=shapely.Polygon()
 for f in base:
  g=shapely.geometry.shape(f['geometry']);bands.append(feature(g.difference(previous),{**f['properties'],'geometryMode':'disjoint_bands'}));previous=g
 write(out/'isochrone_bands.geojson',fc(bands));write(out/'candidate_60.geojson',fc([f for f in core_base if f['properties']['minutes']==60]));write(out/'candidate_60_slow.geojson',fc([f for f in core_slow if f['properties']['minutes']==60]));write(out/'core_isochrones_base.geojson',fc(core_base));write(out/'core_isochrones_slow.geojson',fc(core_slow));core=json.loads(a.core.read_text());core['properties']['kind']='core';core['properties']['name']='Краснодар: принятый контур НП';write(out/'core.geojson',fc([core]))
 # Candidate and surrounding real census places; retain unknown observations.
 pp=p[p.time_minutes_base.le(110)|p.time_minutes_to_core.le(90)|p.snap_m.gt(2000)].copy();features=[]
 fields=['source_record_id','settlement_name','settlement_type','region_norm','district_raw','effective_population','time_minutes_base','time_minutes_slow','time_minutes_to_core','time_minutes_to_core_slow','snap_m','access_class','core_access_class','functional_commuting_status']
 for r in pp.to_dict('records'):
  prop={k:(None if pd.isna(r.get(k)) or isinstance(r.get(k),(float,np.floating)) and not np.isfinite(r.get(k)) else r[k]) for k in fields};prop.update({'name':r['settlement_name'],'population':None if pd.isna(r['effective_population']) else r['effective_population'],'populationYear':2021,'evidence':'census_point_and_network_model'})
  features.append(feature(Point(r['lon'],r['lat']),prop))
 write(out/'places.geojson',fc(features));
 if not a.skip_context:
  h=Context();h.apply_file(str(a.pbf),locations=True,idx='flex_mem');groups=defaultdict(list)
  for f in h.features:
   pr=f['properties'];key=(pr['kind'],pr.get('highway','') if pr['kind']=='road' else pr.get('name','') if pr['kind']=='river' else '')
   groups[key].append(shapely.geometry.shape(f['geometry']))
  context_features=[]
  for (kind,label),gg in groups.items():
   merged=shapely.line_merge(shapely.union_all(gg)).simplify(.0008)
   context_features.append(feature(merged,{'kind':kind,'name':label,'source_way_count':len(gg),'source':'OpenStreetMap / Geofabrik2026-10-29'}))
  context_features.append(core);context_features.append(feature(Point(float(s['centre']['lon']),float(s['centre']['lat'])),{'kind':'centre','name':'Принятая точка Краснодара','year':2021}));write(out/'context.geojson',fc(context_features))
 else:
  context_features=json.loads((out/'context.geojson').read_text())['features']
 counts=[]
 for kind,col in [('central_point','time_minutes_base'),('core_contour','time_minutes_to_core')]:
  for minutes in [30,60,90]:
   q=p[p[col].le(minutes)];counts.append({'destination':kind,'minutes':minutes,'settlementRecords':len(q),'settlementUnit':'переписных записей НП2021 с принятой точкой','inhabitedSettlements':int(q.effective_population.gt(0).sum()),'population2021':int(q.effective_population.sum()),'populationUnit':'человек, эффективная численность принятой базы2021','populationMissingRecords':int(q.effective_population.isna().sum()),'includesKrasnodar':True})
 write(out/'statistics.json',{'counts':counts,'accessClasses':s['access_class_counts'],'coreAccessClasses':p.core_access_class.value_counts().to_dict(),'core60Range':{'minSettlements':int(p.time_minutes_to_core_slow.le(60).sum()),'maxSettlements':int(p.time_minutes_to_core.le(60).sum()),'minPopulation2021':int(p[p.time_minutes_to_core_slow.le(60)].effective_population.sum()),'maxPopulation2021':int(p[p.time_minutes_to_core.le(60)].effective_population.sum()),'rangeType':'two_speed_scenarios_not_confidence_interval'},'unknownCriterion':'Доля занятых, работающих в ядре, не рассчитана: OD-матрица отсутствует','direction':'inbound','timeUnit':'модельные минуты','speedSensitivity':'Время×1.3: сценарий, не измеренная пробка'})
 manifest={'version':'krasnodar-road-access-20261031-v1','title':'Дорожная доступность Краснодара: транспортный сценарий','direction':'inbound','destination':'accepted_census_central_point','centre':s['centre'],'centreCoordinateYear':2021,'roadSnapshot':'2026-10-29','isochrones':{'url':'isochrone_bands.geojson','cumulativeUrl':'isochrones_base.geojson','slowUrl':'isochrones_slow.geojson','geometryMode':'disjoint_bands','minutes':[30,60,90],'unit':'модельные минуты до принятой точки Краснодара'},'candidate':{'geometryUrl':'candidate_60.geojson','robustGeometryUrl':'candidate_60_slow.geojson','destination':'accepted_core_contour','minutes':60,'evidence':'road_network_model','notFunctionalAgglomeration':True},'places':{'url':'places.geojson'},'context':{'url':'context.geojson'},'core':{'url':'core.geojson','isochronesUrl':'core_isochrones_base.geojson','slowIsochronesUrl':'core_isochrones_slow.geojson','timesField':'time_minutes_to_core','geometryKind':core['properties']['geometryKind']},'statistics':{'url':'statistics.json'},'table':{'url':'settlement_access.csv','rosterUrl':'candidate_roster.csv'},'provenance':{'url':'summary.json'},'sampleRoutes':{'url':'sample_routes.geojson','checksUrl':'sample_routes.json','evidence':'model_routes_not_observed_journeys'},'limits':s['limits']};write(out/'manifest.json',manifest)
 print(json.dumps({'counts':counts,'contextFeatures':len(context_features),'placesFeatures':len(features)},ensure_ascii=False))
if __name__=='__main__':main()
