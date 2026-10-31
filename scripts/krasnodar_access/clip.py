"""Clip v1 display polygons to the pinned Russian outline, without rerouting.

python scripts/krasnodar_access/clip.py --results V1 --output V2 --adm1 RUS-adm1.geojson
V1 is immutable. Census membership, times, graph, road lines and route checks
are preserved byte-for-byte; only polygon drawings and their metadata change.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import shapely
from shapely.geometry import shape,mapping,Polygon,box
from shapely.ops import transform
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.sgrt_saratov.country_scope import load_russia
MASK_URL='https://github.com/ZakBu/russian-settlements-research/releases/download/atlas-boundaries-20261026-v1/RUS-adm1.geojson'
MASK_SHA='f8cd605958b61598265c12647d43279ad5ca2605c05509df281f769c330c82f4'
PROJECT=Transformer.from_crs(4326,32637,always_xy=True).transform

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
def polygonal(g):
 if g.geom_type in {'Polygon','MultiPolygon'}:return g
 if g.geom_type=='GeometryCollection':return shapely.union_all([polygonal(p) for p in g.geoms if p.geom_type in {'Polygon','MultiPolygon','GeometryCollection'}])
 return Polygon()
def clipped_geojson(document,mask,filename):
 diagnostics=[];changed=False;features=[]
 for index,f in enumerate(document.get('features',[])):
  g=shape(f['geometry'])
  if g.geom_type not in {'Polygon','MultiPolygon'}:features.append(f);continue
  valid=shapely.make_valid(g);outside=valid.difference(mask);cut=polygonal(valid.intersection(mask))
  if cut.is_empty or not cut.is_valid:raise ValueError(f'Empty/invalid clipped polygon: {filename}:{index}')
  if cut.difference(mask).area>1e-14:raise ValueError(f'Polygon outside pinned mask: {filename}:{index}')
  p=f.get('properties',{});diagnostics.append({'file':filename,'feature':index,'minutes':p.get('minutes'),'destination':p.get('destination'),'speed_time_factor':p.get('speed_time_factor'),'removed_area_km2':float(transform(PROJECT,outside).area/1e6),'removed_area_degrees2':float(outside.area),'outside_parts':len([v for v in shapely.get_parts(outside) if v.area>0]),'outside_representative_points':[[round(v.representative_point().x,6),round(v.representative_point().y,6)] for v in sorted([v for v in shapely.get_parts(outside) if v.area>0],key=lambda v:v.area,reverse=True)[:5]]})
  features.append({**f,'geometry':mapping(cut),'properties':{**p,'display_country_scope':'Russia_pinned_atlas_outline','country_mask_sha256':MASK_SHA,'country_clip_display_only':True}});changed=True
 return {**document,'features':features},diagnostics,changed

def run(results,output,adm1):
 results=Path(results).resolve();output=Path(output).resolve();adm1=Path(adm1).resolve()
 if results==output or results in output.parents:raise ValueError('Output must be separate from immutable v1 input')
 if output.exists() and any(output.iterdir()):raise ValueError('Refusing to replace an existing v2 result directory')
 if sha(adm1)!=MASK_SHA:raise ValueError('ADM1 SHA256 differs from pinned source')
 full_mask=load_russia(adm1);mask=full_mask.intersection(box(36,43,42,48))
 output.mkdir(parents=True,exist_ok=True)
 for p in results.iterdir():
  if p.is_file():shutil.copyfile(p,output/p.name)
  else:raise ValueError('Expected flat v1 result files')
 protected=[p.name for p in results.iterdir() if p.suffix in {'.csv','.parquet'} or p.name in {'statistics.json','sample_routes.json','sample_routes.geojson','input_provenance.json','population_schema.json','reachable_roads_90.geojson'}]
 diagnostics=[];modified=[]
 for path in sorted(output.glob('*.geojson')):
  doc=json.loads(path.read_text());doc,dd,changed=clipped_geojson(doc,mask,path.name)
  if changed:dump(path,doc);modified.append(path.name);diagnostics.extend(dd)
 # Derive the disjoint point-time bands from delivered clipped cumulative sets.
 cumulative=output/'isochrones_base.geojson'
 if cumulative.exists() and (output/'isochrone_bands.geojson').exists():
  data=json.loads(cumulative.read_text());previous=Polygon();bands=[]
  for f in sorted(data['features'],key=lambda f:f['properties']['minutes']):
   g=shape(f['geometry']);band=polygonal(g.difference(previous));previous=shapely.union(previous,g);bands.append({**f,'geometry':mapping(band),'properties':{**f['properties'],'geometryMode':'disjoint_bands'}})
  dump(output/'isochrone_bands.geojson',{**data,'features':bands})
 hashes={n:{'before':sha(results/n),'after':sha(output/n)} for n in protected}
 if any(v['before']!=v['after'] for v in hashes.values()):raise ValueError('Time, membership, source or route file changed')
 # A reference-mask crop says nothing about the accuracy of the OSM speeds or
 # the original route calculations. Do not copy Saratov's legacy-transit flag.
 provenance={'schema':'krasnodar.country-display-clip.v2','source_version':'krasnodar-access-maps-20261031-v1','result_version':'krasnodar-access-maps-20261031-v2','operation':'polygon_intersection_after_all_buffers_and_simplification','rerouting':False,'membership_changed':False,'times_changed':False,'mask':{'url':MASK_URL,'sha256':MASK_SHA,'bytes':adm1.stat().st_size,'archive_member':'input/RUS-adm1.geojson','source':'Terrae2026.10 / OpenStreetMap','source_snapshot':'2026-09-28','kind':'reference_ADM1_union_not_legal_boundary','features':83},'modified_polygon_files':modified,'unchanged_files':hashes,'diagnostics':diagnostics,'interpretation':'Raw pinned ADM1 is used, not the simplified UI regions. Removed core90 fragments are coastal buffers near Dzhubga; small gaps in the UI outline are not evidence of foreign land. Road and sample-route lines remain original and are not geometrically cropped.','route_scope_basis':'Fresh regional graph bbox37–41E/43.8–46.7N, north of the international boundary in this longitude interval; this crop does not itself validate route geometry or costs.'}
 dump(output/'country_clip.json',provenance)
 for filename in ['manifest.json','summary.json']:
  path=output/filename
  if not path.exists():continue
  data=json.loads(path.read_text());data['country_clip']={'url':'country_clip.json','mask_sha256':MASK_SHA,'display_only':True}
  if filename=='manifest.json':
   data['version']='krasnodar-road-access-20261031-v2';data.setdefault('provenance',{})['geographyUrl']='country_clip.json'
  dump(path,data)
 # Every delivered polygon, including the context's display core, is checked.
 max_outside=0.
 for path in output.glob('*.geojson'):
  for f in json.loads(path.read_text()).get('features',[]):
   g=shape(f['geometry'])
   if g.geom_type in {'Polygon','MultiPolygon'}:
    if not g.is_valid:raise ValueError('Invalid delivered polygon:'+path.name)
    max_outside=max(max_outside,float(g.difference(mask).area))
 if max_outside>1e-14:raise ValueError('Delivered polygon left country mask')
 print(json.dumps({'version':'v2','polygon_files':len(modified),'protected_files':len(hashes),'max_remaining_outside_degrees2':max_outside,'core90_removed_km2':next((d['removed_area_km2'] for d in diagnostics if d['file']=='core_isochrone_90_1.geojson'),None)},ensure_ascii=False))
 return provenance

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--results',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--adm1',type=Path,required=True);a=parser.parse_args();run(a.results,a.output,a.adm1)
