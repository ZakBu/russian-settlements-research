#!/usr/bin/env python3
"""Read-only extent audit of broad centre candidates, not only strict groups.

Diameters are point-to-point geodesic extents, not radii. Direct automobile
minutes describe the declared scenario, not observed school or patient trips.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Geod

SPHERE = Geod(a=6371008.8,b=6371008.8)
ELLIPSOID = Geod(ellps='WGS84')
COUNTS = {1:'one_or_more_core_external_positive_whole',
          2:'two_or_more_core_external_positive_whole',
          3:'all_three_core_external_positive_whole'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def independent_diameter(frame,geod=SPHERE):
    """Independently recompute all point pairs; no hierarchy geometry helper."""
    points=frame[['lon','lat']].dropna().to_numpy(dtype=float)
    result=0.
    for i in range(len(points)-1):
        n=len(points)-i-1
        _,_,metres=geod.inv(np.full(n,points[i,0]),np.full(n,points[i,1]),
                          points[i+1:,0],points[i+1:,1])
        result=max(result,float(np.max(metres))/1000)
    return result


def run(scenario_dir,reference_path,output,case_output=None,source_context='current_corrected_calculation'):
    files={name:scenario_dir/(name+'.parquet') for name in
           ['centre_stars','centre_memberships','functional_links','functional_stars']}
    files['reference']=reference_path
    before={k:sha(v) for k,v in files.items()}
    stars=pd.read_parquet(files['centre_stars'])
    members=pd.read_parquet(files['centre_memberships'])
    links=pd.read_parquet(files['functional_links'])
    functions=pd.read_parquet(files['functional_stars'])
    reference=pd.read_parquet(reference_path).dropna(subset=['source_record_id']).set_index('source_record_id')
    if not reference.index.is_unique:
        raise ValueError('Reference census identities must be unique')
    eligible=stars[stars.centre_positive_population_known & stars.centre_unmarked_whole_record
                   & stars.centre_in_analysis_origin & stars.centre_ordinary_credited_or_nonadditive_context
                   & stars[COUNTS[1]].gt(0)].copy()
    report={'source_context':source_context,'input_sha256':before,
            'scope':'Independent read-only tail audit; no source or membership changes',
            'eligible_known_centre_stars':len(eligible),
            'centre_filter':'positive-known unmarked-whole analysis centre; ordinary credited or explicit nonadditive context; >=1 external positive credited whole record with a core service link',
            'subset_rule':'For each N, include the centre plus external positive credited whole records with >=N directly selected core families at that centre. Centre own supply is NOT additionally required for the one/two-family descriptive strata.',
            'three_family_stratum_is_not_automatically_strict_validated_sgrt':True,
            'diameter_units':'point-to-point spherical great-circle km, R=6371.0088km; not radius and not WGS84 ellipsoid distance',
            'positive_subset_stats':{}}
    for n,count in COUNTS.items():
        subset=eligible[eligible[count].gt(0)]
        col=f'{n}_core_subset_geodesic_diameter_km'
        report['positive_subset_stats'][str(n)]={
            'stars_with_nonempty_external_subset':len(subset),
            'diameter_quantiles':{str(k):float(v) for k,v in subset[col].quantile([.5,.9,.95,.99,1]).items()},
            'diameter_above_km':{str(t):int(subset[col].gt(t).sum()) for t in [30,40,50]},
            'centres_with_own_all_three_core':int(subset.centre_own_all_three_core_confirmed.sum())}
    columns=['centre_name','centre_region','centre_settlement_id',*COUNTS.values(),
             '1_core_subset_geodesic_diameter_km','2_core_subset_geodesic_diameter_km']
    report['largest_one_core_stars']=eligible.nlargest(10,'1_core_subset_geodesic_diameter_km')[columns].to_dict('records')
    chosen=eligible.nlargest(10,'1_core_subset_geodesic_diameter_km')
    chosen=pd.concat([chosen,eligible[eligible[COUNTS[2]].gt(0)].nlargest(3,'2_core_subset_geodesic_diameter_km')]).drop_duplicates('star_id')
    cases=[]; case_rows=[]
    for row in chosen.itertuples(index=False):
        g=links[links.provider_settlement_id.eq(row.centre_settlement_id)]
        member=members[members.star_id.eq(row.star_id)]
        one=member[member.in_1_core_positive_whole_subset]
        independent=independent_diameter(one)
        expected=float(eligible.loc[eligible.star_id.eq(row.star_id),'1_core_subset_geodesic_diameter_km'].iloc[0])
        if not np.isclose(independent,expected,rtol=0,atol=1e-9):
            raise ValueError(f'Independent diameter differs: {row.centre_name}')
        outside_ids=set(one.loc[one.member_role.eq('direct_surroundings'),'origin_id'])
        positive_routes=g[g.origin_id.isin(outside_ids)].copy()
        byservice=positive_routes.groupby('service_family').agg(
            external_positive_credited_whole_records=('origin_id','nunique'),
            maximum_directed_minutes=('cost_minutes','max'),
            maximum_point_separation_km=('point_separation_km','max')).reset_index().to_dict('records')
        case={'centre_name':row.centre_name,'centre_region':row.centre_region,
              'centre_settlement_id':row.centre_settlement_id,
              'centre_population_2021':float(reference.loc[row.centre_settlement_id,'population_2021']),
              'one_core_subset_diameter_km':expected,'independent_one_core_diameter_km':independent,
              'comparison_wgs84_ellipsoid_diameter_km':independent_diameter(one,ELLIPSOID),
              'two_core_subset_diameter_km':float(eligible.loc[eligible.star_id.eq(row.star_id),'2_core_subset_geodesic_diameter_km'].iloc[0]),
              'positive_external_per_service':byservice,
              'road_endpoint_review_records':int(one.road_endpoint_review_needed.sum()),
              'component_lt100_diagnostic_records':int(one.road_component_lt100_diagnostic.sum()),
              'component_quality_unknown_records':int(one.road_component_quality_unknown.sum()),
              'coincident_coordinate_review_records':int(one.coincident_coordinate_requires_review.sum())}
        far=positive_routes.nlargest(3,'point_separation_km').copy()
        keep=['origin_id','origin_name','origin_population_2021','service_family','cost_minutes',
              'point_separation_km','provider_name','provider_site_id','source_id','source_year','school_stage_unknown']
        case['farthest_selected_routes']=far[keep].to_dict('records')
        far['audited_centre_name']=row.centre_name
        far['audited_centre_id']=row.centre_settlement_id
        far['one_core_subset_diameter_km']=expected
        case_rows.append(far[keep+['audited_centre_name','audited_centre_id','one_core_subset_diameter_km']])
        cases.append(case)
    report['actual_tail_cases']=cases
    positive_ids=set(members.loc[members.positive_credited_whole,'origin_id'])
    largest=[]
    for family in ['medical_basic','school','grocery']:
        for row in functions[functions.service_family.eq(family)&functions.external_positive_whole_records.gt(0)].nlargest(3,'external_positive_whole_records').itertuples(index=False):
            g=links[links.provider_settlement_id.eq(row.centre_settlement_id)&links.service_family.eq(family)]
            outside=g[g.origin_id.ne(row.centre_settlement_id)&g.origin_id.isin(positive_ids)]
            largest.append({'family':family,'centre_name':reference.loc[row.centre_settlement_id,'name'],
                            'external_positive_credited_whole_records':len(outside),
                            'external_population_2021_sum':float(outside.origin_population_2021.sum()),
                            'external_population_2021_median':float(outside.origin_population_2021.median()),
                            'external_with_population_at_most10':int(outside.origin_population_2021.le(10).sum()),
                            'school_stage_unknown_records':int(outside.school_stage_unknown.sum()),
                            'maximum_directed_minutes':float(outside.cost_minutes.max())})
    report['largest_functional_basin_examples']=largest
    report['interpretation']=[
        'Broad direct service basins overlap; their populations must not be added across stars.',
        'Strict three-family examples must not replace the broader candidate count in presentation.',
        'A nearest known supplier can be distant because the inventory omits nearer alternatives.',
        'Automobile scenario minutes do not establish school bus time, daily trips or patient assignment.',
        'A large count of tiny villages is not measured pupil/patient demand; capacity and age-specific demand remain unknown.',
        'This audit covers current corrected outputs identified by hashes; earlier pre-programme observations remain historical controls, not current results.']
    if before!={k:sha(v) for k,v in files.items()}:
        raise ValueError('Input changed during audit')
    output.parent.mkdir(parents=True,exist_ok=True)
    report['inputs_unchanged']=True
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    case_output=case_output or output.with_name(output.stem+'_cases.parquet')
    pd.concat(case_rows,ignore_index=True).to_parquet(case_output,index=False)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario-dir',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cases-output',type=Path)
    p.add_argument('--source-context',default='current_corrected_calculation')
    a=p.parse_args()
    result=run(a.scenario_dir,a.reference,a.output,a.cases_output,a.source_context)
    print(json.dumps({'eligible_known_centre_stars':result['eligible_known_centre_stars'],
                      'positive_subset_stats':result['positive_subset_stats']},ensure_ascii=False))
