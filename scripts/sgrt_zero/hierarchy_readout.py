#!/usr/bin/env python3
"""Describe completed service partitions without changing membership or rank."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quantiles(values):
    q=pd.to_numeric(values,errors='coerce').dropna()
    return {'records':len(q),**{str(p):float(q.quantile(p)) if len(q) else None for p in [0,.25,.5,.75,.9,.95,.99,1]}}


def extent(points,anchor=None):
    q=points[['lat','lon']].dropna().drop_duplicates()
    if q.empty:return {'wgs84_member_diameter_km':None,'anchor_max_distance_km':None}
    lat=q.lat.to_numpy(dtype=float);lon=q.lon.to_numpy(dtype=float);g=Geod(ellps='WGS84');maximum=0.
    for i in range(max(0,len(q)-1)):
        _,_,d=g.inv(np.full(len(q)-i,lon[i]),np.full(len(q)-i,lat[i]),lon[i:],lat[i:])
        maximum=max(maximum,float(np.max(d)))
    radius=None
    if anchor is not None:
        if len(q)==1:_,_,d=g.inv(float(anchor.lon),float(anchor.lat),float(lon[0]),float(lat[0]))
        else:_,_,d=g.inv(np.full(len(q),float(anchor.lon)),np.full(len(q),float(anchor.lat)),lon,lat)
        radius=float(np.max(d))/1000
    return {'wgs84_member_diameter_km':maximum/1000,'anchor_max_distance_km':radius}


def partial_core_reasons(units,members,edges):
    """Separate a distant known offer from an unresolved route/inventory.

    Reasons may differ between services and between members sharing the same
    admitted profile. Count mutually exclusive sets of units as well as the
    underlying NP-by-function records; never interpret a distant known offer
    as proof that an unrecorded closer institution does not exist.
    """
    if members.origin_id.duplicated().any():raise ValueError('Repeated demand-point membership')
    if edges.duplicated(['origin_id','service_family']).any():raise ValueError('Repeated demand-point/function evidence')
    ids=set(units.loc[units.positive_credited_member_records.ge(2)&~units.all_core_daily_families_have_candidate,'unit_id'])
    core=edges.service_family.isin(['medical_basic','school','grocery'])
    missing=edges[core&~edges.l0_admitted]
    selected=members[members.unit_id.isin(ids)].merge(missing,on='origin_id',validate='one_to_many')
    if not selected.service_status.isin(['far_known_candidate','unknown_route_or_inventory']).all():
        raise ValueError('Unadmitted core direction has an inconsistent reason')
    far=set(selected.loc[selected.service_status.eq('far_known_candidate'),'unit_id'])
    unknown=set(selected.loc[selected.service_status.eq('unknown_route_or_inventory'),'unit_id'])
    if far|unknown!=ids:raise ValueError('Partial core profile lacks reason evidence')
    return {'partial_core_multi_np_units':len(ids),'mutually_exclusive_groups':{
      'only_far_known_missing_core_channels':len(far-unknown),
      'only_unknown_route_or_inventory_missing_core_channels':len(unknown-far),
      'both_far_and_unknown_missing_core_channels':len(far&unknown)},
      'missing_core_origin_family_edge_rows':len(selected),
      'edge_status_counts':selected.service_status.value_counts().to_dict(),
      'edge_family_status_counts':selected.groupby(['service_family','service_status']).size().reset_index(name='rows').to_dict('records'),
      'unknown_reason_edge_counts':selected.unknown_reason.value_counts().to_dict(),
      'one_missing_core_direction_can_have_different_reasons_among_group_members':True,
      'far_known_candidate_is_not_proof_of_real_local_service_absence':True}


def describe(directory,reference,is_zero):
    reference=reference[reference.source_record_id.notna()].copy()
    stem='level0_' if is_zero else ''
    units_path=directory/(stem+'units.parquet');members_path=directory/(stem+'memberships.parquet')
    units=pd.read_parquet(units_path);members=pd.read_parquet(members_path)
    if members.origin_id.duplicated().any() or set(members.origin_id)!=set(reference.loc[reference.analysis_origin,'source_record_id']):
        raise ValueError('Membership is not an exact partition of the analysis frame')
    multi=units.positive_credited_member_records.ge(2)
    result={'units':len(units),'source_point_records':len(members),
      'units_with_one_member_record':int(units.member_records.eq(1).sum()),
      'units_with_exactly_one_positive_credited_ordinary_np':int(units.positive_credited_member_records.eq(1).sum()),
      'units_with_no_positive_credited_ordinary_np':int(units.positive_credited_member_records.eq(0).sum()),
      'units_with_at_least_two_positive_credited_ordinary_np':int(multi.sum()),
      'ordinary_credited_population_2021_in_multi_np_units':float(units.loc[multi,'member_population_2021_credited_sum'].sum()),
      'ordinary_credited_population_2021_all_units':float(units.member_population_2021_credited_sum.sum()),
      'member_records_per_unit':quantiles(units.member_records),
      'spherical_member_diameter_km_all_units':quantiles(units.member_geodesic_diameter_km),
      'spherical_member_diameter_km_multi_inhabited_units':quantiles(units.loc[multi,'member_geodesic_diameter_km']),
      'spherical_radius_earth_km':6371.0088,
      'diameter_is_not_radius_or_driving_time':True,
      'nonadditive_city_context_population_is_excluded_from_population_sums':True,
      'observed_sgrt_or_city_rank_established':False,
      'input_sha256':{str(units_path):digest(units_path),str(members_path):digest(members_path)}}
    if is_zero:
        no=units.known_daily_families.eq(0)
        result.update(no_admitted_daily_link_units=int(no.sum()),
          inhabited_multi_np_service_groups=int((multi&~no).sum()),
          inhabited_multi_np_with_all_three_core_families=int((multi&~no&units.all_core_daily_families_have_candidate).sum()),
          inhabited_multi_np_with_partial_core_evidence=int((multi&~no&~units.all_core_daily_families_have_candidate).sum()))
    else:
        result.update(new_multichild_mergers=int(units.new_territorial_merger.sum()),
          maximum_effective_merge_depth=int(units.effective_merge_depth.max()),
          merge_depth_is_not_a_functional_city_rank=True)
    named=reference[reference.name.isin(['Москва','Санкт-Петербург','Саратов','Энгельс','Новоузенск','Питерка','Челябинск','Магнитогорск'])&reference.region.fillna('').str.contains('саратов|москв|петербург|челябин',case=False)&reference.analysis_origin].copy()
    named=named[named.settlement_type_2021.eq('город')|named.name.eq('Питерка')]
    wanted=set(members.loc[members.origin_id.isin(named.source_record_id),'unit_id'])|set(units.nlargest(10,'member_geodesic_diameter_km').unit_id)
    linked=members[members.unit_id.isin(wanted)].merge(reference[['source_record_id','lat','lon','population_2021','population_role','credit_2021']],left_on='origin_id',right_on='source_record_id',validate='one_to_one')
    groups={key:part for key,part in linked.groupby('unit_id',sort=False)};indexed=units.set_index('unit_id')
    result['named_cases']=[]
    for r in named.itertuples():
        member=members[members.origin_id.eq(r.source_record_id)]
        uid=member.unit_id.iloc[0];u=indexed.loc[uid];points=groups[uid]
        inhabited=points[points.population_role.eq('ordinary_settlement_record')&points.credit_2021.fillna(False)&points.population_2021.gt(0)]
        result['named_cases'].append({'name':r.name,'source_record_id':r.source_record_id,
          'settlement_type_2021':None if pd.isna(r.settlement_type_2021) else str(r.settlement_type_2021),
          'unit_id':uid,'member_records':int(u.member_records),
          'positive_credited_member_records':int(u.positive_credited_member_records),
          **extent(points,r),'positive_ordinary_points_wgs84_diameter_km':extent(inhabited)['wgs84_member_diameter_km']})
    result['largest_declared_spherical_diameter_units']=[]
    for uid,u in units.nlargest(10,'member_geodesic_diameter_km').set_index('unit_id').iterrows():
        result['largest_declared_spherical_diameter_units'].append({'unit_id':uid,'member_records':int(u.member_records),
          'positive_credited_member_records':int(u.positive_credited_member_records),
          'spherical_member_diameter_km':float(u.member_geodesic_diameter_km),**extent(groups[uid])})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    reference=pd.read_parquet(a.reference)
    paths=[(x,True) for x in sorted(a.root.glob('hierarchy/*')) if (x/'level0_units.parquet').exists()]
    paths +=[(x,False) for pattern in ['upward/*/*','upward_extended/*/*/*'] for x in sorted(a.root.glob(pattern)) if (x/'units.parquet').exists()]
    if len(paths)!=15:raise ValueError('Expected five daily, four strict and six extended completed partitions')
    result={'reference_sha256':digest(a.reference),'code_sha256':digest(__file__),
      'partitions':{str(path.relative_to(a.root)):describe(path,reference,is_zero) for path,is_zero in paths}}
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    policy=json.loads((a.root/'screens_final/summary.json').read_text())
    main_directory=a.root/'hierarchy'/policy['main_scenario']
    up=main_directory/'level0_units.parquet';mp=main_directory/'level0_memberships.parquet';ep=main_directory/'daily_edge_evidence.parquet'
    reasons=partial_core_reasons(pd.read_parquet(up,columns=['unit_id','positive_credited_member_records','all_core_daily_families_have_candidate']),
      pd.read_parquet(mp,columns=['unit_id','origin_id']),
      pd.read_parquet(ep,columns=['origin_id','service_family','l0_admitted','service_status','unknown_reason']))
    reasons.update(main_scenario=policy['main_scenario'],source_edges_sha256=digest(ep),
      input_sha256={str(x):digest(x) for x in [up,mp,ep]},code_sha256=digest(__file__))
    (a.output/'main_partial_core_reason_breakdown.json').write_text(json.dumps(reasons,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'partitions':len(paths),'output':str(a.output/'summary.json')}))


if __name__=='__main__':main()
