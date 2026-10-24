#!/usr/bin/env python3
"""Snap mapped education sites to road geometry without inventing NP identity.

All map features retain their real OSM representative coordinates, including
objects without address locality. A nearest reference settlement is a labelled
proxy only. Road vertices and graph share the pinned access-v2 index.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

GRAPH_SHA256='a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366'
N_VERTICES=9533601
RADIUS_KM=6371.0088
ROAD_PREFIX='research/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/road_nodes/'
STRICT_IDENTITY='explicit_locality_and_exact_legacy_census_bridge'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def sphere_xyz(lat,lon):
    lat=np.radians(np.asarray(lat,dtype=float));lon=np.radians(np.asarray(lon,dtype=float))
    return np.column_stack([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])


def chord_km(chord):
    return 2*RADIUS_KM*np.arcsin(np.clip(np.asarray(chord)/2,0,1))


def snap_points(points,roads,*,max_snap_km=10.,tie_atol_km=1e-8):
    """Nearest great-circle vertex on a sphere, with deterministic exact ties.

    Selecting an access vertex is a geometry operation. It does not assert that
    an institution belongs to the nearest settlement or that the connector is a
    mapped driveway. All distances beyond the explicit screen are retained.
    """
    if max_snap_km < 0 or not np.isfinite(max_snap_km):raise ValueError('Invalid snap distance')
    if roads.empty or roads[['lat','lon','node_index','osm_id']].isna().any().any():raise ValueError('Invalid road vertices')
    if not roads.node_index.is_unique or not roads.osm_id.is_unique:raise ValueError('Nonunique road vertex identity')
    if points[['site_lat','site_lon']].isna().any().any():raise ValueError('Missing site coordinates')
    if not points.site_lat.between(-90,90).all() or not points.site_lon.between(-180,180).all():raise ValueError('Invalid site coordinates')
    xyz=sphere_xyz(roads.lat,roads.lon)
    query=sphere_xyz(points.site_lat,points.site_lon)
    tree=cKDTree(xyz)
    distances,indices=tree.query(query,k=2 if len(roads)>1 else 1,workers=1)
    if len(roads)==1:
        d1=np.asarray(distances);chosen=np.asarray(indices);ties=np.zeros(len(points),bool)
    else:
        d1=distances[:,0];chosen=indices[:,0].copy()
        ties=np.abs(chord_km(distances[:,1])-chord_km(d1))<=tie_atol_km
    osm=roads.osm_id.to_numpy();tie_ids={}
    for i in np.flatnonzero(ties):
        candidates=np.asarray(tree.query_ball_point(query[i],float(d1[i]+tie_atol_km/RADIUS_KM*1.01)),dtype=np.int64)
        dist=chord_km(np.linalg.norm(xyz[candidates]-query[i],axis=1))
        close=candidates[np.abs(dist-chord_km(d1[i]))<=tie_atol_km]
        chosen[i]=close[np.argmin(osm[close])]
        tie_ids[i]=json.dumps(sorted(map(int,osm[close])))
    selected=roads.iloc[chosen]
    result=points.copy().reset_index(drop=True)
    result['road_node_index']=selected.node_index.to_numpy(dtype=np.int64)
    result['road_osm_node']=selected.osm_id.to_numpy(dtype=np.int64)
    result['road_snap_lat']=selected.lat.to_numpy(dtype=float)
    result['road_snap_lon']=selected.lon.to_numpy(dtype=float)
    if 'weak_component' in selected:result['weak_component']=selected.weak_component.to_numpy()
    result['snap_km']=chord_km(np.linalg.norm(xyz[chosen]-query,axis=1))
    result['accepted_snap']=result.snap_km.le(max_snap_km)
    result['snap_over_2km']=result.snap_km.gt(2)
    result['nearest_vertex_distance_tie']=ties
    result['nearest_vertex_tie_osm_ids_json']=[tie_ids.get(i,'[]') for i in range(len(result))]
    result['tie_policy']='lowest_osm_id_among_equal_great_circle_distance_vertices'
    result['destination_connector_minutes']=result.snap_km*4
    result['connector_scenario_kmh']=15.
    return result


def read_verified_roads(directory,catalog,graph_dir,origin_index):
    cat=json.loads(Path(catalog).read_text())
    rows={r['path']:r for r in cat['files'] if r['path'].startswith(ROAD_PREFIX)}
    parts=sorted(Path(directory).glob('part_*.parquet'))
    if len(parts)!=len(rows) or len(parts)!=24:raise ValueError('Incomplete road coordinate parts')
    hashes=[]
    for part in parts:
        relative=ROAD_PREFIX+part.name;row=rows[relative];obj=cat['objects'][row['blob']]
        h=sha(part)
        if part.stat().st_size!=row['bytes'] or h!=obj['sha256']:raise ValueError('Road vertex part differs: '+part.name)
        hashes.append({'path':relative,'bytes':part.stat().st_size,'sha256':h})
    roads=pd.read_parquet(directory,columns=['node_index','osm_id','lat','lon','weak_component'])
    if len(roads)!=N_VERTICES or not np.array_equal(roads.node_index,np.arange(N_VERTICES)):raise ValueError('Road vertex index differs')
    graph_hash=hashlib.sha256()
    for part in sorted((Path(graph_dir)/'graph_npz_parts').glob('part_*.bin')):
        with part.open('rb') as f:
            for block in iter(lambda:f.read(4*1024*1024),b''):graph_hash.update(block)
    if graph_hash.hexdigest()!=GRAPH_SHA256:raise ValueError('Road graph SHA256 differs')
    old=pd.read_parquet(origin_index)
    old=old[old.road_node_index.notna()].copy()
    selected=roads.iloc[old.road_node_index.to_numpy(dtype=np.int64)]
    osm_equal=np.array_equal(selected.osm_id.to_numpy(),old.road_osm_node.to_numpy(dtype=np.int64))
    lat_error=np.max(np.abs(selected.lat.to_numpy()-old.road_snap_lat.to_numpy()))
    lon_error=np.max(np.abs(selected.lon.to_numpy()-old.road_snap_lon.to_numpy()))
    if not osm_equal or lat_error>1e-12 or lon_error>1e-12:raise ValueError('Vertex mapping disagrees with national NP road snaps')
    return roads,{'vertices':len(roads),'graph_sha256':GRAPH_SHA256,'parts':hashes,
                 'prior_np_snap_records_checked':len(old),'all_prior_np_osm_nodes_equal':bool(osm_equal),
                 'maximum_prior_snap_lat_difference_degrees':float(lat_error),'maximum_prior_snap_lon_difference_degrees':float(lon_error)}


def prepare_sites(objects,reference):
    objects=objects.copy()
    allowed={'school_general','preschool','vocational_education','higher_education'}
    objects=objects[objects.service_code.isin(allowed)&objects.possible_duplicate_of.isna()].copy()
    objects['provider_id']=objects.canonical_site_id.fillna(objects.site_id)
    if objects.duplicated(['provider_id','service_code']).any():raise ValueError('Unreconciled canonical site duplicates')
    objects['site_lat']=objects.lat;objects['site_lon']=objects.lon
    objects['proxy_reference_source_record_id']=objects.source_record_id.where(objects.current_identity_status.ne(STRICT_IDENTITY))
    objects['source_record_id']=objects.source_record_id.where(objects.current_identity_status.eq(STRICT_IDENTITY))
    # This status describes a mapped feature's presence, not proof of activity
    # at a particular day or of ownership by a settlement.
    temporal=objects.temporal_eligible.fillna(True).astype(bool) if 'temporal_eligible' in objects else pd.Series(True,index=objects.index)
    lifecycle=objects.lifecycle_eligible.fillna(True).astype(bool) if 'lifecycle_eligible' in objects else pd.Series(True,index=objects.index)
    objects['supply_status']=np.where(~temporal,'excluded_temporal',np.where(~lifecycle,'excluded_lifecycle','observed'))
    objects['eligible_site_supply']=temporal&lifecycle
    objects['site_evidence_kind']='mapped_education_feature_OSM_snapshot_20210101'
    objects['geometry_direct']=True
    objects['site_coordinate_is_building_entrance']=False
    objects['geometry_role_scope']='source_node_or_vertex_mean_representative_not_confirmed_entrance'
    objects['capacity_total']=np.nan
    ref=reference[reference.lat.notna()&reference.lon.notna()].copy()
    distances,indices=cKDTree(sphere_xyz(ref.lat,ref.lon)).query(sphere_xyz(objects.site_lat,objects.site_lon),k=1,workers=1)
    selected=ref.iloc[indices]
    objects['nearest_reference_source_record_id']=selected.source_record_id.to_numpy()
    objects['nearest_reference_name']=selected.name.to_numpy()
    objects['nearest_reference_region']=selected.region.to_numpy()
    objects['nearest_reference_distance_km']=chord_km(distances)
    objects['nearest_reference_is_identity']=False
    objects['established_flow']=False
    objects['observation_year']=2021
    return objects


def build(args):
    start=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=True)
    roads,verification=read_verified_roads(args.road_nodes,args.catalog,args.graph_dir,args.road_origins)
    if args.resnap_np_endpoints:
        endpoints=pd.read_parquet(args.resnap_np_endpoints)
        fresh=endpoints[~endpoints.road_endpoint_accepted].copy()
        keep=['source_record_id','root','name','region','lat','lon','population','working_credit_present','accepted_point_present']
        points=fresh[keep].copy()
        points['prior_road_endpoint_status']=fresh.road_endpoint_status
        points['prior_road_node_index']=fresh.road_node_index
        points['prior_snap_km']=fresh.snap_km
        points['site_lat']=points.lat;points['site_lon']=points.lon
        result=snap_points(points,roads,max_snap_km=args.max_snap_km)
        result['road_identity_basis']='fresh_great_circle_snap_of_current_accepted_census_point'
        result['legacy_identity_used']=False
        result['census_identity_changed']=False
        result['road_endpoint_accepted']=result.accepted_snap
        result['road_endpoint_status']=np.where(result.accepted_snap,'accepted_fresh_current_point_road_snap','fresh_current_point_road_snap_over10km')
        result['current_point_reference_year']=2021
        result.to_parquet(out/'fresh_np_resnaps.parquet',index=False,compression='zstd')
        result.to_csv(out/'fresh_np_resnaps.csv',index=False)
        verification.update({'input_endpoint_sha256':sha(args.resnap_np_endpoints),'points_resnapped':len(result),
            'newly_routable':int(result.road_endpoint_accepted.sum()),'still_over_10km':int((~result.road_endpoint_accepted).sum()),
            'newly_routable_by_prior_reason':result[result.accepted_snap].groupby('prior_road_endpoint_status').size().to_dict(),
            'source_identity_changed':False,'elapsed_seconds':time.monotonic()-start})
        (out/'fresh_np_summary.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in verification.items() if k!='parts'},ensure_ascii=False,indent=2))
        return
    raw=pd.read_parquet(args.objects)
    if not {'temporal_eligible','lifecycle_eligible'}<=set(raw):
        raise ValueError('Geometry routing input must include the education parser temporal/lifecycle screens; rebuild osm_object_links')
    reference=pd.read_parquet(args.reference)
    sites=prepare_sites(raw,reference)
    snapped=snap_points(sites,roads,max_snap_km=args.max_snap_km)
    columns=['provider_id','site_id','canonical_site_id','source_record_id','proxy_reference_source_record_id',
             'nearest_reference_source_record_id','nearest_reference_name','nearest_reference_region','nearest_reference_distance_km','nearest_reference_is_identity',
             'service_code','site_lat','site_lon','road_node_index','road_osm_node','road_snap_lat','road_snap_lon','weak_component','snap_km','accepted_snap','snap_over_2km',
             'nearest_vertex_distance_tie','nearest_vertex_tie_osm_ids_json','tie_policy','destination_connector_minutes','connector_scenario_kmh',
             'supply_status','site_evidence_kind','geometry_direct','site_coordinate_is_building_entrance','geometry_role','geometry_role_scope',
             'eligible_site_supply','temporal_status','temporal_eligible','lifecycle_exclusion_reason','lifecycle_eligible','source_start_date','source_end_date',
             'current_identity_status','name','source_address_locality','source_address_state','source_id','observation_year','capacity_total','established_flow']
    snapped=snapped[columns]
    snapped.to_parquet(out/'site_road_seeds.parquet',index=False,compression='zstd')
    snapped.to_csv(out/'site_road_seeds.csv',index=False)
    grouped=[]
    for code,g in snapped.groupby('service_code'):
        grouped.append({'service_code':code,'mapped_sites':len(g),'road_snap_accepted':int(g.accepted_snap.sum()),
                        'eligible_site_supply':int(g.eligible_site_supply.sum()),
                        'excluded_temporal_or_lifecycle':int((~g.eligible_site_supply).sum()),
                        'strict_settlement_identity':int(g.source_record_id.notna().sum()),'not_assigned_settlement_identity':int(g.source_record_id.isna().sum()),
                        'snap_over_2km':int(g.snap_over_2km.sum()),'snap_over_10km':int(g.snap_km.gt(10).sum()),
                        'nearest_vertex_ties':int(g.nearest_vertex_distance_tie.sum()),'snap_p50_km':float(g.snap_km.median()),'snap_p99_km':float(g.snap_km.quantile(.99))})
    coverage=pd.DataFrame(grouped);coverage.to_csv(out/'coverage.csv',index=False)
    verification.update({'input_objects_sha256':sha(args.objects),'input_reference_sha256':sha(args.reference),
                         'raw_eligible_objects':len(raw),'deduplicated_mapped_sites':len(snapped),'road_snap_accepted':int(snapped.accepted_snap.sum()),
                         'eligible_site_supply':int(snapped.eligible_site_supply.sum()),'excluded_temporal_or_lifecycle':int((~snapped.eligible_site_supply).sum()),
                         'strict_settlement_identity':int(snapped.source_record_id.notna().sum()),'geometry_without_invented_np_identity':int(snapped.source_record_id.isna().sum()),
                         'max_snap_km_scenario':args.max_snap_km,'coverage':grouped,'elapsed_seconds':time.monotonic()-start,
                         'limitations':['OSM mapped presence is not independently observed operation or a complete school inventory.',
                                        'Most features use a vertex-mean representative, which need not lie inside the feature or at an entrance.',
                                        'Straight connectors at15km/h are explicit scenarios, not mapped driveways.',
                                        'A nearest reference NP is not accepted identity; catchments may remain institution-centred without a known NP centre.',
                                        'Educational grades and institutional capacity remain unknown unless separately sourced.']})
    (out/'summary.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in verification.items() if k!='parts'},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['road-nodes','graph-dir','road-origins','output']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['objects','reference']:p.add_argument('--'+name,type=Path)
    p.add_argument('--resnap-np-endpoints',type=Path,help='Separate fresh snaps of currently unavailable accepted NP points; never changes census identity or site seeds')
    p.add_argument('--catalog',type=Path,default=Path('data/catalog.json'))
    p.add_argument('--max-snap-km',type=float,default=10.)
    args=p.parse_args()
    if not args.resnap_np_endpoints and (not args.objects or not args.reference):p.error('Site mode requires --objects and --reference')
    build(args)
