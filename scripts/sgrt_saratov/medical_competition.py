"""Compare local primary-care and physician destinations on the same road map.

The display window is fixed independently of medical supply. National directed
competition is solved first. Shared school-map helpers retain native road bends
and the exact minimum-cost envelope, while the drawing remains deliberately
coarse. No patient trips, referral rules or verified operating capacity inferred.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape,mapping
from shapely.ops import transform
from pyproj import Transformer

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_mass.routes import load_graph,weighted_multisource,GRAPH_SHA256
from scripts.sgrt_saratov.school_competition import (PITERKA,THRESHOLDS,edge_intervals,
    fraction_geometry,omit_empty_display_features,sha,write)
from scripts.sgrt_saratov.generalized_maps import generalize_corridor,protect_water,polygonal

FAMILIES=('medical_basic','medical_physician')


def prepare_medical_seeds(catalog,family):
    if family not in FAMILIES:raise ValueError('Unsupported medical need family')
    seeds=catalog[catalog.family.eq(family)&catalog.routable_provider.eq(True)].copy()
    if seeds.empty:raise ValueError('No known routable provider for '+family)
    if seeds.catalog_id.duplicated().any():raise ValueError('Nonunique physical/source provider identity')
    seeds=seeds.sort_values('catalog_id').reset_index(drop=True)
    seeds['source_record_id']=seeds.correctsource_record_id
    seeds['anchor_precision']=seeds.location_precision
    return seeds


def display_groups(tables,roster):
    """Choose a common small legend, never a functional-centre rank or weight."""
    counts=pd.concat(tables,ignore_index=True).dropna(subset=['destination_np_id']).groupby('destination_np_id').size()
    ids=sorted(counts.index,key=lambda sid:(sid!=PITERKA,-int(counts.loc[sid]),str(sid)))[:4]
    names=roster.set_index('source_record_id')['name'].to_dict()
    classes={str(sid):i for i,sid in enumerate(ids)}
    labels={str(i):str(names.get(sid,'Медицинский центр')) for sid,i in classes.items()}
    labels['4']='Другие известные медицинские площадки'
    return classes,labels


def compare_medical_nodes(output):
    output=Path(output);tables=[]
    for family in FAMILIES:
        frame=pd.read_parquet(output/(family+'_road_nodes.parquet'))
        tables.append(frame[['node_index','minutes_to_nearest_known_provider']].rename(
            columns={'minutes_to_nearest_known_provider':family+'_minutes'}))
    d=tables[0].merge(tables[1],on='node_index',validate='one_to_one')
    finite=np.isfinite(d.medical_basic_minutes)&np.isfinite(d.medical_physician_minutes)
    d['physician_minus_basic_minutes']=np.where(finite,d.medical_physician_minutes-d.medical_basic_minutes,np.nan)
    d.to_parquet(output/'road_node_function_comparison.parquet',index=False,compression='zstd')
    return {'road_nodes_compared':len(d),'finite_in_both':int(finite.sum()),
        'basic_faster_nodes':int((d.physician_minus_basic_minutes>1e-8).sum()),
        'same_time_nodes':int((d.physician_minus_basic_minutes.abs()<=1e-8).sum()),
        'physician_faster_nodes':int((d.physician_minus_basic_minutes< -1e-8).sum()),
        'median_basic_minutes':float(d.loc[finite,'medical_basic_minutes'].median()) if finite.any() else None,
        'median_physician_minutes':float(d.loc[finite,'medical_physician_minutes'].median()) if finite.any() else None,
        'denominator':'road_nodes_in_map_window_not_people_or_settlements'}


def run(graph_dir,native_path,reachable_path,provider_path,roster_path,water_path,output,resume=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    roster=pd.read_parquet(roster_path);catalog=pd.read_parquet(provider_path)
    native=pd.read_parquet(native_path);roads=shapely.from_wkb(native.native_geometry_wkb.to_numpy())
    forward=Transformer.from_crs(4326,32638,always_xy=True);back=Transformer.from_crs(32638,4326,always_xy=True)
    reach=pd.read_parquet(reachable_path);source=reach[reach.centre_id.eq(PITERKA)&reach.minutes.eq(60.)].iloc[0]
    window_metric=shapely.from_wkb(source.reachable_road_geometry_wkb).buffer(250)
    window=transform(back.transform,window_metric);display_window=generalize_corridor(window_metric,expansion_m=1500.)
    keep=shapely.intersects(roads,window);native=native.loc[keep].reset_index(drop=True);roads=roads[keep]
    raw=json.loads(Path(water_path).read_text());water=polygonal(shapely.union_all([shape(f['geometry']) for f in raw['features']]))
    water=transform(forward.transform,water).intersection(window_metric.buffer(5000))
    water=polygonal(shapely.union_all([g for g in shapely.get_parts(water) if g.area>=5e6])).simplify(800,preserve_topology=True)
    graph=load_graph(graph_dir);reverse=graph.T.tocsr();del graph
    node_axis=np.unique(np.r_[native.u.to_numpy(),native.v.to_numpy()]).astype('int64')
    tables=[];facts=[]
    for family in FAMILIES:
        seeds=prepare_medical_seeds(catalog,family)
        print(json.dumps({'event':'medical_competition_search','family':family,'national_provider_seeds':len(seeds)}),flush=True)
        if resume and (output/(family+'_road_nodes.parquet')).exists():
            old=pd.read_parquet(output/(family+'_seeds.parquet'));cols=['catalog_id','road_node_index','destination_connector_minutes']
            if not old[cols].equals(seeds[cols]):raise ValueError('Resume medical source seeds differ')
            nodes=pd.read_parquet(output/(family+'_road_nodes.parquet'))
            if not np.array_equal(nodes.node_index.to_numpy(),node_axis):raise ValueError('Resume medical node axis differs')
            distance=np.full(reverse.shape[0],np.inf);selected=np.full(reverse.shape[0],-1,dtype='int64')
            distance[node_axis]=nodes.minutes_to_nearest_known_provider;selected[node_axis]=nodes.seed_index
        else:
            distance,selected=weighted_multisource(reverse,seeds.road_node_index.to_numpy(dtype='int64'),seeds.destination_connector_minutes.to_numpy(dtype=float))
            nodes=pd.DataFrame({'node_index':node_axis,'minutes_to_nearest_known_provider':distance[node_axis],'seed_index':selected[node_axis]})
        nodes.to_parquet(output/(family+'_road_nodes.parquet'),index=False,compression='zstd')
        seeds.to_parquet(output/(family+'_seeds.parquet'),index=False,compression='zstd')
        pieces=[]
        for i,road in enumerate(native.itertuples(index=False)):
            for a,b,exit,band,mid in edge_intervals(distance[road.u],distance[road.v],float(road.edge_minutes),int(road.oneway)):
                seed_index=int(selected[road.u if exit=='u' else road.v])
                if seed_index<0:continue
                geom=fraction_geometry(np.asarray(roads[i].coords),a,b)
                if geom is None or geom.is_empty:continue
                s=seeds.iloc[seed_index]
                pieces.append({'family':family,'u':int(road.u),'v':int(road.v),'way_id':int(road.way_id),
                    'start_fraction':a,'end_fraction':b,'exit_endpoint':exit,'minutes_band_upper':THRESHOLDS[band],
                    'midpoint_minutes':mid,'provider_id':s.catalog_id,'destination_key':s.provider_destination_key,
                    'destination_np_id':s.source_record_id,'provider_name':s.provider_name,
                    'anchor_precision':s.anchor_precision,'historical_only':bool(s.historical_only),
                    'operation_verified':bool(s.operation_verified),'geometry_crs':'EPSG:4326','geometry_wkb':shapely.to_wkb(geom)})
        table=pd.DataFrame(pieces)
        if table.empty:raise ValueError('No nonempty medical road pieces in the display window: '+family)
        table.to_parquet(output/(family+'_road_competition.parquet'),index=False,compression='zstd');tables.append(table)
        facts.append({'family':family,'national_provider_seeds':len(seeds),'historical_provider_seeds':int(seeds.historical_only.sum()),
            'sampled_road_nodes':len(node_axis),'road_nodes_within_60_minutes':int((nodes.minutes_to_nearest_known_provider<=60.).sum()),
            'road_destination_groups':int(table.destination_key.nunique()),'road_pieces':len(table)})
        del distance,selected
    classes,labels=display_groups(tables,roster);names=roster.set_index('source_record_id')['name'].to_dict()
    for table,fact in zip(tables,facts):
        features=[]
        for key,part in table.groupby('destination_key',sort=True):
            line=shapely.union_all(shapely.from_wkb(part.geometry_wkb.to_numpy()))
            metric=transform(forward.transform,line);corridor=shapely.union_all(shapely.buffer(shapely.get_parts(metric),250,quad_segs=2))
            coarse=protect_water(generalize_corridor(corridor),corridor,water).intersection(display_window)
            p=part.iloc[0];sid=str(p.destination_np_id) if pd.notna(p.destination_np_id) else None
            name=names.get(sid,p.provider_name)
            if pd.isna(name):name='Медицинская площадка: населённый пункт не установлен'
            geom=polygonal(shapely.set_precision(polygonal(transform(back.transform,coarse)),1e-7))
            features.append({'type':'Feature','properties':{'id':key,'name':str(name),'destination_np_id':sid,
                'class_index':classes.get(sid,4),'family':fact['family'],'provider_records_not_capacity':int(part.provider_id.nunique()),
                'historical_source_present':bool(part.historical_only.any()),'actual_operation_of_all_sites_verified':bool(part.operation_verified.all()),
                'interpretation':'generalized_display_of_nearest_known_provider_roads_not_observed_patient_flows'},'geometry':mapping(geom)})
        features,omissions=omit_empty_display_features(features)
        if any(not shape(f['geometry']).is_valid for f in features):raise ValueError('Invalid medical display geometry')
        write(output/(fact['family']+'_zones.geojson'),{'type':'FeatureCollection','features':features})
        fact.update(displayed_destination_groups=len(features),empty_display_omissions=omissions,
            geometry_vertices=int(sum(shapely.get_num_coordinates(shape(f['geometry'])) for f in features)))
    summary={'schema':'sgrt.saratov.medical_competition.v1','graph_sha256':GRAPH_SHA256,
        'display_window':'same_Piterka60_native_road_window_as_school_example_not_medical_service_radius',
        'families':facts,'road_node_function_comparison':compare_medical_nodes(output),'display_centre_classes':classes,'centre_display_class_labels':labels,
        'display_class_selection':'Piterka first if present, then three known NP with most road pieces across both functions; display only, no model effect',
        'cartography':{'road_corridor_m':250,'expansion_m':1250,'closing_m':2000,'simplification_m':600,'fill_holes_under_m2':25e6,
            'water_simplification_m':800,'minimum_water_component_m2':5e6,'coordinate_precision_degrees':1e-7},
        'limits':['Primary-care offer and physician offer are separate needs; they are not interchangeable centre masses.',
            'All dated known supply is used; historical source flags remain, current operation is not verified.',
            'Provider counts are not capacity; nearest known site is not a demonstrated patient journey or referral.',
            'A deterministic minimum-cost winner is shown; all equal-cost alternatives are not enumerated.',
            'Only road pieces within sixty minutes are drawn; farther destinations remain in full regional functional tables.',
            'Generalized polygons may overlap; no off-road household accessibility inferred.'],
        'inputs':[{'path':str(p),'sha256':sha(p),'bytes':Path(p).stat().st_size} for p in [native_path,reachable_path,provider_path,roster_path,water_path]]}
    write(output/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True);return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['graph-dir','native-path','reachable-path','provider-path','roster-path','water-path','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--resume',action='store_true');a=p.parse_args();run(**vars(a))

if __name__=='__main__':main()
