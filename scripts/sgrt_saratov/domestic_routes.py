"""Exact domestic rerouting inside the archived six-anchor travel-time window.

For target c and archived anchor a, let A_a(c) be the original node-to-anchor
cost including the anchor connector. Every path to c of node cost at most
60 - A_a(c) stays inside the original 60-minute node window of a. Removing
roads cannot introduce a cheaper path. Thus H(c)=max_a(60-A_a(c))+connector(c)
certifies NP-to-NP totals up to H(c), also with nonnegative origin connectors.
Outside that horizon a finite path is normally only an upper bound. If it
matches the unrestricted full-graph optimum, the lower and upper bounds meet:
that domestic route is exact too, without imposing a universal time radius.
No service destination is reassigned from these centroid-to-centroid costs.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Point, LineString, MultiLineString, mapping, box
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scripts.sgrt_saratov.country_scope import load_russia
from scripts.sgrt_saratov.domestic_native_edges import inside_directed_arcs

OLD='sgrt/saratov-isochrones20261028/results'
NEW='sgrt/saratov-fields20261029-v2/results'
TOL=1e-7


def sparse_graph(arcs, axis):
    u=np.searchsorted(axis,arcs.u.to_numpy(dtype='int64'))
    v=np.searchsorted(axis,arcs.v.to_numpy(dtype='int64'))
    return csr_matrix((arcs.edge_minutes.to_numpy(),(u,v)),shape=(len(axis),len(axis)))


def connector_allowed(lon,lat,road_xy,mask):
    if not np.isfinite([lon,lat,*road_xy]).all():return False
    if lon==road_xy[0] and lat==road_xy[1]:return bool(mask.covers(Point(lon,lat)))
    return bool(mask.covers(LineString([(lon,lat),road_xy])))


def domestic_status(minutes,horizon,allowed=True):
    if not allowed:return 'endpoint_or_connector_country_scope_unresolved'
    if np.isfinite(minutes) and minutes<=horizon:return 'exact_domestic_cost_within_certificate'
    return 'no_domestic_path_within_certificate'


def route_evidence(minutes,old_global,horizon,allowed=True):
    if not allowed:return 'endpoint_or_connector_country_scope_unresolved'
    if np.isfinite(minutes) and minutes<old_global-TOL:
        raise ValueError('A restricted path cannot beat the unrestricted optimum')
    if np.isfinite(minutes) and abs(minutes-old_global)<=TOL:
        return 'exact_domestic_cost_by_matching_lower_bound'
    if horizon is not None and old_global<=horizon:
        return domestic_status(minutes,horizon,allowed)
    return 'feasible_domestic_path_upper_bound_only' if np.isfinite(minutes) else 'not_resolved_by_available_native_graph'


def choice_margins(links):
    """Describe winner/alternative gaps, without imposing a new choice rule.

    These are the archived physical-provider costs, not the new centroid route
    costs. Half the gap is a worst-case reversal boundary under independent
    opposite signed errors, never an estimated error or confidence interval.
    """
    x=links[links.evidence_scenario.eq('all_dated_known')
        &links.family.isin(['school','medical_basic','grocery'])
        &links.population_2021.gt(0)&~links.known_local_supply
        &links.cost_minutes.notna()].copy()
    if x.duplicated(['origin_id','family']).any():raise ValueError('Repeated origin/family choice')
    x['margin_to_next_known_destination_minutes']=x.second_distinct_destination_minutes-x.cost_minutes
    if x.margin_to_next_known_destination_minutes.dropna().lt(-TOL).any():
        raise ValueError('Second destination is cheaper than the selected nearest site')
    x['opposite_error_reversal_boundary_minutes']=x.margin_to_next_known_destination_minutes/2
    x['cost_basis']='archived_v2_physical_provider_costs_not_domestic_np_centroid_costs'
    rows=[]
    for family,g in x.groupby('family'):
        known=g.margin_to_next_known_destination_minutes.dropna()
        row={'family':family,'inhabited_origins_without_known_local_supply_and_known_first_cost':len(g),
            'choices_with_known_second_destination':len(known),
            'second_destination_unknown':int(g.second_distinct_destination_minutes.isna().sum()),
            'selected_destination_np_identity_unknown':int(g.provider_settlement_id.isna().sum()),
            'exact_primary_ties_in_known_catalogue':int(g.primary_destination_tie_count.gt(1).sum()),
            'median_reversal_boundary_minutes':float(known.median()/2) if len(known) else None}
        for q in [.1,.25,.5,.75,.9]:
            row['margin_p'+str(int(q*100))+'_minutes']=float(known.quantile(q)) if len(known) else None
        rows.append(row)
    return x,pd.DataFrame(rows)


def run(source,boundary,output):
    source,output=Path(source),Path(output);output.mkdir(parents=True,exist_ok=True)
    native=pd.read_parquet(source/OLD/'model/native_edges.parquet')
    saved=pd.read_parquet(source/OLD/'model/road_arrivals.parquet')
    anchors=pd.read_csv(source/OLD/'inputs/centres.csv')
    roster=pd.read_parquet(source/NEW/'fields/regional_roster.parquet').sort_values('row_index').reset_index(drop=True)
    if roster.source_record_id.duplicated().any() or not np.array_equal(roster.row_index,np.arange(len(roster))):
        raise ValueError('Regional matrix axis differs')
    original=np.load(source/NEW/'fields/regional_costs.npy',mmap_mode='r')
    if original.shape!=(len(roster),len(roster)):raise ValueError('Regional matrix shape differs')
    profiles=pd.read_parquet(source/NEW/'physical_official/basic_centre_profiles.parquet')
    profiles=profiles[profiles.evidence_scenario.eq('all_dated_known')&profiles.centre_in_regional_roster]
    if len(profiles)!=511:raise ValueError('Preferred candidate inventory differs')
    doc=pd.read_csv(Path(__file__).resolve().parents[2]/'sgrt/saratov/documented_school_catchments_2025.csv')
    school=pd.read_parquet(source/NEW/'physical_official/functional_links.parquet')
    margins,margin_summary=choice_margins(school)
    margins.to_parquet(output/'service_choice_margins.parquet',index=False,compression='zstd')
    margin_summary.to_csv(output/'service_choice_margin_summary.csv',index=False)
    school=school[school.family.eq('school')&school.evidence_scenario.eq('all_dated_known')]
    target_ids=set(profiles.centre_id)|set(doc.campus_id)|set(anchors.source_record_id)
    for v in school[school.origin_id.isin(doc.origin_id)].coequal_primary_keys_json:
        target_ids.update(k[3:] for k in json.loads(v) if k.startswith('np:'))
    target=roster[roster.source_record_id.isin(target_ids)].copy()
    geometries=shapely.from_wkb(native.native_geometry_wkb.to_numpy())
    bounds=shapely.total_bounds(geometries)
    mask=load_russia(boundary)
    local_mask=mask.intersection(box(bounds[0]-1,bounds[1]-1,bounds[2]+1,bounds[3]+1))
    shapely.prepare(mask)
    shapely.prepare(local_mask)
    axis=np.unique(np.r_[native.u.to_numpy(dtype='int64'),native.v.to_numpy(dtype='int64')])
    baseline=sparse_graph(inside_directed_arcs(native,box(bounds[0]-1,bounds[1]-1,bounds[2]+1,bounds[3]+1)),axis)
    domestic=sparse_graph(inside_directed_arcs(native,local_mask),axis)
    # Original graph vertex positions are preserved, including parallel-road agreement.
    uxy=shapely.get_point(geometries,0);vxy=shapely.get_point(geometries,-1)
    coords=pd.DataFrame({'node':np.r_[native.u,native.v],
        'lon':np.r_[shapely.get_x(uxy),shapely.get_x(vxy)],
        'lat':np.r_[shapely.get_y(uxy),shapely.get_y(vxy)]})
    if coords.groupby('node')[['lon','lat']].agg(lambda s:s.max()-s.min()).to_numpy().max(initial=0)>TOL:
        raise ValueError('Inconsistent native vertex coordinates')
    xy=coords.drop_duplicates('node').set_index('node')
    kept_native=native.loc[shapely.covers(local_mask,geometries)].sort_values(['edge_minutes','way_id'],kind='stable')
    geometry_for_arc={}
    for k,r in kept_native.iterrows():
        if r.oneway>=0:geometry_for_arc.setdefault((int(r.u),int(r.v)),(k,False))
        if r.oneway<=0:geometry_for_arc.setdefault((int(r.v),int(r.u)),(k,True))
    anchor_costs=[];validation=[]
    for a in anchors.itertuples(index=False):
        node=int(a.road_node_index);idx=int(np.searchsorted(axis,node))
        if idx>=len(axis) or axis[idx]!=node:raise ValueError('Anchor outside native graph')
        costs=dijkstra(baseline.T.tocsr(),directed=True,indices=idx)+float(a.snap_km)*4
        expected=saved[saved.centre_id.eq(a.source_record_id)]
        selected=np.searchsorted(axis,expected.node_index.to_numpy(dtype='int64'))
        error=np.abs(costs[selected]-expected.time_minutes_to_centre.to_numpy())
        if not np.isfinite(error).all() or error.max(initial=0)>TOL:
            raise ValueError('Archived global-to-native anchor costs do not reproduce')
        actual=set(axis[costs<=60-TOL]);desired=set(expected.node_index[expected.time_minutes_to_centre<=60-TOL])
        if actual!=desired:raise ValueError('Archived anchor window membership differs')
        anchor_costs.append(costs)
        validation.append({'anchor_id':a.source_record_id,'name':a.name,'checked_nodes':len(expected),
            'maximum_absolute_error_minutes':float(error.max(initial=0))})
    nearest_anchor=np.min(np.stack(anchor_costs),axis=0)
    endpoints=roster.road_endpoint_accepted.eq(True)&roster.road_node_index.notna()&roster.snap_km.between(0,10)
    node_indices=np.full(len(roster),-1,dtype='int64')
    country_ok=np.zeros(len(roster),dtype=bool)
    for i,r in roster[endpoints].iterrows():
        node=int(r.road_node_index);p=int(np.searchsorted(axis,node))
        if p<len(axis) and axis[p]==node:
            node_indices[i]=p
            q=xy.loc[node]
            country_ok[i]=connector_allowed(float(r.lon),float(r.lat),(float(q.lon),float(q.lat)),mask)
    origin_connector=4*roster.snap_km.to_numpy(dtype=float)
    # Reconstruct six road witnesses for the three previously detected school
    # disagreements. The endpoints are settlement points, not school buildings.
    case_pairs={}
    for r in doc[doc.origin_id.notna()&doc.origin_population_2021.gt(0)].itertuples(index=False):
        selected=school[school.origin_id.eq(r.origin_id)].iloc[0]
        keys=json.loads(selected.coequal_primary_keys_json)
        if 'np:'+r.campus_id not in keys:
            case_pairs[(r.origin_id,r.campus_id)]='documented_campus_locality'
            for key in keys:
                if key.startswith('np:'):case_pairs[(r.origin_id,key[3:])]='model_selected_provider_locality'
    comparison=[];target_summary=[];new_anchor_arrays={};witness_features=[]
    max_baseline_error=0.;baseline_cells=0
    for r in target.itertuples(index=False):
        j=int(r.row_index);p=int(node_indices[j])
        if p<0:
            target_summary.append({'target_id':r.source_record_id,'name':r.name,'candidate':r.source_record_id in set(profiles.centre_id),
                'horizon_minutes':None,'status':'outside_certified_native_window'})
            continue
        dest_connector=float(r.snap_km)*4
        # Record the same rounding margin that is used for admission. Otherwise
        # a result just below the raw boundary could be labelled beyond a
        # certificate whose displayed value still included it.
        horizon=(max(0.,60-float(nearest_anchor[p])+dest_connector-TOL)
            if np.isfinite(nearest_anchor[p]) and nearest_anchor[p]<=60 else None)
        before=dijkstra(baseline.T.tocsr(),directed=True,indices=p)
        after,predecessors=dijkstra(domestic.T.tocsr(),directed=True,indices=p,return_predecessors=True)
        before_np=np.full(len(roster),np.inf);after_np=np.full(len(roster),np.inf)
        mapped=node_indices>=0
        before_np[mapped]=before[node_indices[mapped]]+origin_connector[mapped]+dest_connector
        after_np[mapped]=after[node_indices[mapped]]+origin_connector[mapped]+dest_connector
        before_np[j]=0.;after_np[j]=0.
        expected=original[:,j]
        certified=(endpoints.to_numpy()&np.isfinite(expected)&(expected<=horizon)
            if horizon is not None else np.zeros(len(roster),dtype=bool))
        difference=np.abs(before_np[certified]-expected[certified])
        if not np.isfinite(difference).all() or difference.max(initial=0)>TOL:
            raise ValueError('Native costs fail certified v2 matrix comparison: '+r.source_record_id)
        max_baseline_error=max(max_baseline_error,float(difference.max(initial=0)));baseline_cells+=int(certified.sum())
        if r.source_record_id in set(anchors.source_record_id):
            new_anchor_arrays[r.source_record_id]=after+dest_connector
        external=mapped&endpoints.to_numpy()&np.isfinite(expected);external[j]=False
        for i in np.flatnonzero(external):
            o=roster.iloc[int(i)]
            admissible=bool(country_ok[i] and country_ok[j])
            status=route_evidence(after_np[i],float(expected[i]),horizon,admissible)
            exact=status.startswith('exact_domestic_cost_')
            delta=float(after_np[i]-expected[i]) if exact else None
            if delta is not None and delta < -TOL:raise ValueError('Road removal improved certified cost')
            comparison.append({'origin_id':o.source_record_id,'origin_name':o['name'],'population_2021':o.population_2021,
                'target_id':r.source_record_id,'target_name':r.name,'target_is_preferred_candidate':r.source_record_id in set(profiles.centre_id),
                'original_v2_np_minutes':float(expected[i]),'certificate_minutes':horizon,
                'domestic_np_minutes':float(after_np[i]) if exact else None,
                'domestic_feasible_path_upper_bound_minutes':float(after_np[i]) if admissible and np.isfinite(after_np[i]) else None,
                'additional_minutes_exact':delta,'status':status,
                'original_pair_within_time_certificate':bool(certified[i]),
                'np_to_np_cost_is_institution_trip':False})
            key=(o.source_record_id,r.source_record_id)
            if key in case_pairs and admissible and np.isfinite(after_np[i]):
                node=int(node_indices[i]);pieces=[];edge_count=0;path_minutes=0.
                road_start=xy.loc[int(axis[node])]
                if o.lon!=road_start.lon or o.lat!=road_start.lat:
                    pieces.append(LineString([(float(o.lon),float(o.lat)),(float(road_start.lon),float(road_start.lat))]))
                while node!=p:
                    next_node=int(predecessors[node])
                    if next_node<0 or edge_count>len(axis):raise ValueError('Broken native route witness')
                    arc=(int(axis[node]),int(axis[next_node]));k,reverse=geometry_for_arc[arc]
                    g=geometries[k];pieces.append(shapely.reverse(g) if reverse else g)
                    path_minutes+=float(native.iloc[k].edge_minutes);edge_count+=1;node=next_node
                road_end=xy.loc[int(axis[p])]
                if r.lon!=road_end.lon or r.lat!=road_end.lat:
                    pieces.append(LineString([(float(road_end.lon),float(road_end.lat)),(float(r.lon),float(r.lat))]))
                if abs(path_minutes+origin_connector[i]+dest_connector-after_np[i])>TOL:
                    raise ValueError('Reconstructed road witness has a different cost')
                g=MultiLineString(pieces)
                if not mask.covers(g):raise ValueError('Route witness leaves country outline')
                witness_features.append({'type':'Feature','geometry':mapping(g),'properties':{
                    'id':o.source_record_id+'__'+r.source_record_id,
                    'name':str(o['name'])+' → '+str(r.name),
                    'class_index':0 if case_pairs[key]=='documented_campus_locality' else 1,
                    'relation_role':case_pairs[key],'origin_id':o.source_record_id,'target_id':r.source_record_id,
                    'unrestricted_np_cost_lower_bound_minutes':float(expected[i]),
                    'domestic_np_route_upper_bound_minutes':float(after_np[i]),
                    'exactness_status':status,'native_road_segments':edge_count,
                    'geometry_scope':'model_road_path_between_settlement_points_not_school_buildings_or_observed_journey'}})
        target_summary.append({'target_id':r.source_record_id,'name':r.name,'candidate':r.source_record_id in set(profiles.centre_id),
            'horizon_minutes':horizon,'status':('certified_target_window' if horizon is not None else 'native_window_without_time_certificate')
            if country_ok[j] else 'target_connector_country_scope_unresolved'})
    pairs=pd.DataFrame(comparison);targets=pd.DataFrame(target_summary)
    pairs.to_parquet(output/'np_route_comparison.parquet',index=False,compression='zstd')
    (output/'school_case_domestic_paths.geojson').write_text(json.dumps({'type':'FeatureCollection','features':witness_features},ensure_ascii=False,separators=(',',':'))+'\n')
    targets.to_csv(output/'target_certificates.csv',index=False)
    axis_frame=pd.DataFrame({'native_index':np.arange(len(axis)),'node_index':axis})
    axis_frame.to_parquet(output/'native_node_axis.parquet',index=False,compression='zstd')
    np.savez_compressed(output/'domestic_anchor_node_costs.npz',**{k.rsplit(':',1)[-1]:v for k,v in new_anchor_arrays.items()})
    changed=pairs[pairs.additional_minutes_exact.gt(TOL)]
    exact_pairs=pairs[pairs.status.str.startswith('exact_domestic_cost_')]
    unresolved=pairs[~pairs.status.str.startswith('exact_domestic_cost_')]
    # A separate locality-to-locality check for the documented school cases.
    # Physical provider costs remain a different quantity and are not replaced.
    pair_lookup=pairs.set_index(['origin_id','target_id'])
    target_lookup=targets.set_index('target_id')
    ids=roster.set_index('source_record_id').row_index.to_dict()
    queries=[]
    for r in doc[doc.origin_id.notna()&doc.origin_population_2021.gt(0)].itertuples(index=False):
        if r.origin_id==r.campus_id:continue
        selected=school[school.origin_id.eq(r.origin_id)].iloc[0]
        choices=[('documented_campus_locality',r.campus_id)]
        choices.extend(('model_selected_provider_locality',k[3:]) for k in json.loads(selected.coequal_primary_keys_json) if k.startswith('np:'))
        for role,destination in choices:
            key=(r.origin_id,destination)
            result=pair_lookup.loc[key].to_dict() if key in pair_lookup.index else {}
            h=target_lookup.loc[destination,'horizon_minutes'] if destination in target_lookup.index else np.nan
            raw=original[ids[r.origin_id],ids[destination]] if destination in ids else np.nan
            queries.append({'origin_id':r.origin_id,'origin_name':r.origin_name_literal,'target_id':destination,
                'target_name':roster.iloc[ids[destination]]['name'] if destination in ids else None,
                'relation_role':role,'original_v2_np_minutes':float(raw) if np.isfinite(raw) else None,
                'certificate_minutes':float(h) if pd.notna(h) else None,
                'domestic_np_minutes':result.get('domestic_np_minutes'),
                'status':result.get('status','outside_target_certificate'),
                'published_model_provider_cost_minutes':float(selected.cost_minutes) if pd.notna(selected.cost_minutes) else None,
                'provider_cost_is_np_centroid_cost':False})
    pd.DataFrame(queries).to_csv(output/'school_locality_route_checks.csv',index=False)
    road_changes=[]
    for a in anchors.itertuples(index=False):
        part=saved[saved.centre_id.eq(a.source_record_id)]
        positions=np.searchsorted(axis,part.node_index.to_numpy(dtype='int64'))
        after=new_anchor_arrays[a.source_record_id][positions]
        inside=shapely.covers(local_mask,shapely.points(part.lon.to_numpy(),part.lat.to_numpy()))
        old_values=part.time_minutes_to_centre.to_numpy()
        finite=np.isfinite(after)
        if np.any(after[finite]<old_values[finite]-TOL):raise ValueError('Country restriction improves an archived road-node cost')
        road_changes.append({'anchor_id':a.source_record_id,'name':a.name,'archived_road_nodes':len(part),
            'archived_nodes_inside_country_outline':int(inside.sum()),
            'inside_nodes_with_larger_or_infinite_cost':int((inside&(~finite|(after>old_values+TOL))).sum()),
            'archived_nodes_outside_country_outline':int((~inside).sum()),
            'outside_nodes_no_longer_reachable':int((~inside&~finite).sum())})
    summary={'schema':'sgrt.saratov.domestic_routes.v1','native_segments':len(native),'native_nodes':len(axis),
        'baseline_directed_arcs':baseline.nnz,'domestic_directed_arcs':domestic.nnz,
        'anchor_validation':validation,'certified_v2_matrix_cells_checked':baseline_cells,
        'anchor_road_node_changes':road_changes,
        'certificate_rounding_margin_minutes':TOL,
        'maximum_certified_baseline_error_minutes':max_baseline_error,
        'preferred_candidate_axis':len(profiles),'targets_requested':len(target),
        'targets_with_certificate':int(targets.horizon_minutes.notna().sum()),
        'preferred_candidates_with_certificate':int((targets.candidate&targets.horizon_minutes.notna()).sum()),
        'external_pairs_compared':len(pairs),'distinct_origins_compared':pairs.origin_id.nunique(),
        'external_pairs_with_original_time_certificate':int(pairs.original_pair_within_time_certificate.sum()),
        'external_pairs_with_exact_domestic_cost':len(exact_pairs),
        'distinct_origins_with_exact_domestic_cost':exact_pairs.origin_id.nunique(),
        'preferred_candidates_with_exact_domestic_cost':exact_pairs.loc[exact_pairs.target_is_preferred_candidate,'target_id'].nunique(),
        'external_positive_population_pairs_with_exact_cost':int(exact_pairs.population_2021.gt(0).sum()),
        'distinct_positive_population_origins_with_exact_cost':exact_pairs[exact_pairs.population_2021.gt(0)].origin_id.nunique(),
        'school_disagreement_native_path_witnesses':len(witness_features),
        'archived_service_choice_margin_summary':json.loads(margin_summary.to_json(orient='records')),
        'service_choice_error_distribution_estimated':False,
        'service_directions_changed_using_margin':False,
        'changed_exact_domestic_pairs':len(changed),'pairs_not_exact_after_domestic_filter':len(unresolved),
        'pair_status_counts':pairs.status.value_counts().to_dict(),
        'all_national_routes_recomputed':False,'all_saratov_service_choices_recomputed':False,
        'new_confirmed_centre_count':None,
        'scope':'Exact NP-centroid costs established by complete target-specific time windows or a domestic feasible path matching the archived unrestricted full-graph lower bound.',
        'limitations':['Outside a certificate is not evidence of isolation or absence of a Russian path.',
            'NP-centroid costs are not school-building costs and do not reassign service directions.',
            'Straight snap connectors are the original model approximation; country-crossing connectors are held for resnapping.',
            'The country outline is the pinned cartographic source, not an exact legal boundary.']}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    changed.to_csv(output/'changed_exact_pairs.csv',index=False)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--boundary',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.boundary,a.output)
