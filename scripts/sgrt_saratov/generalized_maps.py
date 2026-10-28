"""Coarse, contrasting time zones for the Saratov atlas.

Only the drawing changes: route costs, settlement membership and time thresholds
are never derived from these generalized polygons. Frozen native road corridors
remain the transport evidence. The separate dated basemap water mask is display
context; it is not retroactively inserted into the 2021 routing graph.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import urllib.request

import numpy as np
import shapely
from shapely.geometry import Polygon, shape, mapping
from shapely.ops import transform
from pyproj import Transformer

CRS = 'EPSG:32638'
THRESHOLDS = (10., 20., 30., 60.)
SLUGS = {'118372':'saratov','118308':'engels','116499':'balakovo',
         '116550':'balashov','117415':'novouzensk','117733':'piterka'}
USER_AGENT = 'Mozilla/5.0 SaratovResearchCartography/1.0'
TILEJSON_URL = 'https://tiles.openfreemap.org/planet'
ATTRIBUTION = 'OpenFreeMap / OpenMapTiles / OpenStreetMap contributors (ODbL)'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def polygonal(geometry):
    if geometry.is_empty:return Polygon()
    geometry=shapely.make_valid(geometry)
    parts=[x for x in shapely.get_parts(geometry) if x.geom_type in {'Polygon','MultiPolygon'}]
    return shapely.union_all(parts) if parts else Polygon()


def fill_small_holes(geometry, maximum_area):
    if maximum_area<0:raise ValueError('Hole area must be nonnegative')
    polygons=[]
    for p in shapely.get_parts(polygonal(geometry)):
        polygons.append(Polygon(p.exterior,[r for r in p.interiors if Polygon(r).area>maximum_area]))
    return polygonal(shapely.union_all(polygons))


def generalize_corridor(corridor, *, expansion_m=1250., closing_m=2000.,
                        simplification_m=600., hole_area_m2=25e6):
    """Prescribed map scale: coalesce local roads rather than trace every bend."""
    if any(not math.isfinite(x) or x<0 for x in (expansion_m,closing_m,simplification_m,hole_area_m2)):
        raise ValueError('Cartographic parameters must be finite and nonnegative')
    g=polygonal(corridor)
    if g.is_empty:return g
    g=g.buffer(expansion_m,quad_segs=4)
    if closing_m:g=g.buffer(closing_m,quad_segs=4).buffer(-closing_m,quad_segs=4)
    g=g.simplify(simplification_m,preserve_topology=True)
    return fill_small_holes(g,hole_area_m2)


def protect_water(generalized, original_corridor, water):
    """Do not replace a large reservoir by land; retain known road crossings.

    Water is removed only from the generalized drawing. Original reachable-road
    corridors through water (including a bridge) remain visible. This is not a
    claim about shoreline accuracy or driveability of every resulting land point.
    """
    if water.is_empty:return polygonal(generalized)
    return polygonal(generalized.difference(water).union(original_corridor.intersection(water)))


def time_bands(cumulative):
    previous=Polygon();result=[];nested=[]
    for geometry in cumulative:
        current=polygonal(geometry.union(previous))
        band=polygonal(current.difference(previous))
        nested.append(current);result.append(band);previous=current
    return nested,result


def feature(geometry,properties):
    return {'type':'Feature','properties':properties,'geometry':mapping(geometry)}


def tile_range(bounds,z):
    west,south,east,north=bounds;n=2**z
    tx=lambda lon:min(n-1,max(0,int((lon+180)/360*n)))
    ty=lambda lat:min(n-1,max(0,int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)))
    return [(z,x,y) for x in range(tx(west),tx(east)+1) for y in range(ty(north),ty(south)+1)]


def tile_water(raw,x,y,z):
    import mapbox_vector_tile
    decoded=mapbox_vector_tile.decode(raw,default_options={'y_coord_down':True})
    layer=decoded.get('water')
    if not layer:return []
    extent=float(layer['extent']);world=40075016.68557849;half=world/2;n=2**z
    def projected(a,b,zcoord=None):
        a=np.asarray(a);b=np.asarray(b)
        return ((x+a/extent)/n*world-half,half-(y+b/extent)/n*world)
    return [polygonal(transform(projected,shape(f['geometry']))) for f in layer['features']
            if f['geometry']['type'] in {'Polygon','MultiPolygon'}]


def fetch_water(bounds,output,z=8,source_manifest=None):
    """Freeze the exact dated basemap snapshot; no Overpass/current-OSM substitution."""
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    expected=json.loads(Path(source_manifest).read_text()) if source_manifest else None
    if expected:
        if list(bounds)!=expected['requested_bounds_wgs84'] or z!=expected['tile_zoom']:
            raise ValueError('Frozen water coverage does not match the requested map extent')
        tilejson_raw=expected['tilejson_text'].encode()
        if hashlib.sha256(tilejson_raw).hexdigest()!=expected['tilejson_sha256']:
            raise ValueError('Frozen tile descriptor differs')
    else:
        request=urllib.request.Request(TILEJSON_URL,headers={'User-Agent':USER_AGENT,'Referer':'https://zakbu.github.io/'})
        with urllib.request.urlopen(request,timeout=45) as r:tilejson_raw=r.read()
    tilejson=json.loads(tilejson_raw);template=tilejson['tiles'][0]
    if '{z}' not in template or '/planet/' not in template:raise ValueError('Unexpected tile source')
    (output/'openfreemap_tilejson.json').write_bytes(tilejson_raw)
    tiles=tile_range(bounds,z);proof=[];all_polys=[]
    expected_tiles={(r['z'],r['x'],r['y']):r for r in expected['tiles']} if expected else None
    if expected_tiles is not None and set(tiles)!=set(expected_tiles):
        raise ValueError('Frozen tile inventory differs')
    def fetch_one(tile):
        zz,xx,yy=tile;url=template.format(z=zz,x=xx,y=yy)
        req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Referer':'https://zakbu.github.io/'})
        with urllib.request.urlopen(req,timeout=45) as r:raw=r.read()
        if expected_tiles is not None:
            spec=expected_tiles[tile]
            if spec['url']!=url or len(raw)!=spec['bytes'] or hashlib.sha256(raw).hexdigest()!=spec['sha256']:
                raise ValueError('Dated cartographic source tile differs from frozen bytes')
        polygons=tile_water(raw,xx,yy,zz)
        return polygons,{'z':zz,'x':xx,'y':yy,'url':url,'bytes':len(raw),
                         'sha256':hashlib.sha256(raw).hexdigest(),'water_polygon_features':len(polygons)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for polygons,row in pool.map(fetch_one,tiles):all_polys.extend(polygons);proof.append(row)
    if not all_polys:raise ValueError('No water surface was supplied by the dated basemap')
    water_mercator=polygonal(shapely.union_all([shapely.set_precision(g,.1) for g in all_polys]))
    to_wgs=Transformer.from_crs(3857,4326,always_xy=True)
    water=polygonal(transform(to_wgs.transform,water_mercator))
    write(output/'water_mask.geojson',{'type':'FeatureCollection','features':[feature(water,{
        'id':'saratov-cartographic-water','name':'Картографическая водная поверхность',
        'attribution':ATTRIBUTION,'source_tile_template':template,'tile_zoom':z,
        'scope':'Dated display context, not a historical 2021 routing barrier.'})]})
    metadata={'schema':'sgrt.saratov.cartographic_water.v1','source_url':TILEJSON_URL,
        'tilejson_sha256':sha(output/'openfreemap_tilejson.json'),'tilejson_text':tilejson_raw.decode(),'tile_template':template,
        'retrieved_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'requested_bounds_wgs84':list(bounds),'tile_zoom':z,'tiles':proof,
        'source_attribution':ATTRIBUTION,'water_mask_sha256':sha(output/'water_mask.geojson'),
        'water_vertices':int(shapely.get_num_coordinates(water)),
        'limits':['Basemap water is simplified and dated independently of the 2021 road graph.',
                  'Water is used only for cartographic display, never to remove routing edges.']}
    write(output/'water_manifest.json',metadata)
    return output/'water_mask.geojson'


def run(source,water_path,output,*,expansion_m=1250.,closing_m=2000.,simplification_m=600.,
        hole_area_m2=25e6,water_simplification_m=800.,minimum_water_area_m2=5e6):
    source=Path(source);water_path=Path(water_path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    raw=json.loads(source.read_text());wet=json.loads(water_path.read_text())
    forward=Transformer.from_crs(4326,CRS,always_xy=True);backward=Transformer.from_crs(CRS,4326,always_xy=True)
    water=polygonal(shapely.union_all([transform(forward.transform,shape(f['geometry'])) for f in wet['features']]))
    water=polygonal(shapely.union_all([g for g in shapely.get_parts(water) if g.area>=minimum_water_area_m2]))
    water=polygonal(fill_small_holes(water,1e6).simplify(water_simplification_m,preserve_topology=True))
    groups={}
    for f in raw['features']:
        p=f['properties'];cid=p['centre_id'];minute=float(p['minutes'])
        if minute not in THRESHOLDS:raise ValueError('Unexpected time threshold')
        if minute in groups.setdefault(cid,{}):raise ValueError('Duplicate centre/time in source')
        groups[cid][minute]=f
    all_bands=[];all_cumulative=[];diagnostics=[]
    for cid,group in groups.items():
        if set(group)!=set(THRESHOLDS):raise ValueError('Each centre requires all four time thresholds')
        name=group[10.]['properties']['centre_name'];bases=[];generalized=[]
        for minute in THRESHOLDS:
            original=polygonal(transform(forward.transform,shape(group[minute]['geometry'])))
            g=generalize_corridor(original,expansion_m=expansion_m,closing_m=closing_m,
                simplification_m=simplification_m,hole_area_m2=hole_area_m2)
            g=protect_water(g,original.simplify(150.,preserve_topology=True),water)
            # Keep full coordinates after inverse projection. Re-snapping water
            # crossings can collapse a narrow bridge and break topology.
            g=polygonal(transform(backward.transform,g))
            bases.append(original);generalized.append(g)
        nested,bands=time_bands(generalized);centre_bands=[]
        for index,(minute,g,band,original) in enumerate(zip(THRESHOLDS,nested,bands,bases)):
            low=0. if index==0 else THRESHOLDS[index-1]
            props={'id':cid+'__generalized_'+str(int(minute)), 'centre_id':cid,'centre_name':name,
                'name':f'{name}: {int(low)}–{int(minute)} мин', 'minutes':minute,'band_from_minutes':low,
                'class_index':index,'direction':'to_centre',
                'geometry_scope':'generalized_cartographic_time_zone_not_observed_catchment',
                'counts_from':'unchanged_exact_network_cost_tables_not_polygon_inclusion'}
            centre_bands.append(feature(band,props));all_bands.append(centre_bands[-1]);all_cumulative.append(feature(g,props))
            display=transform(forward.transform,g)
            diagnostics.append({'centre_id':cid,'centre_name':name,'minutes':minute,
                'source_cumulative_vertices':int(shapely.get_num_coordinates(original)),
                'generalized_cumulative_vertices':int(shapely.get_num_coordinates(g)),
                'generalized_band_vertices':int(shapely.get_num_coordinates(band)),
                'source_corridor_area_km2':float(original.area/1e6),
                'generalized_display_area_km2':float(display.area/1e6),
                'generalized_area_is_not_accessible_land_or_system_area':True})
        slug=SLUGS.get(cid.rsplit(':',1)[-1],cid.rsplit(':',1)[-1])
        write(output/f'isochrones_generalized_{slug}.geojson',{'type':'FeatureCollection','features':centre_bands})
        write(output/f'layer_{slug}_pending.json',{'id':'saratov-iso-'+slug,'researchId':'sgrt',
            'title':name+': обобщённые зоны времени поездки',
            'description':'Четыре контрастные полосы 0–10, 10–20, 20–30 и 30–60 расчётных минут. Границы обобщены для обзора; число поселений определяется исходным дорожным временем.',
            'datasetId':'PENDING_NEW_RELEASE_DATASET_'+slug,'adapter':'geojson','geometry':'polygon',
            'fields':{'id':'id','name':'name','value':'class_index'},'palette':'categorical','valueLabels':{'0':'0–10 мин','1':'10–20 мин','2':'20–30 мин','3':'30–60 мин'},
            'unit':'временная полоса; интервалы указаны в названиях',
            'period':'Дорожная сеть 2021; отдельная датированная картографическая водная маска',
            'evidence':'model','visibility':'draft'})
    write(output/'isochrones_generalized_bands.geojson',{'type':'FeatureCollection','features':all_bands})
    write(output/'isochrones_generalized_cumulative.geojson',{'type':'FeatureCollection','features':all_cumulative})
    write(output/'geometry_diagnostics.json',diagnostics)
    summary={'schema':'sgrt.saratov.generalized_time_zones.v1','input_geojson_sha256':sha(source),
        'water_mask_sha256':sha(water_path),'time_thresholds_minutes':list(THRESHOLDS),'working_crs':CRS,
        'cartographic_parameters':{'extra_expansion_m':expansion_m,'closing_radius_m':closing_m,
            'simplification_m':simplification_m,'fill_holes_smaller_than_m2':hole_area_m2,
            'water_simplification_m':water_simplification_m,'minimum_display_water_area_m2':minimum_water_area_m2,
            'fill_display_water_islands_smaller_than_m2':1e6,'bridge_corridor_simplification_m':150.},
        'centre_count':len(groups),'band_feature_count':len(all_bands),
        'cartographic_overlay_precision_grid_degrees':0.,
        'palette':'categorical','color_values':[0,1,2,3],
        'source_cumulative_vertices':sum(r['source_cumulative_vertices'] for r in diagnostics),
        'generalized_cumulative_vertices':sum(r['generalized_cumulative_vertices'] for r in diagnostics),
        'route_costs_recalculated':False,'settlement_accessibility_counts_changed':False,
        'limits':['Zones are cartographic generalizations, not travel-time values for every location.',
                  'Morphological expansion/closing do not create trips, membership or service catchments.',
                  'Large display water bodies remain open except for original reachable-road crossings.',
                  'Administrative outlines must not be confused with generalized time-zone boundaries.']}
    write(output/'summary.json',summary);return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--water-mask',type=Path);p.add_argument('--fetch-water',action='store_true')
    p.add_argument('--water-source-manifest',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--water-tile-zoom',type=int,default=8)
    a=p.parse_args();water=a.water_mask
    if a.fetch_water:
        raw=json.loads(a.source.read_text());bounds=shapely.total_bounds([shape(f['geometry']) for f in raw['features']])
        water=fetch_water(bounds,a.output/'water_source',a.water_tile_zoom,a.water_source_manifest)
    if water is None:p.error('A frozen water mask is required; use --fetch-water once to acquire it')
    print(json.dumps(run(a.source,water,a.output),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
