#!/usr/bin/env python3
"""Bounded service overlays and evidence-dependent upward aggregation.

The partition is an operational partition of demand points with equal provider
profiles, not a declaration of observed SGRT boundaries. Provider anchors are
stored separately and are never counted again as residents of every area.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4<<20),b''):digest.update(block)
    return digest.hexdigest()


def dumps(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def unique_json(values):
    return dumps(sorted(set(str(x) for x in values if pd.notna(x))))


def stable_id(level,scenario,signature):
    return f'L{level}:'+hashlib.sha256((str(scenario)+'|'+signature).encode()).hexdigest()[:24]


def provider_keys(frame):
    known=frame.provider_settlement_id.notna()
    out=pd.Series(pd.NA,index=frame.index,dtype='string')
    out.loc[known]='np:'+frame.loc[known,'provider_settlement_id'].astype(str)
    sites=~known&frame.provider_site_id.notna()
    out.loc[sites]='site:'+frame.loc[sites,'provider_site_id'].astype(str)
    return out


def canonical_edges(edges,admission='l0_admitted'):
    out=edges.copy()
    needed={'origin_id','service_family','provider_settlement_id','provider_site_id','cost_minutes',admission}
    if not needed.issubset(out):raise ValueError('Missing edge fields: '+str(sorted(needed-set(out))))
    if 'scenario_id' not in out:out['scenario_id']='source_aware_current_service_scenario'
    if out[['origin_id','service_family','scenario_id']].isna().any().any():raise ValueError('Null origin/family/scenario')
    if out.duplicated(['scenario_id','origin_id','service_family']).any():
        raise ValueError('More than one provider per origin/family/scenario: select an explicit source scenario first')
    if out[admission].isna().any() or not out[admission].isin([True,False]).all():raise ValueError('Admission must be explicit boolean')
    out[admission]=out[admission].astype(bool)
    out['provider_key']=provider_keys(out)
    costs=pd.to_numeric(out.cost_minutes,errors='coerce')
    if (out[admission]&(~np.isfinite(costs)|costs.lt(0)|out.provider_key.isna())).any():
        raise ValueError('Admitted edge lacks a provider or finite nonnegative directed cost')
    out['cost_minutes']=costs
    for col in ['source_id','source_year','evidence_kind','admission_basis','provider_name','provider_lat','provider_lon']:
        if col not in out:out[col]=pd.NA
    if 'admission_limit_minutes' not in out:out['admission_limit_minutes']=np.nan
    limits=pd.to_numeric(out.admission_limit_minutes,errors='coerce')
    if (out[admission]&limits.notna()&costs.gt(limits+1e-8)).any():raise ValueError('Admitted edge exceeds its own service time bound')
    out['admission_limit_minutes']=limits
    if (out[admission]&out.admission_basis.isna()).any():raise ValueError('Admitted edge needs explicit admission basis')
    return out


def coordinate_diameter(latitudes,longitudes):
    lat=pd.to_numeric(latitudes,errors='coerce').to_numpy(dtype=float,na_value=np.nan)
    lon=pd.to_numeric(longitudes,errors='coerce').to_numpy(dtype=float,na_value=np.nan)
    good=np.isfinite(lat)&np.isfinite(lon)
    if not good.any():return np.nan
    p=np.unique(np.column_stack([lat[good],lon[good]]),axis=0)
    if len(p)==1:return 0.
    lat,lon=np.deg2rad(p[:,0]),np.deg2rad(p[:,1]);maximum=0.
    for start in range(0,len(p),256):
        a=np.sin((lat[start:start+256,None]-lat)/2)**2+np.cos(lat[start:start+256,None])*np.cos(lat)*np.sin((lon[start:start+256,None]-lon)/2)**2
        maximum=max(maximum,float(np.max(a)))
    return float(2*6371.0088*np.arcsin(np.sqrt(min(1.,maximum))))


def geodesic_diameter(frame):
    """Exact NP-point great-circle diameter, not a road round-trip claim."""
    return coordinate_diameter(frame.lat,frame.lon)


def demographic_summaries(members,reference):
    cols=['source_record_id','lat','lon','population_role']+[f'{field}_{year}' for year in [2002,2010,2021] for field in ['population','credit']]
    ref=reference[reference.source_record_id.notna()][cols].copy()
    if not ref.source_record_id.is_unique:raise ValueError('Reference source_record_id must be unique')
    rows=members[['unit_id','origin_id']].merge(ref,left_on='origin_id',right_on='source_record_id',how='left',validate='many_to_one')
    ordinary=rows.population_role.eq('ordinary_settlement_record')
    rows['positive_credited_member']=ordinary&rows.credit_2021.fillna(False)&rows.population_2021.gt(0)
    for y in [2002,2010,2021]:
        rows[f'known_{y}']=ordinary&rows[f'credit_{y}'].fillna(False)&rows[f'population_{y}'].notna()
        rows[f'credited_population_{y}']=rows[f'population_{y}'].where(rows[f'known_{y}'])
    grouped=rows.groupby('unit_id',sort=False)
    out=grouped.agg(member_records=('origin_id','size'),positive_credited_member_records=('positive_credited_member','sum'))
    for y in [2002,2010,2021]:
        out[f'member_population_{y}_credited_sum']=grouped[f'credited_population_{y}'].sum(min_count=1)
        out[f'member_population_{y}_known_records']=grouped[f'known_{y}'].sum()
    for a,b in [(2002,2021),(2010,2021)]:
        cohort=rows[f'known_{a}']&rows[f'known_{b}'];g=rows[cohort].groupby('unit_id',sort=False)
        out[f'comparable_records_{a}_{b}']=g.size().reindex(out.index).fillna(0).astype(int)
        out[f'complete_member_demography_{a}_{b}']=out[f'comparable_records_{a}_{b}'].eq(out.member_records)
        start=g[f'population_{a}'].sum(min_count=1).reindex(out.index);end=g[f'population_{b}'].sum(min_count=1).reindex(out.index)
        direction=pd.Series('unknown',index=out.index)
        known=start.notna()&end.notna();direction.loc[known&end.gt(start)]='growth';direction.loc[known&end.lt(start)]='decline';direction.loc[known&end.eq(start)]='unchanged'
        out[f'member_direction_{a}_{b}']=direction
    good=rows.lat.notna()&rows.lon.notna();counts=good.groupby(rows.unit_id).sum()
    out['member_geodesic_diameter_km']=np.where(out.index.to_series().map(counts).gt(0),0.,np.nan)
    # Most service overlays contain one NP. Only multi-point groups need an
    # exact pairwise geometric diagnostic; this does not search road pairs.
    for uid,positions in grouped.indices.items():
        if len(positions)>1:out.loc[uid,'member_geodesic_diameter_km']=geodesic_diameter(rows.iloc[positions])
    return out.reset_index()


def aggregate_anchors(selected):
    keys=['unit_id','service_family','provider_key'];grouped=selected.groupby(keys,sort=False,dropna=False)
    out=grouped.size().rename('origin_records').to_frame()
    out['provider_settlement_id']=grouped.provider_settlement_id.first()
    out['maximum_directed_minutes']=grouped.cost_minutes.max()
    out['median_directed_minutes']=grouped.cost_minutes.median()
    columns={'provider_site_id':'provider_site_ids_json','source_id':'source_ids_json','source_year':'source_years_json',
        'admission_basis':'admission_bases_json','evidence_kind':'evidence_kinds_json'}
    if 'quality' in selected:columns['quality']='source_quality_json'
    precision='location_precision' if 'location_precision' in selected else 'provider_geometry_kind' if 'provider_geometry_kind' in selected else None
    if precision:columns[precision]='provider_location_precision_json'
    # Most values are constant for one provider profile. Use vectorized first
    # and distinct counts, and invoke a Python set only for truly mixed groups.
    for source,target in columns.items():
        values=selected[source].astype('string')
        g=values.groupby([selected[k] for k in keys],sort=False,dropna=False)
        first=g.first();counts=g.nunique(dropna=True)
        encoded=first.map(lambda v:'[]' if pd.isna(v) else dumps([str(v)]))
        mixed=set(counts.index[counts.gt(1)])
        if mixed:
            for key,positions in g.indices.items():
                if key in mixed:encoded.loc[key]=unique_json(values.iloc[positions])
        out[target]=encoded.reindex(out.index)
    if 'source_quality_json' not in out:out['source_quality_json']='["unknown"]'
    if 'provider_location_precision_json' not in out:out['provider_location_precision_json']='["unknown"]'
    out['anchor_location_precision']=['known_settlement_multiple_physical_providers_possible' if str(k[2]).startswith('np:') else 'physical_provider_site_unknown_np' for k in out.index]
    out['anchor_population_is_nonadditive']=True;out['reverse_route_or_pairwise_road_diameter_established']=False
    geometry=selected[keys].copy()
    geometry['lat']=pd.to_numeric(selected.provider_lat,errors='coerce')
    geometry['lon']=pd.to_numeric(selected.provider_lon,errors='coerce')
    geometry=geometry[np.isfinite(geometry.lat)&np.isfinite(geometry.lon)]
    if len(geometry):
        geo_group=geometry.groupby(keys,sort=False,dropna=False)
        sizes=geo_group.size().reindex(out.index).fillna(0)
        out['provider_geodesic_extent_km']=np.where(sizes.gt(0),0.,np.nan)
        distinct=geo_group[['lat','lon']].nunique()
        variable=distinct.index[distinct.gt(1).any(axis=1)]
        for key in variable:
            e=geo_group.get_group(key)
            out.loc[key,'provider_geodesic_extent_km']=coordinate_diameter(e.lat,e.lon)
    else:out['provider_geodesic_extent_km']=np.nan
    order=['provider_settlement_id','provider_site_ids_json','source_ids_json','source_years_json','admission_bases_json','evidence_kinds_json','source_quality_json',
        'origin_records','maximum_directed_minutes','median_directed_minutes','anchor_location_precision','anchor_population_is_nonadditive',
        'reverse_route_or_pairwise_road_diameter_established','provider_location_precision_json','provider_geodesic_extent_km']
    return out[order].reset_index()


def build_level_zero(edges,reference,expected_families,core_families=None):
    families=sorted(set(expected_families))
    if not families:raise ValueError('Declare at least one daily service family')
    core=sorted(set(core_families if core_families is not None else families))
    if not core or not set(core).issubset(families):raise ValueError('Core families must be a nonempty subset of profile families')
    frame=canonical_edges(edges)
    if not set(frame.service_family).issubset(families):raise ValueError('Non-daily family present in L0 input')
    origin_mask=reference.analysis_origin.fillna(False) if 'analysis_origin' in reference else reference.ordinary_spatial_2021.fillna(False)
    origins=reference.loc[origin_mask&reference.source_record_id.notna(),'source_record_id'].astype(str)
    if not origins.is_unique:raise ValueError('Ordinary spatial origins must be unique')
    if not frame.origin_id.isin(origins).all():raise ValueError('Unknown origin outside accepted spatial frame')
    if not frame.loc[frame.provider_settlement_id.notna(),'provider_settlement_id'].isin(reference.source_record_id.dropna()).all():
        raise ValueError('A declared provider settlement is outside the accepted identity reference')
    parts=[];units=[];anchor_parts=[]
    for scenario,g in frame.groupby('scenario_id',sort=True):
        selected=g[g.l0_admitted].copy()
        profile=selected.pivot(index='origin_id',columns='service_family',values='provider_key').reindex(index=origins,columns=families)
        signatures=[]
        for origin,values in zip(profile.index,profile.itertuples(index=False,name=None)):
            values=[None if pd.isna(v) else str(v) for v in values]
            signatures.append(dumps({'providers':list(zip(families,values)),**({'unresolved_origin':str(origin)} if not any(values) else {})}))
        profile['profile_signature']=signatures;profile['unit_id']=[stable_id(0,scenario,s) for s in signatures]
        profile['origin_id']=profile.index;profile['scenario_id']=scenario
        members=profile[['unit_id','origin_id','scenario_id','profile_signature']].reset_index(drop=True);parts.append(members)
        lookup=members.set_index('origin_id').unit_id
        selected['unit_id']=selected.origin_id.map(lookup)
        for values_row in profile.drop_duplicates('unit_id')[['unit_id','profile_signature',*families]].itertuples(index=False,name=None):
            uid,signature,*raw_values=values_row
            values=[str(v) for v in raw_values if pd.notna(v)];keys=sorted(set(values));n_np=sum(k.startswith('np:') for k in keys)
            known_core=sum(pd.notna(raw_values[families.index(c)]) for c in core)
            typ='no_supported_daily_link' if not len(values) else 'monocentric_service_profile' if len(keys)==1 and n_np==1 else 'polycentric_service_profile' if n_np==len(keys) else 'supplier_settlement_identity_partial_or_unknown'
            units.append({'unit_id':uid,'level':0,'functional_layer_index':0,'effective_merge_depth':0,'scenario_id':scenario,'profile_signature':signature,
                'known_daily_families':len(values),'expected_daily_families':len(families),'all_declared_daily_families_have_candidate':len(values)==len(families),
                'known_core_daily_families':known_core,'expected_core_daily_families':len(core),'all_core_daily_families_have_candidate':known_core==len(core),
                'evidence_completeness':'no_daily_evidence' if not len(values) else 'all_core_channels_known' if known_core==len(core) else 'partial_daily_evidence',
                'provider_anchor_count':len(keys),'known_np_anchor_count':n_np,'provider_keys_json':dumps(keys),'type_code':typ,
                'unit_is_observed_sgrt':False,'daily_needs_actually_satisfied':pd.NA,'population_used_for_assignment':False,
                'operational_partition_of_demand_points':True,'anchors_are_nonadditive_context':True})
        if len(selected):anchor_parts.append(aggregate_anchors(selected))
    if not units:raise ValueError('No source scenario supplied')
    members=pd.concat(parts,ignore_index=True);out=pd.DataFrame(units)
    out=out.merge(demographic_summaries(members,reference),on='unit_id',validate='one_to_one')
    out['inhabited_multi_np_service_area']=out.positive_credited_member_records.ge(2)&out.known_daily_families.gt(0)
    out['demographic_type']=out.member_direction_2002_2021
    return out,members,pd.concat(anchor_parts,ignore_index=True) if anchor_parts else pd.DataFrame(),frame


def higher_candidates(memberships,higher_edges,reference):
    """All candidate next-order links, including split and unobserved coverage."""
    frame=canonical_edges(higher_edges,admission='higher_admitted')
    if not frame.loc[frame.provider_settlement_id.notna(),'provider_settlement_id'].isin(reference.source_record_id.dropna()).all():
        raise ValueError('A declared higher provider settlement is outside the accepted identity reference')
    if memberships.duplicated(['scenario_id','origin_id']).any():raise ValueError('Child memberships must form an explicit partition per scenario')
    families=sorted(frame.service_family.unique());result=[]
    # Higher service sources can use one scenario shared by every L0 source
    # scenario; never silently join different origin versions.
    if frame.scenario_id.nunique()!=1:raise ValueError('Choose one explicit higher source scenario per call')
    if 'parent_target_key' not in frame:frame['parent_target_key']=frame.provider_key
    else:frame['parent_target_key']=frame.parent_target_key.fillna(frame.provider_key)
    if 'parent_target_kind' not in frame:frame['parent_target_kind']='provider'
    else:frame['parent_target_kind']=frame.parent_target_kind.fillna('provider')
    is_reference=frame.parent_target_key.astype('string').str.startswith('efua:',na=False)
    if (is_reference&frame.parent_target_kind.eq('provider')).any():raise ValueError('An external area cannot masquerade as one provider')
    good=frame[frame.higher_admitted].copy()
    for scenario,member in memberships.groupby('scenario_id',sort=True):
        joined=member[['unit_id','origin_id']].merge(good,on='origin_id',how='left',validate='one_to_many')
        groups=joined.groupby(['unit_id','service_family'],sort=False).indices
        empty=joined.iloc[0:0]
        for child,g in member.groupby('unit_id',sort=False):
            for family in families:
                positions=groups.get((child,family))
                e=joined.iloc[positions] if positions is not None else empty
                n_all=len(g);n_covered=e.origin_id.nunique();keys=sorted(e.parent_target_key.dropna().unique())
                single_complete=len(keys)==1 and n_covered==n_all
                status='no_known_higher_candidate' if not keys else 'split_higher_candidates' if len(keys)>1 else 'partial_higher_coverage' if n_covered<n_all else 'complete_single_external_area_candidate' if str(keys[0]).startswith('efua:') else 'complete_single_higher_candidate'
                for key in keys or [None]:
                    q=e[e.parent_target_key.eq(key)] if key is not None else e.iloc[0:0]
                    guard=q.territorial_merge_admitted.eq(True) if 'territorial_merge_admitted' in q else pd.Series(False,index=q.index)
                    row={'child_unit_id':child,'scenario_id':scenario,'service_family':family,'parent_target_key':key,
                        'provider_key':q.provider_key.dropna().iloc[0] if q.provider_key.nunique()==1 else pd.NA,
                        'real_provider_keys_json':unique_json(q.provider_key),'real_provider_site_ids_json':unique_json(q.provider_site_id),
                        'parent_target_kinds_json':unique_json(q.parent_target_kind),'external_reference_parent_target':bool(str(key).startswith('efua:')),
                        'coverage_type':status,
                        'child_member_records':n_all,'higher_covered_member_records':n_covered,'members_for_this_provider':q.origin_id.nunique(),
                        'maximum_directed_minutes':q.cost_minutes.max(),'complete_single_parent_by_this_function':single_complete,
                        'territorial_merge_admitted_for_all_child_members':bool(single_complete and len(q)==n_all and guard.all()),
                        'territorial_guard_bases_json':unique_json(q.territorial_guard_basis) if 'territorial_guard_basis' in q else '[]',
                        'source_ids_json':unique_json(q.source_id),'source_years_json':unique_json(q.source_year),
                        'is_observed_commuting_or_patient_flow':False,'rare_service_alone_defines_agglomeration':False}
                    result.append(row)
    return pd.DataFrame(result)


def promote_layer(child_units,memberships,candidates,level,previous_families=()):
    """Promote only new functions with independent territorial admissibility.

    Every child is retained in the crosswalk. Unknown/split/unguarded children
    are not assigned to a dominant city. A layer with no actual merger is a
    stopping result, not another claimed spatial order.
    """
    families=sorted(candidates.service_family.unique())
    if set(families)&set(previous_families):raise ValueError('Repeated functional layer cannot manufacture another hierarchy level')
    if level<1:raise ValueError('Higher layer number must be positive')
    rows=[]
    groups=candidates.groupby(['child_unit_id','scenario_id'],sort=False).indices
    for u in child_units.itertuples():
        positions=groups.get((u.unit_id,u.scenario_id))
        g=candidates.iloc[positions] if positions is not None else candidates.iloc[0:0]
        valid=g[g.territorial_merge_admitted_for_all_child_members]
        complete=len(valid)==len(families) and set(valid.service_family)==set(families)
        if complete:
            targets=valid.parent_target_key if 'parent_target_key' in valid else valid.provider_key
            signature=dumps({'new_service_profile':sorted(zip(valid.service_family,targets))})
            parent=stable_id(level,u.scenario_id,signature);status='complete_new_function_profile_with_territorial_guard'
        else:
            signature=dumps({'retained_child':u.unit_id});parent=stable_id(level,u.scenario_id,signature)
            status='retained_without_forced_parent'
        rows.append({'child_unit_id':u.unit_id,'unit_id':parent,'scenario_id':u.scenario_id,'level':level,'promotion_status':status,'profile_signature':signature,
            'external_reference_in_parent':bool(complete and valid.get('external_reference_parent_target',pd.Series(False,index=valid.index)).any())})
    crosswalk=pd.DataFrame(rows)
    parent_units=crosswalk.groupby(['unit_id','scenario_id','profile_signature'],sort=False).agg(child_units=('child_unit_id','nunique')).reset_index()
    parent_units['level']=level;parent_units['functional_layer_index']=level
    parent_units['new_territorial_merger']=parent_units.child_units.gt(1)
    depths=child_units.set_index('unit_id')['effective_merge_depth'] if 'effective_merge_depth' in child_units else child_units.set_index('unit_id')['level']
    crosswalk['child_effective_merge_depth']=crosswalk.child_unit_id.map(depths)
    maximum_depth=crosswalk.groupby('unit_id').child_effective_merge_depth.max()
    parent_units['effective_merge_depth']=parent_units.unit_id.map(maximum_depth).astype(int)+parent_units.new_territorial_merger.astype(int)
    inherited=child_units.set_index('unit_id')['boundary_depends_on_external_reference'] if 'boundary_depends_on_external_reference' in child_units else pd.Series(False,index=child_units.unit_id)
    crosswalk['inherited_external_reference_boundary']=crosswalk.child_unit_id.map(inherited).fillna(False).astype(bool)
    crosswalk['current_or_inherited_external_reference']=crosswalk.external_reference_in_parent|crosswalk.inherited_external_reference_boundary
    reference_flag=crosswalk.groupby('unit_id').current_or_inherited_external_reference.any()
    parent_units['boundary_depends_on_external_reference']=parent_units.unit_id.map(reference_flag)
    parent_units['independently_discovered_agglomeration_boundary']=False
    promoted=crosswalk[crosswalk.promotion_status.eq('complete_new_function_profile_with_territorial_guard')]
    details=candidates.merge(promoted[['child_unit_id','scenario_id','unit_id']],on=['child_unit_id','scenario_id'],how='inner',validate='many_to_one')
    provider_sets={}
    for uid,g in details.groupby('unit_id',sort=False):
        values=set()
        if 'real_provider_keys_json' in g:
            for value in g.real_provider_keys_json.dropna():values.update(json.loads(value))
        else:values.update(str(v) for v in g.provider_key.dropna())
        provider_sets[uid]=sorted(values)
    parent_units['real_provider_keys_json']=parent_units.unit_id.map(lambda uid:dumps(provider_sets.get(uid,[])))
    parent_units['known_provider_np_count']=parent_units.unit_id.map(lambda uid:sum(str(v).startswith('np:') for v in provider_sets.get(uid,[])))
    parent_units['multiple_providers_do_not_prove_urban_polycentricity']=True
    parent_units['type_code']=np.where(parent_units.new_territorial_merger,'guarded_multichild_functional_candidate','retained_subsystem')
    parent_members=memberships.drop(columns=['profile_signature'],errors='ignore').rename(columns={'unit_id':'child_unit_id'}).merge(crosswalk[['child_unit_id','scenario_id','unit_id']],on=['child_unit_id','scenario_id'],validate='many_to_one')
    parent_members=parent_members.drop(columns='child_unit_id')
    stopping={'actual_new_mergers':int(parent_units.new_territorial_merger.sum()),'new_functions':families,
        'stop':not bool(parent_units.new_territorial_merger.any()),'reason':'no_new_guarded_multichild_merger' if not parent_units.new_territorial_merger.any() else 'new_function_and_territorial_evidence_supported_some_mergers',
        'Moscow_only_top_required':False,'target_number_of_levels':None}
    return parent_units,parent_members,crosswalk,stopping


def save(frame,path):
    path.parent.mkdir(parents=True,exist_ok=True);frame.to_parquet(path.with_suffix('.parquet'),index=False,compression='zstd')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--edges',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--families',nargs='+',required=True);p.add_argument('--core-families',nargs='+');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--higher-edges',type=Path);p.add_argument('--higher-level',type=int,default=1);p.add_argument('--scenario-id')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    input_paths=[a.edges,a.reference]+([a.higher_edges] if a.higher_edges else [])
    input_sha256={str(path):file_sha256(path) for path in input_paths}
    source_code_sha256=file_sha256(Path(__file__))
    reference=pd.read_parquet(a.reference)
    daily=pd.read_parquet(a.edges,filters=[('scenario_id','==',a.scenario_id)]) if a.scenario_id else pd.read_parquet(a.edges)
    units,members,anchors,edges=build_level_zero(daily,reference,a.families,a.core_families)
    for name,frame in [('level0_units',units),('level0_memberships',members),('level0_provider_anchors',anchors),('daily_edge_evidence',edges)]:save(frame,a.output/name)
    summary={'level0_units':len(units),'origins':members.origin_id.nunique(),'scenarios':members.scenario_id.nunique(),
        'inhabited_multi_np_service_areas':int(units.inhabited_multi_np_service_area.sum()),'unit_types':units.type_code.value_counts().to_dict(),
        'population_used_for_assignment':False,'observed_sgrt_claimed':False,'provider_anchor_population_is_nonadditive':True,
        'profile_families':sorted(a.families),'core_families':sorted(a.core_families or a.families),
        'input_sha256':input_sha256,'hierarchy_code_sha256':source_code_sha256}
    if a.higher_edges:
        higher=canonical_edges(pd.read_parquet(a.higher_edges),admission='higher_admitted')
        save(higher,a.output/'higher_edge_evidence')
        candidates=higher_candidates(members,higher,reference)
        parents,pm,cross,stop=promote_layer(units,members,candidates,a.higher_level,a.families)
        for name,frame in [('parent_candidates',candidates),('higher_units',parents),('higher_memberships',pm),('subsystem_crosswalk',cross)]:save(frame,a.output/name)
        summary['upward_attempt']=stop
    if input_sha256!={str(path):file_sha256(path) for path in input_paths} or source_code_sha256!=file_sha256(Path(__file__)):
        raise RuntimeError('An input or hierarchy code changed during calculation; output is not a frozen scientific result')
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
