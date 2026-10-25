#!/usr/bin/env python3
"""Directed nearest suitable service from mixed building and settlement evidence.

Source geometry precision is retained. A settlement-presence record can support
local service without being an extra external attraction seed. Raw nearest
costs have no L0 radius: local membership is decided in the hierarchy module.
"""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/sgrt_mass'))
from routes import load_graph, nearest_for_sites, safe_name, sha256
from site_geometry import read_verified_roads, snap_points

META=['location_precision','evidence_quality','evidence_kind','source_id','source_year',
      'source_snapshot','supply_status','np_identity_basis','default_external_seed_eligible',
      'source_input','source_object_id','operator','provider_name','source_service_code','source_pool',
      'source_population_role','historical_supply_needs_current_confirmation','actual_operational_status_checked',
      'source_status_semantics_verified','counts_as_independent_service_channel','source_isced_level','source_grades',
      'grades_known','grade_evidence_basis','school_program_evidence_json','service_basis',
      'historical_supply_proxy','historical_source_only','saratov_historical_2021_evidence_present',
      'restriction_scope_unknown','actual_operational_status_verified','source_public_scope_check',
      'medical_need_scope','general_adult_profile_evidence','named_child_only_contingent','universal_hospital_suitability_verified','education_need_scope','programme_mismatch_reason',
      'physical_coordinates_observed','external_seed_assumption']
BOOLEAN_META={'default_external_seed_eligible','historical_supply_needs_current_confirmation',
              'actual_operational_status_checked','source_status_semantics_verified','counts_as_independent_service_channel','grades_known','historical_supply_proxy','historical_source_only',
              'saratov_historical_2021_evidence_present','restriction_scope_unknown','actual_operational_status_verified',
              'general_adult_profile_evidence','named_child_only_contingent','universal_hospital_suitability_verified','physical_coordinates_observed'}


def truth(series,default=False):
    """Explicit booleans; strings such as 'false' must not become truthy."""
    if series is None:return None
    return series.map(lambda x: default if pd.isna(x) else x is True or x==1 or str(x).lower()=='true')


def normalise_input(frame,path,kind,endpoints):
    frame=frame.copy()
    required={'provider_id','service_code','supply_status'}
    if not required.issubset(frame):raise ValueError(f'{path}: missing {required-set(frame)}')
    for c in ['source_record_id','source_id','source_year','source_snapshot','evidence_quality','evidence_kind',
              'np_identity_basis','source_object_id','operator','provider_name']:
        if c not in frame:frame[c]=None
    if 'quality' in frame:frame['evidence_quality']=frame.evidence_quality.fillna(frame.quality)
    for alias in ['provider_name','site_name','object_name','source_name','name','subdivision_name']:
        if alias in frame:frame['provider_name']=frame.provider_name.fillna(frame[alias])
    for alias in ['observation_year','snapshot_year']:
        if alias in frame:frame['source_year']=frame.source_year.fillna(frame[alias])
    if 'location_precision' not in frame:
        frame['location_precision']='mapped_site' if kind=='sites' else 'settlement_point_not_institution'
    frame['source_input']=str(path)
    frame['input_kind']=kind
    for target,aliases in [('site_lat',['lat','latitude']),('site_lon',['lon','longitude'])]:
        if target not in frame:
            frame[target]=next((frame[c] for c in aliases if c in frame),np.nan)
        frame[target]=pd.to_numeric(frame[target],errors='coerce')
    if kind=='np':
        # The census source identity, never nearest coordinates, determines the
        # point used for a coarse settlement-presence offer.
        idx=endpoints.set_index('source_record_id')
        for col,site_col in [('lat','site_lat'),('lon','site_lon')]:
            mapped=frame.source_record_id.map(idx[col])
            frame.loc[mapped.notna(),site_col]=mapped[mapped.notna()]
    if 'default_external_seed_eligible' not in frame:
        # Mapped physical offers can seed access; aggregated OSM NP records
        # must be explicitly marked by source builders before being admitted.
        frame['default_external_seed_eligible']=kind=='sites'
    frame['default_external_seed_eligible']=truth(frame.default_external_seed_eligible)
    frame['explicit_source_eligible']=True
    for col in ['eligible','route_eligible']:
        if col in frame:frame['explicit_source_eligible'] &= truth(frame[col])
    for col in META:
        if col not in frame:frame[col]=None
    for col in ['provider_id','service_code','supply_status','source_record_id']:
        frame[col]=frame[col].astype('string')
    for col in META:
        if col in BOOLEAN_META:
            frame[col]=frame[col].map(lambda x: pd.NA if pd.isna(x) else x is True or x==1 or str(x).lower()=='true').astype('boolean')
        else:
            frame[col]=frame[col].map(lambda x: json.dumps(x,ensure_ascii=False) if isinstance(x,(list,dict)) else x).astype('string')
    keep=['provider_id','service_code','source_record_id','site_lat','site_lon','input_kind','explicit_source_eligible',*META]
    return frame[list(dict.fromkeys(keep))]


def prepare_provider_rows(site_frames,np_frames,endpoints,accepted_statuses=('observed','proxy')):
    frames=[normalise_input(d,p,'sites',endpoints) for p,d in site_frames]
    frames += [normalise_input(d,p,'np',endpoints) for p,d in np_frames]
    if not frames:raise ValueError('No source offers supplied')
    frame=pd.concat(frames,ignore_index=True)
    if frame[['provider_id','service_code']].isna().any().any():raise ValueError('Provider and service IDs are required')
    frame['accepted_supply_status']=frame.supply_status.isin(accepted_statuses)
    frame['admitted_offer']=frame.accepted_supply_status & frame.explicit_source_eligible
    # Duplicate source records cannot become extra virtual origins. Merging
    # conflicting geometry under one source identifier would hide an error.
    key=['service_code','provider_id']
    if frame.duplicated(key).any():
        for _,g in frame[frame.duplicated(key,keep=False)].groupby(key,dropna=False):
            for col in ['source_record_id','site_lat','site_lon','location_precision']:
                if g[col].nunique(dropna=False)>1:raise ValueError(f'Conflicting duplicate provider identity: {g.provider_id.iloc[0]} {col}')
        frame=frame.sort_values(['service_code','provider_id','source_input']).drop_duplicates(key)
    frame['coordinate_available']=frame.site_lat.between(-90,90)&frame.site_lon.between(-180,180)
    # A nearest settlement suggestion is deliberately absent from identity.
    frame['np_identity_was_invented_from_nearest_point']=False
    return frame.reset_index(drop=True)


def admit_prepared_providers(providers,accepted_statuses):
    """Reuse geometry, never silently reuse another scenario's admission."""
    required={'supply_status','explicit_source_eligible','default_external_seed_eligible','accepted_snap'}
    if not required.issubset(providers):raise ValueError('Prepared provider eligibility evidence missing')
    out=providers.copy()
    out['accepted_supply_status']=out.supply_status.isin(accepted_statuses)
    out['admitted_offer']=out.accepted_supply_status & out.explicit_source_eligible
    out['external_seed_eligible']=out.admitted_offer & out.default_external_seed_eligible
    out['road_endpoint_accepted']=out.accepted_snap.eq(True)&out.external_seed_eligible
    return out


def attach_road_seeds(providers,roads,*,mapped_max_snap_km=2.,np_max_snap_km=10.):
    out=providers.copy()
    good=out.coordinate_available.eq(True)
    columns=['road_node_index','road_osm_node','road_snap_lat','road_snap_lon','snap_km','weak_component',
             'nearest_vertex_distance_tie','nearest_vertex_tie_osm_ids_json','destination_connector_minutes']
    for col in columns:out[col]=None if 'json' in col else np.nan
    out['accepted_snap']=False
    if good.any():
        snapped=snap_points(out.loc[good].reset_index(drop=True),roads,max_snap_km=max(mapped_max_snap_km,np_max_snap_km))
        for col in columns:
            if col in snapped:out.loc[good,col]=snapped[col].to_numpy()
        limit=np.where(out.loc[good,'input_kind'].eq('sites'),mapped_max_snap_km,np_max_snap_km)
        out.loc[good,'accepted_snap']=snapped.snap_km.to_numpy()<=limit
    out['external_seed_eligible']=out.admitted_offer & out.default_external_seed_eligible
    out['road_endpoint_accepted']=out.accepted_snap.eq(True)&out.external_seed_eligible
    out['connector_scenario_kmh']=15.
    out['road_snap_is_not_a_mapped_driveway']=True
    out['snap_limit_km']=np.where(out.input_kind.eq('sites'),mapped_max_snap_km,np_max_snap_km)
    return out


def reuse_prepared_geometry(providers,cached):
    """Reuse only source-ID and coordinate-identical sites on the same graph.

    Service roles, NP identity, eligibility and source dates come from the new
    inputs. A new or moved point is an error and must be snapped afresh.
    """
    keys=['provider_id','input_kind','site_lat','site_lon']
    geometry=['road_node_index','road_osm_node','road_snap_lat','road_snap_lon','snap_km','weak_component',
              'nearest_vertex_distance_tie','nearest_vertex_tie_osm_ids_json','destination_connector_minutes',
              'accepted_snap','connector_scenario_kmh','road_snap_is_not_a_mapped_driveway','snap_limit_km']
    available=[c for c in geometry if c in cached]
    if {'road_node_index','snap_km','accepted_snap'}-set(available):raise ValueError('Geometry cache misses road evidence')
    check=cached[keys+available].drop_duplicates()
    if check.duplicated(keys).any():raise ValueError('Geometry cache has conflicting road mappings')
    out=providers.merge(check,on=keys,how='left',validate='many_to_one',indicator='_geometry_match',sort=False)
    out['geometry_reuse_basis']='same_source_id_and_coordinates'
    # A role-specific aggregate ID can change while the census settlement
    # point remains the same. This does not identify physical institutions.
    missing_np=out._geometry_match.ne('both')&out.input_kind.eq('np')&out.source_record_id.notna()
    if missing_np.any():
        np_keys=['source_record_id','input_kind','site_lat','site_lon']
        lookup=cached[cached.input_kind.eq('np')][np_keys+available].drop_duplicates()
        if lookup.duplicated(np_keys).any():raise ValueError('Conflicting cached settlement-point geometry')
        recovered=out.loc[missing_np,np_keys].merge(lookup,on=np_keys,how='left',validate='many_to_one',indicator='_np_match',sort=False)
        if recovered._np_match.eq('both').all():
            for col in available:out.loc[missing_np,col]=recovered[col].to_numpy()
            out.loc[missing_np,'_geometry_match']='both'
            out.loc[missing_np,'geometry_reuse_basis']='same_census_np_identity_and_coordinates_not_building_identity'
    if out._geometry_match.ne('both').any():raise ValueError('Geometry cache cannot represent new or moved source points; snap afresh')
    out=out.drop(columns='_geometry_match')
    out['external_seed_eligible']=out.admitted_offer & out.default_external_seed_eligible
    out['road_endpoint_accepted']=out.accepted_snap.eq(True)&out.external_seed_eligible
    return out


def additional_origins(endpoints,context,roads):
    if context.empty:return endpoints.copy()
    required={'source_record_id','lat','lon'}
    if not required.issubset(context):raise ValueError('Additional origins require identity and independent coordinates')
    if context.source_record_id.isna().any() or not context.source_record_id.is_unique:raise ValueError('Invalid additional context origin IDs')
    if set(context.source_record_id)&set(endpoints.source_record_id):raise ValueError('Additional origin duplicates an ordinary census point')
    if 'budget_population_credit' in context and truth(context.budget_population_credit).any():raise ValueError('Additional city contexts cannot enter the ordinary population budget')
    c=context.copy();c['site_lat']=pd.to_numeric(c.lat);c['site_lon']=pd.to_numeric(c.lon)
    snap=snap_points(c,roads,max_snap_km=10.)
    c['road_node_index']=snap.road_node_index;c['snap_km']=snap.snap_km
    c['road_snap_lat']=snap.road_snap_lat;c['road_snap_lon']=snap.road_snap_lon
    c['road_endpoint_accepted']=snap.accepted_snap
    c['road_endpoint_status']=np.where(snap.accepted_snap,'additional_nonadditive_context_road_snap','additional_context_without_accepted_road_snap')
    c['road_connector_over_2km']=snap.snap_over_2km
    c['origin_id']=c.source_record_id
    c['budget_population_credit']=False;c['working_credit_present']=False;c['credited_population_2021']=np.nan
    c['origin_is_additional_context']=True
    e=endpoints.copy();e['origin_is_additional_context']=False
    if 'budget_population_credit' not in e:e['budget_population_credit']=e.working_credit_present.fillna(False) if 'working_credit_present' in e else True
    return pd.concat([e,c.drop(columns=['site_lat','site_lon'])],ignore_index=True)


def nearest_service(endpoints,providers,reverse_graph,service_code):
    p=providers[providers.service_code.eq(service_code)&providers.admitted_offer].copy()
    for col in META:
        if col not in p:p[col]=pd.NA
    if p.provider_id.duplicated().any():raise ValueError('Duplicate routed provider ID')
    p=p.sort_values('provider_id').reset_index(drop=True)
    out=nearest_for_sites(endpoints,p,reverse_graph,service_code)
    # Pick an evidence representative for within-NP presence, not a clinic for
    # a particular patient. Source confidence affects that representation only;
    # it never changes the complete directed external travel cost.
    local=p[p.source_record_id.isin(endpoints.source_record_id)].copy()
    local['_status_rank']=local.supply_status.map({'observed':0,'proxy':1}).fillna(2)
    local['_precision_rank']=np.where(local.input_kind.eq('sites').fillna(False),0,1)
    local=local.sort_values(['_status_rank','_precision_rank','provider_id']).drop_duplicates('source_record_id')
    own=endpoints.source_record_id.map(local.set_index('source_record_id').provider_id)
    out.loc[own.notna(),'selected_provider_id']=own.loc[own.notna()].to_numpy()
    idx=p.set_index('provider_id')
    # Refresh all old-format selected metadata after the local representative.
    for source,target in {'source_record_id':'selected_provider_source_record_id',
            'site_lat':'selected_provider_site_lat','site_lon':'selected_provider_site_lon','snap_km':'provider_snap_km',
            **{c:'selected_provider_'+c for c in ['source_id','source_year','np_identity_basis','supply_status']}}.items():
        out[target]=out.selected_provider_id.map(idx[source])
    for col in META+['input_kind','external_seed_eligible']:
        out['provider_'+col]=out.selected_provider_id.map(idx[col])
    for col in ['evidence_quality','evidence_kind','source_id','source_year','source_snapshot']:
        out[col]=out['provider_'+col]
    out['provider_settlement_id']=out.selected_provider_source_record_id
    out['provider_site_id']=out.selected_provider_id
    out['provider_lat']=out.selected_provider_site_lat;out['provider_lon']=out.selected_provider_site_lon
    from routes import haversine_km
    out['point_separation_km']=haversine_km(out.lat,out.lon,out.provider_lat,out.provider_lon)
    out['location_precision']=out.provider_location_precision
    out['unconstrained_nearest_provider_id']=out.unconstrained_nearest_site_provider_id
    out['unconstrained_nearest_cost_minutes']=out.unconstrained_nearest_site_cost_minutes
    out['known_offer_records']=out.known_provider_sites
    out['routable_external_provider_seeds']=out.routable_known_provider_sites
    out=out.drop(columns=['known_provider_sites','routable_known_provider_sites'])
    out['specific_institution_choice_established']=False
    out['raw_nearest_has_no_time_cutoff']=True
    out['l0_membership_not_decided_by_transport']=True
    out['origin_is_additional_context']=endpoints.origin_is_additional_context.to_numpy() if 'origin_is_additional_context' in endpoints else False
    out['budget_population_credit']=endpoints.budget_population_credit.to_numpy() if 'budget_population_credit' in endpoints else endpoints.working_credit_present.fillna(False).to_numpy() if 'working_credit_present' in endpoints else True
    out['candidate_unit_kind']=np.where(out.provider_input_kind.eq('sites').fillna(False),'mapped_service_site','settlement_function_presence_point')
    out.loc[out.provider_site_id.isna(),'candidate_unit_kind']='no_supported_provider'
    return out


def bounded_pairs(endpoints,graph,pairs,limit_minutes):
    """Exact requested directed pairs; never infer a national N-squared matrix.

    Search stops at the explicit numerical limit. Missing road route means an
    unknown motor-vehicle relation, not geographical independence.
    """
    from scipy.sparse.csgraph import dijkstra
    if not np.isfinite(limit_minutes) or limit_minutes<0:raise ValueError('Finite pair-search limit required')
    if not {'origin_id','destination_id'}.issubset(pairs):raise ValueError('Requested pair IDs missing')
    if pairs.duplicated(['origin_id','destination_id']).any():raise ValueError('Duplicate requested directed pair')
    ep=endpoints.set_index('source_record_id');rows=[]
    for source,g in pairs.groupby('origin_id',sort=True):
        valid=source in ep.index and bool(ep.loc[source,'road_endpoint_accepted'])
        costs=None
        if valid:
            a=ep.loc[source];costs=dijkstra(graph,directed=True,indices=int(a.road_node_index),limit=limit_minutes)
        for item in g.itertuples(index=False):
            destination=item.destination_id
            row={'origin_id':source,'destination_id':destination,'cost_minutes':np.nan,
                 'pair_search_limit_minutes':limit_minutes,'network_search_limit_minutes':limit_minutes,'pair_status':'road_endpoint_unknown',
                 'observed_flow':False,'assignment_established':False}
            if valid and destination in ep.index and bool(ep.loc[destination,'road_endpoint_accepted']):
                b=ep.loc[destination];value=costs[int(b.road_node_index)]
                if np.isfinite(value):
                    row['network_minutes']=float(value);row['connector_minutes']=float((a.snap_km+b.snap_km)*4)
                    row['cost_minutes']=row['network_minutes']+row['connector_minutes']
                    row['pair_status']='directed_road_cost_found'
                else:row['pair_status']='no_directed_road_path_within_numerical_search_limit'
            rows.append(row)
        del costs
    return pd.DataFrame(rows)


def independent_nearest_samples(endpoints,providers,graph,assignments,origin_ids):
    """Forward one-origin Dijkstra versus reverse weighted multisource result.

    Every eligible seed of each requested service is inspected, including its
    destination connector. This checks global optimal cost on the same graph,
    not observed travel behaviour or inventory completeness.
    """
    from scipy.sparse.csgraph import dijkstra
    ep=endpoints.set_index('source_record_id');rows=[]
    prepared={}
    for service,table in assignments.items():
        seeds=providers[providers.service_code.eq(service)&providers.admitted_offer&providers.road_endpoint_accepted].copy()
        prepared[service]=(seeds,table.set_index('origin_id'))
    for origin in origin_ids:
        if origin not in ep.index or not bool(ep.loc[origin,'road_endpoint_accepted']):continue
        point=ep.loc[origin]
        distance=dijkstra(graph,directed=True,indices=int(point.road_node_index))
        for service,(seeds,predictions) in prepared.items():
            if origin not in predictions.index:continue
            prediction=predictions.loc[origin]
            costs=distance[seeds.road_node_index.to_numpy(dtype=np.int64)]+(seeds.snap_km.to_numpy(float)+float(point.snap_km))*4
            finite=np.isfinite(costs);minimum=float(np.min(costs[finite])) if finite.any() else np.nan
            raw=float(prediction.unconstrained_nearest_cost_minutes) if pd.notna(prediction.unconstrained_nearest_cost_minutes) else np.nan
            candidate=prediction.unconstrained_nearest_provider_id
            matched=(bool(np.isclose(raw,minimum,rtol=0,atol=1e-7)) if np.isfinite(minimum) else not np.isfinite(raw))
            chosen_cost=np.nan
            if pd.notna(candidate) and candidate in set(seeds.provider_id):
                chosen_cost=float(costs[np.flatnonzero(seeds.provider_id.eq(candidate).to_numpy())[0]])
            rows.append({'origin_id':origin,'origin_name':point.get('name'), 'region':point.get('region'),
                'service_code':service,'eligible_seed_count':len(seeds),'selected_provider_id':candidate,
                'multisource_raw_minutes':raw,'independent_forward_minimum_minutes':minimum,
                'independent_selected_provider_minutes':chosen_cost,
                'absolute_difference_minutes':abs(raw-minimum) if np.isfinite(raw) and np.isfinite(minimum) else np.nan,
                'equal_cost':matched,'observed_trip_validation':False})
        del distance
    return pd.DataFrame(rows)


def origin_geometry_fingerprint(endpoints):
    cols=['source_record_id','lat','lon','road_node_index','snap_km','road_endpoint_accepted']
    d=endpoints[cols].sort_values('source_record_id').copy()
    return hashlib.sha256(pd.util.hash_pandas_object(d,index=False).to_numpy().tobytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sites',type=Path,nargs='*',default=[])
    p.add_argument('--np-supply',type=Path,nargs='*',default=[])
    p.add_argument('--endpoints',type=Path,required=True)
    p.add_argument('--additional-origins',type=Path)
    p.add_argument('--road-nodes',type=Path)
    p.add_argument('--road-origins',type=Path)
    p.add_argument('--graph-dir',type=Path,required=True)
    p.add_argument('--catalog',type=Path,default=REPO/'data/catalog.json')
    p.add_argument('--accepted-statuses',default='observed,proxy')
    p.add_argument('--services',help='Optional comma-separated service classes')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--geometry-cache',type=Path,help='Reuse verified geometry for an exact source-ID/coordinate-identical subset; no silent moved points')
    p.add_argument('--prepared-providers',type=Path,help='Already snapped exact provider rows; source hashes retained in their summary')
    p.add_argument('--pairs',type=Path)
    p.add_argument('--pair-limit-minutes',type=float,default=180.)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    ep=pd.read_parquet(args.endpoints)
    if not ep.source_record_id.is_unique:raise ValueError('Duplicate origin identities')
    inputs=[args.endpoints,*args.sites,*args.np_supply]
    if args.additional_origins:inputs.append(args.additional_origins)
    provenance={str(f):sha256(f) for f in inputs}
    roads=None;road_provenance={}
    if (not args.prepared_providers and not args.geometry_cache and not args.pairs) or args.additional_origins:
        if not args.road_nodes or not args.road_origins:p.error('Road coordinates and origin index required for fresh geometric snaps')
        roads,road_provenance=read_verified_roads(args.road_nodes,args.catalog,args.graph_dir,args.road_origins)
    if args.additional_origins:
        ep=additional_origins(ep,pd.read_parquet(args.additional_origins),roads)
    else:
        if 'origin_is_additional_context' not in ep:ep['origin_is_additional_context']=False
        if 'budget_population_credit' not in ep:
            ep['budget_population_credit']=ep.working_credit_present.fillna(False) if 'working_credit_present' in ep else True
    ep.to_parquet(args.output/'endpoints.parquet',index=False,compression='zstd')
    if args.pairs:
        graph=load_graph(args.graph_dir)
        result=bounded_pairs(ep,graph,pd.read_parquet(args.pairs),args.pair_limit_minutes)
        result.to_parquet(args.output/'requested_pair_costs.parquet',index=False,compression='zstd')
        (args.output/'pair_run.json').write_text(json.dumps({'requested_pair_input_sha256':sha256(args.pairs),
            'origin_geometry_fingerprint':origin_geometry_fingerprint(ep),'network_search_limit_minutes':args.pair_limit_minutes,
            'found_pairs':int(result.cost_minutes.notna().sum()),'requested_pairs':len(result),
            'code_sha256':sha256(Path(__file__))},ensure_ascii=False,indent=2)+'\n')
        return
    if args.prepared_providers:
        prep_path=args.prepared_providers.parent/'provider_preparation.json'
        if not prep_path.is_file():raise ValueError('Prepared provider seeds require provider_preparation.json')
        prep=json.loads(prep_path.read_text())
        if prep['provider_seeds_sha256']!=sha256(args.prepared_providers):raise ValueError('Prepared provider seeds differ from their manifest')
        if prep['origin_geometry_fingerprint']!=origin_geometry_fingerprint(ep):raise ValueError('Prepared NP seeds do not refer to the same origin geometry')
        provider_rows=admit_prepared_providers(pd.read_parquet(args.prepared_providers),args.accepted_statuses.split(','))
        provenance[str(args.prepared_providers)]=sha256(args.prepared_providers)
        provenance[str(prep_path)]=sha256(prep_path)
        road_provenance=prep['road_geometry']
    else:
        provider_rows=prepare_provider_rows([(f,pd.read_parquet(f)) for f in args.sites],[(f,pd.read_parquet(f)) for f in args.np_supply],ep,tuple(args.accepted_statuses.split(',')))
        cache_provenance={}
        if args.geometry_cache:
            cache_manifest_path=args.geometry_cache.parent/'provider_preparation.json'
            cache_meta=json.loads(cache_manifest_path.read_text())
            cache_sha=sha256(args.geometry_cache)
            if cache_meta['provider_seeds_sha256']!=cache_sha:raise ValueError('Geometry cache differs from its manifest')
            if cache_meta['origin_geometry_fingerprint']!=origin_geometry_fingerprint(ep):raise ValueError('Cached NP geometry uses a different origin frame')
            road_provenance=cache_meta['road_geometry']
            provider_rows=reuse_prepared_geometry(provider_rows,pd.read_parquet(args.geometry_cache))
            cache_provenance={'source_seed_sha256':cache_sha,'source_manifest_sha256':sha256(cache_manifest_path),
                              'reuse_rule':'same_source_id_or_same_census_np_point_and_exact_coordinates; new_service_metadata_retained'}
            provenance[str(args.geometry_cache)]=cache_sha
        else:provider_rows=attach_road_seeds(provider_rows,roads)
        seed_path=args.output/'provider_road_seeds.parquet'
        provider_rows.to_parquet(seed_path,index=False,compression='zstd')
        prep={'source_input_sha256':provenance,'provider_seeds_sha256':sha256(seed_path),
              'origin_geometry_fingerprint':origin_geometry_fingerprint(ep),'road_geometry':road_provenance,
              'accepted_supply_statuses':args.accepted_statuses.split(','),
              'mapped_site_max_snap_km':2.,'settlement_point_max_snap_km':10.,
              'code_sha256':sha256(Path(__file__)),'population_is_not_attraction_weight':True,'geometry_cache':cache_provenance}
        (args.output/'provider_preparation.json').write_text(json.dumps(prep,ensure_ascii=False,indent=2)+'\n')
    del roads;gc.collect()
    if args.prepare_only:return
    graph=load_graph(args.graph_dir)
    reverse=graph.T.tocsr();del graph;gc.collect()
    services=sorted(set(provider_rows.loc[provider_rows.admitted_offer,'service_code']))
    if args.services:services=[x for x in services if x in args.services.split(',')]
    target=args.output/'nearest';target.mkdir(exist_ok=True)
    summaries=[]
    for service in services:
        t=time.monotonic();result=nearest_service(ep,provider_rows,reverse,service)
        result['source_supply_sha256']=json.dumps(provenance,sort_keys=True)
        result.to_parquet(target/(safe_name(service)+'.parquet'),index=False,compression='zstd')
        summary={'service_code':service,'origins':len(result),'known_offer_records':int(result.known_offer_records.iloc[0]),
                 'routable_external_provider_seeds':int(result.routable_external_provider_seeds.iloc[0]),
                 'known_local':int(result.known_local_supply.sum()),'finite_nearest':int(result.cost_minutes.notna().sum()),
                 'external_known_np':int((result.provider_settlement_id.notna()&result.provider_settlement_id.ne(result.origin_id)).sum()),
                 'mapped_site_unknown_np':int((result.provider_settlement_id.isna()&result.provider_site_id.notna()).sum()),
                 'precision_counts':result.location_precision.value_counts(dropna=False).to_dict(),
                 'elapsed_seconds':round(time.monotonic()-t,3)}
        # JSON keys cannot be pandas.NA.
        summary['precision_counts']={str(k):int(v) for k,v in summary['precision_counts'].items()}
        summaries.append(summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    meta={'origin_rows':len(ep),'ordinary_origin_rows':int((~ep.origin_is_additional_context).sum()),
          'additional_nonadditive_context_origins':int(ep.origin_is_additional_context.sum()),
          'source_input_sha256':provenance,'road_geometry':road_provenance,
          'services':summaries,'raw_nearest_time_cutoff':None,'observed_flows':False,
          'l0_admission_is_separate':True,'accepted_supply_statuses':args.accepted_statuses.split(','),'elapsed_seconds':round(time.monotonic()-started,3)}
    (args.output/'summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
