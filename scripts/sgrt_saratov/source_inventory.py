"""Pin the complete Saratov reference and six exact transport anchors.

No population filter, replacement coordinates, or administrative clipping of
routes is applied. The region boundary is display context from another epoch.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_field_pilot.input_inventory import catalog_source, digest

TRANSPORT = 'research/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/'
REFERENCE = 'sgrt/zero20261025/context/analysis_reference.parquet'
ENDPOINTS = 'sgrt/identity20261026/routes/endpoint_network_quality.parquet'
UNITS = 'sgrt/common20261027/results/level0/units.parquet'
EDGES = 'sgrt/identity20261026/analysis/scenarios/daily_20_school30_wb/daily_edges.parquet'
PREFIX = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'
ANCHORS = {'Саратов':118372, 'Энгельс':118308, 'Балаково':116499,
           'Балашов':116550, 'Новоузенск':117415, 'Питерка':117733}
BOUNDARY_URL = 'https://github.com/ZakBu/russian-settlements-research/releases/download/atlas-boundaries-20261026-v1/RUS-adm1.geojson'
BOUNDARY_SHA256 = 'f8cd605958b61598265c12647d43279ad5ca2605c05509df281f769c330c82f4'
BOUNDARY_BYTES = 13213661
FAMILIES = ('school', 'medical_basic', 'grocery')


def prepare(reference, endpoints, units, edges):
    """Every accepted current point is retained, including zero/uncredited values."""
    region = reference.loc[reference.region.eq('саратовская')].copy()
    current = region.loc[region.source_record_id.notna()].copy()
    if current.source_record_id.duplicated().any() or endpoints.source_record_id.duplicated().any():
        raise ValueError('Current identities must be unique')
    points = current.loc[current.ordinary_spatial_2021.eq(True) & current.accepted_point_present.eq(True)].copy()
    excluded = current.loc[~current.source_record_id.isin(points.source_record_id)].copy()
    history = region.loc[region.source_record_id.isna()].copy()
    epcols = ['source_record_id','road_node_index','snap_km','road_endpoint_accepted',
              'verified_component_id','verified_component_node_count']
    points = points.merge(endpoints[epcols], on='source_record_id', how='left', validate='one_to_one')
    points['accepted_route_endpoint'] = (points.road_endpoint_accepted.eq(True)
        & points.road_node_index.notna() & points.snap_km.between(0,10))
    relevant = edges.loc[edges.origin_id.isin(points.source_record_id) & edges.service_family.isin(FAMILIES)]
    if relevant.duplicated(['origin_id','service_family']).any():
        raise ValueError('One service outcome per settlement and family required')
    for family in FAMILIES:
        part = relevant.loc[relevant.service_family.eq(family)].set_index('origin_id')
        present = points.source_record_id.map(part.known_local_supply).eq(True)
        points[family+'_known_local_presence'] = present
        points[family+'_source_row_known'] = points.source_record_id.isin(part.index)
        points[family+'_known_historical_only'] = points.source_record_id.map(part.provider_historical_source_only).eq(True) & present
    points['known_local_basic_function_count'] = sum(points[f+'_known_local_presence'].astype(int) for f in FAMILIES)
    registered = units.loc[units.is_registered_external_serving_centre.eq(True)]
    if registered.centre_settlement_id.duplicated().any():
        raise ValueError('Published centre identities must be unique')
    ix = registered.set_index('centre_settlement_id')
    points['published_external_serving_centre'] = points.source_record_id.isin(ix.index)
    points['published_external_participant_count'] = points.source_record_id.map(ix.external_participant_count)
    ids = {PREFIX+str(x) for x in ANCHORS.values()}
    anchors = points.loc[points.source_record_id.isin(ids)].copy()
    if len(anchors)!=len(ANCHORS): raise ValueError('A requested anchor is absent')
    for name,number in ANCHORS.items():
        row=anchors.loc[anchors.source_record_id.eq(PREFIX+str(number))].iloc[0]
        if row['name']!=name or row.settlement_type_2021!=('село' if name=='Питерка' else 'город'):
            raise ValueError('Exact anchor identity/type differs: '+name)
        if not row.accepted_route_endpoint: raise ValueError('Anchor road endpoint held: '+name)
    return region,points,excluded,history,anchors,relevant


def build(input_root, road_root, output, boundary_file=None):
    output.mkdir(parents=True, exist_ok=True)
    selections = [('data/zero_catalog_20261025.json',REFERENCE,input_root/REFERENCE),
      ('data/identity_catalog_20261026.json',ENDPOINTS,input_root/ENDPOINTS),
      ('data/common_systems_catalog_20261027.json',UNITS,input_root/UNITS),
      ('data/identity_catalog_20261026.json',EDGES,input_root/EDGES)]
    for n in range(3):
        rel=TRANSPORT+f'graph_npz_parts/part_{n:03d}.bin'
        selections.append(('data/catalog.json',rel,input_root/rel))
    for n in range(24):
        rel=TRANSPORT+f'road_nodes/part_{n:03d}.parquet'
        selections.append(('data/catalog.json',rel,road_root/f'part_{n:03d}.parquet'))
    manifest=[]
    for catalogue,rel,path in selections:
        spec=catalog_source(REPO/catalogue,rel)
        if path.stat().st_size!=spec['bytes'] or digest(path)!=spec['sha256']:
            raise ValueError('Pinned source bytes differ: '+rel)
        manifest.append(spec)
    r=pd.read_parquet(input_root/REFERENCE);e=pd.read_parquet(input_root/ENDPOINTS)
    u=pd.read_parquet(input_root/UNITS)
    needed=['origin_id','service_family','provider_settlement_id','cost_minutes','known_local_supply',
            'local_service_present','l0_admitted','source_id','source_year','provider_historical_source_only']
    schema=pq.read_schema(input_root/EDGES);edge=pq.read_table(input_root/EDGES,columns=[c for c in needed if c in schema.names]).to_pandas()
    region,points,excluded,history,anchors,relevant=prepare(r,e,u,edge)
    region.to_parquet(output/'region_reference.parquet',index=False,compression='zstd')
    points.to_parquet(output/'settlements.parquet',index=False,compression='zstd')
    all_current=pd.concat([points,excluded.reindex(columns=points.columns)],ignore_index=True)
    no_point=~all_current.accepted_point_present.eq(True) | ~all_current.ordinary_spatial_2021.eq(True)
    all_current.loc[no_point,['lat','lon']]=np.nan
    all_current.loc[no_point,'accepted_route_endpoint']=False
    if len(all_current)!=len(points)+len(excluded) or all_current.source_record_id.duplicated().any():
        raise ValueError('All-current identities were lost or duplicated')
    all_current.sort_values('source_record_id').to_parquet(output/'all_current_settlements.parquet',index=False,compression='zstd')
    excluded.to_parquet(output/'current_without_geometry.parquet',index=False,compression='zstd')
    history.to_parquet(output/'historical_only_chains.parquet',index=False,compression='zstd')
    relevant.to_parquet(output/'regional_function_evidence.parquet',index=False,compression='zstd')
    centrecols=['source_record_id','name','region','district','settlement_type_2021','lat','lon',
       'population_2021','credit_2021','budget_population_credit','road_node_index','snap_km',
       'road_endpoint_accepted','verified_component_id','verified_component_node_count']
    anchors[centrecols].to_csv(output/'centres.csv',index=False)
    if boundary_file is None:
        raw=urllib.request.urlopen(BOUNDARY_URL,timeout=60).read()
    else: raw=Path(boundary_file).read_bytes()
    if len(raw)!=BOUNDARY_BYTES or hashlib.sha256(raw).hexdigest()!=BOUNDARY_SHA256:
        raise ValueError('Boundary source differs')
    features=[f for f in json.loads(raw)['features'] if 'saratov' in json.dumps(f['properties']).lower()
              or 'саратов' in json.dumps(f['properties'],ensure_ascii=False).lower()]
    if len(features)!=1: raise ValueError('Unique Saratov source boundary required')
    boundary={'type':'FeatureCollection','features':features}
    (output/'saratov_boundary.geojson').write_text(json.dumps(boundary,ensure_ascii=False,separators=(',',':'))+'\n')
    summary={'schema':'sgrt.saratov_source_inventory.v1','population_reference_sha256':digest(input_root/REFERENCE),
      'region_literal':'саратовская','current_settlement_types':{str(k):int(v) for k,v in points.settlement_type_2021.value_counts(dropna=False).items()},
      'published_centres_own_known_basic_function_count':{str(k):int(v) for k,v in u.loc[u.is_registered_external_serving_centre.eq(True) & u.centre_settlement_id.isin(points.source_record_id),'own_known_basic_function_count'].value_counts().sort_index().items()},
      'region_reference_chains':len(region),'current_2021_records':int(region.source_record_id.notna().sum()),
      'all_current_roster_rows':len(all_current),'all_current_roster_scope':'1821 current identities, including explicit unknown geometry; no coordinate replacement',
      'current_spatial_records':len(points),'current_records_without_accepted_geometry':len(excluded),
      'historical_only_chains':len(history),'current_spatial_population_raw':float(points.population_2021.sum()),
      'current_spatial_population_credited':float(points.loc[points.credit_2021.eq(True)&points.budget_population_credit.eq(True),'population_2021'].sum()),
      'current_spatial_zero_population_records':int(points.population_2021.eq(0).sum()),
      'current_spatial_uncredited_records':int((~points.credit_2021.eq(True)).sum()),
      'accepted_road_endpoints':int(points.accepted_route_endpoint.sum()),
      'published_external_serving_centres':int(points.published_external_serving_centre.sum()),
      'known_local_basic_function_count':{str(k):int(v) for k,v in points.known_local_basic_function_count.value_counts().sort_index().items()},
      'own_function_presence':{f:int(points[f+'_known_local_presence'].sum()) for f in FAMILIES},
      'own_historical_only_presence':{f:int(points[f+'_known_historical_only'].sum()) for f in FAMILIES},
      'anchors':anchors[centrecols].to_dict('records'),'piterka_station_not_anchor':PREFIX+'117688',
      'boundary_source':{'url':BOUNDARY_URL,'bytes':BOUNDARY_BYTES,'sha256':BOUNDARY_SHA256,
         'provider':'Terrae / OpenStreetMap','epoch':'2026.10; 2026-09-28','medium_precision_approx_m':150,
         'properties':features[0]['properties'],'scope':'Display context; not census membership, a water mask, or a route clipping boundary.'},
      'hydrography_mask_available':False,'water_scope':'No pinned independent water polygons identified locally. Do not interpret the administrative boundary as a water mask.',
      'source_files':manifest,'source_file_count':len(manifest),'population_base_unchanged':True,
      'known_services_are_not_verified_operation_or_capacity':True,'service_choice_not_observed_trip':True}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--road-nodes',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--boundary-source',type=Path)
    a=p.parse_args();s=build(a.input_root,a.road_nodes,a.output,a.boundary_source)
    print(json.dumps({k:v for k,v in s.items() if k not in {'source_files','anchors','boundary_source'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
